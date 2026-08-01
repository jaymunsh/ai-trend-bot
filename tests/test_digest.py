from datetime import UTC, datetime

from pydantic import HttpUrl

from ai_trend_bot.models import DigestItem, RawItem, SourceKind
from ai_trend_bot.telegram import render_digest, render_digest_chunks


def test_render_digest_when_items_exist() -> None:
    # Given
    items = (
        DigestItem(
            title="새 AI 모델 공개",
            summary="더 빠르고 저렴한 모델이 공개됐습니다.",
            source_url=HttpUrl("https://example.com/news"),
            source_label="Example",
        ),
    )

    # When
    rendered = render_digest(items)

    # Then
    assert "1. 새 AI 모델 공개" in rendered
    assert "더 빠르고 저렴한 모델" in rendered
    assert "https://example.com/news" in rendered


def test_raw_item_key_when_content_is_same() -> None:
    # Given
    published_at = datetime(2026, 8, 1, tzinfo=UTC)
    first = RawItem(
        source="Example",
        source_kind=SourceKind.FEED,
        title="Title",
        text="Body",
        url=HttpUrl("https://example.com/post"),
        published_at=published_at,
        priority=70,
    )
    second = first.model_copy()

    # When / Then
    assert first.key == second.key


def test_render_digest_chunks_when_digest_exceeds_limit() -> None:
    # Given
    items = tuple(
        DigestItem(
            title=f"소식 {index}",
            summary="긴 요약입니다. " * 20,
            source_url=HttpUrl(f"https://example.com/{index}"),
            source_label="Example",
        )
        for index in range(3)
    )

    # When
    chunks = render_digest_chunks(items, max_length=300)

    # Then
    assert len(chunks) == 3
    assert all(len(chunk) <= 300 for chunk in chunks)
