from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from briarwood.data_quality.cleanup import cleanup_records, delete_junk_records
from briarwood.data_quality.eligibility import classify_comp_eligibility
from briarwood.data_quality.pipeline import DataQualityPipeline


def audit_store(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text())
    key = "sales" if "sales" in payload else "listings"
    records = [row for row in payload.get(key, []) if isinstance(row, dict)]
    pipeline = DataQualityPipeline()
    cleaned, cleanup_actions = cleanup_records(records)
    kept, delete_actions = delete_junk_records(cleaned, pipeline=pipeline)
    pipeline_results = [pipeline.run(record, record_type="sale" if record.get("sale_date") or record.get("sale_price") else "listing") for record in kept]
    validated = [(result.normalized_record, result.status, result.issues) for result in pipeline_results]

    issue_counts: Counter[str] = Counter()
    issue_records: dict[str, list[dict[str, str]]] = {}
    rejected_records: list[dict[str, str]] = []
    needs_review_records: list[dict[str, str]] = []
    accepted_with_warnings_records: list[dict[str, str]] = []
    accepted_records: list[dict[str, str]] = []
    auto_fixable_records: list[dict[str, object]] = []
    eligibility_summary: Counter[str] = Counter()
    comp_gate_summary: Counter[str] = Counter()
    suggested_actions: Counter[str] = Counter()
    reviewed_records: list[dict[str, object]] = []
    missing_core_fields: Counter[str] = Counter()

    for result in pipeline_results:
        record = result.normalized_record
        status = result.status
        issues = result.issues
        gate = classify_comp_eligibility(result.evidence_profile)
        eligibility_summary[status] += 1
        comp_gate_summary[gate.status] += 1
        for issue in issues:
            issue_counts[issue.code] += 1
            issue_records.setdefault(
                issue.code,
                [],
            ).append(
                {
                    "id": str(record.get("source_ref") or record.get("address") or "unknown"),
                    "address": str(record.get("address") or "Unknown"),
                }
            )
            if issue.suggested_fix:
                suggested_actions[issue.suggested_fix] += 1
        for field_name in ("beds", "baths", "sqft", "year_built", "lot_size", "latitude", "longitude", "tax_amount", "last_sale_price", "last_sale_date"):
            if record.get(field_name) in (None, "", [], {}):
                missing_core_fields[field_name] += 1
        reviewed_records.append(
            {
                "id": str(record.get("source_ref") or record.get("address") or "unknown"),
                "address": str(record.get("address") or "Unknown"),
                "status": status,
                "comp_eligibility_gate": gate.status,
                "issues": [issue.code for issue in issues],
                "summary_flags": dict(result.evidence_profile.summary_flags) if result.evidence_profile is not None else {},
                "rejection_reason": result.rejection_reason,
                "core_missing_fields": [field_name for field_name in ("beds", "baths", "sqft", "year_built", "lot_size", "latitude", "longitude", "tax_amount", "last_sale_price", "last_sale_date") if record.get(field_name) in (None, "", [], {})],
                "auto_fixable": sorted({issue.suggested_fix for issue in issues if issue.suggested_fix}),
            }
        )
        if any(issue.suggested_fix for issue in issues):
            auto_fixable_records.append(
                {
                    "id": str(record.get("source_ref") or record.get("address") or "unknown"),
                    "address": str(record.get("address") or "Unknown"),
                    "suggested_fixes": sorted({issue.suggested_fix for issue in issues if issue.suggested_fix}),
                }
            )
        if status == "rejected":
            rejected_records.append(
                {
                    "id": str(record.get("source_ref") or record.get("address") or "unknown"),
                    "address": str(record.get("address") or "Unknown"),
                }
            )
        elif status == "needs_review":
            needs_review_records.append({"id": str(record.get("source_ref") or record.get("address") or "unknown"), "address": str(record.get("address") or "Unknown")})
        elif status == "accepted_with_warnings":
            accepted_with_warnings_records.append({"id": str(record.get("source_ref") or record.get("address") or "unknown"), "address": str(record.get("address") or "Unknown")})
        elif status == "accepted":
            accepted_records.append({"id": str(record.get("source_ref") or record.get("address") or "unknown"), "address": str(record.get("address") or "Unknown")})

    for action in cleanup_actions + delete_actions:
        for note in action.notes:
            suggested_actions[note] += 1
    for action in delete_actions:
        rejected_records.append(
            {
                "id": action.record_id,
                "address": str(action.before.get("address") or "Unknown"),
            }
        )
        eligibility_summary["rejected"] += 1

    return {
        "path": str(path),
        "record_count": len(records),
        "counts_by_issue_type": dict(issue_counts),
        "records_by_issue_type": issue_records,
        "rejected_records": rejected_records,
        "needs_review_records": needs_review_records,
        "accepted_with_warnings_records": accepted_with_warnings_records,
        "accepted_records": accepted_records,
        "auto_fixable_records": auto_fixable_records,
        "suggested_fix_actions": dict(suggested_actions),
        "comp_eligibility_summary": dict(eligibility_summary),
        "comp_eligibility_gate_summary": dict(comp_gate_summary),
        "missing_core_fields_summary": dict(missing_core_fields),
        "records": reviewed_records,
        "human_summary": _human_summary(path, eligibility_summary, issue_counts, rejected_records),
    }


def _human_summary(
    path: Path,
    eligibility_summary: Counter[str],
    issue_counts: Counter[str],
    rejected_records: list[dict[str, str]],
) -> str:
    lines = [f"Comp audit for {path}"]
    lines.append("Eligibility summary: " + ", ".join(f"{key}={value}" for key, value in sorted(eligibility_summary.items())))
    if issue_counts:
        lines.append("Top issue types: " + ", ".join(f"{key}={value}" for key, value in issue_counts.most_common(6)))
    if rejected_records:
        lines.append("Rejected: " + ", ".join(item["address"] for item in rejected_records[:10]))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Briarwood comp store quality.")
    parser.add_argument("path", help="Path to sales_comps.json or active_listings.json")
    args = parser.parse_args()
    summary = audit_store(Path(args.path))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
