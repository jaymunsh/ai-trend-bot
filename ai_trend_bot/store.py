import calendar
import json
import os
import tempfile
from collections import Counter
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar, final
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, HttpUrl

from ai_trend_bot.models import DigestItem, item_key


class SentRecord(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    key: str
    title: str = ""
    url: str = ""
    source: str = ""
    category: str = ""
    event: str = ""
    sent_at: AwareDatetime
    also: tuple[tuple[str, str], ...] = ()


@final
class SentLog:
    """Current-month delivery log and permanent, Korean-calendar monthly archives.

    Readers never move files. Rotation happens explicitly or before appending a
    successful delivery. All files remain available for duplicate checks.
    """

    def __init__(self, path: Path, *, now: datetime | None = None) -> None:
        self._path = path
        self._clock = now
        self._keys = self._load()

    def _now(self) -> datetime:
        return self._clock or datetime.now(tz=UTC)

    def _paths(self) -> tuple[Path, ...]:
        return (*sorted((self._path.parent / "archive").glob("until_????-??-??.jsonl")), self._path)

    def _load(self) -> set[str]:
        keys: set[str] = set()
        for record in self._records():
            keys.add(record.key)
            keys.update(item_key(HttpUrl(url)) for _, url in record.also)
        return keys

    def unseen(self, keys: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(key for key in keys if key not in self._keys)

    def last_sent_at(self) -> datetime | None:
        """When the most recent item went out, or None if nothing ever has."""
        return max((record.sent_at for record in self._records()), default=None)

    def _records(self) -> Iterator[SentRecord]:
        for path in self._paths():
            if path.exists():
                with path.open(encoding="utf-8") as log:
                    for line in log:
                        if line.strip():
                            yield SentRecord.model_validate_json(line)

    def recent_events(self, *, days: int = 14) -> tuple[str, ...]:
        """Event summaries from recent sends, so triage can spot follow-up coverage."""
        cutoff = self._now() - timedelta(days=days)
        events = [r.event for r in self._records() if r.event and r.sent_at >= cutoff]
        return tuple(dict.fromkeys(events))

    @staticmethod
    def _replace(path: Path, lines: Sequence[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.writelines(line.rstrip("\n") + "\n" for line in lines)
                output.flush()
                os.fsync(output.fileno())
            Path(temporary).replace(path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def rotate(self) -> None:
        """Archive previous months without deleting records, safely retryable.

        Archives are replaced first. If the active-file replacement fails, the
        original remains intact; a retry recognises the already archived rows.
        Original JSON fields are preserved, including fields unknown to this version.
        """
        if not self._path.exists():
            return
        current = self._now().astimezone(ZoneInfo("Asia/Seoul"))
        active: list[str] = []
        months: dict[Path, list[str]] = {}
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = SentRecord.model_validate_json(line)
            local = record.sent_at.astimezone(ZoneInfo("Asia/Seoul"))
            if (local.year, local.month) >= (current.year, current.month):
                active.append(line)
            else:
                last_day = calendar.monthrange(local.year, local.month)[1]
                name = f"until_{local.year:04d}-{local.month:02d}-{last_day:02d}.jsonl"
                months.setdefault(self._path.parent / "archive" / name, []).append(line)
        if not months:
            return
        for path, lines in months.items():
            previous = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
            # Compare full JSON objects, not just URLs: repeated sends are history too.
            examples = {
                json.dumps(json.loads(line), sort_keys=True, ensure_ascii=False): line
                for line in (*previous, *lines)
                if line.strip()
            }
            # Retain repeated identical records within the original history, but
            # do not multiply them when retrying an interrupted rotation.
            old_counts = Counter(
                json.dumps(json.loads(line), sort_keys=True, ensure_ascii=False) for line in previous if line.strip()
            )
            new_counts = Counter(json.dumps(json.loads(line), sort_keys=True, ensure_ascii=False) for line in lines)
            self._replace(
                path, tuple(examples[key] for key, count in (old_counts | new_counts).items() for _ in range(count))
            )
        self._replace(self._path, active)

    def mark(self, items: Sequence[DigestItem]) -> None:
        """Record delivered items. Called per delivered chunk, never before delivery."""
        if not items:
            return
        self.rotate()
        sent_at = self._now().isoformat()
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
                    "also": item.also,
                    "sent_at": sent_at,
                }
                log.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._keys.update(item.key for item in items)
        self._keys.update(item_key(HttpUrl(url)) for item in items for _, url in item.also)
