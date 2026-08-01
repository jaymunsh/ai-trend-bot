from datetime import datetime
from typing import ClassVar, final

import httpx2
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from ai_trend_bot.config import WatchAccount
from ai_trend_bot.models import RawItem, SourceKind


class ThreadsPost(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    id: str
    text: str = Field(min_length=1)
    timestamp: datetime
    permalink: HttpUrl
    username: str


class ThreadsPostList(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    data: tuple[ThreadsPost, ...] = ()


def parse_threads_posts(payload: bytes | str, source_name: str, priority: int) -> tuple[RawItem, ...]:
    response = ThreadsPostList.model_validate_json(payload)
    return tuple(
        RawItem(
            source=source_name,
            source_kind=SourceKind.THREADS_ACCOUNT,
            title=post.text[:80],
            text=post.text,
            url=post.permalink,
            published_at=post.timestamp,
            priority=priority,
            external_id=post.id,
        )
        for post in response.data
    )


@final
class ThreadsClient:
    def __init__(self, client: httpx2.AsyncClient, access_token: str) -> None:
        self._client = client
        self._access_token = access_token

    async def fetch_account(self, account: WatchAccount, limit: int = 5) -> tuple[RawItem, ...]:
        response = await self._client.get(
            "https://graph.threads.net/profile_posts",
            params={
                "username": account.username,
                "fields": "id,text,timestamp,permalink,username",
                "limit": limit,
                "access_token": self._access_token,
            },
        )
        response.raise_for_status()
        items = parse_threads_posts(response.content, f"@{account.username}", account.priority)
        if not account.collect_replies:
            return items
        return await self._append_self_replies(items, account.username)

    async def search(self, keyword: str, limit: int = 2) -> tuple[RawItem, ...]:
        response = await self._client.get(
            "https://graph.threads.net/keyword_search",
            params={
                "q": keyword,
                "search_type": "RECENT",
                "fields": "id,text,timestamp,permalink,username",
                "limit": limit,
                "access_token": self._access_token,
            },
        )
        response.raise_for_status()
        parsed = parse_threads_posts(response.content, f"Threads 검색: {keyword}", 40)
        return tuple(item.model_copy(update={"source_kind": SourceKind.THREADS_KEYWORD}) for item in parsed)

    async def _append_self_replies(self, items: tuple[RawItem, ...], username: str) -> tuple[RawItem, ...]:
        expanded: list[RawItem] = []
        for item in items:
            if item.external_id is None:
                expanded.append(item)
                continue
            try:
                response = await self._client.get(
                    f"https://graph.threads.net/{item.external_id}/conversation",
                    params={
                        "fields": "id,text,timestamp,permalink,username",
                        "access_token": self._access_token,
                    },
                )
                response.raise_for_status()
            except (httpx2.HTTPStatusError, httpx2.RequestError):
                expanded.append(item)
                continue
            replies = ThreadsPostList.model_validate_json(response.content).data
            own_texts = tuple(reply.text for reply in replies if reply.username.casefold() == username.casefold())
            text = "\n\n".join((item.text, *own_texts))
            expanded.append(item.model_copy(update={"text": text}))
        return tuple(expanded)
