"""
ATTOM-driven backfill for `data/comps/sales_comps.json` data-integrity findings.

Closes (in priority order) the issues from `docs/MODEL_BACKTEST_2026-04-30.md`:

  1. Eligibility-gate densification — fills beds/baths on `market_only` rows so
     they can pass `_minimum_structural_profile` (3-of-4 of beds/baths/sqft/
     property_type).
  2. Sqft corruption cleanup — overrides implausible `sqft > 10000` SR1A
     bulk-encoded values with ATTOM's `building.size.universalsize`.
  3. (Deferred) Non-arms-length deed-type filter — would require
     `/saleshistory/snapshot`. NOT included in this script; see investigation
     memo § 4.

Outputs:
  - `data/comps/sales_comps_attom_backfilled.json`  (NEW file; original is not
    mutated. Owner approves promotion separately.)
  - `data/eval/attom_backfill_log_2026-04-30.jsonl` (per-row before/after deltas)

Hard contract:
  - Read-only on producer math (no edits to briarwood/agents/comparable_sales/
    agent.py, briarwood/modules/comparable_sales.py, etc.).
  - Streaming writes — Ctrl-C leaves a partial JSONL log and a partial output JSON.
  - Sample mode is the default (`--sample 50`). Full pool requires explicit
    `--full` flag AND owner approval.

Usage (sample mode):
    venv/bin/python3 scripts/data_quality/attom_comp_store_backfill.py --sample 50

Usage (full pool, after approval):
    venv/bin/python3 scripts/data_quality/attom_comp_store_backfill.py --full
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import signal
import sys
import time
from pathlib import Path

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Ensure repo root is on sys.path AND .env is loaded via briarwood package init.
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
import briarwood  # noqa: F401 — triggers dotenv load for ATTOM_API_KEY

from briarwood.agents.comparable_sales.attom_enricher import ATTOMEnricher
from briarwood.data_quality.eligibility import classify_comp_eligibility
from briarwood.data_quality.pipeline import DataQualityPipeline

logger = logging.getLogger(__name__)

INPUT_PATH = _ROOT / "data" / "comps" / "sales_comps.json"
OUTPUT_PATH = _ROOT / "data" / "comps" / "sales_comps_attom_backfilled.json"
LOG_PATH = _ROOT / "data" / "eval" / "attom_backfill_log_2026-04-30.jsonl"

# Sqft outside this range on residential parcels is treated as corrupt and may
# be overridden by ATTOM. Lower bound matches DataQualityPipeline's own
# numeric-range validator (briarwood/data_quality/pipeline.py:276).
SQFT_PLAUSIBLE_MIN = 100
SQFT_PLAUSIBLE_MAX = 20000
SQFT_CORRUPTION_THRESHOLD = 10000

# Stop the loop cleanly on SIGINT (Ctrl-C). The signal handler sets a flag and
# the loop checks it between rows; the JSONL log and output JSON are flushed
# after every row, so partial state is durable.
_SHOULD_STOP = False


def _sigint_handler(signum, frame):  # type: ignore[no-untyped-def]
    global _SHOULD_STOP
    _SHOULD_STOP = True
    logger.warning("SIGINT received — stopping after current row.")


def _install_retry_adapter(enricher: ATTOMEnricher) -> None:
    # Mount a Retry-aware HTTPAdapter at runtime. urllib3 retries 429/5xx with
    # exponential backoff before the request reaches the enricher's exception
    # handler. The enricher source is read-only (producer-math constraint); we
    # only mutate the session this script holds.
    retry = Retry(
        total=5,
        connect=3,
        read=3,
        status=5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        backoff_factor=2.0,  # 1s, 2s, 4s, 8s, 16s
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    enricher._session.mount("https://", adapter)
    enricher._session.mount("http://", adapter)


# ---------- targeting predicates ----------

def _is_sqft_corrupted(sale: dict) -> bool:
    sqft = sale.get("sqft")
    return isinstance(sqft, (int, float)) and sqft > SQFT_CORRUPTION_THRESHOLD


def _is_market_only_candidate(sale: dict, *, pipeline: DataQualityPipeline) -> bool:
    """Replicates the agent's load-time gate logic against a single row."""
    record_type = "sale" if sale.get("sale_date") or sale.get("sale_price") else "listing"
    result = pipeline.run(dict(sale), record_type=record_type)
    gate = classify_comp_eligibility(result.evidence_profile)
    return gate.status == "market_only"


def _needs_backfill(sale: dict, *, pipeline: DataQualityPipeline) -> tuple[bool, list[str]]:
    """Return (needs_backfill, reasons)."""
    reasons: list[str] = []
    if _is_sqft_corrupted(sale):
        reasons.append("sqft_corrupted")
    # Cheap check first: identity + structural-core shape. Defer the full
    # pipeline pass to avoid running it on rows we will skip anyway.
    if not sale.get("address") or sale.get("state") != "NJ":
        return (bool(reasons), reasons)
    structural_present = sum(
        1 for k in ("beds", "baths", "sqft", "property_type")
        if sale.get(k) not in (None, "", 0)
    )
    if structural_present < 3:
        if _is_market_only_candidate(sale, pipeline=pipeline):
            reasons.append("market_only_promotable")
    return (bool(reasons), reasons)


# ---------- sampling ----------

def _build_sample(
    sales: list[dict],
    *,
    sample_size: int,
    pipeline: DataQualityPipeline,
    seed: int,
) -> list[tuple[int, dict, list[str]]]:
    """Build a 50-row sample mixing corrupted-sqft + market_only-2024 + market_only-2025.

    Returns list of (index, sale_dict, reasons) tuples.
    """
    rng = random.Random(seed)

    corrupted = [(i, s) for i, s in enumerate(sales) if _is_sqft_corrupted(s)]

    market_only_2024: list[tuple[int, dict]] = []
    market_only_2025: list[tuple[int, dict]] = []
    # Cheap pre-filter: rows where structural-present < 3 AND year matches.
    for i, s in enumerate(sales):
        year = (s.get("sale_date") or "")[:4]
        if year not in ("2024", "2025"):
            continue
        structural_present = sum(
            1 for k in ("beds", "baths", "sqft", "property_type")
            if s.get(k) not in (None, "", 0)
        )
        if structural_present >= 3:
            continue
        if not s.get("address") or s.get("state") != "NJ":
            continue
        bucket = market_only_2024 if year == "2024" else market_only_2025
        bucket.append((i, s))

    # Mix: 20 corrupted + 10 market_only-2024 + 10 market_only-2025 + 10 overlap
    target_corrupted = min(20, len(corrupted))
    target_mo24 = min(10, len(market_only_2024))
    target_mo25 = min(10, len(market_only_2025))

    picked_corrupted = rng.sample(corrupted, target_corrupted) if target_corrupted else []
    picked_mo24 = rng.sample(market_only_2024, target_mo24) if target_mo24 else []
    picked_mo25 = rng.sample(market_only_2025, target_mo25) if target_mo25 else []

    seen: set[int] = set()
    sample: list[tuple[int, dict, list[str]]] = []
    for idx, s in picked_corrupted + picked_mo24 + picked_mo25:
        if idx in seen:
            continue
        ok, reasons = _needs_backfill(s, pipeline=pipeline)
        if ok:
            sample.append((idx, s, reasons))
            seen.add(idx)
        if len(sample) >= sample_size:
            break

    # Fill remaining slots with anything that needs backfill.
    if len(sample) < sample_size:
        for i, s in enumerate(sales):
            if i in seen:
                continue
            ok, reasons = _needs_backfill(s, pipeline=pipeline)
            if ok:
                sample.append((i, s, reasons))
                seen.add(i)
                if len(sample) >= sample_size:
                    break

    return sample[:sample_size]


# ---------- backfill logic ----------

def _snapshot(sale: dict) -> dict:
    return {
        "sqft": sale.get("sqft"),
        "beds": sale.get("beds"),
        "baths": sale.get("baths"),
        "year_built": sale.get("year_built"),
        "lot_size": sale.get("lot_size"),
        "latitude": sale.get("latitude"),
        "longitude": sale.get("longitude"),
        "stories": sale.get("stories"),
        "garage_spaces": sale.get("garage_spaces"),
        "quality_status": sale.get("quality_status"),
        "comp_eligibility_gate": (sale.get("source_provenance") or {}).get("comp_eligibility_gate"),
    }


def _apply_attom_fields(sale: dict, attom_fields: dict, *, reasons: list[str]) -> list[str]:
    """Apply ATTOM fields onto the comp row. Return list of fields actually changed."""
    changed: list[str] = []

    # Sqft: override on corruption, fill otherwise.
    if attom_fields.get("sqft") is not None:
        new_sqft = int(attom_fields["sqft"])
        if SQFT_PLAUSIBLE_MIN <= new_sqft <= SQFT_PLAUSIBLE_MAX:
            current = sale.get("sqft")
            if current is None:
                sale["sqft"] = new_sqft
                changed.append("sqft")
            elif "sqft_corrupted" in reasons and current > SQFT_CORRUPTION_THRESHOLD:
                sale["sqft"] = new_sqft
                changed.append("sqft")

    # Fill-only on the rest (matches existing enricher policy).
    for field in ("beds", "baths", "year_built", "lot_size", "latitude", "longitude", "stories", "garage_spaces"):
        if not sale.get(field) and attom_fields.get(field) is not None:
            sale[field] = attom_fields[field]
            changed.append(field)

    return changed


def _restamp_eligibility(sale: dict, *, pipeline: DataQualityPipeline) -> tuple[str, str]:
    """Re-run the pipeline + gate and stamp results onto the row.

    Returns (quality_status, comp_eligibility_gate).
    """
    record_type = "sale" if sale.get("sale_date") or sale.get("sale_price") else "listing"
    result = pipeline.run(dict(sale), record_type=record_type)
    gate = classify_comp_eligibility(result.evidence_profile)
    sale["quality_status"] = result.status
    sale["quality_issues"] = [issue.code for issue in result.issues]
    provenance = dict(sale.get("source_provenance") or {})
    provenance["comp_eligibility_gate"] = gate.status
    provenance["comp_eligibility_reasons"] = list(gate.reasons)
    provenance["comp_eligibility_warnings"] = list(gate.warnings)
    provenance["summary_flags"] = dict(result.evidence_profile.summary_flags)
    sale["source_provenance"] = provenance
    return result.status, gate.status


# ---------- main loop ----------

def run_backfill(
    *,
    sample_size: int | None,
    seed: int,
    full: bool,
    write_output: bool,
) -> dict:
    if not full and sample_size is None:
        raise ValueError("Specify --sample N or --full.")

    enricher = ATTOMEnricher()
    _install_retry_adapter(enricher)
    pipeline = DataQualityPipeline()

    raw = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    sales = raw.get("sales", [])
    metadata = dict(raw.get("metadata") or {})

    if full:
        # Full pool: every row that needs backfill, in original order.
        targets: list[tuple[int, dict, list[str]]] = []
        for i, s in enumerate(sales):
            ok, reasons = _needs_backfill(s, pipeline=pipeline)
            if ok:
                targets.append((i, s, reasons))
    else:
        targets = _build_sample(
            sales, sample_size=sample_size or 50, pipeline=pipeline, seed=seed,
        )

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_handle = LOG_PATH.open("a", encoding="utf-8")

    summary = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "targets_total": len(targets),
        "rows_processed": 0,
        "attom_calls_ok": 0,
        "attom_calls_404": 0,
        "attom_calls_error": 0,
        "sqft_corrected": 0,
        "promoted_to_eligible": 0,
        "still_market_only": 0,
        "wall_clock_per_row_seconds": [],
    }

    progress_print_every = 100
    cooldown_every = 250
    cooldown_seconds = 5.0
    output_flush_every = 250
    progress_started_at = time.monotonic()

    try:
        for idx, sale, reasons in targets:
            if _SHOULD_STOP:
                break
            row_start = time.monotonic()
            before = _snapshot(sale)

            # Run the eligibility classifier first to get the precise BEFORE gate.
            before_gate = "unknown"
            try:
                record_type = "sale" if sale.get("sale_date") or sale.get("sale_price") else "listing"
                result = pipeline.run(dict(sale), record_type=record_type)
                before_gate = classify_comp_eligibility(result.evidence_profile).status
            except Exception as exc:  # never crash the loop
                logger.warning("Pre-gate failed for index=%d: %s", idx, exc)
            before["comp_eligibility_gate"] = before_gate

            address1 = sale.get("address") or ""
            address2 = enricher._build_address2(sale)  # type: ignore[attr-defined]
            attom_status = "ok"
            attom_fields: dict = {}
            changed: list[str] = []

            try:
                prop = enricher.lookup_property(address1, address2)
            except Exception as exc:
                attom_status = f"error: {exc}"
                prop = None
                summary["attom_calls_error"] += 1

            if prop is None and attom_status == "ok":
                # lookup_property returns None for both 404 and other failures;
                # the enricher already logs the distinction, but we cannot tell
                # them apart here. Treat as 404 for summary purposes.
                attom_status = "no_match"
                summary["attom_calls_404"] += 1
            elif prop is not None:
                attom_fields = enricher.extract_fields(prop)
                changed = _apply_attom_fields(sale, attom_fields, reasons=reasons)
                summary["attom_calls_ok"] += 1
                if "sqft" in changed and "sqft_corrupted" in reasons:
                    summary["sqft_corrected"] += 1

            after_quality, after_gate = _restamp_eligibility(sale, pipeline=pipeline)
            after = _snapshot(sale)

            if before_gate == "market_only" and after_gate == "eligible":
                summary["promoted_to_eligible"] += 1
            elif before_gate == "market_only" and after_gate == "market_only":
                summary["still_market_only"] += 1

            row_elapsed = time.monotonic() - row_start
            summary["wall_clock_per_row_seconds"].append(round(row_elapsed, 3))
            summary["rows_processed"] += 1

            log_handle.write(json.dumps({
                "index": idx,
                "address": sale.get("address"),
                "town": sale.get("town"),
                "sale_date": sale.get("sale_date"),
                "reasons": reasons,
                "attom_status": attom_status,
                "attom_fields_used": changed,
                "before": before,
                "after": after,
                "row_elapsed_seconds": round(row_elapsed, 3),
            }) + "\n")
            log_handle.flush()

            done = summary["rows_processed"]
            if done % progress_print_every == 0:
                elapsed = time.monotonic() - progress_started_at
                rate = done / elapsed if elapsed else 0.0
                remaining = max(0, summary["targets_total"] - done)
                eta_min = (remaining / rate / 60) if rate else 0.0
                logger.info(
                    "progress: %d / %d rows | ok=%d no_match=%d err=%d | "
                    "promoted=%d sqft_fixed=%d | rate=%.2f rows/s eta=%.1f min",
                    done,
                    summary["targets_total"],
                    summary["attom_calls_ok"],
                    summary["attom_calls_404"],
                    summary["attom_calls_error"],
                    summary["promoted_to_eligible"],
                    summary["sqft_corrected"],
                    rate,
                    eta_min,
                )

            if write_output and done % output_flush_every == 0 and done > 0:
                # Periodically flush the output JSON so a crash mid-run still
                # leaves a usable side-by-side file with partial progress.
                metadata["attom_backfill_run_date"] = time.strftime("%Y-%m-%d")
                metadata["attom_backfill_rows_processed"] = done
                metadata["attom_backfill_promoted_to_eligible"] = summary["promoted_to_eligible"]
                metadata["attom_backfill_sqft_corrected"] = summary["sqft_corrected"]
                tmp = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".partial")
                tmp.write_text(
                    json.dumps({"metadata": metadata, "sales": sales}, indent=2) + "\n",
                    encoding="utf-8",
                )
                tmp.replace(OUTPUT_PATH)

            # Throttle (matches the existing enricher's policy).
            time.sleep(0.5)

            # Periodic cool-down — defense in depth against ATTOM bucket fills.
            if done % cooldown_every == 0 and done > 0:
                logger.info("cool-down %.1fs after %d rows", cooldown_seconds, done)
                time.sleep(cooldown_seconds)
    finally:
        log_handle.close()

    if write_output and summary["rows_processed"] > 0:
        # Persist the full sales list to the BACKFILL output (NOT in-place).
        metadata["attom_backfill_run_date"] = time.strftime("%Y-%m-%d")
        metadata["attom_backfill_rows_processed"] = summary["rows_processed"]
        metadata["attom_backfill_promoted_to_eligible"] = summary["promoted_to_eligible"]
        metadata["attom_backfill_sqft_corrected"] = summary["sqft_corrected"]
        out = {"metadata": metadata, "sales": sales}
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    summary["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return summary


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--sample", type=int, default=50,
        help="Number of rows to backfill in sample mode. Default 50.",
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Run on every row that needs backfill. Requires owner approval.",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="RNG seed for sample selection. Default 42.",
    )
    parser.add_argument(
        "--no-write", action="store_true",
        help="Skip writing the output JSON; only emit the JSONL log.",
    )
    args = parser.parse_args()

    if args.full and args.sample != 50:
        logger.warning("--full ignores --sample.")

    signal.signal(signal.SIGINT, _sigint_handler)

    summary = run_backfill(
        sample_size=None if args.full else args.sample,
        seed=args.seed,
        full=args.full,
        write_output=not args.no_write,
    )

    print("\n" + "=" * 60)
    print("ATTOM Comp-Store Backfill — Summary")
    print("=" * 60)
    print(f"Mode:                       {'FULL' if args.full else f'SAMPLE ({args.sample})'}")
    print(f"Targets total:              {summary['targets_total']}")
    print(f"Rows processed:             {summary['rows_processed']}")
    print(f"ATTOM calls ok:             {summary['attom_calls_ok']}")
    print(f"ATTOM calls no-match:       {summary['attom_calls_404']}")
    print(f"ATTOM calls error:          {summary['attom_calls_error']}")
    print(f"Sqft corrections applied:   {summary['sqft_corrected']}")
    print(f"Promoted market_only→elig:  {summary['promoted_to_eligible']}")
    print(f"Still market_only:          {summary['still_market_only']}")
    if summary["wall_clock_per_row_seconds"]:
        wc = summary["wall_clock_per_row_seconds"]
        avg = sum(wc) / len(wc)
        print(f"Wall-clock per row (s):     avg={avg:.2f} min={min(wc):.2f} max={max(wc):.2f}")
    print(f"Log:    {LOG_PATH}")
    if not args.no_write:
        print(f"Output: {OUTPUT_PATH}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
