from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from .models import Event, parse_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    category    TEXT NOT NULL,
    title       TEXT NOT NULL,
    summary     TEXT NOT NULL DEFAULT '',
    time        TEXT NOT NULL,
    lat         REAL,
    lon         REAL,
    region      TEXT,
    severity    REAL NOT NULL,
    url         TEXT NOT NULL DEFAULT '',
    ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(time);
"""

_COLUMNS = ("id", "source", "category", "title", "summary", "time", "lat", "lon", "region", "severity", "url")


def resolve_db_path(path: str | os.PathLike | None = None) -> Path:
    return Path(path or os.environ.get("OVERLOOK_DB") or "data/overlook.db")


@contextmanager
def connect(path: str | os.PathLike | None = None) -> Iterator[sqlite3.Connection]:
    db_path = resolve_db_path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ts(dt: datetime) -> str:
    # Fixed-width UTC strings keep lexicographic and chronological order identical.
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def upsert_events(conn: sqlite3.Connection, events: Iterable[Event]) -> int:
    """Insert or update events by id (feeds revise magnitudes and status). Returns rows written."""
    now = _ts(datetime.now(timezone.utc))
    rows = [
        (e.id, e.source, e.category, e.title, e.summary, _ts(e.time), e.lat, e.lon, e.region, e.severity, e.url, now)
        for e in events
    ]
    conn.executemany(
        """
        INSERT INTO events (id, source, category, title, summary, time, lat, lon, region, severity, url, ingested_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            source=excluded.source, category=excluded.category, title=excluded.title,
            summary=excluded.summary, time=excluded.time, lat=excluded.lat, lon=excluded.lon,
            region=excluded.region, severity=excluded.severity, url=excluded.url,
            ingested_at=excluded.ingested_at
        """,
        rows,
    )
    return len(rows)


def query_events(
    conn: sqlite3.Connection,
    since: datetime | None = None,
    categories: Iterable[str] | None = None,
    min_severity: float = 0.0,
    limit: int | None = None,
) -> list[Event]:
    clauses, params = ["severity >= ?"], [min_severity]
    if since is not None:
        clauses.append("time >= ?")
        params.append(_ts(since))
    cats = list(categories or [])
    if cats:
        clauses.append(f"category IN ({','.join('?' * len(cats))})")
        params.extend(cats)
    sql = f"SELECT {', '.join(_COLUMNS)} FROM events WHERE {' AND '.join(clauses)} ORDER BY time DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return [
        Event(
            id=r["id"], source=r["source"], category=r["category"], title=r["title"],
            summary=r["summary"], time=parse_iso(r["time"]), lat=r["lat"], lon=r["lon"],
            region=r["region"], severity=r["severity"], url=r["url"],
        )
        for r in conn.execute(sql, params)
    ]


def status(conn: sqlite3.Connection) -> dict:
    by_source = {r["source"]: r["n"] for r in conn.execute("SELECT source, COUNT(*) AS n FROM events GROUP BY source")}
    last = conn.execute("SELECT MAX(ingested_at) AS t FROM events").fetchone()["t"]
    return {"event_count": sum(by_source.values()), "sources": by_source, "last_ingest": last}
