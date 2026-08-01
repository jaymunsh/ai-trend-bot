import calendar
import re
from datetime import UTC, datetime
from typing import Final, final

import feedparser
import httpx2
from pydantic import HttpUrl

from ai_trend_bot.config import FeedCategory, FeedSource
from ai_trend_bot.models import RawItem, SourceKind

TAG_PATTERN: Final = re.compile(r"<[^>]+>")


def feed_priority(category: FeedCategory) -> int:
    return {
        FeedCategory.OFFICIAL: 80,
        FeedCategory.RESEARCH: 30,
        FeedCategory.COMMUNITY: 20,
    }[category]


def parse_feed(payload: bytes, source_name: str, priority: int) -> tuple[RawItem, ...]:
    parsed = feedparser.parse(payload)
    items: list[RawItem] = []
    for entry in parsed.entries:
        title = str(entry.get("title", "")).strip()
        link = str(entry.get("link", "")).strip()
        text = TAG_PATTERN.sub(" ", str(entry.get("summary", title))).strip()
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        published_at = (
            datetime.fromtimestamp(calendar.timegm(published), tz=UTC)
            if published is not None
            else datetime.now(tz=UTC)
        )
        if title and link and text:
            items.append(
                RawItem(
                    source=source_name,
                    source_kind=SourceKind.FEED,
                    title=title,
                    text=text,
                    url=HttpUrl(link),
                    published_at=published_at,
                    priority=priority,
                ),
            )
    return tuple(items)


@final
class FeedClient:
    def __init__(self, client: httpx2.AsyncClient) -> None:
        self._client = client

    async def fetch(self, source: FeedSource) -> tuple[RawItem, ...]:
        response = await self._client.get(str(source.url))
        response.raise_for_status()
        return parse_feed(response.content, source.name, feed_priority(source.category))
