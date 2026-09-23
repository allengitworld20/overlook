from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

CATEGORIES = (
    "earthquake",
    "wildfire",
    "storm",
    "volcano",
    "flood",
    "drought",
    "landslide",
    "disease",
    "other",
)


def parse_iso(value: str) -> datetime:
    """Parse an ISO 8601 timestamp (with optional trailing Z) into an aware UTC datetime."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def from_epoch_ms(ms: int | float) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


@dataclass(frozen=True)
class Event:
    """One normalized event from any source.

    severity is a source-specific magnitude mapped onto [0, 1]. It is only
    comparable within a category, never across sources.
    """

    id: str
    source: str
    category: str
    title: str
    time: datetime
    summary: str = ""
    lat: float | None = None
    lon: float | None = None
    region: str | None = None
    severity: float = 0.3
    url: str = ""

    @property
    def has_location(self) -> bool:
        return self.lat is not None and self.lon is not None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["time"] = self.time.isoformat()
        return d
