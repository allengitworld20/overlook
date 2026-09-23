from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

import numpy as np

from .countries import ALIASES, CENTROIDS

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km. Accepts scalars or numpy arrays (broadcasting)."""
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(v, dtype=float)) for v in (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def to_xyz_km(lats, lons) -> np.ndarray:
    """Project lat/lon (degrees) onto a sphere of Earth radius; returns an (n, 3) array in km.

    Euclidean distance between these points is the chord length, which tracks
    great-circle distance closely for the short ranges we cluster over and has no
    dateline or pole discontinuities.
    """
    lat = np.radians(np.asarray(lats, dtype=float))
    lon = np.radians(np.asarray(lons, dtype=float))
    return EARTH_RADIUS_KM * np.column_stack(
        [np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)]
    )


def mean_lat_lon(lats, lons) -> tuple[float, float]:
    """Centroid of points on a sphere (safe across the dateline)."""
    x, y, z = to_xyz_km(lats, lons).mean(axis=0)
    return float(np.degrees(np.arctan2(z, np.hypot(x, y)))), float(np.degrees(np.arctan2(y, x)))


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return text.lower().replace("’", "'")


@lru_cache(maxsize=1)
def _country_index() -> tuple[re.Pattern[str], dict[str, str]]:
    names = {_normalize(c): c for c in CENTROIDS}
    names.update({_normalize(a): c for a, c in ALIASES.items()})
    # Longest first so "Papua New Guinea" wins over "Guinea" at the same position.
    ordered = sorted(names, key=len, reverse=True)
    pattern = re.compile(r"(?<!\w)(" + "|".join(re.escape(n) for n in ordered) + r")(?!\w)")
    return pattern, names


def find_country(text: str) -> tuple[str, float, float] | None:
    """Return (canonical country, lat, lon) for the first country named in text, else None.

    WHO titles follow "Disease - Country", so the segment after the last dash is
    searched before the whole title.
    """
    pattern, names = _country_index()
    # Split before normalizing: normalization drops non-ASCII, which includes the en dash.
    tail = re.split(r"\s[-–—]\s", text)[-1]
    for candidate in (_normalize(tail), _normalize(text)):
        m = pattern.search(candidate)
        if m:
            country = names[m.group(1)]
            lat, lon = CENTROIDS[country]
            return country, lat, lon
    return None
