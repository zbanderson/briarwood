"""CLI entry point for the minutes freshness runner.

Example usage:

    python -m scripts.refresh_minutes                       # refresh all stale feeds
    python -m scripts.refresh_minutes --dry-run             # discover only, no writes
    python -m scripts.refresh_minutes --slug avon-by-the-sea-nj-planning-board
    python -m scripts.refresh_minutes --force               # re-scan even if fresh

A cron/ScheduleWakeup job can invoke this periodically; interactive runs are
fine too — the runner is idempotent.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from briarwood.local_intelligence.minutes_runner import run_refresh


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refresh per-town published-minutes manifests.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run discovery only; don't fetch documents or write to disk.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore staleness TTLs and re-scan every matching feed.",
    )
    parser.add_argument(
        "--slug",
        action="append",
        default=None,
        help="Only refresh feeds with this slug. May be passed multiple times.",
    )
    parser.add_argument(
        "--polite-delay",
        type=float,
        default=0.0,
        help="Seconds to sleep between document fetches (be kind to town CMSes).",
    )
    parser.add_argument(
        "--max-feeds",
        type=int,
        default=None,
        help="Cap how many eligible feeds this run processes (for chunking at scale).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the report as JSON instead of a human-readable summary.",
    )
    args = parser.parse_args(argv)

    report = run_refresh(
        dry_run=args.dry_run,
        force=args.force,
        slug_filter=set(args.slug) if args.slug else None,
        polite_delay_seconds=args.polite_delay,
        max_feeds=args.max_feeds,
    )

    if args.json:
        payload = {
            "started_at": report.started_at,
            "finished_at": report.finished_at,
            "total_fetched": report.total_fetched,
            "total_failed": report.total_failed,
            "results": [asdict(r) for r in report.results],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(
        f"Minutes refresh: started {report.started_at}  "
        f"fetched={report.total_fetched}  failed={report.total_failed}"
    )
    for r in report.results:
        status = "skipped" if r.skipped_reason else "checked"
        print(
            f"  {r.slug}  [{status}]  "
            f"stale={r.stale_before}  missing={len(r.missing_before)}  "
            f"fetched={len(r.fetched_months)}  failed={len(r.failed_months)}"
        )
        if r.error:
            print(f"    error: {r.error.strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
