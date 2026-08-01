from collections.abc import Sequence
from typing import final

import httpx2

from ai_trend_bot.models import DigestItem

HEADER = "AI 트렌드 브리핑"
TELEGRAM_SAFE_LENGTH = 3_800


def render_digest(items: Sequence[DigestItem]) -> str:
    sections = [HEADER]
    for index, item in enumerate(items, start=1):
        sections.append(_render_section(index, item))
    return "\n\n".join(sections)


def render_digest_chunks(
    items: Sequence[DigestItem],
    max_length: int = TELEGRAM_SAFE_LENGTH,
) -> tuple[str, ...]:
    chunks: list[str] = []
    current = HEADER
    for index, item in enumerate(items, start=1):
        section = _render_section(index, item)
        candidate = f"{current}\n\n{section}"
        if len(candidate) <= max_length:
            current = candidate
            continue
        if current != HEADER:
            chunks.append(current)
        available = max_length - len(HEADER) - 2
        while len(section) > available:
            chunks.append(f"{HEADER}\n\n{section[:available]}")
            section = section[available:]
        current = f"{HEADER}\n\n{section}"
    if current != HEADER:
        chunks.append(current)
    return tuple(chunks)


def _render_section(index: int, item: DigestItem) -> str:
    return "\n".join(
        (
            f"{index}. {item.title}",
            item.summary,
            f"출처: {item.source_label}",
            str(item.source_url),
        ),
    )


@final
class TelegramClient:
    def __init__(self, client: httpx2.AsyncClient, bot_token: str, chat_id: str) -> None:
        self._client = client
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id

    async def send(self, items: Sequence[DigestItem]) -> None:
        for message in render_digest_chunks(items):
            response = await self._client.post(
                self._url,
                json={"chat_id": self._chat_id, "text": message, "disable_web_page_preview": True},
            )
            response.raise_for_status()
