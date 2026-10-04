import html
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Final, final
from zoneinfo import ZoneInfo

import httpx2

from ai_trend_bot.models import DigestItem

SEOUL: Final = ZoneInfo("Asia/Seoul")
# Telegram rejects sendMessage over 4096 characters. The margin absorbs HTML entity
# expansion (&#x27; is 6 characters for one quote) that is invisible in the source text.
TELEGRAM_SAFE_LENGTH: Final = 3_800
# Width reserved for the " (10/10)" counter appended to split messages.
COUNTER_RESERVE: Final = 10
SEPARATOR: Final = "\n\n"
WEEKDAYS: Final = ("월", "화", "수", "목", "금", "토", "일")
NOON: Final = 12
EVENING: Final = 18


def _slot(hour: int) -> str:
    if hour < NOON:
        return "🌤️"
    if hour < EVENING:
        return "☀️"
    return "🌙"


def render_header(now: datetime, count: int) -> str:
    return (
        f"<b>{_slot(now.hour)} AI 브리핑 · "
        f"{now.month}/{now.day} ({WEEKDAYS[now.weekday()]}) · {count}건</b>"
    )


def _link(label: str, url: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def _section(index: int, item: DigestItem, *, summary: str | None = None) -> str:
    outlets = {label.strip().casefold() for label, _ in item.also if label.strip()}
    outlets.add(item.source_label.strip().casefold())
    additional = len(outlets) - 1
    source = _link(item.source_label, str(item.source_url))
    if additional:
        source += f" 외 {additional}곳"
    # "원문:" spelled out — an outlet name on its own does not read as a tappable link.
    return "\n".join(
        (
            f"<b>{index:02d}. [{html.escape(item.title)}]</b>",
            html.escape(item.summary if summary is None else summary),
            f"원문: {source}",
        )
    )


def _fit_section(index: int, item: DigestItem, room: int) -> str:
    section = _section(index, item)
    if len(section) <= room:
        return section
    if len(_section(index, item, summary="…")) > room:
        msg = "기사 제목·출처 링크가 텔레그램 메시지 상한을 초과했습니다."
        raise ValueError(msg)
    # Truncate plain text BEFORE escaping, retaining the source link and complete HTML.
    low, high = 0, len(item.summary)
    while low < high:
        middle = (low + high + 1) // 2
        if len(_section(index, item, summary=item.summary[:middle] + "…")) <= room:
            low = middle
        else:
            high = middle - 1
    return _section(index, item, summary=item.summary[:low] + "…")


def render_digest_chunks(
    items: Sequence[DigestItem],
    header: str,
    max_length: int = TELEGRAM_SAFE_LENGTH,
) -> tuple[tuple[str, tuple[DigestItem, ...]], ...]:
    """Split a digest into sendable messages, each paired with the items it carries.

    Pairing lets the caller record delivery per message, so a failure partway
    through does not re-send what already arrived.
    """
    # The "(1/3)" counter is appended after splitting, once the total is known, so its
    # width is reserved up front rather than pushing a finished message over the limit.
    budget = max_length - COUNTER_RESERVE
    room = budget - len(header) - len(SEPARATOR)
    chunks: list[tuple[str, tuple[DigestItem, ...]]] = []
    sections: list[str] = []
    carried: list[DigestItem] = []
    for index, item in enumerate(items, start=1):
        section = _fit_section(index, item, room)
        if sections and len(SEPARATOR.join((header, *sections, section))) > budget:
            chunks.append((SEPARATOR.join((header, *sections)), tuple(carried)))
            sections, carried = [], []
        sections.append(section)
        carried.append(item)
    if sections:
        chunks.append((SEPARATOR.join((header, *sections)), tuple(carried)))
    if len(chunks) == 1:
        return tuple(chunks)
    return tuple(
        (_number_header(message, position, len(chunks)), carried_items)
        for position, (message, carried_items) in enumerate(chunks, start=1)
    )


def _number_header(message: str, position: int, total: int) -> str:
    """Mark a split message as `(1/3)` at the end of the header's first line."""
    first, separator, rest = message.partition("\n")
    return f"{first} ({position}/{total}){separator}{rest}"


@final
class TelegramClient:
    def __init__(self, client: httpx2.AsyncClient, bot_token: str, chat_id: str) -> None:
        self._client = client
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id

    async def send(self, items: Sequence[DigestItem], header: str) -> AsyncIterator[tuple[DigestItem, ...]]:
        """Send each message, yielding its items once delivery is confirmed."""
        for message, delivered in render_digest_chunks(items, header):
            response = await self._client.post(
                self._url,
                json={
                    "chat_id": self._chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            response.raise_for_status()
            yield delivered
