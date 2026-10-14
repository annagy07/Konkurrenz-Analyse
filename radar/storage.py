"""SQLite state: which items were already seen, page snapshots for diffing, and the signal history."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Signal

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    source_key TEXT NOT NULL,
    item_id TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    PRIMARY KEY (source_key, item_id)
);
CREATE TABLE IF NOT EXISTS snapshots (
    url TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signals (
    key TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    artist TEXT NOT NULL,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    score INTEGER NOT NULL,
    level TEXT NOT NULL,
    release_date TEXT,
    reasons TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def has_baseline(self, source_key: str) -> bool:
        row = self.db.execute("SELECT 1 FROM seen WHERE source_key = ? LIMIT 1", (source_key,)).fetchone()
        return row is not None

    def is_seen(self, source_key: str, item_id: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM seen WHERE source_key = ? AND item_id = ?", (source_key, item_id)
        ).fetchone()
        return row is not None

    def mark_seen(self, source_key: str, item_id: str) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO seen (source_key, item_id, first_seen) VALUES (?, ?, ?)",
            (source_key, item_id, _now()),
        )

    def get_snapshot(self, url: str) -> str | None:
        row = self.db.execute("SELECT content FROM snapshots WHERE url = ?", (url,)).fetchone()
        return row[0] if row else None

    def put_snapshot(self, url: str, content: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO snapshots (url, content, fetched_at) VALUES (?, ?, ?)",
            (url, content, _now()),
        )

    def save_signal(self, s: Signal) -> None:
        # Collisions are deliberately not stored: they would leak own release plans into the DB.
        self.db.execute(
            "INSERT OR REPLACE INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                s.key, _now(), s.item.artist, s.item.source, s.item.title, s.item.url, s.score, s.level,
                s.release_date.isoformat() if s.release_date else None,
                "; ".join(s.reasons),
            ),
        )

    def recent_signals(self, days: int = 60) -> list[sqlite3.Row]:
        self.db.row_factory = sqlite3.Row
        rows = self.db.execute(
            "SELECT * FROM signals WHERE created_at >= datetime('now', ?) ORDER BY created_at DESC",
            (f"-{days} days",),
        ).fetchall()
        self.db.row_factory = None
        return rows

    def commit(self) -> None:
        self.db.commit()
