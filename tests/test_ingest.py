import httpx
import pytest

from overlook import db
from overlook.ingest import eonet, ingest_all, usgs, who

USGS_PAYLOAD = {
    "features": [
        {
            "id": "us1",
            "properties": {
                "mag": 5.0, "place": "76 km W of Ollague, Chile", "time": 1789993025292, "url": "https://x/us1",
                "type": "earthquake", "magType": "mb", "tsunami": 0, "title": "M 5.0 - 76 km W of Ollague, Chile",
            },
            "geometry": {"type": "Point", "coordinates": [-68.99, -21.26, 121.2]},
        },
        {  # quarry blast: not an earthquake
            "id": "us2",
            "properties": {"mag": 3.0, "place": "Somewhere, CA", "time": 1789993025292, "type": "quarry blast"},
            "geometry": {"type": "Point", "coordinates": [-120.0, 35.0, 1.0]},
        },
    ]
}

EONET_PAYLOAD = {
    "events": [
        {
            "id": "EONET_1", "title": "Wildfire Breezy, Texas", "description": "7 miles NE",
            "link": "https://eonet/1", "categories": [{"id": "wildfires"}],
            "sources": [{"id": "IRWIN", "url": "https://irwin/1"}],
            "geometry": [
                {"date": "2026-09-10T00:00:00Z", "type": "Point", "coordinates": [-98.0, 26.0], "magnitudeValue": 10, "magnitudeUnit": "acres"},
                {"date": "2026-09-16T20:17:00Z", "type": "Point", "coordinates": [-98.7, 26.4], "magnitudeValue": 500.0, "magnitudeUnit": "acres"},
            ],
        },
        {
            "id": "EONET_2", "title": "Iceberg A23", "categories": [{"id": "seaLakeIce"}],
            "geometry": [{"date": "2026-09-10T00:00:00Z", "type": "Point", "coordinates": [0, -60]}],
        },
        {
            "id": "EONET_3", "title": "Flood region", "categories": [{"id": "floods"}],
            "geometry": [{"date": "2026-09-12T00:00:00Z", "type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]}],
        },
    ]
}

WHO_PAYLOAD = {
    "value": [
        {
            "Id": "abc", "Title": "Cholera – Sudan", "UseOverrideTitle": False, "OverrideTitle": "",
            "PublicationDateAndTime": "2026-09-01T00:00:00Z", "ItemDefaultUrl": "/2026-DON999",
            "Summary": "", "Overview": "<p>Cases <b>rose</b> &amp; spread.</p>",
        },
        {"Id": "def", "Title": "", "PublicationDateAndTime": "2026-09-01T00:00:00Z"},  # untitled: skipped
    ]
}


def test_usgs_parse():
    (ev,) = usgs.parse(USGS_PAYLOAD)
    assert ev.id == "usgs:us1" and ev.category == "earthquake"
    assert (ev.lat, ev.lon) == (-21.26, -68.99)
    assert ev.region == "Chile"
    assert ev.severity == pytest.approx(0.5)
    assert "depth 121 km" in ev.summary


def test_eonet_parse_uses_latest_fix_and_skips_ice():
    events = {e.id: e for e in eonet.parse(EONET_PAYLOAD)}
    assert set(events) == {"eonet:EONET_1", "eonet:EONET_3"}
    fire = events["eonet:EONET_1"]
    assert (fire.lat, fire.lon) == (26.4, -98.7)
    assert fire.category == "wildfire" and fire.url == "https://irwin/1"
    assert 0 < fire.severity < 1
    flood = events["eonet:EONET_3"]
    assert (flood.lat, flood.lon) == pytest.approx((0.8, 0.8))  # mean of the 5 ring points, closing point included


def test_who_parse_geocodes_and_cleans_html():
    (ev,) = who.parse(WHO_PAYLOAD)
    assert ev.region == "Sudan" and ev.has_location
    assert ev.summary == "Cases rose & spread."
    assert ev.url.endswith("/item/2026-DON999")


def test_ingest_all_isolates_failing_source(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if "usgs.gov" in request.url.host:
            return httpx.Response(200, json=USGS_PAYLOAD)
        if "eonet" in request.url.host:
            return httpx.Response(500)
        return httpx.Response(200, json=WHO_PAYLOAD)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with db.connect(tmp_path / "t.db") as conn:
        # Fixture timestamps are in the past, so the cutoff filter needs a wide window.
        results = ingest_all(conn, days=3650, who_days=3650, client=client)
        stored = db.status(conn)
    assert results["usgs"] == 1
    assert results["who"] == 1
    assert str(results["eonet"]).startswith("error:")
    assert stored["event_count"] == 2
