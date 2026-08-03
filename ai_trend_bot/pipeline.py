import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Final, final

import httpx2
from pydantic import ValidationError

from ai_trend_bot.config import AppConfig
from ai_trend_bot.enrich import fetch_body
from ai_trend_bot.feeds import FeedClient
from ai_trend_bot.gemini import GeminiClient
from ai_trend_bot.models import DigestItem, RawItem
from ai_trend_bot.store import SentLog
from ai_trend_bot.telegram import SEOUL, TelegramClient, render_header
from ai_trend_bot.triage import Dropped, Selection, apply_triage

# Free-tier Gemini answers 503 to a few hundred candidates in one request; 100 is served reliably.
TRIAGE_BATCH: Final = 100
# The first round judges each item on its own merits, which is the right question when
# screening hundreds. Asked the same way twice, the second round just re-approves nearly
# everything, so it is framed as picking a lineup instead.
FINAL_ROUND_GUIDANCE: Final = (
    "\n이것은 최종 선별입니다. 위 후보는 이미 1차를 통과한 것들이므로 개별적으로는 모두 그럴듯해 보입니다. "
    "지금 할 일은 재심사가 아니라 **오늘 브리핑에 실을 것을 고르는 것**입니다. "
    "하루 세 번 발송하므로 한 회차에 실리는 것은 보통 3~8건입니다. "
    "서로 비교했을 때 상대적으로 약한 것, 같은 회사의 사소한 업데이트, "
    "같은 사건의 다른 측면을 다룬 것은 keep=false로 떨어뜨리세요. 애매하면 버립니다.\n"
)


@dataclass(frozen=True, slots=True)
class RunOptions:
    limit: int
    dry_run: bool


@dataclass(frozen=True, slots=True)
class RunResult:
    items: tuple[DigestItem, ...]
    warnings: tuple[str, ...]
    header: str = ""
    dropped: tuple[Dropped, ...] = ()
    candidates: int = 0


@dataclass(frozen=True, slots=True)
class PipelineClients:
    feeds: FeedClient
    gemini: GeminiClient
    telegram: TelegramClient
    http: httpx2.AsyncClient


@final
class BotPipeline:
    def __init__(self, clients: PipelineClients, log: SentLog, editorial_path: Path) -> None:
        self._clients = clients
        self._log = log
        self._editorial_path = editorial_path

    async def run(self, config: AppConfig, options: RunOptions) -> RunResult:
        candidates, warnings = await self._collect(config)
        if not candidates:
            return RunResult(items=(), warnings=tuple(warnings))

        selection = await self._triage(candidates, limit=options.limit)
        if not selection.kept:
            return RunResult(
                items=(),
                warnings=tuple(warnings),
                dropped=selection.dropped,
                candidates=len(candidates),
            )

        # Only survivors get the article body fetched; that is what makes it affordable.
        enriched = await asyncio.gather(
            *(fetch_body(self._clients.http, selected.item) for selected in selection.kept),
        )
        summaries = await self._clients.gemini.summarize(enriched)
        digest = tuple(
            summary.model_copy(
                update={
                    "category": str(selected.verdict.category),
                    "event": selected.verdict.event,
                    "also": tuple((other.source, str(other.url)) for other in selected.merged),
                },
            )
            for summary, selected in zip(summaries, selection.kept, strict=True)
        )

        header = render_header(datetime.now(tz=SEOUL), len(digest))
        if not options.dry_run:
            # Record per delivered message so a failure partway through does not re-send.
            async for delivered in self._clients.telegram.send(digest, header):
                self._log.mark(delivered)
        return RunResult(
            items=digest,
            warnings=tuple(warnings),
            header=header,
            dropped=selection.dropped,
            candidates=len(candidates),
        )

    async def _triage(self, candidates: tuple[RawItem, ...], *, limit: int) -> Selection:
        """Screen in batches, then re-screen the survivors together.

        A few hundred candidates in one request exceeds what the free tier will serve
        (it answers 503), so the first round runs in batches. Batching alone would let
        two outlets covering the same event land in different batches and both survive,
        so the survivors — a few dozen — get one more pass that dedupes and ranks
        across the whole set.
        """
        editorial = self._editorial_path.read_text(encoding="utf-8")
        recent = self._log.recent_events()
        batches = [candidates[start : start + TRIAGE_BATCH] for start in range(0, len(candidates), TRIAGE_BATCH)]
        rounds = await asyncio.gather(
            *(self._clients.gemini.triage(batch, editorial=editorial, recent_events=recent) for batch in batches),
        )
        screened = [
            apply_triage(batch, verdicts, limit=len(batch)) for batch, verdicts in zip(batches, rounds, strict=True)
        ]
        dropped = tuple(drop for result in screened for drop in result.dropped)
        survivors = tuple(selected.item for result in screened for selected in result.kept)
        if len(batches) == 1:
            return Selection(kept=screened[0].kept[:limit], dropped=dropped)

        final = await self._clients.gemini.triage(
            survivors,
            editorial=editorial,
            recent_events=recent,
            guidance=FINAL_ROUND_GUIDANCE,
        )
        settled = apply_triage(survivors, final, limit=limit)
        return Selection(kept=settled.kept, dropped=(*dropped, *settled.dropped))

    async def _collect(self, config: AppConfig) -> tuple[tuple[RawItem, ...], list[str]]:
        warnings: list[str] = []
        fetched = await asyncio.gather(
            *(self._fetch(partial(self._clients.feeds.fetch, feed), feed.name) for feed in config.feeds),
        )
        raw_items: list[RawItem] = []
        for items, warning in fetched:
            raw_items.extend(items)
            if warning:
                warnings.append(warning)
        unique = {item.key: item for item in raw_items}
        ordered = sorted(unique.values(), key=lambda item: (item.priority, item.published_at), reverse=True)
        unseen_keys = set(self._log.unseen(tuple(item.key for item in ordered)))
        return tuple(item for item in ordered if item.key in unseen_keys), warnings

    @staticmethod
    async def _fetch(
        fetch: Callable[[], Awaitable[tuple[RawItem, ...]]],
        label: str,
    ) -> tuple[tuple[RawItem, ...], str | None]:
        try:
            return await fetch(), None
        except httpx2.HTTPStatusError as error:
            return (), f"{label}: HTTP {error.response.status_code}"
        except httpx2.RequestError:
            return (), f"{label}: 네트워크 오류"
        except (ValidationError, ValueError, KeyError) as error:
            return (), f"{label}: 응답 형식 오류 ({type(error).__name__})"
