"""NASA EONET natural event tracker (https://eonet.gsfc.nasa.gov/docs/v3)."""

from __future__ import annotations

import math

import httpx

from ..models import Event, parse_iso

API_URL = "https://eonet.gsfc.nasa.gov/api/v3/events"

CATEGORY_MAP = {
    "wildfires": "wildfire",
    "severeStorms": "storm",
    "volcanoes": "volcano",
    "floods": "flood",
    "drought": "drought",
    "landslides": "landslide",
    "earthquakes": "earthquake",
}
# Iceberg tracking and water-colour observations are routine monitoring, not situations.
IGNORED = {"seaLakeIce", "waterColor"}


def _severity(magnitude: float | None, unit: str | None) -> float:
    if magnitude is None:
        return 0.3
    if unit == "acres":
        return min(1.0, math.log10(magnitude + 1) / 5)  # 100k acres -> 1.0
    if unit == "kts":
        return min(1.0, magnitude / 130)  # roughly Cat 4 sustained wind
    return 0.3


def _centroid(geometry: dict) -> tuple[float, float] | None:
    coords = geometry.get("coordinates")
    if not coords:
        return None
    if geometry.get("type") == "Point":
        lon, lat = coords[:2]
    elif geometry.get("type") == "Polygon":
        ring = coords[0]
        lon = sum(p[0] for p in ring) / len(ring)
        lat = sum(p[1] for p in ring) / len(ring)
    else:
        return None
    return float(lat), float(lon)


def parse(payload: dict) -> list[Event]:
    events = []
    for ev in payload["events"]:
        cat_ids = [c["id"] for c in ev.get("categories", [])]
        if not cat_ids or all(c in IGNORED for c in cat_ids):
            continue
        category = CATEGORY_MAP.get(cat_ids[0], "other")
        geoms = sorted(ev.get("geometry", []), key=lambda g: g["date"])
        if not geoms:
            continue
        latest = geoms[-1]  # events are tracks over time; the newest fix is where it is now
        point = _centroid(latest)
        sources = ev.get("sources") or []
        events.append(
            Event(
                id=f"eonet:{ev['id']}",
                source="eonet",
                category=category,
                title=ev["title"],
                summary=ev.get("description") or "",
                time=parse_iso(latest["date"]),
                lat=point[0] if point else None,
                lon=point[1] if point else None,
                region=None,
                severity=_severity(latest.get("magnitudeValue"), latest.get("magnitudeUnit")),
                url=sources[0]["url"] if sources else ev.get("link", ""),
            )
        )
    return events


def fetch(client: httpx.Client, days: int = 30) -> list[Event]:
    resp = client.get(API_URL, params={"status": "all", "days": days, "limit": 500})
    resp.raise_for_status()
    return parse(resp.json())
