from __future__ import annotations

import json
import pickle
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from briarwood.dash_app.view_models import build_property_analysis_view
from briarwood.agents.comparable_sales.store import JsonComparableSalesStore
from briarwood.runner import run_report, run_report_from_listing_text, write_report_html
from briarwood.reports.pdf_renderer import write_tear_sheet_pdf
from briarwood.schemas import AnalysisReport


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"
SAVED_PROPERTY_DIR = DATA_DIR / "saved_properties"
LEGACY_MANUAL_ENTRY_DIR = DATA_DIR / "manual_entries"
SALES_COMPS_PATH = DATA_DIR / "comps" / "sales_comps.json"


@dataclass(frozen=True, slots=True)
class PropertyPreset:
    preset_id: str
    label: str
    description: str
    loader: Callable[[], AnalysisReport]


@dataclass(frozen=True, slots=True)
class SavedPropertySummary:
    property_id: str
    address: str
    label: str
    ask_price: float | None
    bcv: float | None
    pricing_view: str
    confidence: float
    comp_trust: str
    missing_input_count: int
    timestamp: str
    tear_sheet_path: Path


def _load_json_report(path: str) -> AnalysisReport:
    return run_report(DATA_DIR / path)


def _load_listing_report(path: str, *, property_id: str, source_url: str) -> AnalysisReport:
    listing_text = (DATA_DIR / path).read_text()
    return run_report_from_listing_text(
        listing_text,
        property_id=property_id,
        source_url=source_url,
    )


PRESETS: tuple[PropertyPreset, ...] = (
    PropertyPreset(
        preset_id="sample-public-record",
        label="Sample Public Record",
        description="Flat JSON input with assumptions and weaker listing evidence.",
        loader=lambda: _load_json_report("sample_property.json"),
    ),
    PropertyPreset(
        preset_id="belmar-l-street",
        label="1600 L St, Belmar",
        description="Listing-assisted Belmar sample used in the tear-sheet workflow.",
        loader=lambda: _load_listing_report(
            "sample_zillow_listing_belmar.txt",
            property_id="belmar-l-street",
            source_url="https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
        ),
    ),
    PropertyPreset(
        preset_id="briarwood-rd-belmar",
        label="1223 Briarwood Rd, Belmar",
        description="Listing-assisted Belmar sample with yearly-rental context.",
        loader=lambda: _load_listing_report(
            "sample_zillow_listing_briarwood_rd_belmar.txt",
            property_id="briarwood-rd-belmar",
            source_url="https://www.zillow.com/homedetails/1223-Briarwood-Rd-Belmar-NJ-07719/39225332_zpid/",
        ),
    ),
)

DEFAULT_PRESET_IDS = ["briarwood-rd-belmar", "belmar-l-street"]
_REPORT_CACHE: dict[str, AnalysisReport] = {}

# Preset list cache: (catalog_version, preset_list)
_PRESET_CACHE: tuple[int, list[PropertyPreset]] | None = None


def list_presets(catalog_version: int | None = None) -> list[PropertyPreset]:
    """Return all property presets, memoized by catalog version.

    When *catalog_version* matches the cached value the previous result is
    returned immediately, avoiding 4 disk-scanning sub-calls.
    """
    global _PRESET_CACHE
    if _PRESET_CACHE is not None and catalog_version is not None and _PRESET_CACHE[0] == catalog_version:
        return _PRESET_CACHE[1]
    ordered: dict[str, PropertyPreset] = {}
    for preset in list(PRESETS) + _saved_property_presets() + _saved_property_directory_presets() + _comp_database_presets() + _legacy_manual_presets():
        ordered[preset.preset_id] = preset
    result = list(ordered.values())
    if catalog_version is not None:
        _PRESET_CACHE = (catalog_version, result)
    return result


def invalidate_preset_cache() -> None:
    """Clear the preset cache so the next list_presets() call re-scans."""
    global _PRESET_CACHE
    _PRESET_CACHE = None


def list_saved_properties() -> list[SavedPropertySummary]:
    SAVED_PROPERTY_DIR.mkdir(parents=True, exist_ok=True)
    summaries: list[SavedPropertySummary] = []
    for property_dir in sorted(SAVED_PROPERTY_DIR.iterdir(), reverse=True):
        if not property_dir.is_dir():
            continue
        summary_path = property_dir / "summary.json"
        if not summary_path.exists():
            continue
        try:
            payload = json.loads(summary_path.read_text())
            summaries.append(
                SavedPropertySummary(
                    property_id=str(payload["property_id"]),
                    address=str(payload["address"]),
                    label=str(payload["label"]),
                    ask_price=_optional_float(payload.get("ask_price")),
                    bcv=_optional_float(payload.get("bcv")),
                    pricing_view=str(payload.get("pricing_view") or "unknown"),
                    confidence=float(payload.get("confidence") or 0.0),
                    comp_trust=str(payload.get("comp_trust") or "No Active Comps"),
                    missing_input_count=int(payload.get("missing_input_count") or 0),
                    timestamp=str(payload.get("timestamp") or ""),
                    tear_sheet_path=property_dir / "tear_sheet.html",
                )
            )
        except Exception:
            continue
    return sorted(summaries, key=lambda item: item.timestamp, reverse=True)


def list_comp_database_rows() -> list[dict[str, str]]:
    try:
        dataset = JsonComparableSalesStore(SALES_COMPS_PATH).load()
    except Exception:
        return []
    rows: list[dict[str, str]] = []
    for sale in dataset.sales:
        price = sale.list_price or sale.sale_price
        rows.append(
            {
                "source_ref": sale.source_ref or sale.address,
                "Address": sale.address,
                "Town": sale.town,
                "Price": _fmt_compact_currency(price),
                "Status": (sale.listing_status or "sold").replace("_", " ").title(),
                "Type": sale.property_type or "Unknown",
            }
        )
    rows.sort(key=lambda row: (row["Town"], row["Address"]))
    return rows


def load_report_for_preset(preset_id: str) -> AnalysisReport:
    if preset_id not in _REPORT_CACHE:
        saved_report = _load_saved_report(preset_id)
        if saved_report is not None:
            _REPORT_CACHE[preset_id] = saved_report
        else:
            preset_map = {preset.preset_id: preset for preset in list_presets()}
            if preset_id not in preset_map:
                raise KeyError(f"Unknown property preset: {preset_id}")
            _REPORT_CACHE[preset_id] = preset_map[preset_id].loader()
    return _REPORT_CACHE[preset_id]


def load_reports(preset_ids: list[str]) -> dict[str, AnalysisReport]:
    results: dict[str, AnalysisReport] = {}
    for preset_id in preset_ids:
        try:
            results[preset_id] = load_report_for_preset(preset_id)
        except KeyError:
            continue
    return results


def export_preset_tear_sheet(preset_id: str) -> Path:
    saved_path = _saved_property_path(preset_id) / "tear_sheet.html"
    if saved_path.exists():
        return saved_path
    report = load_report_for_preset(preset_id)
    filename = f"{preset_id}_tear_sheet.html"
    return write_report_html(report, OUTPUT_DIR / filename)


def export_preset_tear_sheet_pdf(preset_id: str) -> Path:
    """Export a PDF tear sheet for a saved/loaded property."""
    report = load_report_for_preset(preset_id)
    filename = f"{preset_id}_tear_sheet.pdf"
    return write_tear_sheet_pdf(report, OUTPUT_DIR / filename)


def load_property_form_defaults(property_id: str) -> tuple[dict[str, object], list[dict[str, object]]]:
    inputs_path = _saved_property_path(property_id) / "inputs.json"
    if inputs_path.exists():
        try:
            payload = json.loads(inputs_path.read_text())
            subject = _subject_from_payload(payload, property_id)
            comps = payload.get("user_assumptions", {}).get("manual_comp_inputs", [])
            return subject, comps if isinstance(comps, list) else []
        except Exception:
            pass

    report = load_report_for_preset(property_id)
    property_input = report.property_input
    assumptions = None if property_input is None else property_input.user_assumptions
    subject = {
        "property_id": property_id,
        "address": getattr(property_input, "address", None),
        "town": getattr(property_input, "town", None),
        "state": getattr(property_input, "state", None),
        "county": getattr(property_input, "county", None),
        "purchase_price": getattr(property_input, "purchase_price", None),
        "beds": getattr(property_input, "beds", None),
        "baths": getattr(property_input, "baths", None),
        "sqft": getattr(property_input, "sqft", None),
        "lot_size": getattr(property_input, "lot_size", None),
        "year_built": getattr(property_input, "year_built", None),
        "property_type": getattr(property_input, "property_type", None),
        "taxes": getattr(property_input, "taxes", None),
        "monthly_hoa": getattr(property_input, "monthly_hoa", None),
        "days_on_market": getattr(property_input, "days_on_market", None),
        "garage_spaces": getattr(property_input, "garage_spaces", None),
        "garage_type": getattr(property_input, "garage_type", None),
        "has_detached_garage": getattr(property_input, "has_detached_garage", None),
        "has_back_house": getattr(property_input, "has_back_house", None),
        "adu_type": getattr(property_input, "adu_type", None),
        "adu_sqft": getattr(property_input, "adu_sqft", None),
        "has_basement": getattr(property_input, "has_basement", None),
        "basement_finished": getattr(property_input, "basement_finished", None),
        "has_pool": getattr(property_input, "has_pool", None),
        "parking_spaces": getattr(property_input, "parking_spaces", None),
        "corner_lot": getattr(property_input, "corner_lot", None),
        "driveway_off_street": getattr(property_input, "driveway_off_street", None),
        "estimated_monthly_rent": getattr(property_input, "estimated_monthly_rent", None),
        "unit_rents": list(getattr(property_input, "unit_rents", []) or []),
        "back_house_monthly_rent": getattr(property_input, "back_house_monthly_rent", None),
        "seasonal_monthly_rent": getattr(property_input, "seasonal_monthly_rent", None),
        "insurance": getattr(property_input, "insurance", None),
        "monthly_maintenance_reserve_override": getattr(property_input, "monthly_maintenance_reserve_override", None),
        "condition_profile": getattr(property_input, "condition_profile", None),
        "capex_lane": getattr(property_input, "capex_lane", None),
        "notes": getattr(property_input, "listing_description", None),
    }
    if assumptions is not None:
        subject["estimated_monthly_rent"] = getattr(assumptions, "estimated_monthly_rent", subject["estimated_monthly_rent"])
        subject["unit_rents"] = list(getattr(assumptions, "unit_rents", []) or subject["unit_rents"])
        subject["back_house_monthly_rent"] = getattr(assumptions, "back_house_monthly_rent", subject["back_house_monthly_rent"])
        subject["seasonal_monthly_rent"] = getattr(assumptions, "seasonal_monthly_rent", subject["seasonal_monthly_rent"])
        subject["insurance"] = getattr(assumptions, "insurance", subject["insurance"])
        subject["monthly_maintenance_reserve_override"] = getattr(assumptions, "monthly_maintenance_reserve_override", subject["monthly_maintenance_reserve_override"])
        subject["notes"] = subject["notes"] or getattr(assumptions, "listing_description", None)
    comps = list(getattr(property_input, "manual_comp_inputs", []) or [])
    return subject, comps


def load_comp_form_defaults(source_ref: str) -> tuple[dict[str, object], list[dict[str, object]]]:
    dataset = JsonComparableSalesStore(SALES_COMPS_PATH).load()
    target = None
    for sale in dataset.sales:
        if (sale.source_ref or sale.address) == source_ref:
            target = sale
            break
    if target is None:
        raise KeyError(f"Unknown comp database row: {source_ref}")
    subject = {
        "property_id": "",
        "address": target.address,
        "town": target.town,
        "state": target.state,
        "county": "Monmouth",
        "purchase_price": target.sale_price,
        "beds": target.beds,
        "baths": target.baths,
        "sqft": target.sqft,
        "lot_size": target.lot_size,
        "year_built": target.year_built,
        "property_type": target.property_type,
        "taxes": None,
        "monthly_hoa": None,
        "days_on_market": target.days_on_market,
        "garage_spaces": target.garage_spaces,
        "garage_type": None,
        "has_detached_garage": None,
        "has_back_house": None,
        "adu_type": None,
        "adu_sqft": None,
        "has_basement": None,
        "basement_finished": None,
        "has_pool": None,
        "parking_spaces": None,
        "corner_lot": None,
        "driveway_off_street": None,
        "estimated_monthly_rent": None,
        "unit_rents": [],
        "back_house_monthly_rent": None,
        "seasonal_monthly_rent": None,
        "insurance": None,
        "monthly_maintenance_reserve_override": None,
        "condition_profile": target.condition_profile,
        "capex_lane": target.capex_lane,
        "notes": f"Seeded from comp database ({target.source_ref or target.address}).",
    }
    return subject, []


def _load_comp_database_report(source_ref: str) -> AnalysisReport:
    subject, comps = load_comp_form_defaults(source_ref)
    property_id = _slugify(str(subject.get("address") or source_ref))
    payload = _manual_payload(property_id=property_id, subject=subject, comps=comps)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir="/tmp") as handle:
        handle.write(json.dumps(payload, indent=2) + "\n")
        temp_path = Path(handle.name)
    try:
        return run_report(temp_path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass


def register_manual_analysis(subject: dict[str, object], comps: list[dict[str, object]]) -> tuple[str, Path]:
    property_id = _slugify(str(subject.get("property_id") or subject.get("address") or "manual-property"))
    property_dir = _saved_property_path(property_id)
    property_dir.mkdir(parents=True, exist_ok=True)

    payload = _manual_payload(property_id=property_id, subject=subject, comps=comps)
    raw_input_path = property_dir / "inputs.json"
    raw_input_path.write_text(json.dumps(payload, indent=2) + "\n")

    report = run_report(raw_input_path)
    tear_sheet_path = write_report_html(report, property_dir / "tear_sheet.html")
    _write_saved_report(property_dir / "report.pkl", report)
    _write_saved_summary(property_dir, report)
    _REPORT_CACHE[property_id] = report
    invalidate_preset_cache()
    return property_id, tear_sheet_path


def _saved_property_presets() -> list[PropertyPreset]:
    presets: list[PropertyPreset] = []
    for summary in list_saved_properties():
        presets.append(
            PropertyPreset(
                preset_id=summary.property_id,
                label=summary.label,
                description=f"Saved analysis from {summary.timestamp[:16].replace('T', ' ')}.",
                loader=lambda property_id=summary.property_id: _reanalyze_saved_property(property_id),
            )
        )
    return presets


def _comp_database_presets() -> list[PropertyPreset]:
    try:
        dataset = JsonComparableSalesStore(SALES_COMPS_PATH).load()
    except Exception:
        return []

    existing_labels = {summary.label.strip().lower() for summary in list_saved_properties()}
    presets: list[PropertyPreset] = []
    for sale in dataset.sales:
        label = sale.address.split(",")[0].strip()
        preset_id = f"compdb-{_slugify(sale.source_ref or sale.address)}"
        if label.lower() in existing_labels:
            continue
        presets.append(
            PropertyPreset(
                preset_id=preset_id,
                label=f"DB: {label}",
                description="Comp database property ready to analyze.",
                loader=lambda source_ref=(sale.source_ref or sale.address): _load_comp_database_report(source_ref),
            )
        )
    return presets


def _subject_from_payload(payload: dict[str, object], property_id: str) -> dict[str, object]:
    facts = payload.get("facts") if isinstance(payload.get("facts"), dict) else {}
    assumptions = payload.get("user_assumptions") if isinstance(payload.get("user_assumptions"), dict) else {}
    return {
        "property_id": payload.get("property_id") or property_id,
        "address": facts.get("address"),
        "town": facts.get("town"),
        "state": facts.get("state"),
        "county": facts.get("county"),
        "purchase_price": facts.get("purchase_price"),
        "beds": facts.get("beds"),
        "baths": facts.get("baths"),
        "sqft": facts.get("sqft"),
        "lot_size": facts.get("lot_size"),
        "year_built": facts.get("year_built"),
        "property_type": facts.get("property_type"),
        "taxes": facts.get("taxes"),
        "monthly_hoa": facts.get("monthly_hoa"),
        "days_on_market": facts.get("days_on_market"),
        "garage_spaces": facts.get("garage_spaces"),
        "garage_type": facts.get("garage_type"),
        "has_detached_garage": facts.get("has_detached_garage"),
        "has_back_house": facts.get("has_back_house"),
        "adu_type": facts.get("adu_type"),
        "adu_sqft": facts.get("adu_sqft"),
        "has_basement": facts.get("has_basement"),
        "basement_finished": facts.get("basement_finished"),
        "has_pool": facts.get("has_pool"),
        "parking_spaces": facts.get("parking_spaces"),
        "corner_lot": facts.get("corner_lot"),
        "driveway_off_street": facts.get("driveway_off_street"),
        "estimated_monthly_rent": assumptions.get("estimated_monthly_rent"),
        "unit_rents": assumptions.get("unit_rents") or [],
        "back_house_monthly_rent": assumptions.get("back_house_monthly_rent"),
        "seasonal_monthly_rent": assumptions.get("seasonal_monthly_rent"),
        "insurance": assumptions.get("insurance"),
        "monthly_maintenance_reserve_override": assumptions.get("monthly_maintenance_reserve_override"),
        "condition_profile": facts.get("condition_profile") or assumptions.get("condition_profile_override"),
        "capex_lane": facts.get("capex_lane") or assumptions.get("capex_lane_override"),
        "notes": facts.get("listing_description"),
    }


def _saved_property_directory_presets() -> list[PropertyPreset]:
    SAVED_PROPERTY_DIR.mkdir(parents=True, exist_ok=True)
    known_ids = {summary.property_id for summary in list_saved_properties()}
    presets: list[PropertyPreset] = []
    for property_dir in sorted(SAVED_PROPERTY_DIR.iterdir(), reverse=True):
        if not property_dir.is_dir():
            continue
        property_id = property_dir.name
        if property_id in known_ids:
            continue
        inputs_path = property_dir / "inputs.json"
        if not inputs_path.exists():
            continue
        label = _saved_property_label_from_inputs(inputs_path, property_id)
        presets.append(
            PropertyPreset(
                preset_id=property_id,
                label=label,
                description="Saved analysis discovered from inputs.json.",
                loader=lambda property_id=property_id: _reanalyze_saved_property(property_id),
            )
        )
    return presets


def _reanalyze_saved_property(property_id: str) -> AnalysisReport:
    """Re-run analysis from saved inputs.json when pickle is missing or stale."""
    inputs_path = _saved_property_path(property_id) / "inputs.json"
    if not inputs_path.exists():
        raise KeyError(f"No inputs.json for saved property: {property_id}")
    report = run_report(inputs_path)
    property_dir = _saved_property_path(property_id)
    _write_saved_report(property_dir / "report.pkl", report)
    _write_saved_summary(property_dir, report)
    return report


def _saved_property_label_from_inputs(path: Path, property_id: str) -> str:
    try:
        payload = json.loads(path.read_text())
    except Exception:
        return property_id.replace("-", " ").title()

    facts = payload.get("facts")
    if isinstance(facts, dict):
        address = facts.get("address")
        if isinstance(address, str) and address.strip():
            return address.split(",")[0].strip()
    return property_id.replace("-", " ").title()


def _fmt_compact_currency(value: float | None) -> str:
    if value is None:
        return "—"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value / 1_000:.0f}K"


def _legacy_manual_presets() -> list[PropertyPreset]:
    if not LEGACY_MANUAL_ENTRY_DIR.exists():
        return []
    presets: list[PropertyPreset] = []
    for path in sorted(LEGACY_MANUAL_ENTRY_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except Exception:
            continue
        property_id = str(payload.get("property_id") or path.stem)
        address = str(((payload.get("facts") or {}) if isinstance(payload.get("facts"), dict) else {}).get("address") or property_id)
        presets.append(
            PropertyPreset(
                preset_id=property_id,
                label=f"Legacy: {address.split(',')[0]}",
                description="Legacy manual entry JSON.",
                loader=lambda path=path: run_report(path),
            )
        )
    return presets


def _manual_payload(*, property_id: str, subject: dict[str, object], comps: list[dict[str, object]]) -> dict[str, object]:
    def manual_status(value: object) -> str:
        return "user_supplied" if value not in (None, "", []) else "missing"

    condition_profile = subject.get("condition_profile")
    capex_lane = subject.get("capex_lane")
    condition_confirmed = True if condition_profile not in (None, "") else None
    capex_confirmed = True if capex_lane not in (None, "") else None

    return {
        "property_id": property_id,
        "facts": {
            "address": str(subject.get("address") or "Unknown Address"),
            "town": str(subject.get("town") or "Unknown"),
            "state": str(subject.get("state") or "NJ"),
            "county": subject.get("county") or "Monmouth",
            "beds": _optional_int(subject.get("beds")),
            "baths": _optional_float(subject.get("baths")),
            "sqft": _optional_int(subject.get("sqft")),
            "lot_size": _optional_float(subject.get("lot_size")),
            "property_type": subject.get("property_type"),
            "condition_profile": subject.get("condition_profile"),
            "capex_lane": subject.get("capex_lane"),
            "year_built": _optional_int(subject.get("year_built")),
            "garage_spaces": _optional_int(subject.get("garage_spaces")),
            "garage_type": subject.get("garage_type"),
            "has_detached_garage": _optional_bool(subject.get("has_detached_garage")),
            "has_back_house": _optional_bool(subject.get("has_back_house")),
            "adu_type": subject.get("adu_type"),
            "adu_sqft": _optional_int(subject.get("adu_sqft")),
            "has_basement": _optional_bool(subject.get("has_basement")),
            "basement_finished": _optional_bool(subject.get("basement_finished")),
            "has_pool": _optional_bool(subject.get("has_pool")),
            "parking_spaces": _optional_int(subject.get("parking_spaces")),
            "corner_lot": _optional_bool(subject.get("corner_lot")),
            "driveway_off_street": _optional_bool(subject.get("driveway_off_street")),
            "purchase_price": _optional_float(subject.get("purchase_price")),
            "taxes": _optional_float(subject.get("taxes")),
            "monthly_hoa": _optional_float(subject.get("monthly_hoa")),
            "days_on_market": _optional_int(subject.get("days_on_market")),
            "listing_description": subject.get("notes"),
        },
        "market_signals": {},
        "user_assumptions": {
            "estimated_monthly_rent": _optional_float(subject.get("estimated_monthly_rent")),
            "back_house_monthly_rent": _optional_float(subject.get("back_house_monthly_rent")),
            "seasonal_monthly_rent": _optional_float(subject.get("seasonal_monthly_rent")),
            "unit_rents": _optional_float_list(subject.get("unit_rents")),
            "rent_confidence_override": subject.get("rent_confidence_override"),
            "insurance": _optional_float(subject.get("insurance")),
            "monthly_maintenance_reserve_override": _optional_float(subject.get("monthly_maintenance_reserve_override")),
            "condition_profile_override": condition_profile,
            "condition_confirmed": condition_confirmed,
            "capex_lane_override": capex_lane,
            "capex_confirmed": capex_confirmed,
            "repair_capex_budget": _optional_float(subject.get("repair_capex_budget")),
            "strategy_intent": subject.get("strategy_intent"),
            "hold_period_years": _optional_int(subject.get("hold_period_years")),
            "risk_tolerance": subject.get("risk_tolerance"),
            "manual_comp_inputs": comps,
        },
        "source_metadata": {
            "evidence_mode": "public_record",
            "provenance": ["manual_subject_entry"],
            "source_coverage": {
                "address": {"status": manual_status(subject.get("address")), "source_name": "manual entry"},
                "price_ask": {"status": manual_status(subject.get("purchase_price")), "source_name": "manual entry"},
                "beds_baths": {"status": "user_supplied", "source_name": "manual entry"},
                "sqft": {"status": manual_status(subject.get("sqft")), "source_name": "manual entry"},
                "lot_size": {"status": manual_status(subject.get("lot_size")), "source_name": "manual entry"},
                "taxes": {"status": manual_status(subject.get("taxes")), "source_name": "manual entry"},
                "hoa": {"status": manual_status(subject.get("monthly_hoa")), "source_name": "manual entry"},
                "listing_history": {"status": manual_status(subject.get("days_on_market")), "source_name": "manual entry"},
                "rent_estimate": {
                    "status": "user_supplied" if _optional_float_list(subject.get("unit_rents")) else manual_status(subject.get("estimated_monthly_rent")),
                    "source_name": "manual entry",
                },
                "rent_confidence": {"status": manual_status(subject.get("rent_confidence_override")), "source_name": "manual entry"},
                "insurance_estimate": {"status": manual_status(subject.get("insurance")), "source_name": "manual entry"},
                "comp_support": {"status": "user_supplied" if comps else "missing", "source_name": "manual entry"},
                "condition_assumption": {"status": manual_status(condition_profile), "source_name": "manual entry"},
                "capex_assumption": {"status": manual_status(capex_lane), "source_name": "manual entry"},
                "capex_budget": {"status": manual_status(subject.get("repair_capex_budget")), "source_name": "manual entry"},
                "strategy_intent": {"status": manual_status(subject.get("strategy_intent")), "source_name": "manual entry"},
                "scarcity_inputs": {"status": "user_supplied", "source_name": "manual entry"},
            },
        },
    }


def _saved_property_path(property_id: str) -> Path:
    return SAVED_PROPERTY_DIR / property_id


def _load_saved_report(property_id: str) -> AnalysisReport | None:
    report_path = _saved_property_path(property_id) / "report.pkl"
    if not report_path.exists():
        return None
    try:
        with report_path.open("rb") as handle:
            return pickle.load(handle)
    except Exception:
        return None


def _write_saved_report(path: Path, report: AnalysisReport) -> None:
    with path.open("wb") as handle:
        pickle.dump(report, handle)


def _write_saved_summary(property_dir: Path, report: AnalysisReport) -> None:
    view = build_property_analysis_view(report)
    summary = {
        "property_id": report.property_id,
        "address": view.address,
        "label": view.address.split(",")[0],
        "ask_price": view.ask_price,
        "bcv": view.bcv,
        "pricing_view": view.pricing_view,
        "confidence": view.overall_confidence,
        "comp_trust": _comp_trust_value(view),
        "missing_input_count": len(view.evidence.missing_inputs),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    (property_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


def _comp_trust_value(view: object) -> str:
    rows = getattr(getattr(view, "comps", None), "rows", [])
    verification_values = {getattr(row, "verification", "") for row in rows}
    if "Mls Verified" in verification_values:
        return "MLS Verified"
    if "Public Record Verified" in verification_values:
        return "Public Record Verified"
    if "Public Record Matched" in verification_values:
        return "Public Record Matched"
    if rows:
        return "Seed / Review Only"
    return "No Active Comps"


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    cleaned = cleaned.strip("-")
    return cleaned or "manual-property"


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    return int(float(str(value)))


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(str(value))


def _optional_float_list(value: object) -> list[float]:
    if not isinstance(value, list):
        return []
    values: list[float] = []
    for item in value:
        parsed = _optional_float(item)
        if parsed is not None and parsed > 0:
            values.append(parsed)
    return values


def _optional_bool(value: object) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None
