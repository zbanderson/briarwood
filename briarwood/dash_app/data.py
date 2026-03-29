from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from briarwood.runner import run_report, run_report_from_listing_text, write_report_html
from briarwood.schemas import AnalysisReport


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"


@dataclass(frozen=True, slots=True)
class PropertyPreset:
    preset_id: str
    label: str
    description: str
    loader: Callable[[], AnalysisReport]


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

PRESET_MAP = {preset.preset_id: preset for preset in PRESETS}
DEFAULT_PRESET_IDS = ["briarwood-rd-belmar", "belmar-l-street"]

_REPORT_CACHE: dict[str, AnalysisReport] = {}


def list_presets() -> list[PropertyPreset]:
    return list(PRESETS)


def load_report_for_preset(preset_id: str) -> AnalysisReport:
    if preset_id not in PRESET_MAP:
        raise KeyError(f"Unknown property preset: {preset_id}")
    if preset_id not in _REPORT_CACHE:
        _REPORT_CACHE[preset_id] = PRESET_MAP[preset_id].loader()
    return _REPORT_CACHE[preset_id]


def load_reports(preset_ids: list[str]) -> dict[str, AnalysisReport]:
    return {preset_id: load_report_for_preset(preset_id) for preset_id in preset_ids if preset_id in PRESET_MAP}


def export_preset_tear_sheet(preset_id: str) -> Path:
    report = load_report_for_preset(preset_id)
    filename = f"{preset_id}_tear_sheet.html"
    return write_report_html(report, OUTPUT_DIR / filename)

