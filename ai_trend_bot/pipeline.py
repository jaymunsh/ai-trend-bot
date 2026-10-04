import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Final, final

import httpx2
from pydantic import ValidationError

from ai_trend_bot.config import AppConfig
from ai_trend_bot.enrich import fetch_body
from ai_trend_bot.feeds import FeedClient
from ai_trend_bot.gemini import GeminiClient, GenerationLimitError
from ai_trend_bot.models import DigestItem, RawItem
from ai_trend_bot.scheduling import wait_until
from ai_trend_bot.store import SentLog
from ai_trend_bot.telegram import SEOUL, TelegramClient, render_header
from ai_trend_bot.triage import Dropped, Selected, Selection, apply_triage

# Free-tier Gemini answers 503 to a few hundred candidates in one request; 100 is served reliably.
TRIAGE_BATCH: Final = 100
SUMMARY_FALLBACK_BATCH: Final = 10
# The first round judges each item on its own merits, which is the right question when
# screening hundreds. Asked the same way twice, the second round just re-approves nearly
# everything, so it is framed as picking a lineup instead.
FINAL_ROUND_GUIDANCE: Final = (
    "\n이것은 최종 선별입니다. 위 후보는 이미 1차를 통과한 것들이므로 개별적으로는 모두 그럴듯해 보입니다. "
    "지금 할 일은 재심사가 아니라 **오늘 브리핑에 실을 것을 고르는 것**입니다. "
    "서로 비교했을 때 상대적으로 약한 것, 같은 회사의 사소한 업데이트, "
    "같은 사건을 새로운 사실 없이 반복한 것은 keep=false로 떨어뜨리세요. "
    "같은 사건의 단순 반복은 대표 기사에 병합하되, 새 수치·확정된 결정·가격·출시일·추가 피해 등 "
    "판단을 바꾸는 새 사실은 후속 보도여도 남기세요. 서로 다른 회사의 별개 발표를 병합하지 마세요.\n"
    "다만 **건수를 맞추려고 자르지 마세요.** 편집 방침의 '반드시 통과시킬 것'에 해당하면 "
    "그날 몇 건이 되든 남기세요. 특히 사고·보안 문제·규제·소송처럼 놓치면 안 되는 것은 "
    "다른 후보와 비교해 덜 화려해 보여도 남깁니다. "
    "큰 사건이 많은 날은 15건이 넘을 수 있고, 조용한 날은 2건일 수 있습니다.\n"
    "반대로 편집 방침을 간신히 넘긴 정도라면 떨어뜨리세요. 브리핑은 하루 세 번 오므로 "
    "지금 안 보내도 정말 중요한 것이면 다음 회차에 다시 후보가 됩니다.\n"
)


@dataclass(frozen=True, slots=True)
class RunOptions:
    limit: int
    dry_run: bool
    send_at: datetime | None = None
    min_gap_hours: float = 0


@dataclass(frozen=True, slots=True)
class RunResult:
    items: tuple[DigestItem, ...]
    warnings: tuple[str, ...]
    header: str = ""
    dropped: tuple[Dropped, ...] = ()
    candidates: int = 0
    skipped: bool = False


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
        summaries = await self._summarize(enriched)
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

        if not options.dry_run:
            if options.send_at is not None:
                await wait_until(options.send_at)
            # A manual run may have delivered while this process was preparing.
            last = self._log.last_sent_at()
            if (
                options.min_gap_hours > 0
                and last is not None
                and (datetime.now(tz=UTC) - last < timedelta(hours=options.min_gap_hours))
            ):
                return RunResult(
                    items=(),
                    warnings=(*warnings, "대기 중 다른 발송이 있어 이번 회차를 건너뜁니다."),
                    candidates=len(candidates),
                    dropped=selection.dropped,
                    skipped=True,
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

    async def _summarize(self, items: Sequence[RawItem]) -> tuple[DigestItem, ...]:
        # One request conserves the free request quota. Split only when the API
        # explicitly reports an output token limit, never on quota/network errors.
        try:
            return await self._clients.gemini.summarize(items)
        except GenerationLimitError:
            if len(items) <= SUMMARY_FALLBACK_BATCH:
                raise
            retried: list[DigestItem] = []
            for start in range(0, len(items), SUMMARY_FALLBACK_BATCH):
                retried.extend(await self._clients.gemini.summarize(items[start : start + SUMMARY_FALLBACK_BATCH]))
            return tuple(retried)

    async def _triage(self, candidates: tuple[RawItem, ...], *, limit: int) -> Selection:
        """Screen in batches, then re-screen the survivors together.

        A few hundred candidates in one request exceeds what the free tier will serve
        (it answers 503), so the first round runs in batches. Batching alone would let
        two outlets covering the same event land in different batches and both survive,
        so the survivors — a few dozen — get one more pass that dedupes and ranks
        across the whole set.
        """
        if not candidates:
            return Selection(kept=(), dropped=())
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
            return apply_triage(candidates, rounds[0], limit=limit)

        if not survivors:
            return Selection(kept=(), dropped=dropped)

        final = await self._clients.gemini.triage(
            survivors,
            editorial=editorial,
            recent_events=recent,
            guidance=FINAL_ROUND_GUIDANCE,
        )
        settled = apply_triage(survivors, final, limit=limit)
        first_round = {selected.item.key: selected for result in screened for selected in result.kept}
        preserved: list[Selected] = []
        for selected in settled.kept:
            merged = {other.key: other for other in first_round[selected.item.key].merged}
            for representative in selected.merged:
                merged[representative.key] = representative
                merged.update((other.key, other) for other in first_round[representative.key].merged)
            preserved.append(Selected(selected.item, selected.verdict, tuple(merged.values())))
        return Selection(kept=tuple(preserved), dropped=(*dropped, *settled.dropped))

    async def _collect(self, config: AppConfig) -> tuple[tuple[RawItem, ...], list[str]]:
        now = datetime.now(tz=UTC)
        warnings: list[str] = []
        fetched = await asyncio.gather(
            *(self._fetch(partial(self._clients.feeds.fetch, feed), feed.name) for feed in config.feeds),
        )
        raw_items: list[RawItem] = []
        for source, (items, warning) in zip(config.feeds, fetched, strict=True):
            if warning:
                warnings.append(warning)
            eligible, uncertain = self._eligible(items, now)
            raw_items.extend(eligible)
            if uncertain:
                warnings.append(f"{source.name}: 게시일 미상·오류 {uncertain}건 (48시간 이내 여부 확인 불가)")
        # Prefer the strongest source that still has room. Do not discard another
        # copy before accepting it: that copy can rescue an item beyond a cap.
        ordered = sorted(
            raw_items,
            key=lambda item: (item.priority, item.published_at_known, min(item.published_at, now)),
            reverse=True,
        )
        unseen_keys = set(self._log.unseen(tuple(item.key for item in ordered)))
        caps = {feed.name: feed.max_items for feed in config.feeds}
        counts: dict[str, int] = {}
        candidates: list[RawItem] = []
        accepted: set[str] = set()
        for item in ordered:
            count = counts.get(item.source, 0)
            if item.key in unseen_keys and item.key not in accepted and count < caps[item.source]:
                candidates.append(item)
                accepted.add(item.key)
                counts[item.source] = count + 1
        return tuple(candidates), warnings

    @staticmethod
    def _eligible(items: tuple[RawItem, ...], now: datetime) -> tuple[tuple[RawItem, ...], int]:
        cutoff = now - timedelta(hours=48)
        normalized = tuple(
            item.model_copy(update={"published_at_known": False})
            if item.published_at > now + timedelta(minutes=5)
            else item
            for item in items
        )
        uncertain = sum(not item.published_at_known for item in normalized)
        return tuple(
            item for item in normalized if not item.published_at_known or item.published_at >= cutoff
        ), uncertain

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
