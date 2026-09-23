"""Volume anomaly detection on daily event counts.

Method: for each category, bucket events into daily counts over a trailing
window and score each day with a robust z-score,

    score = (count - median) / max(1.4826 * MAD, sqrt(max(median, 1)))

The median/MAD pair is insensitive to the very spikes we are looking for, unlike
mean/stddev. The Poisson-style floor sqrt(median) matters for sparse series
where MAD collapses to 0 and any nonzero day would otherwise score infinity.
A minimum absolute count keeps a jump from 0 to 1 from ever being an "anomaly".
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

import numpy as np

from ..models import Event


@dataclass(frozen=True)
class Anomaly:
    category: str
    date: str
    count: int
    baseline: float
    score: float

    def to_dict(self) -> dict:
        return asdict(self)


def detect_anomalies(
    events: Iterable[Event],
    now: datetime | None = None,
    window_days: int = 30,
    z_threshold: float = 3.5,
    min_count: int = 3,
) -> list[Anomaly]:
    end = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date()
    start = end - timedelta(days=window_days - 1)

    counts: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(window_days))
    for e in events:
        day = e.time.astimezone(timezone.utc).date()
        if start <= day <= end:
            counts[e.category][(day - start).days] += 1

    found = []
    for category, series in counts.items():
        median = float(np.median(series))
        mad = float(np.median(np.abs(series - median)))
        scale = max(1.4826 * mad, np.sqrt(max(median, 1.0)))
        scores = (series - median) / scale
        for i in np.flatnonzero((scores >= z_threshold) & (series >= min_count)):
            found.append(
                Anomaly(
                    category=category,
                    date=(start + timedelta(days=int(i))).isoformat(),
                    count=int(series[i]),
                    baseline=median,
                    score=round(float(scores[i]), 2),
                )
            )
    return sorted(found, key=lambda a: (-a.score, a.date))
