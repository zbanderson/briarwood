"""Dry-run loader for Stage 4 ground-truth outcome files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from briarwood.eval.outcomes import load_outcomes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a Stage 4 outcome file.")
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="omit valid records from the JSON output",
    )
    args = parser.parse_args(argv)

    result = load_outcomes(args.path)
    payload = result.to_summary()
    if args.summary_only:
        payload.pop("records", None)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
