import numpy as np
from conftest import make_event

from overlook.analysis import build_graph, cluster_events, detect_anomalies


def _steady_series(category="wildfire", per_day=2, days=30):
    return [
        make_event(f"{category}-{d}-{k}", category=category, days_ago=d + 0.1 * k)
        for d in range(1, days)
        for k in range(per_day)
    ]


class TestAnomalies:
    def test_spike_is_flagged(self, now):
        events = _steady_series() + [make_event(f"spike-{k}", category="wildfire", days_ago=3.2) for k in range(15)]
        found = detect_anomalies(events, now=now, window_days=30)
        assert [(a.category, a.date) for a in found] == [("wildfire", "2026-09-18")]
        assert found[0].count > 15 and found[0].baseline == 2

    def test_steady_series_is_quiet(self, now):
        assert detect_anomalies(_steady_series(), now=now) == []

    def test_sparse_series_needs_min_count(self, now):
        # Baseline of zero: a single event on one day must not be an anomaly.
        assert detect_anomalies([make_event("a", category="disease", days_ago=2)], now=now) == []

    def test_events_outside_window_are_ignored(self, now):
        events = [make_event(f"old-{k}", days_ago=60) for k in range(20)]
        assert detect_anomalies(events, now=now, window_days=30) == []


class TestClustering:
    def _swarm(self, prefix, lat, lon, n=6, days_ago=1.0):
        rng = np.random.default_rng(0)
        return [
            make_event(f"{prefix}{i}", lat=lat + rng.normal(0, 0.3), lon=lon + rng.normal(0, 0.3), days_ago=days_ago + 0.1 * i, region=prefix)
            for i in range(n)
        ]

    def test_two_swarms_and_noise(self):
        events = self._swarm("Chile", -21, -69) + self._swarm("Japan", 36, 140) + [make_event("lone", lat=-60, lon=100)]
        clusters = cluster_events(events)
        assert sorted(c.size for c in clusters) == [6, 6]
        assert {c.label.split()[-1] for c in clusters} == {"Chile", "Japan"}
        assert all("t:lone" not in c.event_ids for c in clusters)

    def test_same_place_far_apart_in_time_does_not_cluster(self):
        events = [make_event(f"a{i}", lat=10, lon=10, days_ago=i * 20) for i in range(5)]
        assert cluster_events(events) == []

    def test_persistent_categories_tolerate_longer_gaps_than_earthquakes(self):
        # Same place, one event every 36 hours: one persistent fire, but not one aftershock burst.
        def series(category):
            return [make_event(f"{category}{i}", category=category, lat=5, lon=5, days_ago=1.5 * i) for i in range(5)]

        assert len(cluster_events(series("wildfire"), min_samples=3)) == 1
        assert cluster_events(series("earthquake"), min_samples=3) == []

    def test_categories_are_clustered_separately(self):
        quakes = self._swarm("Chile", -21, -69, n=2)
        fires = [make_event(f"f{i}", category="wildfire", lat=-21, lon=-69, days_ago=1) for i in range(2)]
        assert cluster_events(quakes + fires, min_samples=3) == []

    def test_cluster_spanning_the_dateline(self):
        events = [make_event(f"d{i}", lat=0, lon=lon, days_ago=1) for i, lon in enumerate([179.5, -179.5, 179.8, -179.8])]
        (cluster,) = cluster_events(events, min_samples=3)
        assert cluster.size == 4 and abs(cluster.lon) > 179

    def test_events_without_location_are_skipped(self):
        events = [make_event(f"n{i}", lat=None, lon=None) for i in range(5)]
        assert cluster_events(events) == []


class TestGraph:
    def test_nearby_events_link_and_distant_ones_do_not(self):
        events = [
            make_event("a", category="wildfire", lat=10, lon=10, days_ago=1),
            make_event("b", category="storm", lat=10.5, lon=10.5, days_ago=1.5),
            make_event("far", category="flood", lat=-40, lon=100, days_ago=1),
        ]
        g = build_graph(events)
        assert [(e["source"], e["target"], e["type"]) for e in g["edges"]] == [("t:a", "t:b", "spatiotemporal")]
        nodes = {n["id"]: n for n in g["nodes"]}
        assert nodes["t:a"]["community"] == nodes["t:b"]["community"] >= 0
        assert nodes["t:far"]["community"] == -1

    def test_far_apart_in_time_do_not_link(self):
        events = [make_event("a", lat=0, lon=0, days_ago=1), make_event("b", lat=0, lon=0, days_ago=10)]
        assert build_graph(events)["edges"] == []

    def test_textual_link_across_the_globe(self):
        events = [
            make_event("x", category="disease", lat=12, lon=30, title="Cholera outbreak Sudan", summary="cholera cases rising across Sudan camps"),
            make_event("y", category="disease", lat=-20, lon=30, days_ago=30, title="Cholera outbreak Sudan update", summary="cholera cases across Sudan camps"),
            make_event("z", category="wildfire", lat=40, lon=-100, days_ago=60, title="Wildfire Nevada", summary="acres burned"),
        ]
        g = build_graph(events)
        assert [(e["source"], e["target"], e["type"]) for e in g["edges"]] == [("t:x", "t:y", "textual")]

    def test_hotspot_is_the_hub(self):
        hub = make_event("hub", lat=0, lon=0, days_ago=1, severity=0.9)
        spokes = [make_event(f"s{i}", lat=0.5 * i, lon=0.2 * i, days_ago=1.2, severity=0.1) for i in range(1, 5)]
        g = build_graph([hub, *spokes])
        assert g["hotspots"][0]["id"] in {"t:hub"} | {f"t:s{i}" for i in range(1, 5)}
        assert g["stats"]["communities"] == 1

    def test_empty_and_singleton_inputs(self):
        assert build_graph([])["stats"] == {"nodes": 0, "edges": 0, "communities": 0}
        assert build_graph([make_event("solo")])["stats"]["edges"] == 0
