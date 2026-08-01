from ai_trend_bot.feeds import parse_feed


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
