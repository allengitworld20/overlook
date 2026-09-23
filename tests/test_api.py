from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from overlook import db
from overlook.api import create_app
from overlook.models import Event


def _recent(i, category, lat, lon, hours_ago, severity=0.5, title=None):
    return Event(
        id=f"t:{i}", source="t", category=category, title=title or f"{category} {i}",
        time=datetime.now(timezone.utc) - timedelta(hours=hours_ago), lat=lat, lon=lon, severity=severity,
    )


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "api.db"
    events = [_recent(i, "earthquake", -21 + 0.1 * i, -69, 5 + i) for i in range(5)]
    events += [_recent("f", "wildfire", 10, 10, 2, severity=0.9)]
    events += [_recent("old", "earthquake", 0, 0, 24 * 60)]
    with db.connect(path) as conn:
        db.upsert_events(conn, events)
    return TestClient(create_app(path))


def test_status(client):
    body = client.get("/api/status").json()
    assert body["event_count"] == 7 and body["sources"] == {"t": 7}


def test_events_filters(client):
    assert client.get("/api/events").json()["count"] == 6  # 60-day-old event excluded by default window
    assert client.get("/api/events", params={"days": 90}).json()["count"] == 7
    only_fire = client.get("/api/events", params={"category": "wildfire"}).json()
    assert [e["category"] for e in only_fire["events"]] == ["wildfire"]
    assert client.get("/api/events", params={"min_severity": 0.8}).json()["count"] == 1


def test_clusters_and_graph(client):
    clusters = client.get("/api/clusters").json()["clusters"]
    assert len(clusters) == 1 and clusters[0]["category"] == "earthquake" and clusters[0]["size"] == 5
    graph = client.get("/api/graph").json()
    assert graph["stats"]["nodes"] == 6 and graph["stats"]["communities"] >= 1


def test_anomalies_endpoint_shape(client):
    body = client.get("/api/anomalies").json()
    assert body["count"] == len(body["anomalies"])


@pytest.mark.parametrize("path, params", [("/api/events", {"days": 0}), ("/api/events", {"min_severity": 2}), ("/api/anomalies", {"days": 1})])
def test_bad_params_rejected(client, path, params):
    assert client.get(path, params=params).status_code == 422


def test_index_served(client):
    resp = client.get("/")
    assert resp.status_code == 200 and "Overlook" in resp.text
