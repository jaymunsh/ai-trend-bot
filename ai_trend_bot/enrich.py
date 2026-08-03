from typing import Final

import httpx2
import trafilatura

from ai_trend_bot.models import RawItem

# Enough article for a real summary without spending the triage budget on one page.
BODY_LIMIT: Final = 12_000


async def fetch_body(client: httpx2.AsyncClient, item: RawItem) -> RawItem:
    """Replace the feed teaser with the article body.

    Feed `summary` fields are often two sentences, so summarising them produces a
    summary of a summary. Any failure falls back to the teaser: one shallow item
    beats a missed digest.
    """
    try:
        response = await client.get(str(item.url))
        response.raise_for_status()
        # ponytail: parsed inline rather than in a worker thread — a handful of pages
        # at a few tens of ms each. Move off the loop if the source list grows a lot.
        body = trafilatura.extract(response.text)
    except (httpx2.HTTPStatusError, httpx2.RequestError, UnicodeDecodeError, ValueError):
        return item
    if not body or len(body) <= len(item.text):
        return item
    return item.model_copy(update={"text": body[:BODY_LIMIT]})
