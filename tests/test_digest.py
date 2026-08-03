from datetime import UTC, datetime

from pydantic import HttpUrl

from ai_trend_bot.models import DigestItem, RawItem, SourceKind
from ai_trend_bot.telegram import SEOUL, render_digest_chunks, render_header


def _item(index: int, summary: str = "요약입니다.") -> DigestItem:
    return DigestItem(
        title=f"소식 {index}",
        summary=summary,
        source_url=HttpUrl(f"https://example.com/{index}"),
        source_label="Example",
    )


def test_render_header_when_slot_changes() -> None:
    # Given / When
    morning = render_header(datetime(2026, 8, 3, 7, 30, tzinfo=SEOUL), 4)
    evening = render_header(datetime(2026, 8, 3, 19, 30, tzinfo=SEOUL), 1)

    # Then
    assert "🌅" in morning
    assert "아침 07:30" in morning
    assert "8월 3일 (월) · 4건" in morning
    assert "🌙" in evening
    assert "저녁 19:30" in evening


def test_render_digest_chunks_when_single_item() -> None:
    # Given
    header = render_header(datetime(2026, 8, 3, 7, 30, tzinfo=SEOUL), 1)
    item = DigestItem(
        title="새 AI 모델 공개",
        summary="더 빠르고 저렴한 모델이 공개됐습니다.",
        source_url=HttpUrl("https://example.com/news"),
        source_label="Example",
    )

    # When
    ((message, carried),) = render_digest_chunks((item,), header)

    # Then
    assert "새 AI 모델 공개" in message
    assert '<a href="https://example.com/news">Example</a>' in message
    assert carried == (item,)


def test_render_digest_chunks_escapes_markup() -> None:
    # Given
    header = render_header(datetime(2026, 8, 3, 7, 30, tzinfo=SEOUL), 1)
    item = DigestItem(
        title="<script>alert(1)</script>",
        summary="a & b",
        source_url=HttpUrl("https://example.com/x"),
        source_label="Example",
    )

    # When
    ((message, _),) = render_digest_chunks((item,), header)

    # Then
    assert "<script>" not in message
    assert "&lt;script&gt;" in message
    assert "a &amp; b" in message


def test_render_digest_chunks_when_digest_exceeds_limit() -> None:
    # Given
    header = render_header(datetime(2026, 8, 3, 7, 30, tzinfo=SEOUL), 3)
    items = tuple(_item(index, "긴 요약입니다. " * 20) for index in range(3))

    # When
    chunks = render_digest_chunks(items, header, max_length=300)

    # Then
    assert len(chunks) == 3
    assert all(len(message) <= 300 for message, _ in chunks)
    # Every item lands in exactly one message, so per-chunk recording stays complete.
    assert tuple(item for _, carried in chunks for item in carried) == items


def test_raw_and_digest_key_match_for_same_url() -> None:
    # Given
    url = HttpUrl("https://example.com/post")
    raw = RawItem(
        source="Example",
        source_kind=SourceKind.FEED,
        title="Title",
        text="Body",
        url=url,
        published_at=datetime(2026, 8, 1, tzinfo=UTC),
        priority=70,
    )
    digest = DigestItem(title="Title", summary="요약", source_url=url, source_label="Example")

    # When / Then
    assert raw.key == digest.key


def test_split_messages_are_numbered() -> None:
    # Given
    header = render_header(datetime(2026, 8, 3, 7, 30, tzinfo=SEOUL), 3)
    items = tuple(_item(index, "긴 요약입니다. " * 20) for index in range(3))

    # When
    chunks = render_digest_chunks(items, header, max_length=320)

    # Then
    assert [message.splitlines()[0][-5:] for message, _ in chunks] == ["[1/3]", "[2/3]", "[3/3]"]
    # The counter is added after splitting, so it must still fit the limit.
    assert all(len(message) <= 320 for message, _ in chunks)


def test_single_message_is_not_numbered() -> None:
    # Given
    header = render_header(datetime(2026, 8, 3, 7, 30, tzinfo=SEOUL), 1)

    # When
    ((message, _),) = render_digest_chunks((_item(1),), header)

    # Then
    assert "[1/1]" not in message
