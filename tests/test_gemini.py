from datetime import UTC, datetime

from pydantic import HttpUrl

from ai_trend_bot.gemini import parse_summary
from ai_trend_bot.models import RawItem, SourceKind


def test_parse_summary_when_response_matches_items() -> None:
    # Given
    raw_items = (
        RawItem(
            source="Example",
            source_kind=SourceKind.FEED,
            title="New model",
            text="A faster model was released.",
            url=HttpUrl("https://example.com/model"),
            published_at=datetime(2026, 8, 1, tzinfo=UTC),
            priority=80,
        ),
    )
    payload = '{"items":[{"index":0,"title":"새 모델 공개","summary":"더 빠른 모델이 공개됐습니다.","relevance":95}]}'

    # When
    digest = parse_summary(payload, raw_items)

    # Then
    assert digest[0].title == "새 모델 공개"
    assert digest[0].source_label == "Example"


def test_parse_summary_keeps_low_relevance_items() -> None:
    # Given
    raw_items = (
        RawItem(
            source="Example",
            source_kind=SourceKind.FEED,
            title="Office party",
            text="Photos from a company party.",
            url=HttpUrl("https://example.com/party"),
            published_at=datetime(2026, 8, 1, tzinfo=UTC),
            priority=80,
        ),
    )
    payload = '{"items":[{"index":0,"title":"사내 행사","summary":"사내 행사 소식입니다.","relevance":20}]}'

    # When
    digest = parse_summary(payload, raw_items)

    # Then
    assert len(digest) == 1
    assert digest[0].title == "사내 행사"
