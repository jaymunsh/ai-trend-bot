import html
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Final, final
from zoneinfo import ZoneInfo

import httpx2

from ai_trend_bot.models import DigestItem

SEOUL: Final = ZoneInfo("Asia/Seoul")
TELEGRAM_SAFE_LENGTH: Final = 3_800
DIVIDER: Final = "────────────────"
SEPARATOR: Final = f"\n\n{DIVIDER}\n\n"
WEEKDAYS: Final = ("월", "화", "수", "목", "금", "토", "일")
NOON: Final = 12
EVENING: Final = 18


def _slot(hour: int) -> tuple[str, str]:
    if hour < NOON:
        return "🌅", "아침"
    if hour < EVENING:
        return "☀️", "점심"
    return "🌙", "저녁"


def render_header(now: datetime, count: int) -> str:
    emoji, slot = _slot(now.hour)
    return "\n".join(
        (
            f"{emoji}  <b>AI 트렌드 브리핑</b> · {slot} {now:%H:%M}",
            f"{now.month}월 {now.day}일 ({WEEKDAYS[now.weekday()]}) · {count}건",
        ),
    )


def _link(label: str, url: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def _section(index: int, item: DigestItem) -> str:
    links = " · ".join(
        (_link(item.source_label, str(item.source_url)), *(_link(label, url) for label, url in item.also)),
    )
    lines = [f"<b>{index:02d}. {html.escape(item.title)}</b>"]
    if item.category:
        lines.append(f"[{html.escape(item.category)}]")
    # "원문:" spelled out — an outlet name on its own does not read as a tappable link.
    lines += ["", html.escape(item.summary), "", f"↳ 원문: {links}"]
    return "\n".join(lines)


def render_digest_chunks(
    items: Sequence[DigestItem],
    header: str,
    max_length: int = TELEGRAM_SAFE_LENGTH,
) -> tuple[tuple[str, tuple[DigestItem, ...]], ...]:
    """Split a digest into sendable messages, each paired with the items it carries.

    Pairing lets the caller record delivery per message, so a failure partway
    through does not re-send what already arrived.
    """
    room = max_length - len(header) - len(SEPARATOR)
    chunks: list[tuple[str, tuple[DigestItem, ...]]] = []
    sections: list[str] = []
    carried: list[DigestItem] = []
    for index, item in enumerate(items, start=1):
        # ponytail: truncate a single oversized section rather than splitting it across
        # messages, which would break its HTML tags. Revisit if summaries reach ~3KB.
        section = _section(index, item)[:room]
        if sections and len(SEPARATOR.join((header, *sections, section))) > max_length:
            chunks.append((SEPARATOR.join((header, *sections)), tuple(carried)))
            sections, carried = [], []
        sections.append(section)
        carried.append(item)
    if sections:
        chunks.append((SEPARATOR.join((header, *sections)), tuple(carried)))
    return tuple(chunks)


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
