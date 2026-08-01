from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import final

import httpx2
from pydantic import ValidationError

from ai_trend_bot.config import AppConfig
from ai_trend_bot.feeds import FeedClient
from ai_trend_bot.gemini import GeminiClient
from ai_trend_bot.models import DigestItem, RawItem
from ai_trend_bot.store import SeenStore
from ai_trend_bot.telegram import TelegramClient
from ai_trend_bot.threads import ThreadsClient


@dataclass(frozen=True, slots=True)
class RunOptions:
    limit: int
    dry_run: bool


@dataclass(frozen=True, slots=True)
class RunResult:
    items: tuple[DigestItem, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PipelineClients:
    feeds: FeedClient
    threads: ThreadsClient
    gemini: GeminiClient
    telegram: TelegramClient


@final
class BotPipeline:
    def __init__(self, clients: PipelineClients, store: SeenStore) -> None:
        self._clients = clients
        self._store = store

    async def run(self, config: AppConfig, options: RunOptions) -> RunResult:
        raw_items: list[RawItem] = []
        warnings: list[str] = []
        for feed in config.feeds:
            fetched, warning = await self._fetch(partial(self._clients.feeds.fetch, feed), feed.name)
            raw_items.extend(fetched)
            if warning:
                warnings.append(warning)
        if config.threads.enabled:
            for account in sorted(
                config.threads.watch_accounts, key=lambda candidate: candidate.priority, reverse=True
            ):
                fetched, warning = await self._fetch(
                    partial(self._clients.threads.fetch_account, account),
                    f"@{account.username}",
                )
                raw_items.extend(fetched)
                if warning:
                    warnings.append(warning)

            keyword_items: list[RawItem] = []
            for keyword in config.threads.keywords:
                fetched, warning = await self._fetch(
                    partial(self._clients.threads.search, keyword),
                    f"키워드 {keyword}",
                )
                keyword_items.extend(fetched)
                if warning:
                    warnings.append(warning)
            raw_items.extend(keyword_items[: config.threads.keyword_daily_max])

        unique = {item.key: item for item in raw_items}
        ordered = sorted(unique.values(), key=lambda item: (item.priority, item.published_at), reverse=True)
        unseen_keys = set(self._store.unseen(tuple(item.key for item in ordered)))
        selected = tuple(item for item in ordered if item.key in unseen_keys)[: options.limit]
        if not selected:
            return RunResult(items=(), warnings=tuple(warnings))

        digest = await self._clients.gemini.summarize(selected)
        if not options.dry_run:
            await self._clients.telegram.send(digest)
            self._store.mark(tuple(item.key for item in selected))
        return RunResult(items=digest, warnings=tuple(warnings))

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
        except ValidationError as error:
            return (), f"{label}: 응답 형식 오류 ({error.error_count()}건)"
