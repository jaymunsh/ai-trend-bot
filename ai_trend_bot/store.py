import sqlite3
from pathlib import Path
from typing import final


@final
class SeenStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS seen (item_key TEXT PRIMARY KEY)")

    def unseen(self, keys: tuple[str, ...]) -> tuple[str, ...]:
        if not keys:
            return ()
        placeholders = ",".join("?" for _ in keys)
        with sqlite3.connect(self._path) as connection:
            rows: list[tuple[str]] = connection.execute(
                f"SELECT item_key FROM seen WHERE item_key IN ({placeholders})",  # noqa: S608
                keys,
            ).fetchall()
        seen = {row[0] for row in rows}
        return tuple(key for key in keys if key not in seen)

    def mark(self, keys: tuple[str, ...]) -> None:
        with sqlite3.connect(self._path) as connection:
            connection.executemany("INSERT OR IGNORE INTO seen (item_key) VALUES (?)", ((key,) for key in keys))
