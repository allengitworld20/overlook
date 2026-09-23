from dataclasses import replace
from datetime import timedelta

from conftest import NOW, make_event

from overlook import db


def test_upsert_is_idempotent_and_updates(tmp_path):
    with db.connect(tmp_path / "t.db") as conn:
        db.upsert_events(conn, [make_event("1", severity=0.2)])
        db.upsert_events(conn, [replace(make_event("1"), severity=0.9, title="revised")])
        (ev,) = db.query_events(conn)
    assert ev.severity == 0.9 and ev.title == "revised"


def test_query_filters(tmp_path):
    events = [
        make_event("old", days_ago=40),
        make_event("quake", category="earthquake", days_ago=1, severity=0.5),
        make_event("fire", category="wildfire", days_ago=1, severity=0.1),
    ]
    with db.connect(tmp_path / "t.db") as conn:
        db.upsert_events(conn, events)
        since = NOW - timedelta(days=7)
        assert {e.id for e in db.query_events(conn, since=since)} == {"t:quake", "t:fire"}
        assert [e.id for e in db.query_events(conn, since=since, categories=["wildfire"])] == ["t:fire"]
        assert [e.id for e in db.query_events(conn, since=since, min_severity=0.4)] == ["t:quake"]
        assert len(db.query_events(conn, limit=1)) == 1


def test_roundtrip_preserves_time_and_location(tmp_path):
    original = make_event("1", lat=12.5, lon=-45.25, days_ago=0.5)
    with db.connect(tmp_path / "t.db") as conn:
        db.upsert_events(conn, [original])
        (ev,) = db.query_events(conn)
    assert ev.time == original.time and (ev.lat, ev.lon) == (12.5, -45.25)
