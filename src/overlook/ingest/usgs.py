"""USGS earthquake feed (https://earthquake.usgs.gov/earthquakes/feed/)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from ..models import Event, from_epoch_ms

FEED_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{name}.geojson"
MIN_MAG, MAX_MAG = 2.5, 7.5  # severity 0 at the feed floor, 1 at a major quake


def parse(payload: dict) -> list[Event]:
    events = []
    for feature in payload["features"]:
        props = feature["properties"]
        if props.get("type") != "earthquake" or props.get("mag") is None:
            continue
        lon, lat, *rest = feature["geometry"]["coordinates"]
        depth = rest[0] if rest else None
        mag = float(props["mag"])
        place = props.get("place") or "Unknown location"
        summary = f"Magnitude {mag:.1f} ({props.get('magType') or 'n/a'})"
        if depth is not None:
            summary += f", depth {depth:.0f} km"
        if props.get("tsunami"):
            summary += ", tsunami advisory flag set"
        events.append(
            Event(
                id=f"usgs:{feature['id']}",
                source="usgs",
                category="earthquake",
                title=props.get("title") or f"M {mag:.1f} - {place}",
                summary=summary,
                time=from_epoch_ms(props["time"]),
                lat=float(lat),
                lon=float(lon),
                region=place.rsplit(",", 1)[-1].strip() if "," in place else place,
                severity=min(1.0, max(0.0, (mag - MIN_MAG) / (MAX_MAG - MIN_MAG))),
                url=props.get("url") or "",
            )
        )
    return events


def fetch(client: httpx.Client, days: int = 30) -> list[Event]:
    # The summary feeds only come in fixed windows; use the smallest that covers `days`.
    feed = "2.5_week" if days <= 7 else "2.5_month"
    resp = client.get(FEED_URL.format(name=feed))
    resp.raise_for_status()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return [e for e in parse(resp.json()) if e.time >= cutoff]
