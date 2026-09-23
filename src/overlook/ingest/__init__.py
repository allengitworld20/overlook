from __future__ import annotations

import sqlite3

import httpx

from .. import db
from . import eonet, usgs, who

USER_AGENT = "overlook/0.1 (open-source situational awareness project)"


def ingest_all(
    conn: sqlite3.Connection,
    days: int = 30,
    who_days: int = 90,
    client: httpx.Client | None = None,
) -> dict[str, int | str]:
    """Pull every source and upsert into the DB.

    One failing source must not block the others, so each result is either a
    row count or an "error: ..." string.
    """
    own_client = client is None
    if client is None:
        client = httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    sources = {
        "usgs": lambda: usgs.fetch(client, days),
        "eonet": lambda: eonet.fetch(client, days),
        "who": lambda: who.fetch(client, who_days),
    }
    results: dict[str, int | str] = {}
    try:
        for name, fetch in sources.items():
            try:
                results[name] = db.upsert_events(conn, fetch())
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                results[name] = f"error: {type(exc).__name__}: {exc}"
    finally:
        if own_client:
            client.close()
    return results
