from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

from briarwood.agents.comparable_sales.store import JsonActiveListingStore
from briarwood.decision_engine import build_decision
from briarwood.evidence import (
    compute_confidence_breakdown,
    compute_critical_assumption_statuses,
    compute_metric_input_statuses,
)
from briarwood.recommendations import (
    recommendation_label_from_score,
    recommendation_rank,
)
from briarwood.modules.town_aggregation_diagnostics import get_town_context, normalize_town_name
from briarwood.modules.market_analyzer import MarketAnalysisOutput, analyze_markets
from briarwood.modules.hybrid_value import get_hybrid_value_payload
from briarwood.modules.value_finder import (
    PropertyValueFinderOutput,
    ValueFinderOutput,
    analyze_property_value_finder,
    analyze_value_finder,
)
from briarwood.local_intelligence.classification import bucket_town_signals
from briarwood.local_intelligence.models import ImpactDirection, SignalStatus, TownSignal
from briarwood.local_intelligence.summarize import build_town_summary
from briarwood.risk_bar import RiskBarItem, build_risk_bar
from briarwood.truth import classify_confidence
from briarwood.reports.section_helpers import (
    get_comparable_sales,
    get_current_value,
    get_income_support,
    get_rental_ease,
    get_scarcity_support,
    get_scenario_output,
    get_town_county_outlook,
    get_value_drivers,
)
from briarwood.reports.sections.conclusion_section import build_conclusion_section
from briarwood.reports.sections.thesis_section import build_thesis_section
from briarwood.schemas import AnalysisReport, InputCoverageStatus, PropertyInput, SectionEvidence

ROOT = Path(__file__).resolve().parents[2]
ACTIVE_LISTINGS_PATH = ROOT / "data" / "comps" / "active_listings.json"
VIEW_MODEL_CACHE_DIR = ROOT / ".cache" / "view_models"
MARKET_ANALYSIS_CACHE_TTL = timedelta(hours=12)


def _fmt_currency(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return f"${value:,.0f}"


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _property_identity(address: str | None, town: str | None = None, state: str | None = None) -> dict[str, str]:
    raw_address = _clean_text(address)
    parts = [part.strip() for part in raw_address.split(",") if part.strip()]
    street = parts[0] if parts else "Unknown Address"
    locality_town = _clean_text(town) or (parts[1] if len(parts) > 1 else "")
    locality_state = _clean_text(state)
    if not locality_state and len(parts) > 2:
        locality_state = parts[2].split()[0].strip()
    locality = ", ".join(part for part in [locality_town, locality_state] if part) or "Unknown Location"
    return {
        "street": street,
        "locality": locality,
        "town": locality_town,
        "state": locality_state,
        "full_address": raw_address or ", ".join(part for part in [street, locality] if part),
    }


def _maps_links(address: str | None, town: str | None = None, state: str | None = None) -> dict[str, str]:
    identity = _property_identity(address, town, state)
    query = quote_plus(identity["full_address"])
    return {
        "google": f"https://www.google.com/maps/search/?api=1&query={query}",
        "apple": f"https://maps.apple.com/?q={query}",
    }


def _maybe_external_url(value: str | None) -> str | None:
    normalized = _clean_text(value)
    if normalized.lower().startswith(("http://", "https://")):
        return normalized
    return None


def _fmt_currency_delta(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    sign = "+" if value >= 0 else "-"
    return f"{sign}${abs(value):,.0f}"


def _fmt_pct(value: float | None, *, scale_100: bool = True) -> str:
    if value is None:
        return "Unavailable"
    pct = value * 100 if scale_100 else value
    return f"{pct:.1f}%"


def _fmt_number(value: float | int | None, suffix: str = "") -> str:
    if value is None:
        return "Unavailable"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.1f}{suffix}"
    return f"{int(value):,}{suffix}"


def _parse_confidence_text(value: str | None) -> float | None:
    if not value or value == "Unavailable":
        return None
    cleaned = value.replace("%", "").strip()
    try:
        return float(cleaned) / 100.0
    except ValueError:
        return None


def _parse_currency_text(value: str | None) -> float | None:
    if not value or value == "Unavailable":
        return None
    cleaned = value.replace("$", "").replace(",", "").strip()
    sign = -1.0 if cleaned.startswith("-") else 1.0
    cleaned = cleaned.lstrip("+-").strip()
    try:
        return float(cleaned) * sign
    except ValueError:
        return None


def _scenario_stress_value(scenario: object) -> float | None:
    return getattr(scenario, "stress_case_value", None)


def _income_attr(income: object, name: str, default=None):
    return getattr(income, name, default)


def _income_list(income: object, name: str) -> list[float]:
    value = getattr(income, name, None)
    return value if isinstance(value, list) else []


def _location_support_state(report: AnalysisReport) -> tuple[str, str]:
    property_input = report.property_input
    location_module = report.module_results.get("location_intelligence")
    payload = getattr(location_module, "payload", None) if location_module is not None else None
    category_results = getattr(payload, "category_results", None)
    missing_inputs = set(getattr(payload, "missing_inputs", []) or [])

    if category_results:
        category_names = ", ".join(
            str(getattr(item, "category", "")).replace("_", " ").title()
            for item in category_results[:2]
            if getattr(item, "category", None)
        )
        detail = (
            f"Subject coordinates were benchmarked against nearby comp buckets for {category_names.lower()}."
            if category_names
            else "Subject coordinates were benchmarked against nearby geo comp buckets."
        )
        return "Geo-Benchmarked", detail
    if property_input is not None and property_input.latitude is not None and property_input.longitude is not None:
        if "landmark_points" in missing_inputs:
            return "Geocoded, Landmark Data Missing", "The property has coordinates, but Briarwood does not yet have landmark points to benchmark beach, park, or train distance for this town."
        return "Geocoded, Proxy-Based", "The property has coordinates, but location scoring still relies mostly on proxy signals rather than full landmark benchmarking."
    return "Address-Linked Only", "Maps can open from the address, but location scoring is still relying on town-level and zone-style proxies because subject coordinates are not attached."


def _location_anchor_summary(report: AnalysisReport) -> str:
    location_module = report.module_results.get("location_intelligence")
    payload = getattr(location_module, "payload", None) if location_module is not None else None
    category_results = getattr(payload, "category_results", None) or []
    if not category_results:
        return ""
    parts: list[str] = []
    for item in category_results[:3]:
        category = str(getattr(item, "category", "")).replace("_", " ").title()
        distance = getattr(item, "subject_distance_miles", None)
        if not category or distance is None:
            continue
        parts.append(f"{category} {distance:.2f} mi")
    return " • ".join(parts)


def _cost_val_metric(report: AnalysisReport, key: str) -> float | None:
    """Extract a metric from the cost_valuation module result."""
    mod = report.module_results.get("cost_valuation")
    if mod is None:
        return None
    val = mod.metrics.get(key)
    return float(val) if val is not None else None


def _fmt_ratio(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return f"{value:.2f}x"


def _rent_source_label(source_type: str) -> str:
    """Human-readable label for rent provenance (for trust calibration)."""
    mapping = {
        "manual_input": "(user provided)",
        "provided": "(user provided)",
        "estimated": "(estimated)",
        "missing": "(missing — using fallback)",
    }
    return mapping.get(source_type, "")


def _monthly_cost(report: AnalysisReport) -> float | None:
    metric = _cost_val_metric(report, "monthly_total_cost")
    if metric is not None:
        return metric
    income = report.module_results.get("income_support")
    if income is None:
        return None
    raw = income.metrics.get("gross_monthly_cost") or income.metrics.get("total_monthly_cost")
    return float(raw) if isinstance(raw, (int, float)) else None


def _rent_offset(report: AnalysisReport) -> float | None:
    income = report.module_results.get("income_support")
    if income is None:
        return None
    raw = income.metrics.get("effective_monthly_rent") or income.metrics.get("monthly_rent_estimate")
    return float(raw) if isinstance(raw, (int, float)) else None


def _net_monthly(report: AnalysisReport) -> float | None:
    monthly_cost = _monthly_cost(report)
    rent_offset = _rent_offset(report)
    if monthly_cost is not None and rent_offset is not None:
        return round(rent_offset - monthly_cost, 2)
    income = report.module_results.get("income_support")
    if income is None:
        return None
    raw = income.metrics.get("monthly_cash_flow")
    return float(raw) if isinstance(raw, (int, float)) else None


def _support_quality(report: AnalysisReport) -> str:
    comps = report.module_results.get("comparable_sales")
    payload = getattr(comps, "payload", None) if comps is not None else None
    selection = getattr(payload, "base_comp_selection", None)
    summary = getattr(selection, "support_summary", None)
    quality = getattr(summary, "support_quality", None)
    return str(quality or "")


def _adu_income_value(report: AnalysisReport) -> float | None:
    hybrid = report.module_results.get("hybrid_value")
    if hybrid is not None:
        raw = hybrid.metrics.get("rear_income_value")
        if isinstance(raw, (int, float)):
            return float(raw)
    comps = report.module_results.get("comparable_sales")
    payload = getattr(comps, "payload", None) if comps is not None else None
    analysis = getattr(payload, "comp_analysis", None)
    raw = getattr(analysis, "cottage_adu_value", None)
    return float(raw) if isinstance(raw, (int, float)) else None


def _expansion_score(report: AnalysisReport) -> float | None:
    comps = report.module_results.get("comparable_sales")
    payload = getattr(comps, "payload", None) if comps is not None else None
    analysis = getattr(payload, "comp_analysis", None)
    feature_engine = getattr(analysis, "feature_engine", None) or {}
    features = feature_engine.get("features", {}) if isinstance(feature_engine, dict) else {}
    expansion = features.get("expansion", {}) if isinstance(features, dict) else {}
    confidence_map = {"high": 1.0, "moderate": 0.7, "low": 0.35, "none": 0.0, "n/a": 0.0}
    confidence = confidence_map.get(str(expansion.get("confidence", "")).lower(), 0.0)
    present = bool(expansion.get("present"))
    return round(confidence if present else 0.0, 2)


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _coastal_profile_label(town_county: object) -> str:
    """Derive a coastal profile tag from the town_county outlook."""
    normalized = getattr(town_county, "normalized", None)
    if normalized is None:
        return ""
    inputs = getattr(normalized, "inputs", None)
    if inputs is None:
        return ""
    signal = getattr(inputs, "coastal_profile_signal", None)
    if signal is None or signal <= 0:
        return ""
    if signal >= 0.8:
        return "Beach Premium"
    if signal >= 0.5:
        return "Downtown Premium"
    return "Coastal"


def _module_confidence(report: AnalysisReport, module_name: str) -> float | None:
    module = report.module_results.get(module_name)
    return None if module is None else float(module.confidence)


def _safe_ratio(value: float | None, baseline: float | None) -> float | None:
    if value in (None, 0) or baseline in (None, 0):
        return None
    return round(float(value) / float(baseline), 3)


def _town_relative_opportunity_score(
    *,
    subject_ppsf_vs_town: float | None,
    subject_price_vs_town: float | None,
    town_context_confidence: float | None,
) -> float | None:
    scores: list[float] = []
    if subject_ppsf_vs_town is not None:
        if subject_ppsf_vs_town <= 0.85:
            scores.append(4.8)
        elif subject_ppsf_vs_town <= 0.95:
            scores.append(4.1)
        elif subject_ppsf_vs_town <= 1.05:
            scores.append(3.0)
        elif subject_ppsf_vs_town <= 1.15:
            scores.append(2.1)
        else:
            scores.append(1.3)
    if subject_price_vs_town is not None:
        if subject_price_vs_town <= 0.85:
            scores.append(4.4)
        elif subject_price_vs_town <= 0.95:
            scores.append(3.8)
        elif subject_price_vs_town <= 1.05:
            scores.append(3.0)
        elif subject_price_vs_town <= 1.15:
            scores.append(2.3)
        else:
            scores.append(1.5)
    if not scores:
        return None
    raw_score = sum(scores) / len(scores)
    confidence = town_context_confidence if town_context_confidence is not None else 0.0
    shrunk = 3.0 + (raw_score - 3.0) * max(0.25, min(confidence, 1.0))
    return round(shrunk, 2)


def _liquidity_metrics(report: AnalysisReport) -> tuple[dict[str, Any], list[str], list[str]]:
    module = report.module_results.get("liquidity_signal")
    if module is not None:
        payload = module.payload
        supporting = list(getattr(payload, "supporting_evidence", [])) if payload is not None else []
        unsupported = list(getattr(payload, "unsupported_claims", [])) if payload is not None else []
        return module.metrics, supporting, unsupported

    property_input = report.property_input
    rental_ease = report.module_results.get("rental_ease")
    town = report.module_results.get("town_county_outlook")
    comparable_sales = report.module_results.get("comparable_sales")
    dom = property_input.days_on_market if property_input else None
    rental_score = None if rental_ease is None else rental_ease.metrics.get("liquidity_score")
    market_view = None if town is None else town.metrics.get("liquidity_view")
    score = rental_score or (82.0 if dom is not None and dom <= 21 else 62.0 if dom is not None and dom <= 45 else 42.0 if dom is not None else 50.0)
    label = (
        "Strong Exit Liquidity" if float(score) >= 78 else
        "Normal Exit Liquidity" if float(score) >= 62 else
        "Mixed Exit Liquidity" if float(score) >= 45 else
        "Thin Exit Liquidity"
    )
    supporting = []
    if dom is not None:
        supporting.append(f"{dom} DOM is being used as the primary legacy liquidity proxy.")
    if market_view:
        supporting.append(f"Town/county liquidity backdrop reads {str(market_view).replace('_', ' ')}.")
    unsupported = ["Canonical liquidity was backfilled from older report outputs because this report predates the dedicated liquidity module."]
    return {
        "liquidity_score": score,
        "liquidity_label": label,
        "market_liquidity_view": market_view,
    }, supporting, unsupported


def _market_momentum_metrics(report: AnalysisReport) -> tuple[dict[str, Any], list[str], list[str]]:
    module = report.module_results.get("market_momentum_signal")
    if module is not None:
        payload = module.payload
        drivers = list(getattr(payload, "drivers", [])) if payload is not None else []
        unsupported = list(getattr(payload, "unsupported_claims", [])) if payload is not None else []
        return module.metrics, drivers, unsupported

    history = report.module_results.get("market_value_history")
    town = report.module_results.get("town_county_outlook")
    local = report.module_results.get("local_intelligence")
    one_year = None if history is None else history.metrics.get("one_year_change_pct")
    town_score = None if town is None else town.metrics.get("town_county_score")
    dev = None if local is None else local.metrics.get("development_activity_score")
    base = 50.0
    if isinstance(town_score, (int, float)):
        base = 0.6 * float(town_score) + 0.4 * base
    if isinstance(one_year, (int, float)):
        base += max(-12.0, min(float(one_year) * 250.0, 12.0))
    if isinstance(dev, (int, float)) and dev >= 65:
        base += 5.0
    score = round(max(0.0, min(base, 100.0)), 1)
    label = (
        "Supportive Momentum" if score >= 72 else
        "Constructive Momentum" if score >= 58 else
        "Mixed Momentum" if score >= 45 else
        "Weak Momentum"
    )
    drivers = []
    if isinstance(one_year, (int, float)):
        drivers.append(
            "positive recent price trend" if float(one_year) >= 0.03 else
            "negative recent price trend" if float(one_year) <= -0.02 else
            "flat recent price trend"
        )
    if isinstance(dev, (int, float)) and dev >= 65:
        drivers.append("active redevelopment pipeline")
    unsupported = ["Canonical market momentum was backfilled from older report outputs because this report predates the dedicated momentum module."]
    return {
        "market_momentum_score": score,
        "market_momentum_label": label,
    }, drivers, unsupported


def build_town_pulse_view_model_from_payload(
    payload: object,
    *,
    town: str,
    state: str,
) -> TownPulseViewModel | None:
    signals = _town_pulse_signals(payload, town=town, state=state)
    if not signals:
        return None
    summary = build_town_summary(town=town, state=state, signals=signals)
    buckets = bucket_town_signals(signals)
    bullish = [_town_pulse_item(signal) for signal in buckets["bullish"][:2]]
    bearish = [_town_pulse_item(signal) for signal in buckets["bearish"][:2]]
    watch = [_town_pulse_item(signal) for signal in buckets["watch"][:2]]
    key_signals = (bullish[:2] + bearish[:1] + watch[:1])[:4]
    return TownPulseViewModel(
        section_title="Town Pulse",
        confidence_label=summary.confidence_label,
        narrative_summary=summary.narrative_summary,
        bullish_signals=bullish,
        bearish_signals=bearish,
        watch_items=watch,
        key_signals=key_signals,
    )


def _town_pulse_signals(payload: object, *, town: str, state: str) -> list[TownSignal]:
    raw_signals = getattr(payload, "signals", None)
    signals: list[TownSignal] = []
    if isinstance(raw_signals, list):
        for raw_signal in raw_signals:
            if isinstance(raw_signal, TownSignal):
                signals.append(raw_signal)
    if signals:
        return signals

    projects = getattr(payload, "projects", None)
    if not isinstance(projects, list):
        return []

    fallback_signals: list[TownSignal] = []
    for index, project in enumerate(projects):
        title = _clean_text(getattr(project, "name", ""))
        if not title:
            continue
        confidence = float(getattr(project, "confidence", 0.0) or 0.0)
        status = _signal_status_from_text(getattr(project, "status", None))
        impact_direction = _impact_direction_from_text(getattr(project, "impact_direction", None), status=status)
        excerpt = _clean_text(getattr(project, "evidence_excerpt", None) or getattr(project, "notes", None) or title)
        now = datetime.now(timezone.utc)
        fallback_signals.append(
            TownSignal(
                id=f"fallback-town-pulse-{index}-{title.lower().replace(' ', '-')[:24]}",
                town=town,
                state=state,
                signal_type=_signal_type_from_text(getattr(project, "type", None)),
                title=title,
                source_document_id=f"fallback-{index}",
                source_type=_source_type_from_project_type(getattr(project, "type", None)),
                source_date=now,
                status=status,
                time_horizon=_time_horizon_from_text(getattr(project, "time_horizon", None), status=status),
                impact_direction=impact_direction,
                impact_magnitude=3,
                confidence=max(0.1, min(confidence, 1.0)),
                facts=list(getattr(project, "facts", []) or []),
                inference=_clean_text(getattr(project, "notes", None)) or None,
                affected_dimensions=[],
                evidence_excerpt=excerpt,
                created_at=now,
                updated_at=now,
                metadata={"location": _clean_text(getattr(project, "location", None)) or None},
            )
        )
    return fallback_signals
def _town_pulse_item(signal: TownSignal) -> TownPulseSignalViewModel:
    tone = (
        "positive" if signal.impact_direction == ImpactDirection.POSITIVE else
        "negative" if signal.impact_direction == ImpactDirection.NEGATIVE else
        "warning"
    )
    status_tag = signal.status.value.replace("_", " ").title()
    confidence_tag = "High" if signal.confidence >= 0.75 else "Medium" if signal.confidence >= 0.55 else "Low"
    description = signal.inference or (signal.facts[0] if signal.facts else signal.evidence_excerpt)
    return TownPulseSignalViewModel(
        title=signal.title,
        status_tag=status_tag,
        confidence_tag=confidence_tag,
        tone=tone,
        description=description,
        evidence_excerpt=signal.evidence_excerpt,
        source_type=signal.source_type.value.replace("_", " ").title(),
        source_date_text=signal.source_date.strftime("%b %d, %Y") if signal.source_date is not None else "",
        source_url=signal.source_url,
        reconciliation_tag=(
            signal.reconciliation_status.value.replace("_", " ").title()
            if signal.reconciliation_status is not None
            else None
        ),
    )


def _signal_status_from_text(value: object) -> SignalStatus:
    text = _clean_text(value).lower().replace(" ", "_")
    for status in SignalStatus:
        if status.value == text:
            return status
    return SignalStatus.MENTIONED


def _impact_direction_from_text(value: object, *, status: SignalStatus) -> ImpactDirection:
    text = _clean_text(value).lower()
    for direction in ImpactDirection:
        if direction.value == text:
            return direction
    if status == SignalStatus.REJECTED:
        return ImpactDirection.NEGATIVE
    if status in {SignalStatus.APPROVED, SignalStatus.FUNDED, SignalStatus.IN_PROGRESS, SignalStatus.COMPLETED}:
        return ImpactDirection.POSITIVE
    return ImpactDirection.MIXED


def _signal_type_from_text(value: object):
    text = _clean_text(value).lower().replace("-", "_").replace(" ", "_")
    for signal_type in SignalType:
        if signal_type.value == text:
            return signal_type
    return SignalType.OTHER


def _source_type_from_project_type(value: object):
    from briarwood.local_intelligence.models import SourceType
    text = _clean_text(value).lower()
    if "zoning" in text:
        return SourceType.ZONING_BOARD_MINUTES
    if "ordinance" in text or "regulation" in text:
        return SourceType.ORDINANCE
    return SourceType.OTHER


def _time_horizon_from_text(value: object, *, status: SignalStatus):
    from briarwood.local_intelligence.models import TimeHorizon
    text = _clean_text(value).lower().replace(" ", "_")
    if text in {TimeHorizon.NEAR_TERM.value, TimeHorizon.MEDIUM_TERM.value, TimeHorizon.LONG_TERM.value}:
        return TimeHorizon(text)
    if status in {SignalStatus.APPROVED, SignalStatus.FUNDED, SignalStatus.IN_PROGRESS, SignalStatus.COMPLETED}:
        return TimeHorizon.NEAR_TERM
    return TimeHorizon.MEDIUM_TERM


def _coverage_status_label(status: InputCoverageStatus) -> str:
    return status.value.replace("_", " ").title()


@dataclass(slots=True)
class MetricChip:
    label: str
    value: str
    tone: str = "neutral"
    subtitle: str = ""


@dataclass(slots=True)
class SectionConfidenceItem:
    label: str
    confidence: float


@dataclass(slots=True)
class ConfidenceFactorItem:
    """One factor contributing to the global confidence level."""
    label: str
    detail: str
    level: str  # "strong", "ok", "weak"


@dataclass(slots=True)
class InputImpactItem:
    """A missing input and the confidence improvement it would yield."""
    field_label: str
    impact_description: str
    affected_component: str


@dataclass(slots=True)
class ConfidenceComponentItem:
    key: str
    label: str
    confidence: float
    weight: float
    reason: str


@dataclass(slots=True)
class AssumptionTransparencyItem:
    label: str
    value: str
    source_kind: str
    source_label: str
    note: str = ""


@dataclass(slots=True)
class AssumptionStatusItem:
    key: str
    label: str
    status: str
    value: str
    source_label: str
    note: str = ""
    affected_components: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MetricInputStatusItem:
    key: str
    label: str
    status: str
    facts_used: list[str] = field(default_factory=list)
    user_inputs_used: list[str] = field(default_factory=list)
    assumptions_used: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    confidence_impact: str = ""
    prompt_fields: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EvidenceViewModel:
    evidence_mode: str
    sourced_inputs: list[str] = field(default_factory=list)
    user_supplied_inputs: list[str] = field(default_factory=list)
    estimated_inputs: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    confidence_components: list[ConfidenceComponentItem] = field(default_factory=list)
    confidence_notes: list[str] = field(default_factory=list)
    assumption_statuses: list[AssumptionStatusItem] = field(default_factory=list)
    transparency_items: list[AssumptionTransparencyItem] = field(default_factory=list)
    metric_statuses: list[MetricInputStatusItem] = field(default_factory=list)
    gap_prompt_fields: list[str] = field(default_factory=list)
    section_confidences: list[SectionConfidenceItem] = field(default_factory=list)


@dataclass(slots=True)
class ValueViewModel:
    component_rows: list[tuple[str, str, str]] = field(default_factory=list)
    market_anchors: list["MarketAnchorViewModel"] = field(default_factory=list)
    value_drivers: list["ValueDriverViewModel"] = field(default_factory=list)
    value_bridge: list["ValueBridgeStepViewModel"] = field(default_factory=list)
    pricing_view: str = ""
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass(slots=True)
class MarketAnchorViewModel:
    label: str
    range_text: str
    confidence_text: str
    detail: str


@dataclass(slots=True)
class ValueDriverViewModel:
    label: str
    impact_text: str
    confidence_text: str
    description: str


@dataclass(slots=True)
class ValueBridgeStepViewModel:
    label: str
    value_text: str
    confidence_text: str


@dataclass(slots=True)
class RiskLocationViewModel:
    risk_summary: str
    risk_score: float
    town_score: float
    town_label: str
    scarcity_score: float
    liquidity_score: float
    liquidity_label: str
    market_momentum_score: float
    market_momentum_label: str
    flood_risk: str
    liquidity_view: str
    # Surfaced risk/market signals (Group 2)
    stress_case_value: float | None = None
    stress_case_text: str = "Unavailable"
    stress_drawdown_pct: float | None = None
    momentum_direction: str = ""  # "accelerating" / "steady" / "decelerating"
    # Location context (Group 3)
    school_signal: float | None = None
    school_signal_text: str = ""
    coastal_profile_label: str = ""  # "Beach Premium", "Downtown Premium", or ""
    location_support_label: str = "Proxy-Based"
    location_support_detail: str = ""
    location_anchor_summary: str = ""
    # Scarcity breakdown (Group 5)
    land_scarcity_score: float | None = None
    location_scarcity_score: float | None = None
    drivers: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    town_pulse: TownPulseViewModel | None = None


@dataclass(slots=True)
class TownPulseSignalViewModel:
    title: str
    status_tag: str
    confidence_tag: str
    tone: str
    description: str
    evidence_excerpt: str
    source_type: str = ""
    source_date_text: str = ""
    source_url: str | None = None
    reconciliation_tag: str | None = None


@dataclass(slots=True)
class TownPulseViewModel:
    section_title: str
    confidence_label: str
    narrative_summary: str
    bullish_signals: list[TownPulseSignalViewModel] = field(default_factory=list)
    bearish_signals: list[TownPulseSignalViewModel] = field(default_factory=list)
    watch_items: list[TownPulseSignalViewModel] = field(default_factory=list)
    key_signals: list[TownPulseSignalViewModel] = field(default_factory=list)


@dataclass(slots=True)
class ForwardViewModel:
    summary: str
    confidence: float
    bull_value_text: str
    base_value_text: str
    bear_value_text: str
    stress_case_value_text: str
    upside_pct_text: str
    downside_pct_text: str
    market_drift_text: str
    location_premium_text: str
    risk_discount_text: str
    optionality_premium_text: str


@dataclass(slots=True)
class IncomeSupportViewModel:
    summary: str
    confidence: float
    rental_ease_label: str
    estimated_days_to_rent_text: str
    total_rent_text: str
    num_units_text: str
    avg_rent_per_unit_text: str
    income_support_ratio_text: str
    monthly_cash_flow_text: str
    operating_cash_flow_text: str
    rent_source_type: str
    risk_view: str
    price_to_rent_text: str
    ptr_classification: str
    # Surfaced investor metrics (Group 1)
    dscr: float | None = None
    dscr_text: str = "Unavailable"
    cash_on_cash_return: float | None = None
    cash_on_cash_return_text: str = "Unavailable"
    gross_yield: float | None = None
    gross_yield_text: str = "Unavailable"
    # Rent source label for trust calibration (Group 4, item 9)
    rent_source_label: str = ""
    unit_breakdown: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CompareMetricRow:
    metric: str
    values: dict[str, str]
    raw_values: dict[str, float | None] = field(default_factory=dict)
    deltas: dict[str, str] = field(default_factory=dict)  # label → "+$50K (+6.3%)"
    winner: str = ""  # label of the winning property for this metric
    higher_is_better: bool = True


@dataclass(slots=True)
class CompReviewRow:
    address: str
    street: str
    locality: str
    sale_price: str
    adjusted_price: str
    fit: str
    status: str
    verification: str
    condition: str
    capex_lane: str
    source_ref: str
    google_maps_url: str
    apple_maps_url: str
    why_comp: str
    cautions: str
    external_url: str | None = None
    thumbnail_url: str | None = None


@dataclass(slots=True)
class ActiveListingViewRow:
    address: str
    street: str
    locality: str
    list_price: str
    status: str
    beds: str
    baths: str
    sqft: str
    dom: str
    condition: str
    source_ref: str
    google_maps_url: str
    apple_maps_url: str
    external_url: str | None = None
    thumbnail_url: str | None = None


@dataclass(slots=True)
class CompsViewModel:
    comparable_value_text: str
    comp_count_text: str
    confidence_text: str
    active_listing_count_text: str
    dataset_name: str
    verification_summary: str
    curation_summary: str
    screening_summary: str
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    rows: list[CompReviewRow] = field(default_factory=list)
    active_listing_rows: list[ActiveListingViewRow] = field(default_factory=list)
    # Hybrid valuation fields for multi-unit properties
    is_hybrid_valuation: bool = False
    primary_dwelling_value_text: str = ""
    additional_unit_income_value_text: str = ""
    additional_unit_count: int = 0
    additional_unit_annual_income_text: str = ""
    additional_unit_cap_rate_text: str = ""
    hybrid_valuation_note: str = ""


@dataclass(slots=True)
class DecisionViewModel:
    recommendation: str
    conviction_score: int
    conviction: float
    best_fit: str
    confidence_level: str
    thesis: str
    primary_reason: str
    secondary_reason: str
    required_beliefs: list[str]
    decisive_driver: str
    decision_drivers: dict[str, list["DecisionDriverItem"]]
    break_condition: str
    required_belief: str
    risk_statement: str
    summary_view: str
    primary_risk: str
    what_changes_view: str
    primary_driver: str
    fit_context: str = ""
    supporting_factors: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    disqualifiers: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DecisionDriverItem:
    metric: str
    direction: str  # "+" or "-"
    strength: str
    summary: str


@dataclass(slots=True)
class PositioningSummaryViewModel:
    entry_basis_label: str
    income_support_label: str
    capex_load_label: str
    liquidity_profile_label: str
    optionality_label: str
    risk_skew_label: str
    summary_line: str


@dataclass(slots=True)
class ReportCardContributionItem:
    factor_name: str
    percentage_impact: int
    explanation: str


@dataclass(slots=True)
class ReportCardViewModel:
    positive: list[ReportCardContributionItem] = field(default_factory=list)
    negative: list[ReportCardContributionItem] = field(default_factory=list)
    factor_scores: dict[str, float] = field(default_factory=dict)
    factor_contributions: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class PropertyEvidenceSummaryViewModel:
    structural_status: str
    tax_status: str
    sale_status: str
    rent_status: str
    comp_eligibility_status: str
    key_notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HybridValueViewModel:
    is_hybrid: bool
    reason: str
    primary_house_value: str
    rear_income_value: str
    optionality_premium_value: str
    total_hybrid_value: str
    confidence: float
    notes: list[str] = field(default_factory=list)
    narrative: str = ""


@dataclass(slots=True)
class ValueFinderViewModel:
    bullets: list[str] = field(default_factory=list)
    supporting_signal: str = ""
    confidence_note: str = ""


@dataclass(slots=True)
class DecisionMetrics:
    fv_vs_ask_pct: float | None = None
    monthly_carry: float | None = None
    confidence: float = 0.0


@dataclass(slots=True)
class RiskMetrics:
    price_gap_pct: float | None = None
    monthly_loss: float | None = None
    liquidity_score: float | None = None
    execution_risk: str = ""
    confidence: float = 0.0


@dataclass(slots=True)
class ValueMetrics:
    adu_income: float | None = None
    expansion_score: float | None = None
    mispricing_pct: float | None = None
    market_tailwind: float | None = None


@dataclass(slots=True)
class PriceSupportMetrics:
    fair_value: float | None = None
    value_range_low: float | None = None
    value_range_high: float | None = None
    comp_count: int = 0
    support_quality: str = ""


@dataclass(slots=True)
class FinancialMetrics:
    monthly_cost: float | None = None
    rent_offset: float | None = None
    net_monthly: float | None = None
    break_even: bool = False


@dataclass(slots=True)
class RiskQuestionViewModel:
    metrics: RiskMetrics
    risk_bar: list[RiskBarItem] = field(default_factory=list)
    summary: str = ""
    top_risks: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ValueQuestionViewModel:
    metrics: ValueMetrics
    value_finder: ValueFinderViewModel | None = None
    hybrid_value: HybridValueViewModel | None = None


@dataclass(slots=True)
class PriceSupportQuestionViewModel:
    metrics: PriceSupportMetrics
    ask_price: float | None
    fair_value: float | None
    value_low: float | None
    value_high: float | None
    mispricing_amount: float | None
    mispricing_pct: float | None
    pricing_view: str
    all_in_basis: float | None
    capex_basis_used: float | None
    capex_basis_source: str
    net_opportunity_delta_value: float | None
    net_opportunity_delta_pct: float | None
    value: ValueViewModel
    comps: CompsViewModel


@dataclass(slots=True)
class FinancialsQuestionViewModel:
    metrics: FinancialMetrics
    income_support: IncomeSupportViewModel
    forward: ForwardViewModel
    base_case: float | None
    bull_case: float | None
    bear_case: float | None
    stress_case: float | None


@dataclass(slots=True)
class PropertyDecisionViewModel:
    decision: DecisionViewModel | None
    decision_metrics: DecisionMetrics
    risk: RiskQuestionViewModel
    value: ValueQuestionViewModel
    price_support: PriceSupportQuestionViewModel
    financials: FinancialsQuestionViewModel


@dataclass(slots=True)
class ValueFinderCandidateViewModel:
    property_id: str
    address: str
    town: str
    opportunity_signal: str
    pricing_posture: str
    short_summary: str
    ask_price_text: str
    briarwood_value_text: str
    dom_text: str
    value_gap_text: str


@dataclass(slots=True)
class MarketViewModel:
    town_name: str
    market_signal: str
    trend: str
    key_metrics: dict[str, str] = field(default_factory=dict)
    signals: list[str] = field(default_factory=list)
    score: float | None = None
    town_slug: str = ""


@dataclass(slots=True)
class MarketsPageViewModel:
    markets: list[MarketViewModel] = field(default_factory=list)
    selected_town: str | None = None
    selected_market: MarketAnalysisOutput | None = None
    sort_mode: str = "strongest"


@dataclass(slots=True)
class PropertyAnalysisView:
    property_id: str
    label: str
    address: str
    evidence_mode: str
    condition_profile: str
    capex_lane: str
    overall_confidence: float
    property_decision_view: PropertyDecisionViewModel
    evidence: EvidenceViewModel
    positioning_summary: PositioningSummaryViewModel | None = None
    report_card: ReportCardViewModel = field(default_factory=ReportCardViewModel)
    metric_chips: list[MetricChip] = field(default_factory=list)
    top_positives: list[str] = field(default_factory=list)
    risk_location: RiskLocationViewModel | None = None
    town_context: dict[str, Any] = field(default_factory=dict)
    compare_metrics: dict[str, Any] = field(default_factory=dict)
    # Defaults transparency
    defaults_applied: dict[str, str] = field(default_factory=dict)
    geocoded: bool = False
    # Scoring layer
    final_score: float | None = None
    recommendation_tier: str | None = None
    recommendation_action: str | None = None
    score_narrative: str | None = None
    category_scores: Any | None = None  # dict[str, CategoryScore] from engine
    lens_scores: Any | None = None  # LensScores from decision_model
    # Confidence layer
    confidence_level: str = "Medium"  # "High", "Medium", "Low"
    confidence_factors: list[ConfidenceFactorItem] = field(default_factory=list)
    top_input_impacts: list[InputImpactItem] = field(default_factory=list)
    markets: list[MarketViewModel] = field(default_factory=list)
    market_view: MarketsPageViewModel | None = None
    property_evidence_summary: PropertyEvidenceSummaryViewModel | None = None
    # Price sensitivity
    deal_curve: list[dict] = field(default_factory=list)
    deal_curve_thresholds: dict | None = None

    @property
    def valuation(self) -> ValueViewModel:
        return self.property_decision_view.price_support.value

    @property
    def decision(self) -> DecisionViewModel | None:
        return self.property_decision_view.decision

    @property
    def risk_bar(self) -> list[RiskBarItem]:
        return self.property_decision_view.risk.risk_bar

    @property
    def top_risks(self) -> list[str]:
        return self.property_decision_view.risk.top_risks

    @property
    def value_finder(self) -> ValueFinderViewModel | None:
        return self.property_decision_view.value.value_finder

    @property
    def hybrid_value(self) -> HybridValueViewModel | None:
        return self.property_decision_view.value.hybrid_value

    @property
    def ask_price(self) -> float | None:
        return self.property_decision_view.price_support.ask_price

    @property
    def bcv(self) -> float | None:
        return self.property_decision_view.price_support.fair_value

    @property
    def value_low(self) -> float | None:
        return self.property_decision_view.price_support.value_low

    @property
    def value_high(self) -> float | None:
        return self.property_decision_view.price_support.value_high

    @property
    def mispricing_amount(self) -> float | None:
        return self.property_decision_view.price_support.mispricing_amount

    @property
    def mispricing_pct(self) -> float | None:
        return self.property_decision_view.price_support.mispricing_pct

    @property
    def pricing_view(self) -> str:
        return self.property_decision_view.price_support.pricing_view

    @property
    def all_in_basis(self) -> float | None:
        return self.property_decision_view.price_support.all_in_basis

    @property
    def capex_basis_used(self) -> float | None:
        return self.property_decision_view.price_support.capex_basis_used

    @property
    def capex_basis_source(self) -> str:
        return self.property_decision_view.price_support.capex_basis_source

    @property
    def net_opportunity_delta_value(self) -> float | None:
        return self.property_decision_view.price_support.net_opportunity_delta_value

    @property
    def net_opportunity_delta_pct(self) -> float | None:
        return self.property_decision_view.price_support.net_opportunity_delta_pct

    @property
    def value(self) -> ValueViewModel:
        return self.property_decision_view.price_support.value

    @property
    def comps(self) -> CompsViewModel:
        return self.property_decision_view.price_support.comps

    @property
    def income_support(self) -> IncomeSupportViewModel:
        return self.property_decision_view.financials.income_support

    @property
    def forward(self) -> ForwardViewModel:
        return self.property_decision_view.financials.forward

    @property
    def base_case(self) -> float | None:
        return self.property_decision_view.financials.base_case

    @property
    def bull_case(self) -> float | None:
        return self.property_decision_view.financials.bull_case

    @property
    def bear_case(self) -> float | None:
        return self.property_decision_view.financials.bear_case

    @property
    def stress_case(self) -> float | None:
        return self.property_decision_view.financials.stress_case

    @property
    def income_support_label(self) -> str:
        return _income_support_label(_parse_currency_text(self.income_support.monthly_cash_flow_text), None)

    @property
    def capex_load_label(self) -> str:
        return _capex_load_label(self.capex_lane.lower() if self.capex_lane else "", None)

    @property
    def liquidity_profile_label(self) -> str:
        for item in self.risk_bar:
            if item.name.lower() == "liquidity":
                return item.label
        return "Mixed Liquidity"

    @property
    def optionality_label(self) -> str:
        if self.value_finder and self.value_finder.bullets:
            return "Supported Edge"
        return "Limited Edge"

    @property
    def buyer_fit(self) -> list[str]:
        if self.decision is None:
            return []
        values = [self.decision.best_fit, self.decision.fit_context]
        return [item for item in values if item]

    @property
    def memo_summary(self) -> str:
        if self.decision is None:
            return ""
        return self.decision.summary_view or self.decision.primary_reason


def _coverage_lists(property_input: PropertyInput | None) -> tuple[list[str], list[str], list[str], list[str]]:
    if property_input is None or property_input.source_metadata is None:
        return [], [], [], []
    sourced: list[str] = []
    user_supplied: list[str] = []
    estimated: list[str] = []
    missing: list[str] = []
    for key, item in property_input.source_metadata.source_coverage.items():
        label = key.replace("_", " ")
        if item.status is InputCoverageStatus.SOURCED:
            sourced.append(label)
        elif item.status is InputCoverageStatus.USER_SUPPLIED:
            user_supplied.append(label)
        elif item.status is InputCoverageStatus.ESTIMATED:
            estimated.append(label)
        else:
            missing.append(label)
    return sorted(sourced), sorted(user_supplied), sorted(estimated), sorted(missing)


def _collect_unsupported_claims(report: AnalysisReport) -> list[str]:
    claims: list[str] = []
    for module in report.module_results.values():
        payload = module.payload
        if hasattr(payload, "unsupported_claims"):
            for claim in getattr(payload, "unsupported_claims"):
                if claim not in claims:
                    claims.append(claim)
    return claims


def _section_confidences(report: AnalysisReport) -> list[SectionConfidenceItem]:
    labels = {
        "current_value": "Value",
        "bull_base_bear": "Forward",
        "income_support": "Income",
        "rental_ease": "Rental",
        "town_county_outlook": "Location",
        "scarcity_support": "Scarcity",
        "comparable_sales": "Comps",
    }
    items: list[SectionConfidenceItem] = []
    for module_name, label in labels.items():
        module = report.module_results.get(module_name)
        if module is None:
            continue
        items.append(SectionConfidenceItem(label=label, confidence=float(module.confidence)))
    return items


def _compute_confidence_level(
    report: AnalysisReport,
    overall_confidence: float,
) -> tuple[str, list[ConfidenceFactorItem]]:
    """Compute shared confidence band (High/Medium/Low) with factor breakdown."""
    factors: list[ConfidenceFactorItem] = []

    # 1. Comp quality
    comp_mod = report.module_results.get("comparable_sales")
    comp_count = int(comp_mod.metrics.get("comp_count", 0)) if comp_mod else 0
    if comp_count >= 5:
        factors.append(ConfidenceFactorItem("Comp quality", f"{comp_count} verified comps", "strong"))
    elif comp_count >= 3:
        factors.append(ConfidenceFactorItem("Comp quality", f"{comp_count} comps (limited)", "ok"))
    else:
        factors.append(ConfidenceFactorItem("Comp quality", f"{comp_count} comps (thin)", "weak"))

    # 2. Income data
    income_mod = report.module_results.get("income_support")
    rent_source = str(income_mod.metrics.get("rent_source_type", "missing")) if income_mod else "missing"
    if rent_source in ("manual_input", "provided"):
        factors.append(ConfidenceFactorItem("Income data", "User provided", "strong"))
    elif rent_source == "estimated":
        factors.append(ConfidenceFactorItem("Income data", "Estimated", "ok"))
    else:
        factors.append(ConfidenceFactorItem("Income data", "Missing — using fallback", "weak"))

    # 3. Town data
    town_mod = report.module_results.get("town_county_outlook")
    town_conf = town_mod.confidence if town_mod else 0.0
    if town_conf >= 0.75:
        factors.append(ConfidenceFactorItem("Town data", "Full coverage", "strong"))
    elif town_conf >= 0.50:
        factors.append(ConfidenceFactorItem("Town data", "Partial coverage", "ok"))
    else:
        factors.append(ConfidenceFactorItem("Town data", "Limited or missing", "weak"))

    # 4. Missing inputs
    pi = report.property_input
    critical_missing: list[str] = []
    if pi:
        if pi.taxes is None:
            critical_missing.append("taxes")
        if pi.insurance is None:
            critical_missing.append("insurance")
        if pi.estimated_monthly_rent is None:
            critical_missing.append("rent")
    non_critical_count = len(critical_missing)
    if non_critical_count == 0:
        factors.append(ConfidenceFactorItem("Missing inputs", "None critical", "strong"))
    elif non_critical_count <= 2:
        factors.append(ConfidenceFactorItem("Missing inputs", f"{non_critical_count} non-critical ({', '.join(critical_missing)})", "ok"))
    else:
        factors.append(ConfidenceFactorItem("Missing inputs", f"{non_critical_count} gaps ({', '.join(critical_missing)})", "weak"))

    assessment = classify_confidence(
        overall_confidence=overall_confidence,
        comp_count=comp_count,
        rent_source=rent_source,
        town_confidence=float(town_conf),
    )

    return assessment.band, factors


_INPUT_IMPACT_MAP: dict[str, tuple[str, str]] = {
    "estimated_monthly_rent": ("Add monthly rent estimate", "income"),
    "unit_rents": ("Add unit-level rents", "income"),
    "taxes": ("Add property taxes", "income"),
    "insurance": ("Add insurance cost", "income"),
    "repair_capex_budget": ("Add renovation/CapEx budget", "capex"),
    "condition_profile_override": ("Confirm property condition", "capex"),
    "condition_confirmed": ("Confirm condition assessment", "capex"),
    "capex_lane_override": ("Override CapEx lane", "capex"),
    "down_payment_percent": ("Set down payment %", "income"),
    "interest_rate": ("Set interest rate", "income"),
    "loan_term_years": ("Set loan term", "income"),
    "local_documents": ("Add local market intel", "market"),
    "market_price_to_rent_benchmark": ("Add price-to-rent benchmark", "income"),
}


def _compute_top_input_impacts(
    metric_statuses: list[object],
    confidence_breakdown: object,
) -> list[InputImpactItem]:
    """Identify the top 3 missing inputs that would most improve confidence."""
    # Build a priority list from metric statuses that are estimated/unresolved
    seen: set[str] = set()
    candidates: list[InputImpactItem] = []
    # Map component keys to their current confidence for impact estimation
    component_conf = {c.key: c.confidence for c in confidence_breakdown.components}

    for status in metric_statuses:
        if status.status == "fact_based":
            continue
        for field_name in status.prompt_fields:
            if field_name in seen:
                continue
            seen.add(field_name)
            label, component = _INPUT_IMPACT_MAP.get(field_name, (field_name.replace("_", " ").title(), "general"))
            current_conf = component_conf.get(component, 0.65)
            # Estimate impact: gap between current and 0.90, scaled
            gap = max(0.90 - current_conf, 0.0)
            impact_pct = round(gap * 100 * 0.4, 0)  # ~40% of the gap as realistic improvement
            if impact_pct < 1:
                continue
            candidates.append(InputImpactItem(
                field_label=label,
                impact_description=f"+{impact_pct:.0f}% confidence in {component} assessment",
                affected_component=component,
            ))

    # Sort by implied impact (descending) and take top 3
    candidates.sort(key=lambda c: float(c.impact_description.split("%")[0].replace("+", "")), reverse=True)
    return candidates[:3]


def _assumption_status_items(report: AnalysisReport) -> list[AssumptionStatusItem]:
    return [
        AssumptionStatusItem(
            key=item.key,
            label=item.label,
            status=item.status,
            value=item.value,
            source_label=item.source_label,
            note=item.note,
            affected_components=list(item.affected_components),
        )
        for item in compute_critical_assumption_statuses(report)
    ]


def _metric_chips(
    *,
    ask_price: float | None,
    bcv: float | None,
    value_low: float | None,
    value_high: float | None,
    mispricing_amount: float | None,
    mispricing_pct: float | None,
    base_case: float | None,
    confidence: float,
) -> list[MetricChip]:
    gap_tone = "positive" if (mispricing_amount or 0) >= 0 else "negative"
    return [
        MetricChip(label="Ask", value=_fmt_currency(ask_price)),
        MetricChip(label="Fair Value", value=_fmt_currency(bcv)),
        MetricChip(
            label="Gap vs Ask",
            value=f"{_fmt_currency_delta(mispricing_amount)} | {_fmt_pct(mispricing_pct, scale_100=False)}",
            tone=gap_tone,
        ),
        MetricChip(label="BCV Range", value=f"{_fmt_currency(value_low)} - {_fmt_currency(value_high)}"),
        MetricChip(label="Base Case", value=_fmt_currency(base_case)),
        MetricChip(label="Confidence", value=_fmt_pct(confidence)),
    ]


def _component_rows(report: AnalysisReport) -> list[tuple[str, str, str]]:
    current_value = get_current_value(report)
    rows = [
        ("Comparable Sales", _fmt_currency(current_value.components.comparable_sales_value), _fmt_pct(current_value.weights.comparable_sales_weight)),
        ("Market-Adjusted", _fmt_currency(current_value.components.market_adjusted_value), _fmt_pct(current_value.weights.market_adjusted_weight)),
        ("Listing-Aligned", _fmt_currency(current_value.components.backdated_listing_value), _fmt_pct(current_value.weights.backdated_listing_weight)),
        ("Income-Supported", _fmt_currency(current_value.components.income_supported_value), _fmt_pct(current_value.weights.income_weight)),
        (
            "Town-Aware Prior",
            _fmt_currency(getattr(current_value.components, "town_prior_value", None)),
            _fmt_pct(getattr(current_value.weights, "town_prior_weight", None)),
        ),
    ]
    return rows


def _fmt_range(low: float | None, midpoint: float | None, high: float | None) -> str:
    if midpoint is not None and low is not None and high is not None:
        return f"{_fmt_currency(low)} - {_fmt_currency(high)}"
    if midpoint is not None:
        return _fmt_currency(midpoint)
    return "Unavailable"


def _market_anchor_rows(report: AnalysisReport) -> list[MarketAnchorViewModel]:
    current_value = get_current_value(report)
    anchors = [
        ("Direct Comps", getattr(current_value, "direct_value_range", None)),
        ("Income-Adjusted", getattr(current_value, "income_adjusted_value_range", None)),
        ("Location Adjustment", getattr(current_value, "location_adjustment_range", None)),
        ("Lot Adjustment", getattr(current_value, "lot_adjustment_range", None)),
        ("Blended Range", getattr(current_value, "blended_value_range", None)),
    ]
    rows: list[MarketAnchorViewModel] = []
    for label, anchor in anchors:
        if anchor is None:
            continue
        rows.append(
            MarketAnchorViewModel(
                label=label,
                range_text=_fmt_range(getattr(anchor, "low", None), getattr(anchor, "midpoint", None), getattr(anchor, "high", None)),
                confidence_text=_fmt_pct(getattr(anchor, "confidence", None)),
                detail=getattr(anchor, "explanation", "") or "No detail available.",
            )
        )
    return rows


def _value_driver_rows(report: AnalysisReport) -> tuple[list[ValueDriverViewModel], list[ValueBridgeStepViewModel]]:
    try:
        payload = get_value_drivers(report)
    except (KeyError, TypeError):
        return [], []
    drivers = [
        ValueDriverViewModel(
            label=item.label,
            impact_text=_fmt_currency_delta(item.estimated_value_impact),
            confidence_text=_fmt_pct(item.confidence),
            description=item.description,
        )
        for item in payload.drivers
    ]
    bridge = [
        ValueBridgeStepViewModel(
            label=item.label,
            value_text=_fmt_currency(item.value),
            confidence_text=_fmt_pct(item.confidence),
        )
        for item in payload.bridge
    ]
    return drivers, bridge


def _comp_rows(report: AnalysisReport) -> list[CompReviewRow]:
    output = get_comparable_sales(report)
    rows: list[CompReviewRow] = []
    for comp in output.comps_used:
        identity = _property_identity(getattr(comp, "address", None), getattr(comp, "town", None), getattr(comp, "state", None))
        maps = _maps_links(identity["full_address"], identity["town"], identity["state"])
        rows.append(
            CompReviewRow(
                address=identity["full_address"],
                street=identity["street"],
                locality=identity["locality"],
                sale_price=_fmt_currency(comp.sale_price),
                adjusted_price=_fmt_currency(comp.adjusted_price),
                fit=comp.fit_label.title(),
                status=(comp.comp_status or "unknown").replace("_", " ").title(),
                verification=(comp.sale_verification_status or "unverified").replace("_", " ").title(),
                condition=(comp.condition_profile or "Unavailable").replace("_", " ").title(),
                capex_lane=(comp.capex_lane or "Unavailable").replace("_", " ").title(),
                source_ref=comp.source_ref or "Unavailable",
                google_maps_url=maps["google"],
                apple_maps_url=maps["apple"],
                external_url=_maybe_external_url(comp.source_ref),
                why_comp="; ".join(comp.why_comp) or "Unavailable",
                cautions="; ".join(comp.cautions) or "",
            )
        )
    return rows


def _screening_summary(report: AnalysisReport) -> str:
    output = get_comparable_sales(report)
    reasons = ", ".join(
        f"{reason.replace('_', ' ')}: {count}"
        for reason, count in sorted(output.rejection_reasons.items())
    )
    return f"{output.comp_count} kept | {output.rejected_count} screened out" + (f" | {reasons}" if reasons else "")


def _market_signal_label(metrics: dict[str, Any]) -> str:
    buyer_vs_seller = _as_float(metrics.get("buyer_vs_seller_score"))
    sell_through = _as_float(metrics.get("sell_through_rate"))
    avg_dom = _as_float(metrics.get("avg_dom"))
    if (
        (buyer_vs_seller is not None and buyer_vs_seller >= 6.6)
        or (sell_through is not None and sell_through >= 0.35)
        or (avg_dom is not None and avg_dom <= 25)
    ):
        return "Tight Market"
    if (
        (buyer_vs_seller is not None and buyer_vs_seller <= 4.0)
        or (sell_through is not None and sell_through <= 0.18)
        or (avg_dom is not None and avg_dom >= 55)
    ):
        return "Soft Market"
    return "Balanced Market"


def _market_trend_label(metrics: dict[str, Any]) -> str:
    price_trend = _as_float(metrics.get("price_trend_pct"))
    dom_trend = _as_float(metrics.get("dom_trend_pct"))
    sell_through = _as_float(metrics.get("sell_through_rate"))
    score = 0.0
    if price_trend is not None:
        score += 1.0 if price_trend >= 0.03 else -1.0 if price_trend <= -0.03 else 0.0
    if dom_trend is not None:
        score += 0.8 if dom_trend <= -0.08 else -0.8 if dom_trend >= 0.08 else 0.0
    if sell_through is not None:
        score += 0.6 if sell_through >= 0.30 else -0.6 if sell_through <= 0.18 else 0.0
    if score >= 0.75:
        return "Improving"
    if score <= -0.75:
        return "Weakening"
    return "Stable"


def _score_band(score: float) -> str:
    if score >= 0.8:
        return "confirmed"
    if score >= 0.55:
        return "confirmed_with_conflict"
    if score >= 0.35:
        return "estimated"
    return "missing"


def _market_signal_lines(analysis: MarketAnalysisOutput) -> list[str]:
    metrics = analysis.metrics
    lines: list[str] = []
    inventory_count = metrics.get("inventory_count")
    inventory_pressure = _as_float(metrics.get("months_of_supply"))
    if inventory_count is not None:
        if inventory_pressure is not None:
            lines.append(f"Inventory at {int(inventory_count)} listings, or about {inventory_pressure:.1f} months of supply.")
        else:
            lines.append(f"Inventory currently shows {int(inventory_count)} active listings.")
    avg_dom = _as_float(metrics.get("avg_dom"))
    dom_trend = _as_float(metrics.get("dom_trend_pct"))
    if avg_dom is not None:
        if dom_trend is not None and dom_trend >= 0.08:
            lines.append("DOM is rising, which points to buyer leverage increasing.")
        elif dom_trend is not None and dom_trend <= -0.08:
            lines.append("DOM is compressing, which suggests demand is tightening.")
        else:
            lines.append(f"Homes are taking about {avg_dom:.0f} days to move.")
    price_trend = _as_float(metrics.get("price_trend_pct"))
    if price_trend is not None:
        direction = "up" if price_trend > 0 else "down"
        lines.append(f"Median sale pricing is {direction} about {abs(price_trend) * 100:.0f}% versus the prior period.")
    sell_through = _as_float(metrics.get("sell_through_rate"))
    if sell_through is not None and not any("demand" in line.lower() for line in lines):
        if sell_through >= 0.35:
            lines.append("Sell-through remains strong relative to current inventory.")
        elif sell_through <= 0.18:
            lines.append("Turnover is slower, so buyers have more room to negotiate.")
    if not lines:
        lines.append("Market read is directionally useful, but turnover history is still thin.")
    return lines[:2]


def _price_history_entry_price(entry: dict[str, Any]) -> float | None:
    for key in ("price", "list_price", "value", "event_price"):
        value = entry.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.replace("$", "").replace(",", "").strip()
            try:
                return float(cleaned)
            except ValueError:
                continue
    return None


def _price_history_metrics(entries: list[dict[str, Any]]) -> tuple[int | None, float | None, int | None]:
    if not entries:
        return None, None, None
    prices = [_price_history_entry_price(entry) for entry in entries]
    prices = [price for price in prices if price is not None]
    price_cut_count = 0
    total_price_cut_pct = 0.0
    relist_count = 0
    previous_price: float | None = None
    for entry in entries:
        text = _clean_text(entry.get("event") or entry.get("status") or entry.get("description")).lower()
        price = _price_history_entry_price(entry)
        if "relist" in text:
            relist_count += 1
        if previous_price not in (None, 0) and price not in (None, 0) and price < previous_price:
            price_cut_count += 1
            total_price_cut_pct += (previous_price - price) / previous_price
        previous_price = price if price is not None else previous_price
    if price_cut_count == 0 and prices:
        total_drop = (max(prices) - min(prices)) / max(prices) if max(prices) > 0 else 0.0
        if total_drop > 0.0:
            price_cut_count = 1
            total_price_cut_pct = total_drop
    return (
        price_cut_count or None,
        round(total_price_cut_pct, 4) if total_price_cut_pct > 0 else None,
        relist_count or None,
    )


def _build_value_finder_output(
    report: AnalysisReport,
    *,
    market_analysis: MarketAnalysisOutput | None = None,
) -> ValueFinderOutput:
    property_input = report.property_input
    current_value = get_current_value(report)
    comp_low = getattr(current_value, "direct_value_range", None).low if getattr(current_value, "direct_value_range", None) is not None else None
    comp_mid = getattr(current_value, "direct_value_range", None).midpoint if getattr(current_value, "direct_value_range", None) is not None else None
    comp_high = getattr(current_value, "direct_value_range", None).high if getattr(current_value, "direct_value_range", None) is not None else None
    town_metrics = market_analysis.metrics if market_analysis is not None else {}
    price_cut_count, total_price_cut_pct, relist_count = _price_history_metrics(
        list(property_input.price_history) if property_input is not None else []
    )
    asking_price = current_value.ask_price
    subject_ppsf = (
        asking_price / property_input.sqft
        if property_input is not None and asking_price not in (None, 0) and property_input.sqft not in (None, 0)
        else None
    )
    return analyze_value_finder(
        asking_price=asking_price,
        briarwood_value=current_value.briarwood_current_value,
        comp_median=comp_mid,
        comp_low=comp_low,
        comp_high=comp_high,
        days_on_market=property_input.days_on_market if property_input is not None else None,
        price_cut_count=price_cut_count,
        total_price_cut_pct=total_price_cut_pct,
        town_dom_trend=_as_float(town_metrics.get("dom_trend_pct")),
        town_inventory_trend=_as_float(town_metrics.get("inventory_trend_pct")),
        subject_price_per_sqft=subject_ppsf,
        cohort_price_per_sqft=_as_float(town_metrics.get("avg_price_per_sqft")),
        confidence=float(current_value.confidence),
        similar_listing_dom=_as_float(town_metrics.get("avg_dom")),
        relist_count=relist_count,
    )


def build_value_finder_view_model(
    report: AnalysisReport,
    *,
    market_analysis: MarketAnalysisOutput | None = None,
) -> ValueFinderViewModel:
    output = analyze_property_value_finder(report)
    return ValueFinderViewModel(
        bullets=list(output.bullets),
        supporting_signal=f"{len(output.bullets)} supported value signal{'s' if len(output.bullets) != 1 else ''}" if output.bullets else "No strong value edge surfaced",
        confidence_note="Value Finder only surfaces bullets backed by actual property facts or structured model outputs.",
    )


def build_value_finder_candidate_view_model(
    report: AnalysisReport,
    *,
    market_analysis: MarketAnalysisOutput | None = None,
) -> ValueFinderCandidateViewModel:
    output = _build_value_finder_output(report, market_analysis=market_analysis)
    property_input = report.property_input
    current_value = get_current_value(report)
    return ValueFinderCandidateViewModel(
        property_id=report.property_id,
        address=(property_input.address if property_input is not None else report.address).split(",")[0],
        town=property_input.town if property_input is not None else "",
        opportunity_signal=output.opportunity_signal,
        pricing_posture=output.pricing_posture,
        short_summary=output.short_summary,
        ask_price_text=_fmt_currency(current_value.ask_price),
        briarwood_value_text=_fmt_currency(current_value.briarwood_current_value),
        dom_text=_fmt_number(property_input.days_on_market if property_input is not None else None, " days"),
        value_gap_text=_fmt_pct(output.value_gap_pct) if output.value_gap_pct is not None else "Unavailable",
    )


def _market_view_model(analysis: MarketAnalysisOutput) -> MarketViewModel:
    metrics = analysis.metrics
    inventory_text = _fmt_number(metrics.get("inventory_count"))
    inventory_subtitle = (
        f"{metrics['months_of_supply']:.1f} mos supply"
        if _as_float(metrics.get("months_of_supply")) is not None
        else "Current only"
    )
    return MarketViewModel(
        town_name=analysis.town,
        market_signal=_market_signal_label(metrics),
        trend=_market_trend_label(metrics),
        key_metrics={
            "Inventory": f"{inventory_text} ({inventory_subtitle})",
            "Median Price": _fmt_currency(metrics.get("median_price")),
            "DOM": _fmt_number(metrics.get("avg_dom"), "d"),
            "Price Trend": _fmt_pct(metrics.get("price_trend_pct"), scale_100=False),
        },
        signals=_market_signal_lines(analysis),
        score=analysis.market_score,
        town_slug=analysis.town.lower().replace(" ", "-"),
    )


def _market_analysis_cache_path(sort_mode: str) -> Path:
    return VIEW_MODEL_CACHE_DIR / f"market_analyses_{sort_mode}.pkl"


def _load_cached_market_analyses_from_disk(sort_mode: str) -> tuple[MarketAnalysisOutput, ...] | None:
    cache_path = _market_analysis_cache_path(sort_mode)
    if not cache_path.exists():
        return None
    try:
        with cache_path.open("rb") as fh:
            payload = pickle.load(fh)
    except (OSError, ValueError, pickle.PickleError) as exc:
        logger.warning("Unable to read market analysis cache %s: %s", cache_path, exc)
        return None
    created_at = payload.get("created_at") if isinstance(payload, dict) else None
    analyses = payload.get("analyses") if isinstance(payload, dict) else None
    if not isinstance(created_at, datetime) or analyses is None:
        return None
    if datetime.now(timezone.utc) - created_at > MARKET_ANALYSIS_CACHE_TTL:
        return None
    try:
        return tuple(analyses)
    except TypeError:
        return None


def _persist_market_analyses_to_disk(sort_mode: str, analyses: tuple[MarketAnalysisOutput, ...]) -> None:
    cache_path = _market_analysis_cache_path(sort_mode)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("wb") as fh:
            pickle.dump({"created_at": datetime.now(timezone.utc), "analyses": analyses}, fh)
    except OSError as exc:
        logger.warning("Unable to persist market analysis cache %s: %s", cache_path, exc)


@lru_cache(maxsize=4)
def _cached_market_analyses(sort_mode: str) -> tuple[MarketAnalysisOutput, ...]:
    cached = _load_cached_market_analyses_from_disk(sort_mode)
    if cached is not None:
        return cached
    analyses = analyze_markets()
    if sort_mode == "weakest":
        analyses = sorted(analyses, key=lambda item: (item.market_score, item.town))
    elif sort_mode == "improving":
        analyses = sorted(
            analyses,
            key=lambda item: (
                0 if _market_trend_label(item.metrics) == "Improving" else 1 if _market_trend_label(item.metrics) == "Stable" else 2,
                -(item.metrics.get("price_trend_pct") or 0.0),
                -(item.market_score or 0.0),
                item.town,
            ),
        )
    else:
        analyses = sorted(analyses, key=lambda item: (-item.market_score, item.town))
    analyses_tuple = tuple(analyses)
    _persist_market_analyses_to_disk(sort_mode, analyses_tuple)
    return analyses_tuple


def build_market_view_model(selected_town: str | None = None, *, sort_mode: str = "strongest") -> MarketsPageViewModel:
    analyses = _cached_market_analyses(sort_mode)
    cards = [_market_view_model(item) for item in analyses]
    normalized_selected = normalize_town_name(selected_town) if selected_town else None
    selected = next((item for item in analyses if item.town == normalized_selected), None)
    if selected is None and analyses:
        selected = analyses[0]
    return MarketsPageViewModel(
        markets=cards,
        selected_town=selected.town if selected is not None else None,
        selected_market=selected,
        sort_mode=sort_mode,
    )


def build_property_evidence_summary_view_model(property_input: PropertyInput | None) -> PropertyEvidenceSummaryViewModel | None:
    if property_input is None:
        return None
    profile = property_input.evidence_profile()
    if profile is None:
        return None
    summary_flags = getattr(profile, "summary_flags", None) or (profile.get("summary_flags") if isinstance(profile, dict) else {})
    structural_score = float(summary_flags.get("structural_data_quality_score", 0.0) or 0.0)
    tax_score = float(summary_flags.get("tax_data_quality_score", 0.0) or 0.0)
    sale_score = float(summary_flags.get("sale_data_quality_score", 0.0) or 0.0)
    rent_score = float(summary_flags.get("rent_data_quality_score", 0.0) or 0.0)
    notes: list[str] = []
    if property_input.provenance_for("sale_price") or property_input.provenance_for("last_sale_price"):
        sale_prov = property_input.provenance_for("sale_price") or property_input.provenance_for("last_sale_price")
        if sale_prov is not None and "sr1a" in sale_prov.source.lower():
            notes.append("Sale verified by NJ SR1A")
    tax_prov = property_input.provenance_for("tax_amount") or property_input.provenance_for("taxes")
    if tax_prov is not None and "attom" in tax_prov.source.lower():
        notes.append("Taxes confirmed via ATTOM assessment")
    sqft_prov = property_input.provenance_for("sqft")
    if sqft_prov is not None and "attom" in sqft_prov.source.lower():
        notes.append("Living size confirmed via ATTOM")
    if str(summary_flags.get("identity_match_status") or "") == "needs_review":
        notes.append("Town mismatch detected between address and stored town")
    rent_prov = property_input.provenance_for("estimated_rent") or property_input.provenance_for("estimated_monthly_rent")
    if rent_prov is None or "estimate" in rent_prov.source.lower() or "briarwood" in rent_prov.source.lower():
        notes.append("Rent remains estimated")
    return PropertyEvidenceSummaryViewModel(
        structural_status=_score_band(structural_score),
        tax_status=_score_band(tax_score),
        sale_status=_score_band(sale_score),
        rent_status=_score_band(rent_score),
        comp_eligibility_status=str(summary_flags.get("comp_eligibility_status") or "unknown"),
        key_notes=notes[:5],
    )


def build_hybrid_value_view_model(report: AnalysisReport) -> HybridValueViewModel | None:
    hybrid_result = report.module_results.get("hybrid_value")
    if hybrid_result is None:
        return None
    hybrid = get_hybrid_value_payload(hybrid_result)
    if not hybrid.is_hybrid:
        return None
    return HybridValueViewModel(
        is_hybrid=True,
        reason=hybrid.reason,
        primary_house_value=_fmt_currency(hybrid.primary_house_value),
        rear_income_value=_fmt_currency(hybrid.rear_income_value),
        optionality_premium_value=_fmt_currency(hybrid.optionality_premium_value),
        total_hybrid_value=_fmt_currency(hybrid.base_case_hybrid_value),
        confidence=float(hybrid.confidence),
        notes=list(hybrid.notes),
        narrative=hybrid.narrative,
    )


def _active_listing_rows(report: AnalysisReport) -> list[ActiveListingViewRow]:
    property_input = report.property_input
    if property_input is None or not ACTIVE_LISTINGS_PATH.exists():
        return []

    town = (property_input.town or "").strip().lower()
    state = (property_input.state or "").strip().lower()
    property_type = (property_input.property_type or "").strip().lower()
    price_anchor = property_input.purchase_price

    try:
        dataset = JsonActiveListingStore(ACTIVE_LISTINGS_PATH).load()
    except (OSError, ValueError, KeyError) as exc:
        logger.warning(
            "Cannot load active listings from %s: %s", ACTIVE_LISTINGS_PATH, exc
        )
        return []

    filtered = []
    for listing in dataset.listings:
        if town and listing.town.strip().lower() != town:
            continue
        if state and listing.state.strip().lower() != state:
            continue
        if property_type and listing.property_type and listing.property_type.strip().lower() != property_type:
            type_penalty = 1
        else:
            type_penalty = 0
        price_gap = abs((listing.list_price or 0.0) - (price_anchor or listing.list_price or 0.0))
        filtered.append((type_penalty, price_gap, listing.address.lower(), listing))

    filtered.sort(key=lambda item: (item[0], item[1], item[2]))
    rows: list[ActiveListingViewRow] = []
    for _, _, _, listing in filtered:
        identity = _property_identity(getattr(listing, "address", None), getattr(listing, "town", None), getattr(listing, "state", None))
        maps = _maps_links(identity["full_address"], identity["town"], identity["state"])
        rows.append(
            ActiveListingViewRow(
                address=identity["full_address"],
                street=identity["street"],
                locality=identity["locality"],
                list_price=_fmt_currency(listing.list_price),
                status=listing.listing_status.replace("_", " ").title(),
                beds=_fmt_number(listing.beds),
                baths=_fmt_number(listing.baths),
                sqft=_fmt_number(listing.sqft),
                dom=_fmt_number(listing.days_on_market, " days"),
                condition=(listing.condition_profile or "Unavailable").replace("_", " ").title(),
                source_ref=listing.source_ref or "Unavailable",
                google_maps_url=maps["google"],
                apple_maps_url=maps["apple"],
                external_url=_maybe_external_url(listing.source_ref),
            )
        )
    return rows


def build_property_analysis_view(report: AnalysisReport) -> PropertyAnalysisView:
    property_input = report.property_input
    current_value = get_current_value(report)
    comparable_sales = get_comparable_sales(report)
    active_listing_rows = _active_listing_rows(report)
    scenario = get_scenario_output(report)
    income = get_income_support(report)
    rental_ease = get_rental_ease(report)
    town_county = get_town_county_outlook(report)
    scarcity = get_scarcity_support(report)
    value_driver_rows, value_bridge_rows = _value_driver_rows(report)
    risk = report.get_module("risk_constraints")
    liquidity_metrics, liquidity_supporting, liquidity_unsupported = _liquidity_metrics(report)
    market_momentum_metrics, market_momentum_drivers, market_momentum_unsupported = _market_momentum_metrics(report)
    local_module = report.module_results.get("local_intelligence")
    town_pulse = build_town_pulse_view_model_from_payload(
        local_module.payload if local_module is not None else None,
        town=property_input.town if property_input else report.address,
        state=property_input.state if property_input else "",
    )
    forward_module = report.get_module("bull_base_bear")
    conclusion = build_conclusion_section(report)
    thesis = build_thesis_section(report)
    sourced, user_supplied, estimated, missing = _coverage_lists(property_input)
    confidence_breakdown = compute_confidence_breakdown(report)
    metric_statuses = compute_metric_input_statuses(report)
    assumption_statuses = _assumption_status_items(report)
    overall_confidence = confidence_breakdown.overall_confidence
    location_support_label, location_support_detail = _location_support_state(report)
    location_anchor_summary = _location_anchor_summary(report)
    market_view_model = build_market_view_model(property_input.town if property_input else None)
    property_evidence_summary = build_property_evidence_summary_view_model(property_input)
    hybrid_value_view = build_hybrid_value_view_model(report)
    value_finder_view = build_value_finder_view_model(
        report,
        market_analysis=market_view_model.selected_market,
    )

    positives = list(town_county.score.demand_drivers[:2]) + list(scarcity.demand_drivers[:1])
    risks = list(rental_ease.risks[:2]) + list(town_county.score.demand_risks[:2])
    positives = [item for item in positives if item][:3]
    risks = [item for item in risks if item][:3]

    ask_price_val = current_value.ask_price
    forward_gap_pct = (
        (scenario.base_case_value - ask_price_val) / ask_price_val
        if ask_price_val
        else None
    )
    town_context_raw = get_town_context(property_input.town if property_input else None)
    subject_ppsf = (ask_price_val / property_input.sqft) if property_input and ask_price_val and property_input.sqft else None
    subject_ppsf_vs_town = _safe_ratio(subject_ppsf, town_context_raw.median_ppsf) if town_context_raw else None
    subject_price_vs_town = _safe_ratio(ask_price_val, town_context_raw.median_price) if town_context_raw else None
    subject_lot_vs_town = _safe_ratio(property_input.lot_size if property_input else None, town_context_raw.median_lot_size) if town_context_raw else None
    town_adjusted_value_gap = (
        round((town_context_raw.median_ppsf - subject_ppsf) / subject_ppsf, 3)
        if town_context_raw and subject_ppsf not in (None, 0) and town_context_raw.median_ppsf not in (None, 0)
        else None
    )
    town_relative_opportunity_score = _town_relative_opportunity_score(
        subject_ppsf_vs_town=subject_ppsf_vs_town,
        subject_price_vs_town=subject_price_vs_town,
        town_context_confidence=(town_context_raw.context_confidence if town_context_raw else None),
    )
    valuation_pct = getattr(current_value, "net_opportunity_delta_pct", None)
    if valuation_pct is None:
        valuation_pct = current_value.mispricing_pct
    confidence_score = max(0, min(int(round(overall_confidence * 100)), 100))
    assumption_lookup = {item.key: item for item in assumption_statuses}
    capex_status = assumption_lookup.get("capex").status if assumption_lookup.get("capex") is not None else None
    strategy_fit_label = _strategy_fit_label(None)
    entry_basis_label = _entry_basis_label(valuation_pct)
    income_support_label = _income_support_label(_income_attr(income, "monthly_cash_flow"), _income_attr(income, "income_support_ratio"))
    capex_load_label = _capex_load_label(property_input.capex_lane if property_input else "", capex_status)
    liquidity_profile_label = _liquidity_profile_label(float(liquidity_metrics.get("liquidity_score") or 0.0))
    optionality_label = _optionality_label(strategy_fit_label, None, scenario.bull_case_value)
    risk_skew_label = _risk_skew_label(float(risk.score), confidence_score)
    positioning_summary = _positioning_summary(
        entry_basis_label=entry_basis_label,
        income_support_label=income_support_label,
        capex_load_label=capex_load_label,
        liquidity_profile_label=liquidity_profile_label,
        optionality_label=optionality_label,
        risk_skew_label=risk_skew_label,
    )
    initial_report_card = ReportCardViewModel()
    town_context = (
        {
            "town": town_context_raw.town,
            "baseline_median_price": town_context_raw.median_price,
            "baseline_median_ppsf": town_context_raw.median_ppsf,
            "baseline_median_sqft": town_context_raw.median_sqft,
            "baseline_median_lot_size": town_context_raw.median_lot_size,
            "town_price_index": town_context_raw.town_price_index,
            "town_ppsf_index": town_context_raw.town_ppsf_index,
            "town_lot_index": town_context_raw.town_lot_index,
            "town_liquidity_index": town_context_raw.town_liquidity_index,
            "town_context_confidence": town_context_raw.context_confidence,
            "qa_flags": list(town_context_raw.qa_flags),
            "subject_ppsf_vs_town": subject_ppsf_vs_town,
            "subject_price_vs_town": subject_price_vs_town,
            "subject_lot_vs_town": subject_lot_vs_town,
            "town_adjusted_value_gap": town_adjusted_value_gap,
            "town_relative_opportunity_score": town_relative_opportunity_score,
            "qa_summary": (
                "Town context is strong enough to inform pricing context."
                if not town_context_raw.qa_flags and town_context_raw.context_confidence >= 0.78
                else f"Town context is directional only because {', '.join(town_context_raw.qa_flags)}."
                if town_context_raw.qa_flags
                else "Town context is usable, but not clean enough to dominate direct comps."
            ),
        }
        if town_context_raw
        else {}
    )
    compare_metrics = {
        "ask_price": ask_price_val,
        "bcv": current_value.briarwood_current_value,
        "bcv_delta": current_value.mispricing_amount,
        "all_in_basis": getattr(current_value, "all_in_basis", None),
        "net_opportunity_delta_value": getattr(current_value, "net_opportunity_delta_value", None),
        "net_opportunity_delta_pct": getattr(current_value, "net_opportunity_delta_pct", None),
        "bcv_range": f"{current_value.value_low:,.0f}-{current_value.value_high:,.0f}",
        "forward_base_case": scenario.base_case_value,
        "lot_size": property_input.lot_size if property_input else None,
        "sqft": property_input.sqft if property_input else None,
        "taxes": property_input.taxes if property_input else None,
        "dom": property_input.days_on_market if property_input else None,
        "income_support_ratio": income.income_support_ratio,
        "price_to_rent": income.price_to_rent,
        "monthly_cash_flow": _income_attr(income, "monthly_cash_flow"),
        "forward_gap_pct": forward_gap_pct,
        "risk_score": risk.score,
        "liquidity_score": liquidity_metrics.get("liquidity_score"),
        "liquidity_label": liquidity_metrics.get("liquidity_label"),
        "market_momentum_score": market_momentum_metrics.get("market_momentum_score"),
        "market_momentum_label": market_momentum_metrics.get("market_momentum_label"),
        "town_county_score": town_county.score.town_county_score,
        "scarcity_score": scarcity.scarcity_support_score,
        "confidence": overall_confidence,
        "missing_inputs": missing,
        "subject_ppsf": subject_ppsf,
        "town_baseline_median_price": town_context.get("baseline_median_price"),
        "town_baseline_median_ppsf": town_context.get("baseline_median_ppsf"),
        "town_baseline_median_sqft": town_context.get("baseline_median_sqft"),
        "town_price_index": town_context.get("town_price_index"),
        "town_ppsf_index": town_context.get("town_ppsf_index"),
        "town_lot_index": town_context.get("town_lot_index"),
        "town_liquidity_index": town_context.get("town_liquidity_index"),
        "town_context_confidence": town_context.get("town_context_confidence"),
        "town_qa_flags": town_context.get("qa_flags", []),
        "subject_ppsf_vs_town": subject_ppsf_vs_town,
        "subject_price_vs_town": subject_price_vs_town,
        "subject_lot_vs_town": subject_lot_vs_town,
        "town_adjusted_value_gap": town_adjusted_value_gap,
        "town_relative_opportunity_score": town_relative_opportunity_score,
        "hybrid_indicated_value": (
            report.module_results.get("hybrid_value").metrics.get("base_case_hybrid_value")
            if report.module_results.get("hybrid_value") is not None
            else None
        ),
    }
    risk_bar = build_risk_bar(report)
    monthly_cost = _monthly_cost(report)
    rent_offset = _rent_offset(report)
    net_monthly = _net_monthly(report)
    support_quality = _support_quality(report)
    decision_metrics = DecisionMetrics(
        fv_vs_ask_pct=current_value.mispricing_pct,
        monthly_carry=net_monthly,
        confidence=overall_confidence,
    )
    risk_metrics = RiskMetrics(
        price_gap_pct=current_value.mispricing_pct,
        monthly_loss=(abs(net_monthly) if isinstance(net_monthly, (int, float)) and net_monthly < 0 else 0.0 if net_monthly is not None else None),
        liquidity_score=float(liquidity_metrics.get("liquidity_score")) if isinstance(liquidity_metrics.get("liquidity_score"), (int, float)) else None,
        execution_risk=((property_input.capex_lane or "unknown").replace("_", " ").title() if property_input else "Unknown"),
        confidence=overall_confidence,
    )
    value_metrics = ValueMetrics(
        adu_income=_adu_income_value(report),
        expansion_score=_expansion_score(report),
        mispricing_pct=current_value.mispricing_pct,
        market_tailwind=float(market_momentum_metrics.get("market_momentum_score")) if isinstance(market_momentum_metrics.get("market_momentum_score"), (int, float)) else None,
    )
    price_support_metrics = PriceSupportMetrics(
        fair_value=current_value.briarwood_current_value,
        value_range_low=current_value.value_low,
        value_range_high=current_value.value_high,
        comp_count=int(comparable_sales.comp_count or 0),
        support_quality=support_quality,
    )
    financial_metrics = FinancialMetrics(
        monthly_cost=monthly_cost,
        rent_offset=rent_offset,
        net_monthly=net_monthly,
        break_even=bool(isinstance(net_monthly, (int, float)) and net_monthly >= 0),
    )
    price_support_view = PriceSupportQuestionViewModel(
        metrics=price_support_metrics,
        ask_price=ask_price_val,
        fair_value=current_value.briarwood_current_value,
        value_low=current_value.value_low,
        value_high=current_value.value_high,
        mispricing_amount=current_value.mispricing_amount,
        mispricing_pct=current_value.mispricing_pct,
        pricing_view=current_value.pricing_view,
        all_in_basis=getattr(current_value, "all_in_basis", None),
        capex_basis_used=getattr(current_value, "capex_basis_used", None),
        capex_basis_source=getattr(current_value, "capex_basis_source", None) or "unknown",
        net_opportunity_delta_value=getattr(current_value, "net_opportunity_delta_value", None),
        net_opportunity_delta_pct=getattr(current_value, "net_opportunity_delta_pct", None),
        value=ValueViewModel(
            component_rows=_component_rows(report),
            market_anchors=_market_anchor_rows(report),
            value_drivers=value_driver_rows,
            value_bridge=value_bridge_rows,
            pricing_view=current_value.pricing_view,
            assumptions=list(current_value.assumptions),
            warnings=list(current_value.warnings),
            unsupported_claims=list(current_value.unsupported_claims),
            confidence=float(current_value.confidence),
        ),
        comps=CompsViewModel(
            comparable_value_text=_fmt_currency(comparable_sales.comparable_value),
            comp_count_text=str(comparable_sales.comp_count),
            confidence_text=_fmt_pct(comparable_sales.confidence),
            active_listing_count_text=str(len(active_listing_rows)),
            dataset_name=comparable_sales.dataset_name or "Unavailable",
            verification_summary=comparable_sales.verification_summary or "Unavailable",
            curation_summary=comparable_sales.curation_summary or "Unavailable",
            screening_summary=_screening_summary(report),
            warnings=list(comparable_sales.warnings),
            assumptions=list(comparable_sales.assumptions),
            unsupported_claims=list(comparable_sales.unsupported_claims),
            rows=_comp_rows(report),
            active_listing_rows=active_listing_rows,
            is_hybrid_valuation=bool(getattr(comparable_sales, "is_hybrid_valuation", False)),
            primary_dwelling_value_text=_fmt_currency(getattr(comparable_sales, "primary_dwelling_value", None)),
            additional_unit_income_value_text=_fmt_currency(getattr(comparable_sales, "additional_unit_income_value", None)),
            additional_unit_count=int(getattr(comparable_sales, "additional_unit_count", 0) or 0),
            additional_unit_annual_income_text=_fmt_currency(getattr(comparable_sales, "additional_unit_annual_income", None)),
            additional_unit_cap_rate_text=f"{getattr(comparable_sales, 'additional_unit_cap_rate', 0) or 0:.1%}",
            hybrid_valuation_note=str(getattr(comparable_sales, "hybrid_valuation_note", "") or ""),
        ),
    )
    financials_view = FinancialsQuestionViewModel(
        metrics=financial_metrics,
        income_support=IncomeSupportViewModel(
            summary=_income_attr(income, "summary", "Income support unavailable."),
            confidence=float(_income_attr(income, "confidence", 0.0)),
            rental_ease_label=rental_ease.rental_ease_label,
            estimated_days_to_rent_text=_fmt_number(rental_ease.estimated_days_to_rent, " days"),
            total_rent_text=_fmt_currency(_income_attr(income, "monthly_rent_estimate") or _income_attr(income, "gross_monthly_rent_before_vacancy")),
            num_units_text=_fmt_number(_income_attr(income, "num_units")),
            avg_rent_per_unit_text=_fmt_currency(_income_attr(income, "avg_rent_per_unit")),
            income_support_ratio_text=(f"{_income_attr(income, 'income_support_ratio'):.2f}x" if _income_attr(income, "income_support_ratio") is not None else "Unavailable"),
            monthly_cash_flow_text=_fmt_currency(_income_attr(income, "monthly_cash_flow")),
            operating_cash_flow_text=_fmt_currency(_income_attr(income, "operating_monthly_cash_flow")),
            rent_source_type=str(_income_attr(income, "rent_source_type", "missing")).replace("_", " ").title(),
            risk_view=str(_income_attr(income, "risk_view", "unknown")).replace("_", " ").title(),
            price_to_rent_text=_fmt_number(_income_attr(income, "price_to_rent"), "x"),
            ptr_classification=_income_attr(income, "price_to_rent_classification") or "Unavailable",
            unit_breakdown=[
                (f"Unit {index + 1}", _fmt_currency(value))
                for index, value in enumerate(_income_list(income, "unit_breakdown"))
            ],
            warnings=list(_income_attr(income, "warnings", [])),
            assumptions=list(_income_attr(income, "assumptions", [])),
            unsupported_claims=list(_income_attr(income, "unsupported_claims", [])),
            dscr=_cost_val_metric(report, "dscr"),
            dscr_text=_fmt_ratio(_cost_val_metric(report, "dscr")),
            cash_on_cash_return=_cost_val_metric(report, "cash_on_cash_return"),
            cash_on_cash_return_text=_fmt_pct(_cost_val_metric(report, "cash_on_cash_return")),
            gross_yield=_cost_val_metric(report, "gross_yield"),
            gross_yield_text=_fmt_pct(_cost_val_metric(report, "gross_yield")),
            rent_source_label=_rent_source_label(str(_income_attr(income, "rent_source_type", "missing"))),
        ),
        forward=ForwardViewModel(
            summary=forward_module.summary,
            confidence=float(forward_module.confidence),
            bull_value_text=_fmt_currency(scenario.bull_case_value),
            base_value_text=_fmt_currency(scenario.base_case_value),
            bear_value_text=_fmt_currency(scenario.bear_case_value),
            stress_case_value_text=_fmt_currency(_scenario_stress_value(scenario)),
            upside_pct_text=_fmt_pct((scenario.bull_case_value - ask_price_val) / ask_price_val) if ask_price_val else "Unavailable",
            downside_pct_text=_fmt_pct((scenario.bear_case_value - ask_price_val) / ask_price_val) if ask_price_val else "Unavailable",
            market_drift_text=_fmt_currency(forward_module.metrics.get("market_drift")),
            location_premium_text=_fmt_currency(forward_module.metrics.get("location_premium")),
            risk_discount_text=_fmt_currency(forward_module.metrics.get("risk_discount")),
            optionality_premium_text=_fmt_currency(forward_module.metrics.get("optionality_premium")),
        ),
        base_case=scenario.base_case_value,
        bull_case=scenario.bull_case_value,
        bear_case=scenario.bear_case_value,
        stress_case=_scenario_stress_value(scenario),
    )
    risk_question_view = RiskQuestionViewModel(
        metrics=risk_metrics,
        risk_bar=risk_bar,
        summary=risk.summary,
        top_risks=risks,
    )
    value_question_view = ValueQuestionViewModel(
        metrics=value_metrics,
        value_finder=value_finder_view,
        hybrid_value=hybrid_value_view,
    )
    property_decision_view = PropertyDecisionViewModel(
        decision=None,
        decision_metrics=decision_metrics,
        risk=risk_question_view,
        value=value_question_view,
        price_support=price_support_view,
        financials=financials_view,
    )

    view = PropertyAnalysisView(
        property_id=report.property_id,
        label=(property_input.address if property_input else report.address).split(",")[0],
        address=property_input.address if property_input else report.address,
        evidence_mode=(property_input.source_metadata.evidence_mode.value.replace("_", " ").title() if property_input and property_input.source_metadata else "Unknown"),
        condition_profile=((property_input.condition_profile or "Unavailable").replace("_", " ").title() if property_input else "Unavailable"),
        capex_lane=((property_input.capex_lane or "Unavailable").replace("_", " ").title() if property_input else "Unavailable"),
        overall_confidence=overall_confidence,
        property_decision_view=property_decision_view,
        evidence=EvidenceViewModel(
            evidence_mode=(property_input.source_metadata.evidence_mode.value.replace("_", " ").title() if property_input and property_input.source_metadata else "Unknown"),
            sourced_inputs=sourced,
            user_supplied_inputs=user_supplied,
            estimated_inputs=estimated,
            missing_inputs=missing,
            unsupported_claims=_collect_unsupported_claims(report),
            confidence_components=[
                ConfidenceComponentItem(
                    key=item.key,
                    label=item.label,
                    confidence=item.confidence,
                    weight=item.weight,
                    reason=item.reason,
                )
                for item in confidence_breakdown.components
            ],
            confidence_notes=list(confidence_breakdown.notes),
            assumption_statuses=assumption_statuses,
            transparency_items=[],
            metric_statuses=[
                MetricInputStatusItem(
                    key=item.key,
                    label=item.label,
                    status=item.status,
                    facts_used=list(item.facts_used),
                    user_inputs_used=list(item.user_inputs_used),
                    assumptions_used=list(item.assumptions_used),
                    missing_inputs=list(item.missing_inputs),
                    confidence_impact=item.confidence_impact,
                    prompt_fields=list(item.prompt_fields),
                )
                for item in metric_statuses
            ],
            gap_prompt_fields=sorted(
                {
                    field
                    for item in metric_statuses
                    if item.status != "fact_based"
                    for field in item.prompt_fields
                }
            ),
            section_confidences=_section_confidences(report),
        ),
        positioning_summary=positioning_summary,
        report_card=initial_report_card,
        top_positives=positives,
        metric_chips=_metric_chips(
            ask_price=ask_price_val,
            bcv=current_value.briarwood_current_value,
            value_low=current_value.value_low,
            value_high=current_value.value_high,
            mispricing_amount=current_value.mispricing_amount,
                mispricing_pct=current_value.mispricing_pct,
            base_case=scenario.base_case_value,
            confidence=overall_confidence,
        ),
        risk_location=RiskLocationViewModel(
            risk_summary=risk.summary,
            risk_score=float(risk.score),
            town_score=float(town_county.score.town_county_score),
            town_label=town_county.score.location_thesis_label,
            scarcity_score=float(scarcity.scarcity_support_score),
            liquidity_score=float(liquidity_metrics.get("liquidity_score") or 0.0),
            liquidity_label=str(liquidity_metrics.get("liquidity_label") or "Unknown"),
            market_momentum_score=float(market_momentum_metrics.get("market_momentum_score") or 0.0),
            market_momentum_label=str(market_momentum_metrics.get("market_momentum_label") or "Unknown"),
            flood_risk=property_input.flood_risk if property_input and property_input.flood_risk else "Unavailable",
            liquidity_view=town_county.score.liquidity_view,
            drivers=list(market_momentum_drivers[:2]) + list(liquidity_supporting[:1]) + list(town_county.score.demand_drivers[:1]) + list(scarcity.demand_drivers[:1]),
            risks=list(market_momentum_unsupported[:1]) + list(liquidity_unsupported[:1]) + list(town_county.score.demand_risks[:2]) + list(scarcity.scarcity_notes[:1]),
            warnings=list(risk.metrics.get("warnings", [])) if isinstance(risk.metrics.get("warnings"), list) else [],
            unsupported_claims=list(town_county.score.unsupported_claims) + list(scarcity.unsupported_claims),
            # Surfaced stress scenario and momentum direction
            stress_case_value=_scenario_stress_value(scenario),
            stress_case_text=_fmt_currency(_scenario_stress_value(scenario)),
            stress_drawdown_pct=_as_float(forward_module.metrics.get("stress_macro_shock_pct")),
            momentum_direction=str(market_momentum_metrics.get("market_momentum_direction", "") or ""),
            # Location context: school signal and coastal profile
            school_signal=property_input.school_rating if property_input else None,
            school_signal_text=f"{property_input.school_rating:.1f}/10" if property_input and property_input.school_rating is not None else "",
            coastal_profile_label=_coastal_profile_label(town_county),
            location_support_label=location_support_label,
            location_support_detail=location_support_detail,
            location_anchor_summary=location_anchor_summary,
            # Scarcity component breakdown
            land_scarcity_score=getattr(scarcity, "land_scarcity_score", None),
            location_scarcity_score=getattr(scarcity, "location_scarcity_score", None),
            town_pulse=town_pulse,
        ),
        town_context=town_context,
        compare_metrics=compare_metrics,
        markets=market_view_model.markets,
        market_view=market_view_model,
        property_evidence_summary=property_evidence_summary,
    )
    view.evidence.transparency_items = _assumption_transparency_items(
        property_input,
        income=income,
        confidence_components=view.evidence.confidence_components,
    )

    # Defaults transparency
    if property_input is not None:
        view.defaults_applied = getattr(property_input, "defaults_applied", {}) or {}
        view.geocoded = getattr(property_input, "geocoded", False)
    missing_assumptions = [item.label.lower() for item in assumption_statuses if item.status == "missing"]
    estimated_assumptions = [item.label.lower() for item in assumption_statuses if item.status == "estimated"]
    if missing_assumptions:
        view.evidence.confidence_notes.append(
            f"Critical underwriting assumptions still missing: {', '.join(missing_assumptions[:4])}."
        )
    elif estimated_assumptions:
        view.evidence.confidence_notes.append(
            f"Key underwriting assumptions are still estimated: {', '.join(estimated_assumptions[:4])}."
        )
    if town_context:
        if town_context.get("qa_flags"):
            view.evidence.confidence_notes.append(
                f"Town context for {town_context['town']} is weaker because {', '.join(town_context['qa_flags'])}."
            )
        elif town_context.get("town_context_confidence") is not None and town_context["town_context_confidence"] >= 0.78:
            view.evidence.confidence_notes.append(
                f"Town context for {town_context['town']} is well covered and can be used as a secondary pricing benchmark."
            )

    # Scoring layer — gracefully degrade if scoring fails. Log so silent score
    # blanks in the UI are debuggable (was bare `except Exception: pass`).
    try:
        from briarwood.decision_model.scoring import calculate_final_score
        fs = calculate_final_score(report)
        view.final_score = fs.score
        view.recommendation_tier = fs.tier
        view.recommendation_action = fs.action
        view.score_narrative = fs.narrative
        view.category_scores = fs.category_scores
    except (AttributeError, KeyError, ValueError, ZeroDivisionError) as exc:
        logger.warning(
            "calculate_final_score failed for %s: %s", report.property_id, exc
        )

    # Lens scoring — multi-perspective evaluation
    try:
        from briarwood.decision_model.lens_scoring import calculate_lens_scores
        view.lens_scores = calculate_lens_scores(report, view.category_scores)
    except (AttributeError, KeyError, ValueError, ZeroDivisionError) as exc:
        logger.warning(
            "calculate_lens_scores failed for %s: %s", report.property_id, exc
        )

    strategy_fit_label = _strategy_fit_label(view.lens_scores)
    optionality_label = _optionality_label(strategy_fit_label, None, scenario.bull_case_value)
    view.positioning_summary = _positioning_summary(
        entry_basis_label=_entry_basis_label(
            view.net_opportunity_delta_pct if view.net_opportunity_delta_pct is not None else view.mispricing_pct
        ),
        income_support_label=view.income_support_label,
        capex_load_label=view.capex_load_label,
        liquidity_profile_label=view.liquidity_profile_label,
        optionality_label=optionality_label,
        risk_skew_label=_risk_skew_label(
            float(view.risk_location.risk_score),
            max(0, min(int(round((view.overall_confidence or 0.0) * 100)), 100)),
        ),
    )

    # Confidence layer — global level, factors, and input impacts
    level, factors = _compute_confidence_level(report, overall_confidence)
    view.confidence_level = level
    view.confidence_factors = factors
    view.top_input_impacts = _compute_top_input_impacts(metric_statuses, confidence_breakdown)

    view.report_card = _build_report_card(view)
    view.property_decision_view.decision = _build_decision_view(view, report)
    view.recommendation_tier = view.property_decision_view.decision.recommendation
    view.recommendation_action = view.property_decision_view.decision.primary_reason

    # Price sensitivity curve
    try:
        from briarwood.deal_curve import build_deal_curve, extract_thresholds as _extract_thresholds
        curve = build_deal_curve(report)
        view.deal_curve = curve
        view.deal_curve_thresholds = _extract_thresholds(curve)
    except Exception as exc:
        logger.warning("build_deal_curve failed for %s: %s", report.property_id, exc)

    return view


def build_evidence_rows(report: AnalysisReport) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    property_input = report.property_input
    if property_input is None or property_input.source_metadata is None:
        return rows
    for category, item in sorted(property_input.source_metadata.source_coverage.items()):
        rows.append(
            {
                "Category": category.replace("_", " ").title(),
                "Status": _coverage_status_label(item.status),
                "Source": item.source_name or "Unavailable",
                "Freshness": item.freshness or "",
                "Note": item.note or "",
            }
        )
    return rows


def build_section_evidence_rows(report: AnalysisReport) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for module in report.module_results.values():
        evidence = module.section_evidence
        if evidence is None:
            continue
        rows.append(_flatten_section_evidence(module.module_name, module.confidence, evidence))
    return rows


def _flatten_section_evidence(module_name: str, confidence: float, evidence: SectionEvidence) -> dict[str, str]:
    return {
        "Section": module_name.replace("_", " ").title(),
        "Confidence": _fmt_pct(confidence),
        "Mode": evidence.evidence_mode.value.replace("_", " ").title(),
        "Estimated": ", ".join(evidence.estimated_inputs[:3]) or "None",
        "Missing": ", ".join(evidence.major_missing_inputs[:3]) or "None",
        "Notes": "; ".join(evidence.notes[:2]) or "",
    }


def _assumption_transparency_items(
    property_input: PropertyInput | None,
    *,
    income: object,
    confidence_components: list[ConfidenceComponentItem],
) -> list[AssumptionTransparencyItem]:
    if property_input is None:
        return []
    assumptions = property_input.user_assumptions
    coverage = property_input.coverage_for
    component_map = {item.key: item for item in confidence_components}
    items: list[AssumptionTransparencyItem] = []

    rent_source = coverage("rent_estimate").status
    rent_value = None
    if assumptions and assumptions.unit_rents:
        rent_value = f"{_fmt_currency(sum(assumptions.unit_rents))}/mo across {len(assumptions.unit_rents)} units"
    elif assumptions and assumptions.estimated_monthly_rent is not None:
        rent_value = f"{_fmt_currency(assumptions.estimated_monthly_rent)}/mo"
    elif _income_attr(income, "monthly_rent_estimate") is not None:
        rent_value = f"{_fmt_currency(_income_attr(income, 'monthly_rent_estimate'))}/mo"
    if rent_value:
        source_kind = "confirmed" if rent_source is InputCoverageStatus.USER_SUPPLIED else "inferred"
        source_label = "User Confirmed" if source_kind == "confirmed" else "Model Inferred"
        note = component_map.get("rent").reason if component_map.get("rent") else ""
        if assumptions and assumptions.rent_confidence_override:
            note = f"{note} Rent confidence override: {assumptions.rent_confidence_override.title()}."
        items.append(
            AssumptionTransparencyItem(
                label="Rent",
                value=rent_value,
                source_kind=source_kind,
                source_label=source_label,
                note=note,
            )
        )

    capex_value = None
    if property_input.repair_capex_budget is not None:
        capex_value = _fmt_currency(property_input.repair_capex_budget)
    elif property_input.capex_lane:
        capex_value = property_input.capex_lane.replace("_", " ").title()
    if capex_value:
        capex_override = bool(
            (assumptions and assumptions.capex_lane_override)
            or getattr(property_input, "capex_confirmed", False)
            or property_input.repair_capex_budget is not None
        )
        source_kind = "confirmed" if capex_override else "inferred"
        source_label = "User Confirmed" if source_kind == "confirmed" else "Model Inferred"
        note = component_map.get("capex").reason if component_map.get("capex") else ""
        items.append(
            AssumptionTransparencyItem(
                label="CapEx",
                value=capex_value,
                source_kind=source_kind,
                source_label=source_label,
                note=note,
            )
        )

    if property_input.condition_profile:
        condition_override = bool((assumptions and assumptions.condition_profile_override) or getattr(property_input, "condition_confirmed", False))
        source_kind = "confirmed" if condition_override else "inferred"
        source_label = "User Confirmed" if source_kind == "confirmed" else "Model Inferred"
        items.append(
            AssumptionTransparencyItem(
                label="Condition",
                value=property_input.condition_profile.replace("_", " ").title(),
                source_kind=source_kind,
                source_label=source_label,
                note="Current condition informs CapEx burden and execution confidence.",
            )
        )

    financing_parts: list[str] = []
    if property_input.down_payment_percent is not None:
        financing_parts.append(f"{property_input.down_payment_percent * 100:.0f}% down")
    if property_input.interest_rate is not None:
        financing_parts.append(f"{property_input.interest_rate * 100:.2f}% rate")
    if property_input.loan_term_years is not None:
        financing_parts.append(f"{property_input.loan_term_years}y term")
    if financing_parts:
        items.append(
            AssumptionTransparencyItem(
                label="Financing",
                value=" / ".join(financing_parts),
                source_kind="confirmed",
                source_label="User Confirmed",
                note="These inputs feed monthly carry, cash flow, and downside support.",
            )
        )
    else:
        items.append(
            AssumptionTransparencyItem(
                label="Financing",
                value="Incomplete",
                source_kind="inferred",
                source_label="Model Inferred",
                note="Monthly carry confidence stays lower until down payment, rate, and term are supplied.",
            )
        )

    preference_parts: list[str] = []
    if getattr(property_input, "strategy_intent", None):
        preference_parts.append(property_input.strategy_intent.replace("_", " ").title())
    if getattr(property_input, "hold_period_years", None) is not None:
        preference_parts.append(f"{property_input.hold_period_years}y hold")
    if getattr(property_input, "risk_tolerance", None):
        preference_parts.append(f"{property_input.risk_tolerance.title()} risk")
    if preference_parts:
        items.append(
            AssumptionTransparencyItem(
                label="Strategy",
                value=" / ".join(preference_parts),
                source_kind="preference",
                source_label="User Preference",
                note="Preference inputs shape interpretation and fit, but do not raise factual confidence on their own.",
            )
        )

    return items


def _confidence_level(confidence: float) -> str:
    if confidence >= 0.75:
        return "High"
    if confidence >= 0.55:
        return "Medium"
    return "Low"


def _driver_strength(score: float) -> str:
    if score >= 28:
        return "strong"
    if score >= 18:
        return "moderate"
    return "light"


def _signal_summary(metric: str, value: float | None) -> str:
    if value is None:
        return "unavailable"
    if metric == "valuation_gap":
        return f"{abs(value) * 100:.0f}% vs basis"
    if metric == "monthly_cash_flow":
        return f"{_fmt_currency(value)}/mo"
    if metric == "income_support_ratio":
        return f"{value:.2f}x coverage"
    if metric == "liquidity_score":
        return f"{value:.0f}/100"
    if metric == "risk_score":
        return f"{value:.0f}/100 risk"
    if metric == "price_to_rent":
        return f"{value:.1f}x PTR"
    if metric == "subject_ppsf_vs_town":
        return f"{abs((value - 1.0) * 100):.0f}% vs town PPSF"
    if metric == "town_adjusted_value_gap":
        return f"{abs(value) * 100:.0f}% vs town baseline"
    if metric == "market_momentum_score":
        return f"{value:.0f}/100 momentum"
    return str(value)


def _entry_basis_label(valuation_pct: float | None) -> str:
    if valuation_pct is None:
        return "Unclear Basis"
    if valuation_pct >= 0.12:
        return "Discounted Entry"
    if valuation_pct >= 0.04:
        return "Supported Entry"
    if valuation_pct > -0.04:
        return "Market Entry"
    if valuation_pct > -0.12:
        return "Rich Entry"
    return "Premium Entry"


def _income_support_label(monthly_cash_flow: float | None, income_support_ratio: float | None) -> str:
    if isinstance(income_support_ratio, (int, float)):
        if income_support_ratio >= 1.05:
            return "Self-Supporting"
        if income_support_ratio >= 0.90:
            return "Partially Supported"
        if income_support_ratio >= 0.75:
            return "Support-Light"
        return "Support-Dependent"
    if isinstance(monthly_cash_flow, (int, float)):
        if monthly_cash_flow >= 250:
            return "Self-Supporting"
        if monthly_cash_flow >= -250:
            return "Partially Supported"
        if monthly_cash_flow >= -750:
            return "Support-Light"
        return "Support-Dependent"
    return "Support-Unclear"


def _capex_load_label(capex_lane: str, capex_status: str | None) -> str:
    lane = (capex_lane or "").strip().lower()
    if lane in {"light", "low"} and capex_status == "confirmed":
        return "Light Confirmed CapEx"
    if lane in {"light", "low"}:
        return "Light CapEx"
    if lane == "moderate" and capex_status == "confirmed":
        return "Moderate Confirmed CapEx"
    if lane == "moderate":
        return "Moderate CapEx"
    if lane == "heavy" and capex_status == "confirmed":
        return "Heavy Confirmed CapEx"
    if lane == "heavy":
        return "Heavy CapEx"
    return "CapEx Unclear"


def _liquidity_profile_label(liquidity_score: float) -> str:
    if liquidity_score >= 70:
        return "High Liquidity"
    if liquidity_score >= 55:
        return "Functional Liquidity"
    if liquidity_score >= 40:
        return "Mixed Liquidity"
    if liquidity_score >= 28:
        return "Thin Liquidity"
    return "Constrained Liquidity"


def _optionality_label(best_fit: str, renovated_value: float | None, bull_case: float | None) -> str:
    if best_fit == "Redevelopment":
        return "Value-Add Optionality"
    if best_fit == "Hybrid":
        return "Flexible Optionality"
    if best_fit == "Primary Residence":
        return "Lifestyle Optionality"
    if best_fit == "Rental Investor":
        return "Yield Optionality"
    if isinstance(renovated_value, (int, float)) or isinstance(bull_case, (int, float)):
        return "Value-Add Optionality"
    return "Limited Optionality"


def _risk_skew_label(risk_score: float, confidence_score: int) -> str:
    if risk_score <= 30 or confidence_score < 40:
        return "High Downside Skew"
    if risk_score <= 45 or confidence_score < 60:
        return "Guarded Downside Skew"
    if risk_score <= 60:
        return "Balanced Risk Skew"
    return "Constructive Risk Skew"


def _positioning_summary(
    *,
    entry_basis_label: str,
    income_support_label: str,
    capex_load_label: str,
    liquidity_profile_label: str,
    optionality_label: str,
    risk_skew_label: str,
) -> PositioningSummaryViewModel:
    summary_line = " | ".join([
        entry_basis_label,
        income_support_label,
        capex_load_label,
        liquidity_profile_label,
        optionality_label,
        risk_skew_label,
    ])
    return PositioningSummaryViewModel(
        entry_basis_label=entry_basis_label,
        income_support_label=income_support_label,
        capex_load_label=capex_load_label,
        liquidity_profile_label=liquidity_profile_label,
        optionality_label=optionality_label,
        risk_skew_label=risk_skew_label,
        summary_line=summary_line,
    )


_REPORT_CARD_WEIGHTS: dict[str, float] = {
    "entry_basis": 0.25,
    "income_support": 0.20,
    "capex_load": 0.15,
    "liquidity_profile": 0.15,
    "optionality": 0.15,
    "risk_skew": 0.10,
}


def _clamp_unit(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _entry_basis_factor_score(valuation_pct: float | None) -> float:
    if valuation_pct is None:
        return 0.0
    return _clamp_unit(valuation_pct / 0.15)


def _income_support_factor_score(monthly_cash_flow: float | None, income_support_ratio: float | None) -> float:
    score_parts: list[float] = []
    if isinstance(income_support_ratio, (int, float)):
        score_parts.append(_clamp_unit((income_support_ratio - 1.0) / 0.35))
    if isinstance(monthly_cash_flow, (int, float)):
        score_parts.append(_clamp_unit(monthly_cash_flow / 1000.0))
    if not score_parts:
        return 0.0
    return _clamp_unit(sum(score_parts) / len(score_parts))


def _capex_factor_score(capex_lane: str, capex_status: str | None) -> float:
    lane = (capex_lane or "").strip().lower()
    lane_score = {
        "light": 0.75,
        "low": 0.75,
        "moderate": 0.0,
        "heavy": -0.8,
    }.get(lane, -0.1)
    if capex_status == "confirmed":
        lane_score += 0.15
    elif capex_status == "missing":
        lane_score -= 0.20
    elif capex_status == "estimated":
        lane_score -= 0.10
    return _clamp_unit(lane_score)


def _liquidity_factor_score(liquidity_score: float) -> float:
    return _clamp_unit((liquidity_score - 50.0) / 30.0)


def _optionality_factor_score(best_fit: str, renovated_value: float | None, bull_case: float | None) -> float:
    if best_fit == "Redevelopment":
        return 0.75
    if best_fit == "Hybrid":
        return 0.45
    if best_fit == "Primary Residence":
        return 0.20
    if best_fit == "Rental Investor":
        return 0.10
    if isinstance(renovated_value, (int, float)) or isinstance(bull_case, (int, float)):
        return 0.35
    return -0.10


def _risk_skew_factor_score(risk_score: float, confidence_score: int) -> float:
    risk_component = _clamp_unit((risk_score - 55.0) / 30.0)
    confidence_component = _clamp_unit((confidence_score - 60.0) / 40.0)
    return _clamp_unit((risk_component * 0.7) + (confidence_component * 0.3))


def _report_card_explanation(factor_name: str, view: PropertyAnalysisView) -> str:
    if factor_name == "entry_basis":
        valuation_pct = view.net_opportunity_delta_pct if view.net_opportunity_delta_pct is not None else view.mispricing_pct
        entry_basis_label = _entry_basis_label(valuation_pct)
        if isinstance(valuation_pct, (int, float)):
            return f"{entry_basis_label} based on about {abs(valuation_pct) * 100:.0f}% versus basis."
        return f"{entry_basis_label} because value support is incomplete."
    if factor_name == "income_support":
        ratio = view.compare_metrics.get("income_support_ratio")
        cash_flow = view.compare_metrics.get("monthly_cash_flow")
        if isinstance(ratio, (int, float)):
            return f"{view.income_support_label} with about {ratio:.2f}x income coverage."
        if isinstance(cash_flow, (int, float)):
            return f"{view.income_support_label} with about {_fmt_currency(cash_flow)}/mo cash flow."
        return f"{view.income_support_label} because rent support is incomplete."
    if factor_name == "capex_load":
        return f"{view.capex_load_label} from the current {view.capex_lane.lower()} capex lane."
    if factor_name == "liquidity_profile":
        return f"{view.liquidity_profile_label} with liquidity near {view.risk_location.liquidity_score:.0f}/100."
    if factor_name == "optionality":
        return f"{view.optionality_label} based on the current strategy fit and upside structure."
    risk_skew_label = _risk_skew_label(
        float(view.risk_location.risk_score),
        max(0, min(int(round((view.overall_confidence or 0.0) * 100)), 100)),
    )
    return f"{risk_skew_label} with risk near {view.risk_location.risk_score:.0f}/100 and confidence around {view.overall_confidence:.0%}."


def _build_report_card(view: PropertyAnalysisView) -> ReportCardViewModel:
    valuation_pct = view.net_opportunity_delta_pct if view.net_opportunity_delta_pct is not None else view.mispricing_pct
    monthly_cash_flow = view.compare_metrics.get("monthly_cash_flow")
    income_support_ratio = view.compare_metrics.get("income_support_ratio")
    confidence_score = max(0, min(int(round((view.overall_confidence or 0.0) * 100)), 100))
    assumption_map = {item.key: item for item in (view.evidence.assumption_statuses if view.evidence else [])}
    capex_status = assumption_map.get("capex").status if assumption_map.get("capex") is not None else None
    best_fit = _strategy_fit_label(view.lens_scores)
    renovated_value = view.compare_metrics.get("renovated_bcv")

    factor_scores = {
        "entry_basis": _entry_basis_factor_score(valuation_pct),
        "income_support": _income_support_factor_score(monthly_cash_flow, income_support_ratio),
        "capex_load": _capex_factor_score(view.capex_lane, capex_status),
        "liquidity_profile": _liquidity_factor_score(view.risk_location.liquidity_score),
        "optionality": _optionality_factor_score(best_fit, renovated_value, view.bull_case),
        "risk_skew": _risk_skew_factor_score(view.risk_location.risk_score, confidence_score),
    }
    raw_contributions = {
        factor_name: factor_scores[factor_name] * weight
        for factor_name, weight in _REPORT_CARD_WEIGHTS.items()
    }
    abs_total = sum(abs(value) for value in raw_contributions.values())
    normalized_contributions = {
        factor_name: int(round((value / abs_total) * 100)) if abs_total > 0 else 0
        for factor_name, value in raw_contributions.items()
    }

    positives: list[ReportCardContributionItem] = []
    negatives: list[ReportCardContributionItem] = []
    for factor_name, impact in normalized_contributions.items():
        explanation = _report_card_explanation(factor_name, view)
        item = ReportCardContributionItem(
            factor_name=factor_name,
            percentage_impact=abs(impact),
            explanation=explanation,
        )
        if impact > 0:
            positives.append(item)
        elif impact < 0:
            negatives.append(item)

    positives.sort(key=lambda item: item.percentage_impact, reverse=True)
    negatives.sort(key=lambda item: item.percentage_impact, reverse=True)
    return ReportCardViewModel(
        positive=positives[:3],
        negative=negatives[:3],
        factor_scores={key: round(value, 3) for key, value in factor_scores.items()},
        factor_contributions=normalized_contributions,
    )


def _strategy_fit_label(lens_scores: Any | None) -> str:
    if lens_scores is None:
        return "Hybrid"
    recommended = (getattr(lens_scores, "recommended_lens", "") or "").strip().lower()
    mapping = {
        "owner": "Primary Residence",
        "investor": "Rental Investor",
        "developer": "Redevelopment",
    }
    if recommended in mapping:
        return mapping[recommended]

    owner = getattr(lens_scores, "owner_score", None)
    investor = getattr(lens_scores, "investor_score", None)
    developer = getattr(lens_scores, "developer_score", None)
    scored = {
        "Primary Residence": owner,
        "Rental Investor": investor,
        "Redevelopment": developer,
    }
    valid = {label: score for label, score in scored.items() if isinstance(score, (int, float))}
    if not valid:
        return "Hybrid"
    ranked = sorted(valid.items(), key=lambda item: item[1], reverse=True)
    if len(ranked) >= 2 and abs(ranked[0][1] - ranked[1][1]) <= 0.35 and ranked[0][0] in {"Primary Residence", "Rental Investor"} and ranked[1][0] in {"Primary Residence", "Rental Investor"}:
        return "Hybrid"
    return ranked[0][0]


def _category_display_label(category_key: str | None) -> str:
    mapping = {
        "price_context": "Price context",
        "economic_support": "Hold economics",
        "optionality": "Strategic optionality",
        "market_position": "Market position",
        "risk_layer": "Downside resilience",
    }
    return mapping.get(str(category_key or ""), "Overall underwriting")


def _build_decision_view(view: PropertyAnalysisView, report: AnalysisReport) -> DecisionViewModel:
    decision_output = build_decision(report)
    recommendation = decision_output.recommendation
    final_score = float(view.final_score or 0.0)
    confidence_level = view.confidence_level or _confidence_level(view.overall_confidence)
    best_fit = _strategy_fit_label(view.lens_scores)
    display_fit = "Value-Add / Renovation" if best_fit == "Redevelopment" else best_fit

    category_scores = view.category_scores or {}
    ranked_categories = sorted(
        category_scores.items(),
        key=lambda item: getattr(item[1], "score", 0.0),
        reverse=True,
    )
    strongest_category_key = ranked_categories[0][0] if ranked_categories else None
    weakest_category_key = ranked_categories[-1][0] if ranked_categories else None
    strongest_dimension = _category_display_label(strongest_category_key)
    weakest_dimension = _category_display_label(weakest_category_key)
    dominant_value_driver = max(
        (
            driver
            for driver in view.value.value_drivers
            if abs(_parse_currency_text(driver.impact_text) or 0.0) > 0
        ),
        key=lambda item: abs(_parse_currency_text(item.impact_text) or 0.0),
        default=None,
    )

    assumption_statuses = view.evidence.assumption_statuses if view.evidence else []
    missing_assumptions = [item for item in assumption_statuses if item.status == "missing"]
    estimated_assumptions = [item for item in assumption_statuses if item.status == "estimated"]
    confirmed_assumptions = sum(1 for item in assumption_statuses if item.status == "confirmed")
    total_assumptions = len(assumption_statuses)
    assumption_completeness = 1.0 if total_assumptions == 0 else confirmed_assumptions / total_assumptions

    conviction_score = max(0, min(int(round(decision_output.conviction * 100)), 100))

    supporting_factors: list[str] = []
    for item in [
        decision_output.primary_reason,
        decision_output.secondary_reason,
        *((view.value_finder.bullets if view.value_finder is not None else [])[:2]),
    ]:
        if item and item not in supporting_factors:
            supporting_factors.append(item)

    risk_labels = [item.label for item in view.risk_bar if item.level == "High"]
    risks = list(view.top_risks)
    for item in risk_labels:
        if item and item not in risks:
            risks.append(item)

    positive_drivers = [
        DecisionDriverItem(metric="reason", direction="+", strength="moderate", summary=item)
        for item in supporting_factors[:3]
    ]
    negative_drivers = [
        DecisionDriverItem(metric="risk", direction="-", strength="moderate", summary=item)
        for item in risks[:3]
    ]

    primary_risk = risks[0] if risks else "No single risk dominates yet."
    if weakest_category_key:
        break_condition = f"{weakest_dimension} is the weakest scored dimension. Main risk: {primary_risk}"
    else:
        break_condition = primary_risk

    dependency_lines: list[str] = []
    for item in missing_assumptions[:2]:
        dependency_lines.append(f"{item.label.lower()} is still missing")
    for item in estimated_assumptions[:2]:
        line = f"{item.label.lower()} is still estimated"
        if line not in dependency_lines:
            dependency_lines.append(line)
    for item in list(decision_output.required_beliefs)[:2]:
        if item and item not in dependency_lines:
            dependency_lines.append(item)
    dependencies = dependency_lines[:3]

    required_beliefs = list(decision_output.required_beliefs)
    required_belief = required_beliefs[0] if required_beliefs else "Core underwriting assumptions need to hold close to the current base case."
    thesis = f"{decision_output.primary_reason} {decision_output.secondary_reason}".strip()
    decisive_driver = decision_output.primary_reason

    fit_context = ""
    if display_fit == "Value-Add / Renovation" and view.bull_case is not None:
        fit_context = f"This reads more like a value-add case than a plain hold. The current upside anchor is about {_fmt_currency(view.bull_case)}."

    risk_statement = f"Primary risk: {primary_risk}."
    summary_view = (
        f"{recommendation}. {decision_output.primary_reason} {decision_output.secondary_reason}".strip()
    )

    disqualifiers: list[str] = []
    if recommendation == "AVOID":
        disqualifiers.append(primary_risk)
    if confidence_level == "Low":
        disqualifiers.append("confidence is still too low for a high-conviction call")
    if view.risk_location.liquidity_score < 35:
        disqualifiers.append("exit liquidity is still thin")

    return DecisionViewModel(
        recommendation=recommendation,
        conviction_score=conviction_score,
        conviction=decision_output.conviction,
        best_fit=display_fit,
        confidence_level=confidence_level,
        thesis=thesis,
        primary_reason=decision_output.primary_reason,
        secondary_reason=decision_output.secondary_reason,
        required_beliefs=required_beliefs,
        decisive_driver=decisive_driver,
        decision_drivers={
            "positive": positive_drivers,
            "negative": negative_drivers,
        },
        break_condition=break_condition,
        required_belief=required_belief,
        risk_statement=risk_statement,
        summary_view=summary_view,
        primary_risk=primary_risk,
        what_changes_view=required_belief,
        primary_driver=decisive_driver,
        fit_context=fit_context,
        supporting_factors=supporting_factors[:4],
        risks=risks[:3],
        dependencies=dependencies,
        disqualifiers=disqualifiers[:3],
    )
