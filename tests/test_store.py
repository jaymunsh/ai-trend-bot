from pydantic import HttpUrl

from ai_trend_bot.models import DigestItem
from ai_trend_bot.store import SentLog


def _item(index: int) -> DigestItem:
    return DigestItem(
        title=f"소식 {index}",
        summary="요약",
        source_url=HttpUrl(f"https://example.com/{index}"),
        source_label="Example",
    )


def test_sent_log_when_item_is_marked(tmp_path) -> None:
    # Given
    path = tmp_path / "sent.jsonl"
    log = SentLog(path)
    first, second = _item(1), _item(2)

    # When
    log.mark((first,))

    # Then
    assert log.unseen((first.key, second.key)) == (second.key,)
    # A fresh reader sees the same history, which is what has to survive across runs.
    assert SentLog(path).unseen((first.key, second.key)) == (second.key,)


def test_last_sent_at_reports_the_most_recent_send(tmp_path) -> None:
    # Given
    path = tmp_path / "sent.jsonl"
    log = SentLog(path)

    # When / Then
    assert log.last_sent_at() is None
    log.mark((_item(1),))
    first = SentLog(path).last_sent_at()
    assert first is not None
    # A second reader must see it too; the backup-run guard depends on this.
    assert SentLog(path).last_sent_at() == first
