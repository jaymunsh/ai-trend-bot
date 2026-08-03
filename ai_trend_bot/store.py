import json
from collections.abc import Sequence
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
        if not self._path.exists():
            return set()
        with self._path.open(encoding="utf-8") as log:
            return {SentRecord.model_validate_json(line).key for line in log if line.strip()}

    def unseen(self, keys: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(key for key in keys if key not in self._keys)

    def recent_events(self, *, days: int = 14) -> tuple[str, ...]:
        """Event summaries from recent sends, so triage can spot follow-up coverage."""
        if not self._path.exists():
            return ()
        cutoff = datetime.now(tz=UTC) - timedelta(days=days)
        events: list[str] = []
        with self._path.open(encoding="utf-8") as log:
            for line in log:
                if not line.strip():
                    continue
                record = SentRecord.model_validate_json(line)
                if record.event and record.sent_at >= cutoff:
                    events.append(record.event)
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
