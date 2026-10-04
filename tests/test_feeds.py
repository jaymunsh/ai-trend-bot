import asyncio
from datetime import UTC, datetime

import httpx2
from pydantic import HttpUrl

from ai_trend_bot.config import FeedCategory, FeedKind, FeedSource
from ai_trend_bot.feeds import FeedClient, parse_feed


def test_parse_feed_when_rss_contains_one_entry() -> None:
    # Given
    payload = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>Example</title><item>
      <title>New model</title><link>https://example.com/model</link>
      <description>A faster model.</description>
      <pubDate>Fri, 01 Aug 2026 00:00:00 GMT</pubDate>
    </item></channel></rss>"""

    # When
    items = parse_feed(payload, source_name="Example", priority=70)

    # Then
    assert len(items) == 1
    assert items[0].title == "New model"
    assert str(items[0].url) == "https://example.com/model"


def test_missing_feed_date_is_explicitly_unknown():
    payload = b'<rss version="2.0"><channel><item><title>Undated</title><link>https://example.com/no-date</link></item></channel></rss>'
    (item,) = parse_feed(payload, "Example", 20)
    assert item.published_at_known is False


def test_feed_client_returns_all_entries_before_pipeline_cap():

    payload = (
        b'<rss version="2.0"><channel>'
        + b"".join(f"<item><title>{i}</title><link>https://example.com/{i}</link></item>".encode() for i in range(3))
        + b"</channel></rss>"
    )

    async def run():
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(lambda request: httpx2.Response(200, content=payload))
        ) as client:
            return await FeedClient(client).fetch(
                FeedSource(
                    name="Example",
                    url=HttpUrl("https://example.com/feed"),
                    category=FeedCategory.COMMUNITY,
                    max_items=1,
                )
            )

    assert len(asyncio.run(run())) == 3


def test_hacker_news_searches_recent_keywords_separately_and_deduplicates():

    requests = []

    def respond(request):
        requests.append(request)
        return httpx2.Response(
            200, json={"hits": [{"objectID": "42", "title": "New model", "created_at": "2026-10-04T00:00:00Z"}]}
        )

    async def run():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(respond)) as client:
            return await FeedClient(client).fetch(
                FeedSource(
                    name="HN",
                    url=HttpUrl("https://hn.algolia.com/api/v1/search_by_date"),
                    category=FeedCategory.COMMUNITY,
                    kind=FeedKind.HACKER_NEWS,
                ),
                now=datetime(2026, 10, 4, tzinfo=UTC),
            )

    assert len(asyncio.run(run())) == 1
    assert {request.url.params["query"] for request in requests} == {"AI", "LLM", "OpenAI", "Anthropic"}
    assert all("created_at_i>=1790899200" in request.url.params["numericFilters"] for request in requests)
    assert all("points" not in request.url.params["numericFilters"] for request in requests)
