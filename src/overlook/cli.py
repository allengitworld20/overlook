from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from . import db
from .analysis import build_graph, cluster_events, detect_anomalies
from .ingest import ingest_all


def _cmd_ingest(args: argparse.Namespace) -> int:
    with db.connect(args.db) as conn:
        results = ingest_all(conn, days=args.days, who_days=args.who_days)
    failed = False
    for source, result in results.items():
        print(f"{source:6} {result}")
        failed |= isinstance(result, str)
    return 1 if failed else 0


def _cmd_report(args: argparse.Namespace) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    with db.connect(args.db) as conn:
        events = db.query_events(conn, since=since)
    print(f"{len(events)} events in the last {args.days} days\n")

    print("Anomalies (daily volume vs. baseline)")
    anomalies = detect_anomalies(events, window_days=max(args.days, 7))
    for a in anomalies[:10]:
        print(f"  {a.date}  {a.category:10} {a.count:4} events (baseline {a.baseline:.0f}, score {a.score})")
    if not anomalies:
        print("  none")

    print("\nTop clusters")
    for c in cluster_events(events)[:10]:
        print(f"  {c.score:5.2f}  {c.label}  ({c.start[:10]} to {c.end[:10]})")

    print("\nMost connected events")
    for n in build_graph(events)["hotspots"][:10]:
        print(f"  {n['strength']:6.2f}  [{n['category']}] {n['title']}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .api import create_app

    uvicorn.run(create_app(args.db), host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="overlook", description=__doc__)
    parser.add_argument("--db", help="SQLite path (default: $OVERLOOK_DB or data/overlook.db)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="pull all sources into the database")
    p.add_argument("--days", type=int, default=30, help="lookback for USGS and EONET")
    p.add_argument("--who-days", type=int, default=90, help="lookback for WHO notices (they are infrequent)")
    p.set_defaults(func=_cmd_ingest)

    p = sub.add_parser("report", help="print anomalies, clusters and hotspots")
    p.add_argument("--days", type=int, default=30)
    p.set_defaults(func=_cmd_report)

    p = sub.add_parser("serve", help="run the API and map UI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
