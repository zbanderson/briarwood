from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from briarwood.data_quality.pipeline import DataQualityPipeline
from briarwood.data_sources.api_strategy import AnalysisRequestContext, ApiStrategy
from briarwood.data_sources.attom_client import AttomClient


PRIORITY_FIELDS = (
    "beds",
    "baths",
    "sqft",
    "year_built",
    "lot_size",
    "latitude",
    "longitude",
    "tax_amount",
    "assessed_total",
    "last_sale_price",
    "last_sale_date",
    "estimated_monthly_rent",
)


def backfill_store(
    path: Path,
    *,
    dry_run: bool = True,
    max_calls: int = 25,
    cache_dir: str | Path | None = None,
    endpoint_selection: list[str] | None = None,
    client: AttomClient | None = None,
) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    key = "sales" if "sales" in payload else "listings"
    records = [row for row in payload.get(key, []) if isinstance(row, dict)]
    pipeline = DataQualityPipeline()
    attom = client or AttomClient(cache_dir=cache_dir)
    strategy = ApiStrategy()

    before_fill = _fill_rate(records)
    updated_records: list[dict[str, Any]] = []
    targeted_records: list[dict[str, Any]] = []
    skipped_records: list[dict[str, Any]] = []
    call_budget_used = 0
    failure_reasons: dict[str, int] = {}
    endpoint_fill_counts: dict[str, int] = {}

    for record in records:
        result = pipeline.run(record, record_type=_record_type(record))
        if result.status == "rejected":
            updated_records.append(dict(record))
            skipped_records.append({"address": str(record.get("address") or "Unknown"), "reason": "rejected"})
            continue

        missing_fields = [field for field in PRIORITY_FIELDS if result.normalized_record.get(field) in (None, "", [], {})]
        if not missing_fields:
            updated_records.append(dict(record))
            skipped_records.append({"address": str(record.get("address") or "Unknown"), "reason": "complete"})
            continue

        if call_budget_used >= max_calls:
            updated_records.append(dict(record))
            skipped_records.append({"address": str(record.get("address") or "Unknown"), "reason": "max_calls_reached"})
            continue

        context = AnalysisRequestContext(
            analysis_id=result.canonical_key,
            missing_rent=False,
            redevelopment_case=False,
            tax_risk_review="tax_amount" in missing_fields,
            multi_unit_ambiguity=False,
        )
        endpoint_plan = strategy.plan_endpoints(context)
        endpoint_sequence = list(endpoint_plan["core"])
        if "tax_amount" in missing_fields or "assessed_total" in missing_fields:
            endpoint_sequence.extend(endpoint_plan["conditional"])
        if "estimated_monthly_rent" in missing_fields and "rental_avm" not in endpoint_sequence:
            endpoint_sequence.append("rental_avm")
        if endpoint_selection:
            allowed = set(endpoint_selection)
            endpoint_sequence = [endpoint for endpoint in endpoint_sequence if endpoint in allowed]
        endpoint_sequence = _unique(endpoint_sequence)

        enriched_record = dict(record)
        record_calls = 0
        field_sources: dict[str, str] = {}
        for endpoint in endpoint_sequence:
            if call_budget_used >= max_calls:
                break
            response = _fetch_endpoint(
                attom,
                endpoint,
                canonical_key=result.canonical_key,
                record=result.normalized_record,
            )
            call_budget_used += 1
            record_calls += 1
            if response.error:
                failure_reasons[response.error] = failure_reasons.get(response.error, 0) + 1
            for field_name, value in response.normalized_payload.items():
                if field_name not in PRIORITY_FIELDS:
                    continue
                if value in (None, "", [], {}):
                    continue
                target_field = "tax_amount" if field_name == "tax_amount" else field_name
                if enriched_record.get(target_field) in (None, "", [], {}):
                    enriched_record[target_field] = value
                    field_sources[target_field] = endpoint
                    endpoint_fill_counts[endpoint] = endpoint_fill_counts.get(endpoint, 0) + 1
            if all(enriched_record.get(field) not in (None, "", [], {}) for field in missing_fields):
                break

        updated_records.append(enriched_record)
        targeted_records.append(
            {
                "address": str(record.get("address") or "Unknown"),
                "missing_fields_before": missing_fields,
                "filled_fields": sorted(field_sources.keys()),
                "field_sources": field_sources,
                "calls_used": record_calls,
                "status_before": result.status,
            }
        )

    after_fill = _fill_rate(updated_records)
    if not dry_run:
        payload[key] = updated_records
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    return {
        "path": str(path),
        "dry_run": dry_run,
        "max_calls": max_calls,
        "calls_used": call_budget_used,
        "records_targeted": len(targeted_records),
        "records_skipped": len(skipped_records),
        "endpoint_selection": endpoint_selection or [],
        "fill_rate_before": before_fill,
        "fill_rate_after": after_fill,
        "fill_rate_improvement": {
            field: round(after_fill.get(field, 0.0) - before_fill.get(field, 0.0), 4)
            for field in PRIORITY_FIELDS
        },
        "fill_counts_by_field": {
            field: sum(1 for item in targeted_records if field in item["filled_fields"])
            for field in PRIORITY_FIELDS
        },
        "endpoint_fill_counts": endpoint_fill_counts,
        "failures_by_reason": failure_reasons,
        "cache_hit_rate_by_endpoint": {
            endpoint: round(attom.tracker.cache_hit_rate(endpoint), 4)
            for endpoint in attom.tracker.call_counts
        },
        "targeted_records": targeted_records,
        "skipped_records": skipped_records,
    }


def _fetch_endpoint(attom: AttomClient, endpoint: str, *, canonical_key: str, record: dict[str, Any]):
    address = str(record.get("address") or "")
    address2 = ", ".join(part for part in [str(record.get("town") or ""), str(record.get("state") or "")] if part)
    locality = str(record.get("town") or "")
    state = str(record.get("state") or "NJ")
    if endpoint == "property_detail":
        return attom.property_detail(canonical_key, address1=address, address2=address2)
    if endpoint == "assessment_detail":
        return attom.assessment_detail(canonical_key, address1=address, address2=address2)
    if endpoint == "assessment_history":
        return attom.assessment_history(canonical_key, address1=address, address2=address2)
    if endpoint == "sale_detail":
        return attom.sale_detail(canonical_key, address1=address, address2=address2)
    if endpoint == "rental_avm":
        return attom.rental_avm(canonical_key, address1=address, address2=address2)
    if endpoint == "building_permits":
        return attom.building_permits(canonical_key, address1=address, address2=address2)
    if endpoint == "sales_trend":
        return attom.sales_trend(canonical_key, locality=locality, state=state)
    if endpoint == "community_demographics":
        return attom.community_demographics(canonical_key, locality=locality, state=state)
    raise ValueError(f"Unsupported endpoint: {endpoint}")


def _record_type(record: dict[str, Any]) -> str:
    return "sale" if record.get("sale_date") or record.get("sale_price") else "listing"


def _fill_rate(records: list[dict[str, Any]]) -> dict[str, float]:
    if not records:
        return {field: 0.0 for field in PRIORITY_FIELDS}
    return {
        field: round(
            sum(1 for row in records if row.get(field) not in (None, "", [], {})) / len(records),
            4,
        )
        for field in PRIORITY_FIELDS
    }


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill Briarwood comp store records with ATTOM data.")
    parser.add_argument("path", help="Path to sales_comps.json or active_listings.json")
    parser.add_argument("--max-calls", type=int, default=25, help="Maximum ATTOM calls to use.")
    parser.add_argument("--write", action="store_true", help="Write enriched results back to the source file.")
    parser.add_argument("--cache-dir", default=None, help="Optional ATTOM cache directory override.")
    parser.add_argument("--endpoint", action="append", default=None, help="Restrict backfill to selected ATTOM endpoints.")
    args = parser.parse_args()
    summary = backfill_store(
        Path(args.path),
        dry_run=not args.write,
        max_calls=args.max_calls,
        cache_dir=args.cache_dir,
        endpoint_selection=args.endpoint,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
