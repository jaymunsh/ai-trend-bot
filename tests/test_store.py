import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import HttpUrl

from ai_trend_bot.models import DigestItem, item_key
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


def test_monthly_rotation_preserves_history_and_uses_korean_month(tmp_path) -> None:

    path = tmp_path / "sent.jsonl"
    rows = [
        {"key": "sep", "event": "previous event", "sent_at": "2026-09-30T14:59:00+00:00", "custom": "preserved"},
        {"key": "oct", "sent_at": "2026-09-30T15:00:00+00:00"},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    now = datetime(2026, 10, 4, tzinfo=UTC)
    log = SentLog(path, now=now)
    log.rotate()
    archived = tmp_path / "archive/until_2026-09-30.jsonl"
    assert [json.loads(line) for line in archived.read_text().splitlines()] == rows[:1]
    assert [json.loads(line) for line in path.read_text().splitlines()] == rows[1:]
    assert SentLog(path, now=now).unseen(("sep", "oct", "new")) == ("new",)
    assert log.recent_events() == ("previous event",)
    log.rotate()
    assert len(archived.read_text().splitlines()) == 1


def test_rotation_is_recoverable_if_active_replacement_fails(tmp_path, monkeypatch) -> None:

    path = tmp_path / "sent.jsonl"
    row = {"key": "old", "sent_at": "2026-08-01T00:00:00+00:00"}
    original = json.dumps(row) + "\n"
    path.write_text(original)
    log = SentLog(path, now=datetime(2026, 10, 4, tzinfo=UTC))
    replace = os.replace

    def fail_active(src, dst):
        if Path(dst) == path:
            message = "simulated interrupted rotation"
            raise OSError(message)
        replace(src, dst)

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", fail_active)
        with pytest.raises(OSError, match="interrupted rotation"):
            log.rotate()
    assert path.read_text() == original
    log.rotate()
    assert path.read_text() == ""
    archive = tmp_path / "archive/until_2026-08-31.jsonl"
    assert [json.loads(line) for line in archive.read_text().splitlines()] == [row]


def test_reading_history_does_not_move_files(tmp_path) -> None:

    path = tmp_path / "sent.jsonl"
    original = '{"key":"old","sent_at":"2026-01-01T00:00:00Z"}\n'
    path.write_text(original)
    assert SentLog(path, now=datetime(2026, 10, 4, tzinfo=UTC)).unseen(("old",)) == ()
    assert path.read_text() == original
    assert not (tmp_path / "archive").exists()


def test_rotation_retains_identical_repeated_records_and_appends_current_month(tmp_path):
    path = tmp_path / "sent.jsonl"
    row = '{"key":"old","sent_at":"2026-09-01T00:00:00Z"}\n'
    path.write_text(row * 2)
    log = SentLog(path, now=datetime(2026, 10, 1, tzinfo=UTC))
    item = _item(2).model_copy(update={"also": (("Other", "https://example.com/also"),)})
    log.mark((item,))
    archived = tmp_path / "archive/until_2026-09-30.jsonl"
    assert len(archived.read_text().splitlines()) == 2
    assert len(path.read_text().splitlines()) == 1
    log.rotate()
    assert len(archived.read_text().splitlines()) == 2
    assert SentLog(path).unseen((_item(2).key, item_key(HttpUrl("https://example.com/also")), "old")) == ()
