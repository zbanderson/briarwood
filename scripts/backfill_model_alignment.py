"""Stage 4 CLI for recording model confidence-vs-outcome alignment rows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.store import ConversationStore
from briarwood.eval.model_alignment_backfill import (
    DEFAULT_MODULES,
    SAVED_PROPERTIES_DIR,
    backfill_model_alignment,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Stage 4 priority modules for outcome-matched saved properties."
    )
    parser.add_argument("--outcomes", type=Path, required=True)
    parser.add_argument("--saved-properties", type=Path, default=SAVED_PROPERTIES_DIR)
    parser.add_argument(
        "--module",
        action="append",
        choices=DEFAULT_MODULES,
        help="Module to backfill; repeatable. Defaults to all Stage 4 priority modules.",
    )
    parser.add_argument("--db", type=Path, default=None, help="SQLite DB path. Defaults to app DB.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-duplicates", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print full row payloads.")
    args = parser.parse_args(argv)

    store = None
    if not args.dry_run:
        store = ConversationStore(args.db) if args.db is not None else None

    result = backfill_model_alignment(
        outcomes_path=args.outcomes,
        saved_properties_dir=args.saved_properties,
        modules=args.module or list(DEFAULT_MODULES),
        dry_run=args.dry_run,
        store=store,
        allow_duplicates=args.allow_duplicates,
    )
    print(json.dumps(result.to_dict(include_rows=args.json), indent=2, sort_keys=True))
    return 1 if result.error else 0


if __name__ == "__main__":
    sys.exit(main())
