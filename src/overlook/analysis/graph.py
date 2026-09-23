"""Event relationship graph.

Nodes are events. Two kinds of edge connect them:

  spatiotemporal  within `dist_km` and `window_days` of each other
                  (weight falls linearly from 1 to 0 across both limits)
  textual         TF-IDF cosine similarity of title + summary >= `text_threshold`

Communities (greedy modularity) group linked events, and weighted degree
("strength") surfaces the events most connected to everything else. Because
edges ignore category, a wildfire linked to a storm or an outbreak linked to a
nearby quake shows up as a cross-hazard community.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

import networkx as nx
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from ..geo import haversine_km
from ..models import Event

MAX_EDGES_RETURNED = 1500


def _add_edge(g: nx.Graph, a: str, b: str, kind: str, weight: float) -> None:
    if g.has_edge(a, b):
        g[a][b]["kinds"].add(kind)
        g[a][b]["weight"] = max(g[a][b]["weight"], weight)
    else:
        g.add_edge(a, b, kinds={kind}, weight=weight)


def _add_spatiotemporal_edges(g: nx.Graph, events: list[Event], dist_km: float, window_days: float) -> None:
    located = [e for e in events if e.has_location]
    if len(located) < 2:
        return
    lats = np.array([e.lat for e in located])
    lons = np.array([e.lon for e in located])
    days = np.array([e.time.timestamp() / 86400 for e in located])
    for i in range(len(located) - 1):
        dist = haversine_km(lats[i], lons[i], lats[i + 1 :], lons[i + 1 :])
        dt = np.abs(days[i + 1 :] - days[i])
        for j in np.flatnonzero((dist <= dist_km) & (dt <= window_days)):
            weight = 1.0 - 0.5 * dist[j] / dist_km - 0.5 * dt[j] / window_days
            _add_edge(g, located[i].id, located[i + 1 + j].id, "spatiotemporal", float(weight))


def _add_text_edges(g: nx.Graph, events: list[Event], threshold: float) -> None:
    if len(events) < 2:
        return
    docs = [f"{e.title}. {e.summary}" for e in events]
    # Letters only, 3+ chars: drops magnitudes, depths and "km". max_df drops
    # boilerplate shared by most of the corpus (e.g. "magnitude" in a quake-heavy set).
    vectorizer = TfidfVectorizer(
        stop_words="english",
        token_pattern=r"(?u)\b[^\W\d_]{3,}\b",
        max_df=0.5 if len(docs) >= 10 else 1.0,
    )
    try:
        matrix = vectorizer.fit_transform(docs)
    except ValueError:  # every term pruned: nothing to compare
        return
    sim = (matrix @ matrix.T).toarray()
    for i, j in zip(*np.nonzero(np.triu(sim >= threshold, k=1))):
        _add_edge(g, events[i].id, events[j].id, "textual", float(sim[i, j]))


def build_graph(
    events: Iterable[Event],
    max_nodes: int = 300,
    dist_km: float = 300.0,
    window_days: float = 3.0,
    text_threshold: float = 0.5,
) -> dict:
    # Cap by severity (ties by id for determinism) to keep the pairwise work bounded.
    selected = sorted(events, key=lambda e: (-e.severity, e.id))[:max_nodes]
    by_id = {e.id: e for e in selected}
    g = nx.Graph()
    g.add_nodes_from(by_id)
    _add_spatiotemporal_edges(g, selected, dist_km, window_days)
    _add_text_edges(g, selected, text_threshold)

    community_of = {node: -1 for node in g}
    if g.number_of_edges():
        groups = nx.community.greedy_modularity_communities(g, weight="weight")
        groups = sorted((sorted(grp) for grp in groups if len(grp) >= 2), key=lambda grp: (-len(grp), grp[0]))
        for cid, grp in enumerate(groups):
            for node in grp:
                community_of[node] = cid
    else:
        groups = []

    strength = dict(g.degree(weight="weight"))
    betweenness = nx.betweenness_centrality(g) if g.number_of_edges() else {n: 0.0 for n in g}

    nodes = [
        {
            "id": n,
            "title": by_id[n].title,
            "category": by_id[n].category,
            "lat": by_id[n].lat,
            "lon": by_id[n].lon,
            "community": community_of[n],
            "degree": g.degree(n),
            "strength": round(strength[n], 3),
            "betweenness": round(betweenness[n], 4),
        }
        for n in g
    ]
    edges = sorted(
        (
            {"source": a, "target": b, "type": "+".join(sorted(d["kinds"])), "weight": round(d["weight"], 3)}
            for a, b, d in g.edges(data=True)
        ),
        key=lambda e: -e["weight"],
    )[:MAX_EDGES_RETURNED]
    communities = [
        {
            "id": cid,
            "size": len(grp),
            "categories": dict(Counter(by_id[n].category for n in grp)),
            "top_event": max(grp, key=lambda n: strength[n]),
        }
        for cid, grp in enumerate(groups)
    ]
    hotspots = sorted((n for n in nodes if n["degree"] > 0), key=lambda n: -n["strength"])[:10]
    return {
        "nodes": nodes,
        "edges": edges,
        "communities": communities,
        "hotspots": hotspots,
        "stats": {"nodes": g.number_of_nodes(), "edges": g.number_of_edges(), "communities": len(groups)},
    }
