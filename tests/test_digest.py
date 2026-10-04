from datetime import UTC, datetime
from xml.etree import ElementTree as ET

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
    assert "🌤️" in morning
    assert morning == "<b>🌤️ AI 브리핑 · 8/3 (월) · 4건</b>"
    assert "\n" not in morning
    assert "트렌드" not in morning
    assert "🌙" in evening
    assert "8/3 (월) · 1건" in evening


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
    assert [message.splitlines()[0] for message, _ in chunks] == [
        f"<b>🌤️ AI 브리핑 · 8/3 (월) · 3건</b> ({index}/3)" for index in range(1, 4)
    ]
    # The counter is added after splitting, so it must still fit the limit.
    assert all(len(message) <= 320 for message, _ in chunks)


def test_single_message_is_not_numbered() -> None:
    # Given
    header = render_header(datetime(2026, 8, 3, 7, 30, tzinfo=SEOUL), 1)

    # When
    ((message, _),) = render_digest_chunks((_item(1),), header)

    # Then
    assert "(1/1)" not in message


def test_oversized_section_keeps_valid_html_and_representative_source():

    item = _item(1, "<&>'" * 2000).model_copy(
        update={"also": (("Other & Source", "https://other.example/news?q=1&x=2"),)}
    )
    ((message, carried),) = render_digest_chunks((item,), "header", max_length=350)
    ET.fromstring(f"<root>{message}</root>")  # noqa: S314 — locally generated test HTML
    assert '<a href="https://example.com/1">Example</a>' in message
    assert "외 1곳" in message
    assert message.count("</a>") == 1
    assert len(message) <= 350
    assert carried == (item,)


def test_compact_digest_shows_only_representative_and_counts_distinct_outlets():
    item = _item(1, "핵심 사실과 중요한 적용 조건을 전달합니다.").model_copy(
        update={
            "category": "정책·산업·자금",
            "also": (
                ("Example", "https://example.com/another"),
                ("Other", "https://other.example/one"),
                ("Other", "https://other.example/two"),
                ("Third", "https://third.example/news"),
            ),
        }
    )
    ((message, carried),) = render_digest_chunks((item, _item(2)), "header")
    assert message.count("<a href=") == 2
    assert '원문: <a href="https://example.com/1">Example</a> 외 2곳' in message
    assert "정책·산업·자금" not in message
    assert "────" not in message
    assert "<b>01. [소식 1]</b>\n핵심 사실" in message
    assert "외 0곳" not in message
    assert carried[0].also == item.also
    assert len(carried[0].also) == 4
