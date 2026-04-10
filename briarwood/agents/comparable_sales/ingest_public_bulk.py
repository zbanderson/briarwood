"""
Bulk ingestion orchestrator: SR1A + MOD-IV → JsonComparableSalesStore.

Reads SR1A files for state-verified sales, enriches with MOD-IV property
details, deduplicates against the existing comp store, and upserts.

Usage (CLI):
    python -m briarwood.agents.comparable_sales.ingest_public_bulk \\
        --sr1a-dir data/public_records/sr1a/ \\
        --modiv-csv data/public_records/modiv/monmouth_modiv.csv \\
        --comps data/comps/sales_comps.json

Usage (programmatic):
    from briarwood.agents.comparable_sales.ingest_public_bulk import run_bulk_ingest
    result = run_bulk_ingest(
        sr1a_dir="data/public_records/sr1a/",
        comps_path="data/comps/sales_comps.json",
    )
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from briarwood.agents.comparable_sales.modiv_enricher import MODIVEnricher
from briarwood.agents.comparable_sales.schemas import ComparableSale
from briarwood.agents.comparable_sales.sr1a_parser import (
    SR1AParseResult,
    parse_sr1a_file,
)
from briarwood.agents.comparable_sales.store import JsonComparableSalesStore

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BulkIngestResult:
    """Summary of a full bulk ingestion run."""
    sr1a_files_processed: int = 0
    sr1a_total_lines: int = 0
    sr1a_total_parsed: int = 0
    modiv_records_loaded: int = 0
    modiv_lookups_matched: int = 0
    modiv_year_built_enriched: int = 0
    modiv_acreage_enriched: int = 0
    modiv_latlon_enriched: int = 0
    duplicates_skipped: int = 0
    new_records_added: int = 0
    existing_records_updated: int = 0
    errors: list[str] = field(default_factory=list)


def run_bulk_ingest(
    *,
    sr1a_dir: str | Path,
    comps_path: str | Path = "data/comps/sales_comps.json",
    modiv_csv: str | Path | None = None,
    modiv_geojson: str | Path | None = None,
    county_code: str = "13",
    target_districts: list[str] | None = None,
    dataset_name: str | None = None,
) -> BulkIngestResult:
    """Run the full SR1A + MOD-IV → comp store pipeline.

    Args:
        sr1a_dir: Directory containing SR1A flat files (*.txt or no extension).
        comps_path: Path to the JSON comp store.
        modiv_csv: Optional path to MOD-IV CSV export.
        modiv_geojson: Optional path to MOD-IV GeoJSON export.
        county_code: County to filter (default "13" = Monmouth).
        target_districts: Optional list of district codes to include.
        dataset_name: Optional dataset name to stamp on the store metadata.
    """
    result = BulkIngestResult()
    sr1a_path = Path(sr1a_dir)
    as_of = datetime.today().strftime("%Y-%m-%d")

    # ── Step 1: Parse all SR1A files ──────────────────────────────────────
    all_sales: list[ComparableSale] = []

    if sr1a_path.is_file():
        sr1a_files = [sr1a_path]
    elif sr1a_path.is_dir():
        sr1a_files = sorted(
            p for p in sr1a_path.iterdir()
            if p.is_file() and p.suffix in {"", ".txt", ".dat", ".sr1a"}
        )
    else:
        result.errors.append(f"SR1A path not found: {sr1a_path}")
        return result

    for sr1a_file in sr1a_files:
        logger.info("Parsing SR1A file: %s", sr1a_file)
        try:
            parse_result: SR1AParseResult = parse_sr1a_file(
                sr1a_file,
                county_code=county_code,
                target_districts=target_districts,
            )
            result.sr1a_files_processed += 1
            result.sr1a_total_lines += parse_result.total_lines
            result.sr1a_total_parsed += parse_result.parsed
            all_sales.extend(parse_result.sales)
            logger.info(
                "  %s: %d lines → %d usable residential sales",
                sr1a_file.name,
                parse_result.total_lines,
                parse_result.parsed,
            )
        except Exception as exc:
            msg = f"Error parsing {sr1a_file}: {exc}"
            logger.error(msg)
            result.errors.append(msg)

    if not all_sales:
        logger.warning("No sales parsed from SR1A files in %s", sr1a_path)
        return result

    # ── Step 2: Deduplicate within the parsed batch ───────────────────────
    seen_refs: dict[str, ComparableSale] = {}
    for sale in all_sales:
        key = sale.source_ref or sale.address
        if key not in seen_refs:
            seen_refs[key] = sale
    deduped_sales = list(seen_refs.values())
    batch_dupes = len(all_sales) - len(deduped_sales)
    if batch_dupes > 0:
        logger.info("Deduplicated %d intra-batch duplicates", batch_dupes)
    all_sales = deduped_sales

    # ── Step 3: Enrich with MOD-IV ────────────────────────────────────────
    enricher = MODIVEnricher()

    if modiv_csv:
        modiv_csv_path = Path(modiv_csv)
        if modiv_csv_path.exists():
            result.modiv_records_loaded += enricher.load_csv(modiv_csv_path)
        else:
            logger.warning("MOD-IV CSV not found: %s", modiv_csv_path)

    if modiv_geojson:
        modiv_gj_path = Path(modiv_geojson)
        if modiv_gj_path.exists():
            result.modiv_records_loaded += enricher.load_geojson(modiv_gj_path)
        else:
            logger.warning("MOD-IV GeoJSON not found: %s", modiv_gj_path)

    if enricher.record_count > 0:
        enrich_result = enricher.enrich_sales(all_sales)
        result.modiv_lookups_matched = enrich_result.lookups_matched
        result.modiv_year_built_enriched = enrich_result.year_built_enriched
        result.modiv_acreage_enriched = enrich_result.acreage_enriched
        result.modiv_latlon_enriched = enrich_result.latlon_enriched

    # ── Step 4: Upsert into comp store ────────────────────────────────────
    store = JsonComparableSalesStore(comps_path)
    dataset = store.load()

    existing_by_ref: dict[str, int] = {}
    for idx, existing in enumerate(dataset.sales):
        if existing.source_ref:
            existing_by_ref[existing.source_ref] = idx

    for sale in all_sales:
        ref = sale.source_ref
        if ref and ref in existing_by_ref:
            # Update existing record with potentially enriched data
            dataset.sales[existing_by_ref[ref]] = sale
            result.existing_records_updated += 1
        else:
            dataset.sales.append(sale)
            if ref:
                existing_by_ref[ref] = len(dataset.sales) - 1
            result.new_records_added += 1

    result.duplicates_skipped = batch_dupes

    # Update metadata
    dataset.metadata["sr1a_ingest_as_of"] = as_of
    dataset.metadata["sr1a_files_processed"] = result.sr1a_files_processed
    dataset.metadata["sr1a_total_parsed"] = result.sr1a_total_parsed
    if dataset_name:
        dataset.metadata["dataset_name"] = dataset_name

    store.save(dataset)

    logger.info(
        "Bulk ingest complete: %d SR1A parsed, %d MOD-IV enriched, "
        "%d new, %d updated, %d batch dupes",
        result.sr1a_total_parsed,
        result.modiv_lookups_matched,
        result.new_records_added,
        result.existing_records_updated,
        result.duplicates_skipped,
    )
    return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Bulk-ingest NJ SR1A public record sales into Briarwood comp store."
    )
    parser.add_argument(
        "--sr1a-dir",
        default="data/public_records/sr1a/",
        help="Directory containing SR1A flat files.",
    )
    parser.add_argument(
        "--modiv-csv",
        default=None,
        help="Optional path to MOD-IV CSV export for enrichment.",
    )
    parser.add_argument(
        "--modiv-geojson",
        default=None,
        help="Optional path to MOD-IV GeoJSON for enrichment.",
    )
    parser.add_argument(
        "--comps",
        default="data/comps/sales_comps.json",
        help="Path to the JSON comp store.",
    )
    parser.add_argument(
        "--county-code",
        default="13",
        help="2-digit NJ county code (default 13 = Monmouth).",
    )
    parser.add_argument(
        "--districts",
        nargs="*",
        default=None,
        help="Optional district codes to filter (e.g. 07 for Belmar).",
    )
    parser.add_argument(
        "--dataset-name",
        default=None,
        help="Optional dataset name for store metadata.",
    )
    args = parser.parse_args()

    result = run_bulk_ingest(
        sr1a_dir=args.sr1a_dir,
        comps_path=args.comps,
        modiv_csv=args.modiv_csv,
        modiv_geojson=args.modiv_geojson,
        county_code=args.county_code,
        target_districts=args.districts,
        dataset_name=args.dataset_name,
    )

    print(f"\n{'='*60}")
    print("Briarwood Public Record Bulk Ingest — Summary")
    print(f"{'='*60}")
    print(f"SR1A files processed:    {result.sr1a_files_processed}")
    print(f"SR1A total lines:        {result.sr1a_total_lines:,}")
    print(f"SR1A usable sales:       {result.sr1a_total_parsed:,}")
    print(f"MOD-IV records loaded:   {result.modiv_records_loaded:,}")
    print(f"MOD-IV lookups matched:  {result.modiv_lookups_matched:,}")
    print(f"  year_built enriched:   {result.modiv_year_built_enriched:,}")
    print(f"  acreage enriched:      {result.modiv_acreage_enriched:,}")
    print(f"  lat/lon enriched:      {result.modiv_latlon_enriched:,}")
    print(f"Batch duplicates:        {result.duplicates_skipped:,}")
    print(f"New records added:       {result.new_records_added:,}")
    print(f"Existing updated:        {result.existing_records_updated:,}")
    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  - {err}")
    print()
    return 0 if not result.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
