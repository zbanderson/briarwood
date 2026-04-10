"""
Download NJ SR1A deed transfer files from the NJ Treasury site, parse them,
and merge residential sales into the comp store.

SR1A files are fixed-width public records published by NJ Division of Taxation.
Each file covers one county for a quarterly or annual period.

Usage:
    # Download and ingest (looks for files in data/public_records/sr1a/)
    python scripts/fetch_sr1a_sales.py

    # Download only, don't ingest
    python scripts/fetch_sr1a_sales.py --download-only

    # Ingest existing files without downloading
    python scripts/fetch_sr1a_sales.py --skip-download

    # Dry run
    python scripts/fetch_sr1a_sales.py --dry-run

    # Specify SR1A files manually
    python scripts/fetch_sr1a_sales.py --sr1a-files data/public_records/sr1a/mon2024.txt
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import briarwood  # noqa: F401

from briarwood.agents.comparable_sales.sr1a_parser import (
    MONMOUTH_DISTRICT_CODES,
    SR1AParseResult,
    parse_sr1a_file,
)
from briarwood.agents.comparable_sales.store import JsonComparableSalesStore

logger = logging.getLogger(__name__)

SR1A_DIR = Path("data/public_records/sr1a")
COMPS_PATH = Path("data/comps/sales_comps.json")

# Monmouth County = county code 13.
COUNTY_CODE = "13"

# Our target town district codes.
TARGET_DISTRICTS = ["04", "06", "07", "08", "30", "44", "47", "52"]  # Asbury Park, Avon, Belmar, Bradley, Manasquan, Sea Girt, Spring Lake, Wall

# NJ Division of Taxation SR1A download URLs (statewide ZIP files).
# Each ZIP contains a single fixed-width text file covering ALL counties.
# We filter to Monmouth County (code 13) and target districts at parse time.
SR1A_DOWNLOADS: dict[str, str] = {
    "2026_ytd": "https://www.nj.gov/treasury/taxation/lpt/statdata/YTDSR1A2026.zip",
    "2025": "https://www.nj.gov/treasury/taxation/lpt/statdata/Sales2025.zip",
    "2024": "https://www.nj.gov/treasury/taxation/lpt/statdata/Sales2024.zip",
    "2023": "https://www.nj.gov/treasury/taxation/lpt/statdata/Sales2023.zip",
}


def download_sr1a_files(
    output_dir: Path,
    *,
    years: list[str] | None = None,
) -> list[Path]:
    """Download statewide SR1A ZIP files from NJ Division of Taxation.

    Returns list of extracted .txt file paths.
    """
    import zipfile
    import io

    output_dir.mkdir(parents=True, exist_ok=True)

    if years is None:
        years = list(SR1A_DOWNLOADS.keys())

    downloaded: list[Path] = []
    needs_manual: list[tuple[str, str]] = []

    for label in years:
        url = SR1A_DOWNLOADS.get(label)
        if not url:
            print(f"  No URL for {label}, skipping")
            continue

        # Check if we already have extracted file(s) for this year
        existing = list(output_dir.glob(f"*{label.replace('_ytd', '')}*"))
        txt_existing = [f for f in existing if f.suffix == ".txt" and f.stat().st_size > 1000]
        if txt_existing:
            print(f"  Already have {label}: {txt_existing[0].name} ({txt_existing[0].stat().st_size:,} bytes)")
            downloaded.extend(txt_existing)
            continue

        print(f"  Downloading {label} from {url}...")
        try:
            import subprocess
            zip_path = output_dir / f"{label}.zip"
            result = subprocess.run(
                ["curl", "-sL", "-o", str(zip_path), url],
                timeout=180,
                capture_output=True,
            )
            if result.returncode != 0 or not zip_path.exists() or zip_path.stat().st_size < 1000:
                print(f"    curl download failed (rc={result.returncode})")
                if zip_path.exists():
                    zip_path.unlink()
                continue
            zip_bytes = zip_path.read_bytes()

            # Check for WAF challenge page (HTML instead of ZIP)
            if zip_bytes[:4] != b"PK\x03\x04":
                print(f"    Got WAF challenge page instead of ZIP ({len(zip_bytes):,} bytes)")
                zip_path.unlink(missing_ok=True)
                needs_manual.append((label, url))
                continue

            print(f"    Downloaded {len(zip_bytes):,} bytes")

            # Extract the ZIP
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                for name in zf.namelist():
                    if name.endswith("/"):
                        continue
                    clean_name = name.replace("/", "_").replace("\\", "_")
                    out_path = output_dir / clean_name
                    out_path.write_bytes(zf.read(name))
                    print(f"    Extracted: {clean_name} ({out_path.stat().st_size:,} bytes)")
                    downloaded.append(out_path)

            # Clean up the zip
            zip_path.unlink(missing_ok=True)

        except Exception as e:
            print(f"    Error: {e}")

        time.sleep(1.0)

    if needs_manual:
        print("\n  Some files need manual download (NJ site blocks automated requests).")
        print(f"  Download these ZIPs in your browser and place the extracted .txt files in:")
        print(f"    {output_dir.resolve()}")
        for label, url in needs_manual:
            print(f"    - {label}: {url}")
        print(f"\n  Then re-run: python scripts/fetch_sr1a_sales.py --skip-download")

    return downloaded


def parse_and_merge(
    sr1a_files: list[Path],
    comps_path: Path,
    *,
    dry_run: bool = False,
) -> dict:
    """Parse SR1A files and merge new sales into the comp store."""
    store = JsonComparableSalesStore(comps_path)
    dataset = store.load()
    existing_refs = {s.source_ref for s in dataset.sales if s.source_ref}
    existing_count = len(dataset.sales)

    all_parsed = 0
    all_new = 0
    town_counts: dict[str, int] = {}

    for sr1a_file in sr1a_files:
        if not sr1a_file.exists():
            print(f"  Skipping {sr1a_file} (not found)")
            continue

        print(f"\n  Parsing {sr1a_file.name}...")
        result = parse_sr1a_file(
            sr1a_file,
            county_code=COUNTY_CODE,
            target_districts=TARGET_DISTRICTS,
        )
        print(f"    Lines: {result.total_lines}, Parsed: {result.parsed}")
        print(f"    Skipped: non-usable={result.skipped_non_usable}, "
              f"non-residential={result.skipped_non_residential}, "
              f"low-price={result.skipped_low_price}")
        all_parsed += result.parsed

        new_in_file = 0
        for sale in result.sales:
            if sale.source_ref in existing_refs:
                continue
            existing_refs.add(sale.source_ref)
            new_in_file += 1
            all_new += 1
            town = sale.town
            town_counts[town] = town_counts.get(town, 0) + 1
            if not dry_run:
                dataset.sales.append(sale)

        print(f"    New records (not in store): {new_in_file}")

    if not dry_run and all_new > 0:
        dataset.metadata["sr1a_ingest_date"] = datetime.now().strftime("%Y-%m-%d")
        dataset.metadata["sr1a_records_added"] = all_new
        dataset.metadata["sr1a_files_processed"] = len(sr1a_files)
        store.save(dataset)
        print(f"\nSaved {all_new} new SR1A records to {comps_path}")
        print(f"Store: {existing_count} -> {existing_count + all_new} records")
    elif dry_run:
        print(f"\n[DRY RUN] Would add {all_new} new records")
    else:
        print("\nNo new records to add.")

    print(f"\nSR1A Summary: {all_parsed} parsed across {len(sr1a_files)} files, {all_new} new")
    for town, count in sorted(town_counts.items()):
        print(f"  {town}: +{count}")

    return {"parsed": all_parsed, "new": all_new, "by_town": town_counts}


def run(
    *,
    download: bool = True,
    ingest: bool = True,
    dry_run: bool = False,
    sr1a_files: list[str] | None = None,
    comps_path: Path = COMPS_PATH,
):
    """Full pipeline: download SR1A files, parse, and merge."""
    files: list[Path] = []

    if sr1a_files:
        files = [Path(f) for f in sr1a_files]
    elif download:
        print("Downloading SR1A files from NJ Treasury...")
        files = download_sr1a_files(SR1A_DIR)
        if not files:
            print("\nCould not download any SR1A files.")
            print("Download these from your browser (NJ site blocks automated requests):")
            print("  SR1A sales: https://www.nj.gov/treasury/taxation/lpt/statdata.shtml")
            print("  MODIV (enrichment): https://www.nj.gov/treasury/taxation/pdf/lpt/modiv-2025.zip")
            print(f"\nExtract SR1A .txt files to: {SR1A_DIR.resolve()}")
            print(f"Extract MODIV CSV to: {(SR1A_DIR.parent / 'modiv').resolve()}")
            print("\nThen re-run: python scripts/fetch_sr1a_sales.py --skip-download")

    if not download and not sr1a_files:
        # Look for existing files
        files = sorted(SR1A_DIR.glob("*.txt"))
        if not files:
            print(f"No SR1A files found in {SR1A_DIR}")
            return

    if ingest and files:
        print(f"\nIngesting {len(files)} SR1A file(s)...")
        parse_and_merge(files, comps_path, dry_run=dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download and ingest NJ SR1A sales data")
    parser.add_argument("--download-only", action="store_true", help="Download files but don't ingest")
    parser.add_argument("--skip-download", action="store_true", help="Ingest existing files only")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--sr1a-files", nargs="+", help="Specific SR1A files to ingest")
    parser.add_argument("--comps", type=str, default=str(COMPS_PATH), help="Path to comp store")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    download = not args.skip_download and not args.sr1a_files
    ingest = not args.download_only

    run(
        download=download,
        ingest=ingest,
        dry_run=args.dry_run,
        sr1a_files=args.sr1a_files,
        comps_path=Path(args.comps),
    )
