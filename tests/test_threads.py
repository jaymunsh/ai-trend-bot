import json

from ai_trend_bot.threads import parse_threads_posts


def test_parse_threads_posts_when_response_is_valid() -> None:
    # Given
    payload = {
        "data": [
            {
                "id": "123",
                "text": "A new AI model",
                "timestamp": "2026-08-01T00:00:00+0000",
                "permalink": "https://www.threads.com/@example/post/123",
                "username": "example",
            },
        ],
    }

    # When
    items = parse_threads_posts(json.dumps(payload), source_name="@example", priority=100)

    # Then
    assert len(items) == 1
    assert items[0].source == "@example"
    assert items[0].priority == 100
    assert items[0].external_id == "123"
