from datetime import datetime, timedelta, timezone

import pytest

from overlook.models import Event

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def make_event(i="1", category="earthquake", lat=0.0, lon=0.0, days_ago=0.0, severity=0.3, title=None, summary="", region=None):
    return Event(
        id=f"t:{i}",
        source="t",
        category=category,
        # No word tokens by default, so unrelated fixtures never look textually similar.
        title=title or f"#{i}",
        summary=summary,
        time=NOW - timedelta(days=days_ago),
        lat=lat,
        lon=lon,
        region=region,
        severity=severity,
    )


@pytest.fixture
def now():
    return NOW
