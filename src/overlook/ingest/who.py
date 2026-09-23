"""WHO Disease Outbreak News (https://www.who.int/emergencies/disease-outbreak-news)."""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone

import httpx

from ..geo import find_country
from ..models import Event, parse_iso

API_URL = "https://www.who.int/api/news/diseaseoutbreaknews"
ITEM_URL = "https://www.who.int/emergencies/disease-outbreak-news/item"
SUMMARY_CHARS = 600
# A WHO notice means officials judged the outbreak notable; there is no per-item magnitude.
DEFAULT_SEVERITY = 0.6


def _strip_html(raw: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse(payload: dict) -> list[Event]:
    events = []
    for item in payload["value"]:
        title = (item.get("OverrideTitle") if item.get("UseOverrideTitle") else None) or item.get("Title") or ""
        title = _strip_html(title)
        if not title or not item.get("PublicationDateAndTime"):
            continue
        body = _strip_html(item.get("Summary")) or _strip_html(item.get("Overview"))
        found = find_country(title)
        events.append(
            Event(
                id=f"who:{item['Id']}",
                source="who",
                category="disease",
                title=title,
                summary=body[:SUMMARY_CHARS],
                time=parse_iso(item["PublicationDateAndTime"]),
                lat=found[1] if found else None,
                lon=found[2] if found else None,
                region=found[0] if found else None,
                severity=DEFAULT_SEVERITY,
                url=f"{ITEM_URL}{item['ItemDefaultUrl']}" if item.get("ItemDefaultUrl") else "",
            )
        )
    return events


def fetch(client: httpx.Client, days: int = 90) -> list[Event]:
    resp = client.get(API_URL, params={"$orderby": "PublicationDateAndTime desc", "$top": 100})
    resp.raise_for_status()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return [e for e in parse(resp.json()) if e.time >= cutoff]
