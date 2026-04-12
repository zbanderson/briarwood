from __future__ import annotations

import argparse
import json

from briarwood.local_intelligence import LocalIntelligenceService


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Briarwood Town Pulse for a town/state.")
    parser.add_argument("town", help="Town name, e.g. 'Avon by the Sea'")
    parser.add_argument("--state", default="NJ", help="State abbreviation")
    parser.add_argument("--json", action="store_true", help="Print full JSON payload")
    args = parser.parse_args()

    run = LocalIntelligenceService().analyze(
        town=args.town,
        state=args.state.upper(),
        raw_documents=[],
    )
    if args.json:
        print(run.model_dump_json(indent=2))
        return 0

    print(f"Town Pulse: {run.town}, {run.state}")
    print(f"Confidence: {run.summary.confidence_label}")
    print(f"Narrative: {run.summary.narrative_summary}")
    print(f"Documents: {len(run.documents)}")
    print(f"Signals: {len(run.signals)}")
    if run.warnings:
        print("Warnings:")
        for warning in run.warnings:
            print(f"- {warning}")
    if run.summary.bullish_signals:
        print("Bullish:")
        for item in run.summary.bullish_signals:
            print(f"- {item}")
    if run.summary.bearish_signals:
        print("Bearish:")
        for item in run.summary.bearish_signals:
            print(f"- {item}")
    if run.summary.watch_items:
        print("Watch:")
        for item in run.summary.watch_items:
            print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
