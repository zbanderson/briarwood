from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from briarwood.data_sources.api_strategy import BATCH_ENDPOINTS, CONDITIONAL_ENDPOINTS, CORE_ENDPOINTS
from briarwood.data_sources.attom_client import ENDPOINT_FIELD_MAP
from briarwood.data_sources.nj_tax_intelligence import NJTaxIntelligenceStore
from scripts.audit_comp_store import audit_store
from scripts.backfill_comp_store import backfill_store


def build_report(
    *,
    comp_store_path: Path,
    tax_csv_path: Path | None = None,
    backfill_max_calls: int = 0,
) -> dict[str, Any]:
    comp_audit = audit_store(comp_store_path)
    backfill = backfill_store(comp_store_path, dry_run=True, max_calls=backfill_max_calls) if backfill_max_calls > 0 else None
    nj_rows = 0
    nj_sources: list[str] = []
    if tax_csv_path is not None and tax_csv_path.exists():
        store = NJTaxIntelligenceStore.load_csv(tax_csv_path)
        nj_rows = len(store.rows)
        nj_sources.append(str(tax_csv_path))

    report = {
        "attom_current_usage": [
            "property detail enrichment",
            "assessment/tax enrichment",
            "sale-history fallback",
            "rental AVM for missing-rent backfill",
            "permits and town snapshot support",
        ],
        "attom_supported_endpoints": {
            "core": list(CORE_ENDPOINTS),
            "conditional": list(CONDITIONAL_ENDPOINTS),
            "batch": list(BATCH_ENDPOINTS),
        },
        "attom_capability_summary": {
            endpoint: {
                "fields_extracted": list(ENDPOINT_FIELD_MAP.get(endpoint, ())),
            }
            for endpoint in list(CORE_ENDPOINTS) + list(CONDITIONAL_ENDPOINTS) + list(BATCH_ENDPOINTS)
        },
        "comp_store_quality": {
            "record_count": comp_audit["record_count"],
            "eligibility_summary": comp_audit["comp_eligibility_summary"],
            "gate_summary": comp_audit.get("comp_eligibility_gate_summary", {}),
            "issue_summary": comp_audit["counts_by_issue_type"],
            "auto_fixable_count": len(comp_audit.get("auto_fixable_records", [])),
            "records_cleaned_or_normalized": len(comp_audit.get("auto_fixable_records", [])),
            "records_rejected": len(comp_audit.get("rejected_records", [])),
            "records_retained": comp_audit["record_count"] - len(comp_audit.get("rejected_records", [])),
        },
        "fill_rate_before_after": None if backfill is None else {
            "before": backfill["fill_rate_before"],
            "after": backfill["fill_rate_after"],
            "improvement": backfill["fill_rate_improvement"],
            "fill_counts_by_field": backfill["fill_counts_by_field"],
            "endpoint_fill_counts": backfill["endpoint_fill_counts"],
            "failures_by_reason": backfill["failures_by_reason"],
            "cache_hit_rate_by_endpoint": backfill["cache_hit_rate_by_endpoint"],
        },
        "nj_data_sources_integrated": {
            "sources": nj_sources,
            "row_count": nj_rows,
            "capabilities": [
                "municipality general tax rates",
                "municipality effective tax rates",
                "equalization ratio context",
                "equalized valuation context",
                "parcel identity context loader support",
            ],
        },
        "provenance_arbitration_status": {
            "field_groups": ["identity", "structural", "sale", "tax", "rent"],
            "field_specific_policy": True,
            "conflict_detection": [
                "sqft >15%",
                "beds/baths mismatch",
                "town mismatch",
                "sale price/date mismatch",
                "tax amount conflict",
            ],
        },
        "comp_eligibility_distribution": comp_audit.get("comp_eligibility_gate_summary", {}),
        "remaining_top_issues": sorted(
            comp_audit["counts_by_issue_type"].items(),
            key=lambda item: item[1],
            reverse=True,
        )[:10],
        "top_next_actions": _top_next_actions(comp_audit=comp_audit, backfill=backfill),
    }
    report["human_summary"] = _human_summary(report)
    return report


def _top_next_actions(*, comp_audit: dict[str, Any], backfill: dict[str, Any] | None) -> list[str]:
    actions: list[str] = []
    rejected = len(comp_audit.get("rejected_records", []))
    review = len(comp_audit.get("needs_review_records", []))
    autofix = len(comp_audit.get("auto_fixable_records", []))
    if rejected:
        actions.append(f"Remove or quarantine {rejected} rejected comp records before any valuation refresh.")
    if review:
        actions.append(f"Resolve identity or structural conflicts on {review} reviewable records to improve comp trust.")
    if autofix:
        actions.append(f"Run cleanup autofixes on {autofix} records before spending ATTOM calls.")
    if backfill is not None:
        strongest = sorted(
            backfill["fill_rate_improvement"].items(),
            key=lambda item: item[1],
            reverse=True,
        )[:3]
        nonzero = [f"{field} (+{improvement:.0%})" for field, improvement in strongest if improvement > 0]
        if nonzero:
            actions.append("Prioritize ATTOM backfill for: " + ", ".join(nonzero) + ".")
    if not actions:
        actions.append("Current store quality is stable; next focus should be batch town snapshots for the Markets tab.")
    return actions


def _human_summary(report: dict[str, Any]) -> str:
    lines = ["Briarwood Property Intelligence Audit"]
    lines.append("ATTOM endpoints: " + ", ".join(report["attom_supported_endpoints"]["core"] + report["attom_supported_endpoints"]["conditional"] + report["attom_supported_endpoints"]["batch"]))
    comp_quality = report["comp_store_quality"]
    lines.append(
        "Comp store quality: "
        + ", ".join(f"{key}={value}" for key, value in sorted(comp_quality["eligibility_summary"].items()))
    )
    if report["fill_rate_before_after"] is not None:
        lines.append("Backfill modeled for fields: " + ", ".join(field for field, value in report["fill_rate_before_after"]["improvement"].items() if value > 0))
    nj_data = report["nj_data_sources_integrated"]
    lines.append(f"NJ tax sources integrated: {nj_data['row_count']} normalized rows.")
    lines.append("Next actions: " + " ".join(report["top_next_actions"]))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Briarwood property-intelligence audit report.")
    parser.add_argument("comp_store_path", help="Path to sales_comps.json or active_listings.json")
    parser.add_argument("--tax-csv", default=None, help="Optional NJ tax intelligence CSV path.")
    parser.add_argument("--backfill-max-calls", type=int, default=0, help="Optional dry-run backfill budget.")
    args = parser.parse_args()
    report = build_report(
        comp_store_path=Path(args.comp_store_path),
        tax_csv_path=Path(args.tax_csv) if args.tax_csv else None,
        backfill_max_calls=args.backfill_max_calls,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
