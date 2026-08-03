import calendar
import re
from datetime import UTC, datetime
from typing import ClassVar, Final, final

import feedparser
import httpx2
from pydantic import BaseModel, ConfigDict, HttpUrl, RootModel

from ai_trend_bot.config import FeedCategory, FeedKind, FeedSource
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


class HackerNewsHit(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    objectID: str  # noqa: N815 - Algolia's field name
    title: str | None = None
    url: HttpUrl | None = None
    points: int = 0
    num_comments: int = 0
    created_at: datetime


class HackerNewsPage(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    hits: tuple[HackerNewsHit, ...] = ()


class HuggingFaceModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    id: str
    downloads: int = 0
    likes: int = 0
    pipeline_tag: str = "미상"
    tags: tuple[str, ...] = ()
    lastModified: datetime | None = None  # noqa: N815 - API field name
    createdAt: datetime | None = None  # noqa: N815 - API field name


class HuggingFacePage(RootModel[tuple[HuggingFaceModel, ...]]):
    pass


def parse_hacker_news(payload: bytes, source_name: str, priority: int) -> tuple[RawItem, ...]:
    """Read the Algolia search API. Points and comment counts are the signal, not the title."""
    page = HackerNewsPage.model_validate_json(payload)
    return tuple(
        RawItem(
            source=source_name,
            source_kind=SourceKind.FEED,
            title=hit.title or "",
            text=f"{hit.title} (Hacker News {hit.points}점, 댓글 {hit.num_comments}개)",
            url=hit.url or HttpUrl(f"https://news.ycombinator.com/item?id={hit.objectID}"),
            published_at=hit.created_at,
            priority=priority,
        )
        for hit in page.hits
        if hit.title
    )


def parse_hugging_face(payload: bytes, source_name: str, priority: int) -> tuple[RawItem, ...]:
    """Read the trending-models API, which surfaces new open weights before any blog post."""
    return tuple(
        RawItem(
            source=source_name,
            source_kind=SourceKind.FEED,
            title=f"Hugging Face 트렌딩 모델: {model.id}",
            text=(
                f"{model.id} · 다운로드 {model.downloads} · 좋아요 {model.likes}"
                f" · 파이프라인 {model.pipeline_tag} · 태그 {', '.join(model.tags[:8])}"
            ),
            url=HttpUrl(f"https://huggingface.co/{model.id}"),
            published_at=model.lastModified or model.createdAt or datetime.now(tz=UTC),
            priority=priority,
        )
        for model in HuggingFacePage.model_validate_json(payload).root
        if model.id
    )


PARSERS: Final = {
    FeedKind.RSS: parse_feed,
    FeedKind.HACKER_NEWS: parse_hacker_news,
    FeedKind.HUGGING_FACE: parse_hugging_face,
}


@final
class FeedClient:
    def __init__(self, client: httpx2.AsyncClient) -> None:
        self._client = client

    async def fetch(self, source: FeedSource) -> tuple[RawItem, ...]:
        response = await self._client.get(str(source.url))
        response.raise_for_status()
        parsed = PARSERS[source.kind](response.content, source.name, feed_priority(source.category))
        return parsed[: source.max_items]
