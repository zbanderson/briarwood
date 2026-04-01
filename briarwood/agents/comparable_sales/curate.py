from __future__ import annotations

import argparse
import json
from pathlib import Path

from briarwood.agents.comparable_sales.schemas import ComparableSale
from briarwood.agents.comparable_sales.store import JsonComparableSalesStore


DEFAULT_TEMPLATE = {
    "address": "123 Example Street",
    "town": "Belmar",
    "state": "NJ",
    "property_type": "Single Family Residence",
    "architectural_style": "Colonial",
    "condition_profile": "maintained",
    "capex_lane": "moderate",
    "sale_price": 650000,
    "sale_date": "2025-06-15",
    "source_name": "manual local comp review",
    "source_quality": "seeded",
    "source_ref": "BELMAR-MANUAL-001",
    "source_notes": "Fill with county record ref, listing note, or broker rationale.",
    "reviewed_at": "2026-03-29",
    "comp_status": "seeded",
    "address_verification_status": "verified",
    "sale_verification_status": "seeded",
    "verification_source_type": "manual_review",
    "verification_source_name": "manual local comp review",
    "verification_source_id": "BELMAR-MANUAL-001",
    "last_verified_by": "analyst",
    "last_verified_at": "2026-03-29",
    "verification_notes": "Address confirmed; sale record not yet tied to county export.",
    "beds": 3,
    "baths": 2.0,
    "sqft": 1400,
    "lot_size": 0.1,
    "year_built": 1930,
    "stories": 2.0,
    "garage_spaces": 1,
    "location_tags": ["downtown", "beach"],
    "micro_location_notes": ["Similar walkability profile to subject."]
}


def write_template(output_path: str | Path) -> None:
    Path(output_path).write_text(json.dumps(DEFAULT_TEMPLATE, indent=2) + "\n")


def append_comp(*, comps_path: str | Path, input_path: str | Path) -> ComparableSale:
    payload = json.loads(Path(input_path).read_text())
    comp = ComparableSale.model_validate(payload)
    store = JsonComparableSalesStore(comps_path)
    store.append(comp)
    return comp


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or append manual Briarwood comp records.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    template_parser = subparsers.add_parser("new-template", help="Write a starter comp JSON template.")
    template_parser.add_argument("--output", required=True)

    append_parser = subparsers.add_parser("append", help="Append a validated comp JSON row to the dataset.")
    append_parser.add_argument("--input", required=True, help="Path to a comp JSON file.")
    append_parser.add_argument("--comps", default="data/comps/sales_comps.json", help="Comparable-sales JSON file.")

    args = parser.parse_args()
    if args.command == "new-template":
        write_template(args.output)
        print(f"Wrote comp template to {args.output}")
        return 0

    comp = append_comp(comps_path=args.comps, input_path=args.input)
    print(f"Appended comp {comp.address} ({comp.town}, {comp.state}) to {args.comps}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
