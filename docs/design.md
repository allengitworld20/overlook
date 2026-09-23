# Overlook design

## Problem

Someone who has to track "what is going on in the world" faces many public
feeds, each with its own schema, cadence and level of detail. Reading them one
by one does not answer the questions that matter for a decision: is something
abnormal, which events are really one situation, and what is related to what.

Overlook normalizes several feeds into one event model and layers three
lightweight analyses on top.

## Users and jobs

| User | Job | Where Overlook helps |
|---|---|---|
| Watch-floor analyst | Notice a developing situation early | Volume anomalies, ranked clusters |
| Planner / responder | Understand scope of a situation | Clusters with extent, dates and severity; the map |
| Researcher | Find cross-hazard relationships | Event graph communities across categories |

## Requirements

Functional
- Ingest at least three independent public sources with no API keys.
- One event schema; re-ingesting must not duplicate rows and must pick up revisions.
- Flag unusual daily volume per category.
- Group events that belong to one situation; rank the groups.
- Link related events, including events with no coordinates.
- Browse everything on a map, with filters.

Non-functional
- Runs on a laptop with `pip install`; no external services beyond the feeds.
- One failing source must not stop the others.
- Analysis is explainable: every flag can be traced to a count, a distance or a similarity score.
- Feed text is untrusted: the UI escapes it and only links `http(s)` URLs.

## Data model

`Event(id, source, category, title, summary, time, lat, lon, region, severity, url)`

- `id` is `source:native_id`, the upsert key.
- `severity` is in [0, 1], derived per source (earthquake magnitude, fire acreage on a log scale, wind speed, or a fixed 0.6 for WHO notices, which have no magnitude). **It is comparable within a category only.**
- `lat/lon` are optional. EONET polygons use the ring mean; EONET tracks use their latest fix; WHO uses a country centroid from a title parse.

## Architecture

Ingest (parse + fetch) -> SQLite -> analysis (pure functions over `list[Event]`)
-> FastAPI -> Leaflet UI / CLI. Parsers are pure so they are tested against
recorded payloads without a network; analysis functions take plain event lists so
they are tested with synthetic data.

## Algorithms and why

### Anomaly detection: robust z-score on daily counts

For each category, bucket into daily counts over the window and score each day
by `(count - median) / max(1.4826 * MAD, sqrt(max(median, 1)))`.

- Median/MAD instead of mean/stddev: the spikes we look for would otherwise inflate the baseline that is meant to expose them.
- The `sqrt(median)` floor is a Poisson-style noise estimate. Without it, sparse categories have MAD = 0 and any nonzero day scores infinity.
- A minimum absolute count (3) stops "0 to 1" from being reported.
- Alternatives considered: Isolation Forest (less explainable for a 1-D series), seasonal decomposition (too little history to fit a season).

### Clustering: spatio-temporal DBSCAN, per category

Points are embedded as (x, y, z on the Earth sphere in km, time * km_per_day)
so one Euclidean `eps` covers both space and time. Using 3-D sphere coordinates
avoids dateline and pole problems that raw lat/lon distance has. DBSCAN is used
because the number of clusters is unknown and isolated events should be noise.
Clustering per category keeps each cluster a single kind of situation.

**Parameters were tuned on live data, not guessed.** First defaults
(eps 250 km, min 3) produced a 784-event, 29-day "cluster" covering all of
Alaska: DBSCAN chaining continuous regional seismicity into one blob. Sweeping
eps / time-scale / min_samples on a month of real events (2,484 events):

| eps km | km/day | min | clusters | largest | longest span | largest radius |
|---|---|---|---|---|---|---|
| 250 | 100 | 3 | 98 | 784 | 29 d | 1744 km |
| 100 | 100 | 5 | 40 | 229 | 6 d | 243 km |
| 50 | 50 | 5 | 21 | 228 | 6 d | 113 km |

Chosen: 100 km / min 5. The largest cluster became the 229-event aftershock
sequence of a real M6.3 mainshock. A second sweep on wildfires alone showed that
a fire complex was being split into one cluster per day at 100 km/day, so
non-earthquake categories use 50 km/day (aftershocks decay fast; fires and
outbreaks persist).

Cluster score is `mean_severity * ln(1 + size)`: size matters, but a large
swarm of weak events should not automatically outrank a small cluster of
severe ones. This is a heuristic, not a calibrated risk score.

### Event graph: proximity + text similarity, then communities

- Edge `spatiotemporal`: within 300 km and 3 days; weight falls linearly toward the limits.
- Edge `textual`: TF-IDF cosine >= 0.5 over title + summary. Tokens are letters only, 3+ chars (drops magnitudes and "km"); terms in over half the corpus are dropped so boilerplate does not link everything.
- Communities: greedy modularity on the weighted graph. Hotspots: highest weighted degree.
- Nodes are capped at the 300 most severe events so the pairwise work stays bounded.

Edges ignore category on purpose, so cross-hazard relationships (a storm near a
flood, an outbreak near a quake zone) can appear. In practice they are rare: on
the 2026-09-21 data, 1 of 46 communities mixed categories (a storm with four
earthquakes). Treat such links as candidates for an analyst to check, not as
findings.

## Validation

- 43 unit and API tests: parsers on recorded payloads, geo helpers (including the dateline), upsert idempotence, anomaly/cluster/graph behavior on synthetic data with known answers, API filtering and validation.
- Live-data checks: the clustering and graph analyses independently surfaced the same M6.3 Alaska sequence.
- Bugs found by testing and fixed: the country lookup stripped the en dash before splitting a WHO title, so "Ebola disease caused by Sudan ebolavirus - Uganda" resolved to Sudan; now the tail after the dash is searched first.

## Known limitations

- **No ground truth.** Nobody has labeled which anomalies or clusters matter, so there is no precision/recall. Results are checked by inspection and by agreement between methods.
- Polling, not streaming.
- WHO locations are country-level and the title parse can be wrong for multi-country notices.
- EONET has no place names, so its cluster labels are coordinates. A reverse-geocode step would fix this.
- Earthquakes dominate event volume (about 80% of a typical window), which biases the graph toward seismic sequences.
- Country centroid table is approximate and hand-entered.

## Roadmap

1. Scheduled ingest and an "alerts since last visit" view.
2. Reverse geocoding for EONET labels.
3. More sources (ReliefWeb, GDELT) and a news/OSINT text stream, where the NLP work gets more interesting: entity extraction and event de-duplication.
4. Replace the fixed severity mapping with per-category percentile ranks.
5. Labeled evaluation set: mark historical events an analyst would have wanted flagged and measure recall and false-alarm rate.
