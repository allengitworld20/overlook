from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse

from . import __version__, db
from .analysis import build_graph, cluster_events, detect_anomalies
from .models import Event

STATIC_DIR = Path(__file__).parent / "static"


def create_app(db_path: str | Path | None = None) -> FastAPI:
    app = FastAPI(title="Overlook", version=__version__)
    path = db.resolve_db_path(db_path)

    def load(days: int, min_severity: float = 0.0, categories: list[str] | None = None, limit: int | None = None) -> list[Event]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        with db.connect(path) as conn:
            return db.query_events(conn, since=since, categories=categories, min_severity=min_severity, limit=limit)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/status")
    def status() -> dict:
        with db.connect(path) as conn:
            return db.status(conn)

    @app.get("/api/events")
    def events(
        days: int = Query(30, ge=1, le=365),
        category: list[str] | None = Query(None),
        min_severity: float = Query(0.0, ge=0.0, le=1.0),
        limit: int = Query(2000, ge=1, le=5000),
    ) -> dict:
        found = load(days, min_severity, category, limit)
        return {"count": len(found), "events": [e.to_dict() for e in found]}

    @app.get("/api/anomalies")
    def anomalies(days: int = Query(30, ge=7, le=365)) -> dict:
        found = detect_anomalies(load(days), window_days=days)
        return {"count": len(found), "anomalies": [a.to_dict() for a in found]}

    @app.get("/api/clusters")
    def clusters(
        days: int = Query(30, ge=1, le=365),
        eps_km: float = Query(100.0, gt=0, le=2000),
        min_samples: int = Query(5, ge=2, le=50),
        limit: int = Query(50, ge=1, le=500),
    ) -> dict:
        found = cluster_events(load(days), eps_km=eps_km, min_samples=min_samples)[:limit]
        return {"count": len(found), "clusters": [c.to_dict() for c in found]}

    @app.get("/api/graph")
    def graph(
        days: int = Query(30, ge=1, le=365),
        max_nodes: int = Query(300, ge=2, le=1000),
    ) -> dict:
        return build_graph(load(days), max_nodes=max_nodes)

    return app
