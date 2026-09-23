"""Spatio-temporal clustering of located events.

Each event becomes a point in 4-D: its 3-D position on the Earth sphere (km)
plus time scaled to km at `km_per_day`. DBSCAN with a single eps then groups
events that are close in both space and time. With eps = 100 km, earthquakes
(100 km/day) are neighbours if simultaneous and 100 km apart or co-located and
1 day apart; other categories (50 km/day) tolerate 2 days, since fires and
outbreaks persist far longer than aftershock bursts.
Defaults were tuned on a month of live USGS/EONET data: a looser eps (250 km)
chains continuous regional seismicity into one month-long, region-wide blob,
while 100 km / min 5 isolates real aftershock sequences and fire complexes.
Clustering runs per category so a "cluster" is always one kind of situation
(an aftershock sequence, a fire complex); cross-category links are the job of
the graph module.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np
from sklearn.cluster import DBSCAN

from ..geo import haversine_km, mean_lat_lon, to_xyz_km
from ..models import Event

MIN_RADIUS_KM = 25.0
# Aftershock sequences decay fast; fires, floods and outbreaks persist for days.
KM_PER_DAY_BY_CATEGORY = {"earthquake": 100.0}
DEFAULT_KM_PER_DAY = 50.0


@dataclass(frozen=True)
class Cluster:
    id: str
    category: str
    label: str
    size: int
    lat: float
    lon: float
    radius_km: float
    start: str
    end: str
    mean_severity: float
    max_severity: float
    score: float
    event_ids: tuple[str, ...]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["event_ids"] = list(self.event_ids)
        return d


def cluster_events(
    events: Iterable[Event],
    eps_km: float = 100.0,
    min_samples: int = 5,
    km_per_day: float | None = None,
) -> list[Cluster]:
    """Cluster located events. `km_per_day` overrides the per-category time scale."""
    by_category: dict[str, list[Event]] = defaultdict(list)
    for e in events:
        if e.has_location:
            by_category[e.category].append(e)

    clusters: list[Cluster] = []
    for category, evs in by_category.items():
        if len(evs) < min_samples:
            continue
        lats = np.array([e.lat for e in evs])
        lons = np.array([e.lon for e in evs])
        t0 = min(e.time for e in evs)
        days = np.array([(e.time - t0).total_seconds() / 86400 for e in evs])
        scale = km_per_day or KM_PER_DAY_BY_CATEGORY.get(category, DEFAULT_KM_PER_DAY)
        features = np.column_stack([to_xyz_km(lats, lons), days * scale])
        labels = DBSCAN(eps=eps_km, min_samples=min_samples).fit_predict(features)

        for label in sorted(set(labels) - {-1}):
            idx = np.flatnonzero(labels == label)
            members = [evs[i] for i in idx]
            clat, clon = mean_lat_lon(lats[idx], lons[idx])
            severities = [m.severity for m in members]
            regions = Counter(m.region for m in members if m.region)
            where = regions.most_common(1)[0][0] if regions else f"{clat:.1f}, {clon:.1f}"
            times = sorted(m.time for m in members)
            mean_sev = float(np.mean(severities))
            clusters.append(
                Cluster(
                    id=f"{category}-{label}",
                    category=category,
                    label=f"{len(members)} {category} events near {where}",
                    size=len(members),
                    lat=clat,
                    lon=clon,
                    radius_km=max(MIN_RADIUS_KM, float(haversine_km(clat, clon, lats[idx], lons[idx]).max())),
                    start=times[0].isoformat(),
                    end=times[-1].isoformat(),
                    mean_severity=round(mean_sev, 3),
                    max_severity=round(max(severities), 3),
                    # log(size) so a 200-event swarm outranks a 5-event one without
                    # drowning out a small cluster of severe events.
                    score=round(mean_sev * float(np.log1p(len(members))), 3),
                    event_ids=tuple(m.id for m in members),
                )
            )
    return sorted(clusters, key=lambda c: -c.score)
