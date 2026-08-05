import json
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar, final

from pydantic import BaseModel, ConfigDict

from ai_trend_bot.models import DigestItem


class SentRecord(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    key: str
    title: str = ""
    url: str = ""
    source: str = ""
    category: str = ""
    event: str = ""
    sent_at: datetime


@final
class SentLog:
    """Append-only record of delivered items, committed to the repository.

    Lives in git rather than an Actions cache so it is never evicted; losing it
    would re-send everything already delivered.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._keys = self._load()

    def _load(self) -> set[str]:
        return {record.key for record in self._records()}

    def unseen(self, keys: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(key for key in keys if key not in self._keys)

    def last_sent_at(self) -> datetime | None:
        """When the most recent item went out, or None if nothing ever has."""
        return max((record.sent_at for record in self._records()), default=None)

    def _records(self) -> Iterator[SentRecord]:
        if not self._path.exists():
            return
        with self._path.open(encoding="utf-8") as log:
            for line in log:
                if line.strip():
                    yield SentRecord.model_validate_json(line)

    def recent_events(self, *, days: int = 14) -> tuple[str, ...]:
        """Event summaries from recent sends, so triage can spot follow-up coverage."""
        cutoff = datetime.now(tz=UTC) - timedelta(days=days)
        events = [r.event for r in self._records() if r.event and r.sent_at >= cutoff]
        return tuple(dict.fromkeys(events))

    def mark(self, items: Sequence[DigestItem]) -> None:
        """Record delivered items. Called per delivered chunk, never before delivery."""
        if not items:
            return
        sent_at = datetime.now(tz=UTC).isoformat()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as log:
            for item in items:
                record = {
                    "key": item.key,
                    "title": item.title,
                    "url": str(item.source_url),
                    "source": item.source_label,
                    "category": item.category,
                    "event": item.event,
                    "sent_at": sent_at,
                }
                log.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._keys.update(item.key for item in items)
