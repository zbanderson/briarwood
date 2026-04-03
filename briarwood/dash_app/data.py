from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from briarwood.dash_app.view_models import build_property_analysis_view
from briarwood.runner import run_report, run_report_from_listing_text, write_report_html
from briarwood.schemas import AnalysisReport


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"
SAVED_PROPERTY_DIR = DATA_DIR / "saved_properties"
LEGACY_MANUAL_ENTRY_DIR = DATA_DIR / "manual_entries"


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


def list_presets() -> list[PropertyPreset]:
    return list(PRESETS) + _saved_property_presets() + _legacy_manual_presets()


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
    preset_map = {preset.preset_id: preset for preset in list_presets()}
    return {preset_id: load_report_for_preset(preset_id) for preset_id in preset_ids if preset_id in preset_map}


def export_preset_tear_sheet(preset_id: str) -> Path:
    saved_path = _saved_property_path(preset_id) / "tear_sheet.html"
    if saved_path.exists():
        return saved_path
    report = load_report_for_preset(preset_id)
    filename = f"{preset_id}_tear_sheet.html"
    return write_report_html(report, OUTPUT_DIR / filename)


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
            "condition_profile_override": subject.get("condition_profile_override"),
            "condition_confirmed": _optional_bool(subject.get("condition_confirmed")),
            "capex_lane_override": subject.get("capex_lane_override"),
            "capex_confirmed": _optional_bool(subject.get("capex_confirmed")),
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
                "condition_assumption": {"status": manual_status(subject.get("condition_profile_override")), "source_name": "manual entry"},
                "capex_assumption": {"status": manual_status(subject.get("capex_lane_override")), "source_name": "manual entry"},
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
