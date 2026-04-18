"""Agent tool handlers.

Each tool is a pure Python function with a narrow signature. Tools are
registered with the answer types that are allowed to invoke them — dispatch
enforces this, not the LLM.

Primary seams:
- get_property_summary: cheap, reads saved_properties/{id}/summary.json
- analyze_property: wraps run_routed_report (full pipeline)
- research_town: town-intelligence collection + synthesis
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from enum import Enum
import json
from dataclasses import dataclass
from pathlib import Path
import re
from statistics import median
from typing import Any

from briarwood.agent.router import AnswerType
from briarwood.data_sources.attom_client import AttomClient
from briarwood.data_sources.google_maps_client import GoogleMapsClient
from briarwood.data_sources.searchapi_zillow_client import SearchApiZillowClient

SAVED_PROPERTIES_DIR = Path("data/saved_properties")


@dataclass(frozen=True)
class ToolError:
    tool: str
    message: str


class ToolUnavailable(Exception):
    """Raised when a tool cannot answer (e.g., unknown property_id)."""


@dataclass(frozen=True)
class PropertyBrief:
    """Underwrite-lite purchase brief for browse-style property questions."""

    property_id: str
    address: str | None
    town: str | None
    state: str | None
    beds: int | None
    baths: float | None
    ask_price: float | None
    pricing_view: str | None
    analysis_depth_used: str | None
    recommendation: str | None
    decision: str | None
    decision_stance: str | None
    best_path: str | None
    key_value_drivers: list[str]
    key_risks: list[str]
    trust_flags: list[str]
    recommended_next_run: str | None
    next_questions: list[str]
    primary_value_source: str | None
    fair_value_base: float | None
    ask_premium_pct: float | None


@dataclass(frozen=True)
class RenovationResaleOutlook:
    """Scenario-first flip / ARV view for renovation and resale questions."""

    property_id: str
    address: str | None
    town: str | None
    state: str | None
    listing_ask_price: float | None
    entry_basis: float | None
    all_in_basis: float | None
    fair_value_base: float | None
    decision_stance: str | None
    recommendation: str | None
    best_path: str | None
    renovated_bcv: float | None
    current_bcv: float | None
    renovation_budget: float | None
    gross_value_creation: float | None
    net_value_creation: float | None
    roi_pct: float | None
    total_hold_cost: float | None
    budget_overrun_margin_pct: float | None
    margin_scenarios: list[dict[str, Any]]
    trust_flags: list[str]
    key_risks: list[str]


@dataclass(frozen=True)
class LiveListingCandidate:
    address: str | None
    town: str | None
    state: str | None
    zip_code: str | None
    ask_price: float | None
    beds: int | None
    baths: float | None
    sqft: int | None
    property_type: str | None
    listing_status: str | None
    listing_url: str | None
    external_id: str | None
    source: str = "searchapi_zillow"


@dataclass(frozen=True)
class LiveListingDecision:
    address: str | None
    ask_price: float | None
    fair_value_base: float | None
    all_in_basis: float | None
    decision_stance: str | None
    primary_value_source: str | None
    trust_flags: list[str]
    recommendation: str | None
    best_path: str | None


@dataclass(frozen=True)
class PromotedPropertyRecord:
    property_id: str
    address: str | None
    town: str | None
    state: str | None
    promotion_status: str
    intake_warnings: list[str]
    created_new: bool
    sourced_fields: list[str]
    inferred_fields: list[str]
    missing_fields: list[str]
    listing_url: str | None = None


@dataclass(frozen=True)
class CapRateScreenResult:
    property_id: str
    address: str | None
    town: str | None
    state: str | None
    ask_price: float | None
    annual_noi: float | None
    monthly_rent: float | None
    cap_rate: float | None
    rent_source_type: str | None


@dataclass(frozen=True)
class ComparableProperty:
    property_id: str
    address: str | None
    town: str | None
    state: str | None
    beds: int | None
    baths: float | None
    ask_price: float | None
    blocks_to_beach: float | None
    selection_rationale: str | None = None


@dataclass(frozen=True)
class CMAResult:
    property_id: str
    address: str | None
    town: str | None
    state: str | None
    ask_price: float | None
    fair_value_base: float | None
    value_low: float | None
    value_high: float | None
    pricing_view: str | None
    primary_value_source: str | None
    comp_selection_summary: str | None
    comps: list[ComparableProperty]
    confidence_notes: list[str]
    missing_fields: list[str]


@dataclass(frozen=True)
class RentOutlook:
    property_id: str
    address: str | None
    current_monthly_rent: float | None
    effective_monthly_rent: float | None
    annual_noi: float | None
    rent_source_type: str | None
    rental_ease_label: str | None
    rental_ease_score: float | None
    horizon_years: int | None
    future_rent_low: float | None
    future_rent_mid: float | None
    future_rent_high: float | None
    basis_to_rent_framing: str | None
    owner_occupy_then_rent: str | None
    zillow_market_rent: float | None
    zillow_market_rent_low: float | None
    zillow_market_rent_high: float | None
    zillow_rental_comp_count: int
    burn_chart_payload: dict[str, Any]
    confidence_notes: list[str]


@dataclass(frozen=True)
class TownMarketRead:
    town: str
    state: str
    confidence_label: str | None
    narrative_summary: str | None
    bullish_signals: list[str]
    bearish_signals: list[str]
    watch_items: list[str]
    document_count: int | None
    warnings: list[str]


@dataclass(frozen=True)
class InvestmentScreenResult:
    filters: dict[str, Any]
    target_cap_rate: float | None
    summary: str
    candidates: list[CapRateScreenResult]


# ---------- get_property_summary ----------


def get_property_summary(property_id: str) -> dict[str, Any]:
    path = SAVED_PROPERTIES_DIR / property_id / "summary.json"
    if not path.exists():
        raise ToolUnavailable(f"no saved property with id '{property_id}'")
    return json.loads(path.read_text())


# ---------- analyze_property ----------


def analyze_property(
    property_id: str,
    *,
    force_refresh: bool = False,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the full routed pipeline and return UnifiedIntelligenceOutput as dict.

    ``overrides`` supports what-if scenarios (e.g. ``{"ask_price": 1_300_000}``).
    When supplied, the inputs.json is mutated in a tempfile before the pipeline
    runs — the on-disk record is never touched.
    """
    from briarwood.agent.overrides import inputs_with_overrides
    from briarwood.runner_routed import run_routed_report

    inputs_path = SAVED_PROPERTIES_DIR / property_id / "inputs.json"
    if not inputs_path.exists():
        raise ToolUnavailable(f"no inputs.json for property '{property_id}'")

    with inputs_with_overrides(inputs_path, overrides or {}) as effective_path:
        result = run_routed_report(effective_path)
    return result.unified_output.model_dump()


def build_property_brief(
    property_id: str,
    summary: dict[str, Any],
    unified: dict[str, Any],
) -> PropertyBrief:
    """Project a PropertyBrief from an already-computed unified output."""
    value_position = dict(unified.get("value_position") or {})
    return PropertyBrief(
        property_id=property_id,
        address=summary.get("address"),
        town=summary.get("town"),
        state=summary.get("state"),
        beds=summary.get("beds"),
        baths=summary.get("baths"),
        ask_price=summary.get("ask_price"),
        pricing_view=summary.get("pricing_view"),
        analysis_depth_used=_enum_value(unified.get("analysis_depth_used")),
        recommendation=unified.get("recommendation"),
        decision=_enum_value(unified.get("decision")),
        decision_stance=_enum_value(unified.get("decision_stance")),
        best_path=unified.get("best_path"),
        key_value_drivers=list(unified.get("key_value_drivers") or []),
        key_risks=list(unified.get("key_risks") or []),
        trust_flags=list(unified.get("trust_flags") or []),
        recommended_next_run=unified.get("recommended_next_run"),
        next_questions=list(unified.get("next_questions") or []),
        primary_value_source=unified.get("primary_value_source"),
        fair_value_base=value_position.get("fair_value_base"),
        ask_premium_pct=value_position.get("ask_premium_pct"),
    )


def get_property_brief(
    property_id: str,
    *,
    overrides: dict[str, Any] | None = None,
) -> PropertyBrief:
    """Run a stable snapshot-style routed analysis for a first purchase read."""
    from briarwood.agent.overrides import inputs_with_overrides
    from briarwood.runner_routed import run_routed_report

    inputs_path = SAVED_PROPERTIES_DIR / property_id / "inputs.json"
    if not inputs_path.exists():
        raise ToolUnavailable(f"no inputs.json for property '{property_id}'")

    summary = get_property_summary(property_id)
    with inputs_with_overrides(inputs_path, overrides or {}) as effective_path:
        result = run_routed_report(
            effective_path,
            user_input="Give me a first purchase read on this property.",
        )
    return build_property_brief(property_id, summary, result.unified_output.model_dump())


def get_renovation_resale_outlook(
    property_id: str,
    *,
    overrides: dict[str, Any] | None = None,
) -> RenovationResaleOutlook:
    """Build a renovation-to-resale scenario payload from native routed modules."""
    from briarwood.agent.overrides import inputs_with_overrides
    from briarwood.runner_routed import run_routed_report

    inputs_path = SAVED_PROPERTIES_DIR / property_id / "inputs.json"
    if not inputs_path.exists():
        raise ToolUnavailable(f"no inputs.json for property '{property_id}'")

    summary = get_property_summary(property_id)
    applied_overrides = overrides or {}
    with inputs_with_overrides(inputs_path, applied_overrides) as effective_path:
        result = run_routed_report(
            effective_path,
            user_input=(
                "Assume a renovation path and tell me the after repair value, "
                "resale range, and margin if we buy, renovate, and sell."
            ),
        )
    outputs = getattr(result.engine_output, "outputs", {}) or {}
    unified = result.unified_output.model_dump()
    arv_data = _module_data(outputs, "arv_model")
    if not arv_data:
        raise ToolUnavailable("renovation resale modules were not selected for this property")
    arv_snapshot = dict(arv_data.get("arv_snapshot") or {})
    margin_data = _module_data(outputs, "margin_sensitivity")
    margin_snapshot = dict(margin_data.get("margin_snapshot") or {})
    value_position = dict(unified.get("value_position") or {})
    decision_stance = _enum_value(unified.get("decision_stance"))
    entry_basis = applied_overrides.get("ask_price")
    if not isinstance(entry_basis, (int, float)):
        entry_basis = summary.get("ask_price")

    return RenovationResaleOutlook(
        property_id=property_id,
        address=summary.get("address"),
        town=summary.get("town"),
        state=summary.get("state"),
        listing_ask_price=summary.get("ask_price"),
        entry_basis=entry_basis,
        all_in_basis=value_position.get("all_in_basis"),
        fair_value_base=value_position.get("fair_value_base"),
        decision_stance=decision_stance,
        recommendation=unified.get("recommendation"),
        best_path=unified.get("best_path"),
        renovated_bcv=arv_snapshot.get("renovated_bcv"),
        current_bcv=arv_snapshot.get("current_bcv"),
        renovation_budget=arv_snapshot.get("renovation_budget"),
        gross_value_creation=arv_snapshot.get("gross_value_creation"),
        net_value_creation=arv_snapshot.get("net_value_creation"),
        roi_pct=arv_snapshot.get("roi_pct"),
        total_hold_cost=margin_snapshot.get("total_hold_cost"),
        budget_overrun_margin_pct=margin_snapshot.get("budget_overrun_margin_pct"),
        margin_scenarios=list(margin_data.get("sensitivity_scenarios") or []),
        trust_flags=list(unified.get("trust_flags") or []),
        key_risks=list(unified.get("key_risks") or []),
    )


# ---------- search_listings ----------


def search_listings(filters: dict[str, Any]) -> list[dict[str, Any]]:
    """Filter the listing index. Returns a list of summary dicts (not full facts)."""
    from briarwood.agent.index import search

    results = search(filters)
    return [
        {
            "property_id": p.property_id,
            "address": p.address,
            "town": p.town,
            "state": p.state,
            "beds": p.beds,
            "baths": p.baths,
            "ask_price": p.ask_price,
            "distance_to_beach_miles": p.distance_to_beach_miles,
            "blocks_to_beach": p.blocks_to_beach,
            "confidence": p.confidence,
        }
        for p in results
    ]


def search_live_listings(
    *,
    query: str,
    max_results: int = 8,
    town: str | None = None,
    state: str | None = None,
    beds: int | None = None,
    beds_min: int | None = None,
    client: SearchApiZillowClient | None = None,
) -> list[LiveListingCandidate]:
    """Run live Zillow discovery through SearchAPI and return Briarwood-shaped candidates."""
    active_client = client or SearchApiZillowClient()
    response = active_client.search_listings(query=query, max_results=max_results)
    if not response.ok:
        raise ToolUnavailable(response.error or "live Zillow discovery failed")
    candidates = active_client.to_listing_candidates(response.normalized_payload)
    if not candidates:
        raise ToolUnavailable("SearchAPI Zillow returned no live listing candidates")
    normalized_town = _norm_place(town)
    normalized_state = _norm_place(state)
    filtered = [
        row
        for row in candidates
        if (
            (not normalized_town or _norm_place(row.town) == normalized_town)
            and (not normalized_state or _norm_place(row.state) == normalized_state)
            and (beds is None or row.beds == beds)
            and (beds_min is None or (isinstance(row.beds, int) and row.beds >= beds_min))
        )
    ]
    if not filtered:
        raise ToolUnavailable("SearchAPI Zillow returned no live listing candidates for the requested town/filters")
    return [
        LiveListingCandidate(
            address=row.address,
            town=row.town,
            state=row.state,
            zip_code=row.zip_code,
            ask_price=row.price,
            beds=row.beds,
            baths=row.baths,
            sqft=row.sqft,
            property_type=row.property_type,
            listing_status=row.listing_status,
            listing_url=row.listing_url,
            external_id=row.zpid,
        )
        for row in filtered[:max_results]
    ]


def _search_zillow_rental_market(
    *,
    town: str | None,
    state: str | None,
    beds: int | None,
    client: SearchApiZillowClient | None = None,
    max_results: int = 8,
) -> dict[str, Any] | None:
    """Query SearchAPI Zillow rentals and return a compact market-rent signal."""
    if not town or not state:
        return None
    active_client = client or SearchApiZillowClient()
    if not active_client.is_configured:
        return None
    response = active_client.search_listings(
        query=f"{town}, {state}",
        max_results=max_results,
        listing_status="for_rent",
        beds_min=max(1, beds - 1) if isinstance(beds, int) else None,
    )
    if not response.ok:
        return None
    rows = active_client.to_listing_candidates(response.normalized_payload)
    filtered = [
        row for row in rows
        if (
            _norm_place(row.town) == _norm_place(town)
            and _norm_place(row.state) == _norm_place(state)
            and (beds is None or (isinstance(row.beds, int) and abs(row.beds - beds) <= 1))
            and isinstance(row.price, (int, float))
        )
    ]
    rents = sorted(float(row.price) for row in filtered if isinstance(row.price, (int, float)))
    if not rents:
        return None
    return {
        "query": f"{town}, {state}",
        "listing_status": "for_rent",
        "rental_comp_count": len(rents),
        "market_rent": round(float(median(rents))),
        "rent_low": round(rents[0]),
        "rent_high": round(rents[-1]),
        "sample_rents": rents[:max_results],
    }


def screen_saved_listings_by_cap_rate(
    *,
    filters: dict[str, Any],
    target_cap_rate: float,
    tolerance: float = 0.0,
    max_results: int = 8,
) -> list[CapRateScreenResult]:
    """Screen saved properties by implied cap rate using Briarwood rent outputs."""
    matches = search_listings(filters)
    screened: list[CapRateScreenResult] = []
    threshold = target_cap_rate - max(0.0, tolerance)
    for match in matches[:20]:
        pid = str(match.get("property_id") or "")
        if not pid:
            continue
        try:
            rent = get_rent_estimate(pid)
        except ToolUnavailable:
            continue
        ask_price = match.get("ask_price")
        annual_noi = rent.get("annual_noi")
        monthly_rent = rent.get("monthly_rent")
        rent_source_type = str(rent.get("rent_source_type") or "") or None
        market_rent = _search_zillow_rental_market(
            town=match.get("town") if isinstance(match.get("town"), str) else None,
            state=match.get("state") if isinstance(match.get("state"), str) else None,
            beds=match.get("beds") if isinstance(match.get("beds"), int) else None,
        )
        if market_rent and isinstance(monthly_rent, (int, float)):
            market_monthly = market_rent.get("market_rent")
            if isinstance(market_monthly, (int, float)):
                if isinstance(annual_noi, (int, float)) and monthly_rent:
                    annual_noi = float(annual_noi) * (float(market_monthly) / float(monthly_rent))
                monthly_rent = float(market_monthly)
                rent_source_type = "zillow_market_rent"
        cap_rate = None
        if isinstance(ask_price, (int, float)) and ask_price > 0 and isinstance(annual_noi, (int, float)):
            cap_rate = float(annual_noi) / float(ask_price)
        if cap_rate is None or cap_rate < threshold:
            continue
        screened.append(
            CapRateScreenResult(
                property_id=pid,
                address=match.get("address"),
                town=match.get("town"),
                state=match.get("state"),
                ask_price=float(ask_price) if isinstance(ask_price, (int, float)) else None,
                annual_noi=float(annual_noi) if isinstance(annual_noi, (int, float)) else None,
                monthly_rent=float(monthly_rent) if isinstance(monthly_rent, (int, float)) else None,
                cap_rate=cap_rate,
                rent_source_type=rent_source_type,
            )
        )
    screened.sort(key=lambda row: row.cap_rate or 0.0, reverse=True)
    return screened[:max_results]


def get_investment_screen(
    *,
    filters: dict[str, Any],
    target_cap_rate: float | None = None,
    tolerance: float = 0.0,
    max_results: int = 8,
) -> InvestmentScreenResult:
    """Return a ranked investment screen contract rather than raw listing rows."""
    candidates: list[CapRateScreenResult] = []
    summary = "No investment candidates qualified."
    if target_cap_rate is not None:
        candidates = screen_saved_listings_by_cap_rate(
            filters=filters,
            target_cap_rate=target_cap_rate,
            tolerance=tolerance,
            max_results=max_results,
        )
        place = ", ".join(
            part for part in (filters.get("town"), filters.get("state")) if isinstance(part, str) and part
        ) or "the saved corpus"
        if candidates:
            summary = (
                f"Found {len(candidates)} saved-corpus candidate(s) near a {target_cap_rate:.1%} cap rate in {place}."
            )
        else:
            summary = (
                f"No saved-corpus candidates cleared roughly {target_cap_rate:.1%} cap rate in {place}."
            )
    return InvestmentScreenResult(
        filters=dict(filters),
        target_cap_rate=target_cap_rate,
        summary=summary,
        candidates=candidates,
    )


def analyze_live_listing(
    *,
    listing_url: str,
    listing_context: dict[str, Any] | None = None,
    user_input: str = "should I buy this property?",
) -> LiveListingDecision:
    """Run a routed analysis directly from a live Zillow URL."""
    from briarwood.inputs.property_loader import load_property_from_listing_intake_result
    from briarwood.listing_intake.normalizer import normalize_listing
    from briarwood.listing_intake.schemas import ListingRawData
    from briarwood.listing_intake.service import ListingIntakeService
    from briarwood.runner_routed import run_routed_analysis_for_property

    if listing_context:
        raw = ListingRawData(
            source="zillow",
            intake_mode="url_intake",
            source_url=listing_url,
            address=str(listing_context.get("address") or "") or None,
            price=_as_float(listing_context.get("ask_price")),
            beds=_as_int(listing_context.get("beds")),
            baths=_as_float(listing_context.get("baths")),
            sqft=_as_int(listing_context.get("sqft")),
            property_type=_as_str(listing_context.get("property_type")),
        )
        intake = normalize_listing(raw, warnings=["Live listing context carried forward from SearchAPI Zillow discovery."])
    else:
        intake = ListingIntakeService().intake_url(listing_url)
    property_input = load_property_from_listing_intake_result(intake, property_id="live-listing")
    result = run_routed_analysis_for_property(property_input, user_input=user_input)
    unified = result.unified_output.model_dump()
    value_position = dict(unified.get("value_position") or {})
    return LiveListingDecision(
        address=result.property_summary.get("address") or intake.normalized_property_data.address,
        ask_price=value_position.get("ask_price") or result.property_summary.get("ask_price"),
        fair_value_base=value_position.get("fair_value_base"),
        all_in_basis=value_position.get("all_in_basis"),
        decision_stance=_enum_value(unified.get("decision_stance")),
        primary_value_source=unified.get("primary_value_source"),
        trust_flags=list(unified.get("trust_flags") or []),
        recommendation=unified.get("recommendation"),
        best_path=unified.get("best_path"),
    )


def promote_discovered_listing(
    *,
    listing_context: dict[str, Any],
) -> PromotedPropertyRecord:
    """Promote a discovered external listing into the saved-property workflow."""
    from briarwood.data_quality.normalizers import normalize_state, normalize_town
    from briarwood.listing_intake.normalizer import normalize_listing
    from briarwood.listing_intake.schemas import ListingRawData

    listing_url = _as_str(listing_context.get("listing_url"))
    raw = ListingRawData(
        source="searchapi_zillow",
        intake_mode="url_intake",
        source_url=listing_url,
        address=_as_str(listing_context.get("address")),
        price=_as_float(listing_context.get("ask_price")),
        beds=_as_int(listing_context.get("beds")),
        baths=_as_float(listing_context.get("baths")),
        sqft=_as_int(listing_context.get("sqft")),
        property_type=_as_str(listing_context.get("property_type")),
    )
    intake = normalize_listing(
        raw,
        warnings=["Live listing context carried forward from SearchAPI Zillow discovery."],
    )
    normalized = intake.normalized_property_data
    resolved_address = normalized.address or raw.address
    if not resolved_address:
        raise ToolUnavailable("promotion needs a resolvable listing address")

    property_id = _existing_or_slugified_property_id(resolved_address)
    property_dir = SAVED_PROPERTIES_DIR / property_id
    created_new = not (property_dir / "inputs.json").exists()

    canonical = intake.normalized_property_data.to_canonical_input(property_id=property_id)
    canonical_payload = _json_ready(asdict(canonical))
    property_dir.mkdir(parents=True, exist_ok=True)
    (property_dir / "inputs.json").write_text(json.dumps(canonical_payload, indent=2) + "\n")
    _write_promoted_summary(
        property_id=property_id,
        listing_context=listing_context,
        intake=intake,
    )

    normalized_town = normalize_town(normalized.town) or normalized.town
    normalized_state = normalize_state(normalized.state) or normalized.state
    sourced_fields = [field for field in ("address", "price_ask", "beds_baths", "sqft") if field not in intake.missing_fields]
    inferred_fields = []
    if normalized.county:
        inferred_fields.append("county")
    if normalized_town and not raw.address:
        inferred_fields.append("town")
    if normalized_state and not raw.address:
        inferred_fields.append("state")
    return PromotedPropertyRecord(
        property_id=property_id,
        address=resolved_address,
        town=normalized_town,
        state=normalized_state,
        promotion_status="created" if created_new else "reused",
        intake_warnings=list(intake.warnings),
        created_new=created_new,
        sourced_fields=sourced_fields,
        inferred_fields=list(dict.fromkeys(inferred_fields)),
        missing_fields=list(intake.missing_fields),
        listing_url=listing_url,
    )


def promote_unsaved_address(address: str) -> PromotedPropertyRecord:
    """Hydrate an unsaved address via Google/ATTOM and promote it into saved properties."""
    from briarwood.data_quality.normalizers import infer_county, normalize_state, normalize_town
    from briarwood.listing_intake.normalizer import normalize_listing
    from briarwood.listing_intake.schemas import ListingRawData

    cleaned_address = _clean_address_query(address)
    if not cleaned_address:
        raise ToolUnavailable("I couldn't extract a usable street address from that question.")

    geocode_client = GoogleMapsClient()
    attom_client = AttomClient()

    geocode_payload: dict[str, Any] = {}
    geocode = geocode_client.geocode(cleaned_address) if geocode_client.is_configured else None
    if geocode and geocode.ok:
        geocode_payload = dict(geocode.normalized_payload or {})

    preliminary_address = _normalize_state_suffix(cleaned_address)
    preliminary_intake = normalize_listing(
        ListingRawData(
            source="attom_direct_address",
            intake_mode="address_intake",
            address=preliminary_address,
        ),
        warnings=[],
    )
    preliminary = preliminary_intake.normalized_property_data

    normalized_address = _as_str(geocode_payload.get("formatted_address")) or cleaned_address
    town = _as_str(geocode_payload.get("town")) or preliminary.town
    state = _as_str(geocode_payload.get("state")) or preliminary.state
    street = normalized_address.split(",", 1)[0].strip() if normalized_address else None
    locality = ", ".join(part for part in (town, state) if part)

    property_detail_payload: dict[str, Any] = {}
    assessment_payload: dict[str, Any] = {}
    sale_history_payload: dict[str, Any] = {}
    rental_payload: dict[str, Any] = {}
    warnings: list[str] = []

    if attom_client.api_key and street and locality:
        property_detail = attom_client.property_detail(cleaned_address, address1=street, address2=locality)
        assessment = attom_client.assessment_detail(cleaned_address, address1=street, address2=locality)
        sale_history = attom_client.sale_history_snapshot(cleaned_address, address1=street, address2=locality)
        rental = attom_client.rental_avm(cleaned_address, address1=street, address2=locality)
        if property_detail.ok:
            property_detail_payload = dict(property_detail.normalized_payload or {})
        elif property_detail.error:
            warnings.append(f"ATTOM property detail unavailable: {property_detail.error}")
        if assessment.ok:
            assessment_payload = dict(assessment.normalized_payload or {})
        elif assessment.error:
            warnings.append(f"ATTOM assessment unavailable: {assessment.error}")
        if sale_history.ok:
            sale_history_payload = dict(sale_history.normalized_payload or {})
        elif sale_history.error:
            warnings.append(f"ATTOM sale history unavailable: {sale_history.error}")
        if rental.ok:
            rental_payload = dict(rental.normalized_payload or {})
        elif rental.error:
            warnings.append(f"ATTOM rental AVM unavailable: {rental.error}")
    else:
        if not attom_client.api_key:
            warnings.append("ATTOM_API_KEY is not configured.")
        else:
            warnings.append("Address normalization was incomplete before ATTOM hydration.")

    raw = ListingRawData(
        source="attom_direct_address",
        intake_mode="address_intake",
        address=_as_str(property_detail_payload.get("address")) or normalized_address,
        price=None,
        beds=_as_int(property_detail_payload.get("beds")),
        baths=_as_float(property_detail_payload.get("baths")),
        sqft=_as_int(property_detail_payload.get("sqft")),
        lot_sqft=_lot_sqft_from_attom(property_detail_payload.get("lot_size")),
        property_type=_as_str(property_detail_payload.get("property_type")),
        year_built=_as_int(property_detail_payload.get("year_built")),
        stories=_as_float(property_detail_payload.get("stories")),
        garage_spaces=_as_int(property_detail_payload.get("garage_spaces")),
        taxes_annual=_as_float(assessment_payload.get("tax_amount")),
    )
    intake = normalize_listing(
        raw,
        warnings=[
            "Unsaved address hydrated through direct address intake.",
            *warnings,
        ],
    )
    normalized = intake.normalized_property_data
    normalized.town = normalize_town(normalized.town) or normalize_town(town) or town
    normalized.state = normalize_state(normalized.state) or normalize_state(state) or state
    normalized.county = (
        normalized.county
        or _as_str(geocode_payload.get("county"))
        or infer_county(town=normalized.town, state=normalized.state, zip_code=normalized.zip_code)
    )
    if not normalized.town or not normalized.state or len(str(normalized.state)) != 2:
        raise ToolUnavailable(
            "I couldn't confirm the town/state cleanly enough to promote that address yet."
        )
    has_core_facts = any(
        value is not None
        for value in (
            normalized.address,
            normalized.beds,
            normalized.baths,
            normalized.sqft,
            normalized.year_built,
        )
    )
    if not has_core_facts:
        raise ToolUnavailable("I couldn't hydrate enough structured property data for that address yet.")

    property_id = _existing_or_slugified_property_id(normalized.address or normalized_address)
    property_dir = SAVED_PROPERTIES_DIR / property_id
    created_new = not (property_dir / "inputs.json").exists()
    canonical = intake.normalized_property_data.to_canonical_input(property_id=property_id)
    canonical_payload = _json_ready(asdict(canonical))

    facts = canonical_payload.get("facts") or {}
    if geocode_payload.get("latitude") is not None:
        facts["latitude"] = geocode_payload.get("latitude")
    if geocode_payload.get("longitude") is not None:
        facts["longitude"] = geocode_payload.get("longitude")
    estimated_rent = _as_float(rental_payload.get("estimated_monthly_rent"))
    if estimated_rent is not None:
        facts["estimated_monthly_rent"] = estimated_rent

    source_metadata = canonical_payload.get("source_metadata") or {}
    source_coverage = source_metadata.get("source_coverage") or {}
    if sale_history_payload.get("sale_history"):
        source_coverage["sale_history"] = {"category": "sale_history", "status": "sourced", "source_name": "attom"}
    if estimated_rent is not None:
        source_coverage["rent_estimate"] = {"category": "rent_estimate", "status": "sourced", "source_name": "attom"}
    if geocode_payload:
        source_coverage["location_geocode"] = {"category": "location_geocode", "status": "sourced", "source_name": "google_maps"}
    source_metadata["source_coverage"] = source_coverage

    property_dir.mkdir(parents=True, exist_ok=True)
    (property_dir / "inputs.json").write_text(json.dumps(canonical_payload, indent=2) + "\n")
    _write_promoted_summary(
        property_id=property_id,
        listing_context={"listing_url": None},
        intake=intake,
    )
    return PromotedPropertyRecord(
        property_id=property_id,
        address=normalized.address or normalized_address,
        town=normalized.town,
        state=normalized.state,
        promotion_status="created" if created_new else "reused",
        intake_warnings=list(intake.warnings),
        created_new=created_new,
        sourced_fields=[
            field
            for field in ("address", "beds_baths", "sqft", "taxes")
            if field not in intake.missing_fields
        ],
        inferred_fields=[
            field
            for field in ("county", "town", "state")
            if getattr(normalized, field, None)
        ],
        missing_fields=list(intake.missing_fields),
        listing_url=None,
    )


def _as_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_address_query(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = str(text).strip()
    address_match = re.search(
        r"(\d+\s+[A-Za-z0-9 .'-]+?\b(?:ave|avenue|st|street|rd|road|dr|drive|ln|lane|blvd|boulevard|ct|court|pl|place|way)\b(?:,\s*[A-Za-z .'-]+)?(?:,\s*[A-Z]{2})?(?:\s+\d{5})?)",
        cleaned,
        re.IGNORECASE,
    )
    if address_match:
        cleaned = address_match.group(1).strip()
    patterns = (
        r"^(?:what do you think of|tell me about|what can you tell me about|underwrite|analyze|analyse|look at|lets look at|let's look at|on)\s+",
        r"^(?:property at|house at)\s+",
    )
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(
        r"\b(?:is worth|worth|value|valued at|priced at|price|should i buy|good deal)\b.*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip(" ,")
    return cleaned.strip(" ?!.," ) or None


def _normalize_state_suffix(address: str) -> str:
    return re.sub(
        r"([,\s]+)([A-Za-z]{2})(\s+\d{5})?$",
        lambda match: f"{match.group(1)}{match.group(2).upper()}{match.group(3) or ''}",
        address.strip(),
        count=1,
    )


def _lot_sqft_from_attom(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"(\d[\d,]*)", value)
        if match:
            try:
                return int(match.group(1).replace(",", ""))
            except ValueError:
                return None
    return None


def _existing_or_slugified_property_id(address: str) -> str:
    from briarwood.agent.resolver import resolve_property_id

    existing, _ = resolve_property_id(address)
    if existing:
        return existing
    return _slugify(address)


def saved_property_has_valid_location(property_id: str) -> bool:
    """Return True when a saved property's persisted town/state are usable."""
    from briarwood.data_quality.normalizers import normalize_state, normalize_town

    inputs_path = SAVED_PROPERTIES_DIR / property_id / "inputs.json"
    if not inputs_path.exists():
        return False
    try:
        payload = json.loads(inputs_path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    facts = dict(payload.get("facts") or {})
    town = normalize_town(facts.get("town"))
    state = normalize_state(facts.get("state"))
    return bool(town and state and len(state) == 2)


def _slugify(value: str) -> str:
    text = value.strip().lower()
    text = "".join(ch if ch.isalnum() else "-" for ch in text)
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-") or "saved-property"


def _json_ready(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_ready(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_json_ready(inner) for inner in value]
    return value


def _write_promoted_summary(
    *,
    property_id: str,
    listing_context: dict[str, Any],
    intake: Any,
) -> None:
    normalized = intake.normalized_property_data
    summary = {
        "property_id": property_id,
        "address": normalized.address,
        "label": (normalized.address or property_id).split(",")[0].strip(),
        "town": normalized.town,
        "state": normalized.state,
        "county": normalized.county,
        "beds": normalized.beds,
        "baths": normalized.baths,
        "ask_price": normalized.price,
        "bcv": None,
        "pricing_view": None,
        "property_type": normalized.property_type,
        "source_url": normalized.source_url or _as_str(listing_context.get("listing_url")),
        "confidence": None,
        "comp_trust": "pending",
        "missing_input_count": len(intake.missing_fields),
        "is_hybrid_valuation": False,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    (SAVED_PROPERTIES_DIR / property_id / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


def underwrite_matches(property_ids: list[str]) -> list[dict[str, Any]]:
    """Batch wrapper — runs analyze_property on each id, returns slim stance records."""
    out: list[dict[str, Any]] = []
    for pid in property_ids:
        try:
            u = analyze_property(pid)
        except ToolUnavailable as exc:
            out.append({"property_id": pid, "error": str(exc)})
            continue
        stance = u.get("decision_stance")
        if hasattr(stance, "value"):
            stance = stance.value
        out.append(
            {
                "property_id": pid,
                "decision_stance": stance,
                "primary_value_source": u.get("primary_value_source"),
                "trust_flags": u.get("trust_flags") or [],
                "value_position": u.get("value_position") or {},
            }
        )
    return out


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _norm_place(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).lower().replace("-", " ").split())


def _module_data(outputs: dict[str, Any], module_name: str) -> dict[str, Any]:
    entry = outputs.get(module_name)
    if entry is None:
        return {}
    data = getattr(entry, "data", None)
    if data is None and isinstance(entry, dict):
        data = entry.get("data")
    return dict(data or {})


# ---------- research_town ----------


def research_town(
    town: str,
    state: str,
    focus: list[str] | None = None,
    *,
    service: Any | None = None,
    budget_seconds: float | None = None,
) -> dict[str, Any]:
    """Run the local_intelligence research pipeline with a wall-clock budget.

    Delegates to ``LocalIntelligenceService.research``. Adapters (static
    registry, web search, minutes feed) are wired at service construction.
    Returns a dict with fresh signals + what documents were retrieved so
    callers can diff against a prior state.
    """
    import os

    from briarwood.local_intelligence.service import LocalIntelligenceService

    svc = service or _default_research_service()
    if budget_seconds is None:
        raw = os.environ.get("BRIARWOOD_AGENT_RESEARCH_BUDGET_S")
        try:
            budget_seconds = float(raw) if raw else 30.0
        except ValueError:
            budget_seconds = 30.0

    run = svc.research(town=town, state=state, focus=focus or [], budget_seconds=budget_seconds)
    return {
        "town": town,
        "state": state,
        "focus": focus or [],
        "document_count": len(run.documents),
        "documents": [
            {"title": d.title, "url": d.url, "source_type": d.source_type.value if hasattr(d.source_type, "value") else d.source_type}
            for d in run.documents
        ],
        "signal_count": len(run.signals),
        "summary": run.summary.model_dump(mode="json"),
        "warnings": list(run.warnings or []),
        "missing_inputs": list(run.missing_inputs or []),
    }


def get_town_market_read(
    town: str,
    state: str,
    *,
    focus: list[str] | None = None,
    service: Any | None = None,
    budget_seconds: float | None = None,
) -> TownMarketRead:
    """Return a structured town-market contract for research and UI rendering."""
    result = research_town(
        town,
        state,
        focus=focus,
        service=service,
        budget_seconds=budget_seconds,
    )
    summary = dict(result.get("summary") or {})
    return TownMarketRead(
        town=town,
        state=state,
        confidence_label=summary.get("confidence_label"),
        narrative_summary=summary.get("narrative_summary"),
        bullish_signals=list(summary.get("bullish_signals") or []),
        bearish_signals=list(summary.get("bearish_signals") or []),
        watch_items=list(summary.get("watch_items") or []),
        document_count=result.get("document_count") if isinstance(result.get("document_count"), int) else None,
        warnings=list(result.get("warnings") or []),
    )


def _default_research_service():
    """Build a LocalIntelligenceService with default adapters wired.

    Kept in a helper so tests can inject a fake service via the
    ``research_town(service=...)`` kwarg.
    """
    from briarwood.local_intelligence.collector import MunicipalDocumentCollector
    from briarwood.local_intelligence.service import LocalIntelligenceService
    from briarwood.local_intelligence.sources import StaticRegistryAdapter
    from briarwood.local_intelligence.sources.minutes_feed_adapter import MinutesFeedAdapter
    from briarwood.local_intelligence.sources.web_search_adapter import WebSearchAdapter

    collector = MunicipalDocumentCollector()
    # Prepend web + minutes adapters; static seed adapter already in the default list.
    collector.adapters = [
        WebSearchAdapter(),
        MinutesFeedAdapter(),
        *collector.adapters,
    ]
    return LocalIntelligenceService(collector=collector)


# ---------- get_projection ----------


def get_projection(property_id: str, *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Force scenario-depth analysis and extract bull/base/bear projection.

    Returns a dict with ask_price, {bull,base,bear}_case_value, stress_case_value,
    {bull,base,bear}_total_adjustment_pct, spread. Values come from the
    resale_scenario module (which replaces bull_base_bear under scoped execution).
    """
    from briarwood.agent.overrides import inputs_with_overrides
    from briarwood.runner_routed import run_routed_report

    inputs_path = SAVED_PROPERTIES_DIR / property_id / "inputs.json"
    if not inputs_path.exists():
        raise ToolUnavailable(f"no inputs.json for property '{property_id}'")

    # The internal router keys on these words to select depth=SCENARIO.
    with inputs_with_overrides(inputs_path, overrides or {}) as effective_path:
        result = run_routed_report(
            effective_path,
            user_input="project forward 5 years bull base bear scenarios",
        )
    outputs = getattr(result.engine_output, "outputs", {}) or {}
    entry = outputs.get("resale_scenario") or outputs.get("bull_base_bear")
    if entry is None:
        raise ToolUnavailable("projection modules were not selected for this property")
    data = getattr(entry, "data", None) or (entry.get("data") if isinstance(entry, dict) else None) or {}
    m = data.get("metrics") or {}
    keys = (
        "ask_price", "bull_case_value", "base_case_value", "bear_case_value",
        "stress_case_value", "spread",
        "bull_total_adjustment_pct", "base_total_adjustment_pct", "bear_total_adjustment_pct",
        "bull_growth_rate", "base_growth_rate", "bear_growth_rate",
        "bcv_anchor",
    )
    return {"property_id": property_id, **{k: m.get(k) for k in keys}}


# ---------- get_rent_estimate ----------


def get_rent_estimate(property_id: str, *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the routed pipeline and surface rent-relevant metrics from carry_cost + rental_option modules."""
    from briarwood.agent.overrides import inputs_with_overrides
    from briarwood.runner_routed import run_routed_report

    inputs_path = SAVED_PROPERTIES_DIR / property_id / "inputs.json"
    if not inputs_path.exists():
        raise ToolUnavailable(f"no inputs.json for property '{property_id}'")

    with inputs_with_overrides(inputs_path, overrides or {}) as effective_path:
        result = run_routed_report(
            effective_path,
            user_input="estimate rent, rental profile, and carry support for this property",
        )
    outputs = getattr(result.engine_output, "outputs", {}) or {}

    def _metrics(mod: str) -> dict[str, Any]:
        entry = outputs.get(mod)
        if entry is None:
            return {}
        data = getattr(entry, "data", None)
        if data is None and isinstance(entry, dict):
            data = entry.get("data")
        return (data or {}).get("metrics") or {}

    carry = _metrics("carry_cost")
    rental = _metrics("rental_option")
    return {
        "property_id": property_id,
        "monthly_rent": carry.get("monthly_rent"),
        "effective_monthly_rent": carry.get("effective_monthly_rent"),
        "rent_source_type": carry.get("rent_source_type"),
        "annual_noi": carry.get("annual_noi"),
        "monthly_cash_flow": carry.get("monthly_cash_flow"),
        "cash_on_cash_return": carry.get("cash_on_cash_return"),
        "rental_ease_score": rental.get("rental_ease_score"),
        "rental_ease_label": rental.get("rental_ease_label"),
        "rent_support_score": rental.get("rent_support_score"),
        "estimated_days_to_rent": rental.get("estimated_days_to_rent"),
    }


def get_rent_outlook(
    property_id: str,
    *,
    years: int | None = None,
    overrides: dict[str, Any] | None = None,
    owner_occupy_then_rent: bool = False,
    rent_payload: dict[str, Any] | None = None,
    property_summary: dict[str, Any] | None = None,
) -> RentOutlook:
    """Return a structured rent outlook contract with optional simple horizon framing."""
    from briarwood.settings import DEFAULT_TEARDOWN_SCENARIO_SETTINGS

    rent = rent_payload or get_rent_estimate(property_id, overrides=overrides)
    summary = property_summary or get_property_summary(property_id)
    current = (
        rent.get("effective_monthly_rent")
        if isinstance(rent.get("effective_monthly_rent"), (int, float))
        else rent.get("monthly_rent")
    )
    growth = DEFAULT_TEARDOWN_SCENARIO_SETTINGS.default_annual_rent_growth_pct
    future_low = future_mid = future_high = None
    notes: list[str] = []
    zillow_market = _search_zillow_rental_market(
        town=summary.get("town") if isinstance(summary.get("town"), str) else None,
        state=summary.get("state") if isinstance(summary.get("state"), str) else None,
        beds=summary.get("beds") if isinstance(summary.get("beds"), int) else None,
    )
    market_anchor = zillow_market.get("market_rent") if zillow_market else None
    low_anchor = zillow_market.get("rent_low") if zillow_market else None
    high_anchor = zillow_market.get("rent_high") if zillow_market else None
    if zillow_market:
        notes.append(
            f"SearchAPI Zillow found {zillow_market['rental_comp_count']} nearby rental listing(s), with a market rent anchor near ${zillow_market['market_rent']:,.0f}/mo."
        )
    if years is not None and isinstance(current, (int, float)):
        current_anchor = float(market_anchor) if isinstance(market_anchor, (int, float)) else float(current)
        floor_anchor = float(low_anchor) if isinstance(low_anchor, (int, float)) else float(current_anchor)
        ceiling_anchor = float(high_anchor) if isinstance(high_anchor, (int, float)) else float(current_anchor)
        future_low = round(floor_anchor)
        future_mid = round(current_anchor * ((1.0 + growth) ** years))
        future_high = round(ceiling_anchor * ((1.0 + (growth + 0.02)) ** years))
        notes.append(
            "Future rent uses a flat-to-moderate annual growth assumption, not a dedicated year-by-year rent curve."
        )
    basis = summary.get("ask_price")
    basis_framing = None
    if isinstance(basis, (int, float)) and isinstance(current, (int, float)) and basis > 0:
        annualized = float(current) * 12.0
        basis_framing = f"Current rent annualizes to roughly {annualized / float(basis):.1%} of the current basis."
    owner_path = None
    if owner_occupy_then_rent:
        owner_path = "Owner-occupy then rent can work if the carry is manageable before the lease-up handoff."
    monthly_obligation = None
    if isinstance(rent.get("effective_monthly_rent"), (int, float)) and isinstance(rent.get("monthly_cash_flow"), (int, float)):
        monthly_obligation = float(rent["effective_monthly_rent"]) - float(rent["monthly_cash_flow"])
    burn_years = years or 5
    burn_anchor = float(market_anchor) if isinstance(market_anchor, (int, float)) else float(current) if isinstance(current, (int, float)) else None
    burn_points: list[dict[str, float | int]] = []
    if burn_anchor is not None:
        for year in range(burn_years + 1):
            burn_points.append(
                {
                    "year": year,
                    "rent_base": round(burn_anchor * ((1.0 + growth) ** year)),
                    "rent_bull": round(burn_anchor * ((1.0 + (growth + 0.02)) ** year)),
                    "rent_bear": round(burn_anchor * ((1.0 + max(growth - 0.02, 0.0)) ** year)),
                    "monthly_obligation": round(monthly_obligation) if isinstance(monthly_obligation, (int, float)) else None,
                }
            )
    return RentOutlook(
        property_id=property_id,
        address=summary.get("address"),
        current_monthly_rent=rent.get("monthly_rent") if isinstance(rent.get("monthly_rent"), (int, float)) else None,
        effective_monthly_rent=rent.get("effective_monthly_rent") if isinstance(rent.get("effective_monthly_rent"), (int, float)) else None,
        annual_noi=rent.get("annual_noi") if isinstance(rent.get("annual_noi"), (int, float)) else None,
        rent_source_type=rent.get("rent_source_type"),
        rental_ease_label=rent.get("rental_ease_label"),
        rental_ease_score=rent.get("rental_ease_score") if isinstance(rent.get("rental_ease_score"), (int, float)) else None,
        horizon_years=years,
        future_rent_low=future_low,
        future_rent_mid=future_mid,
        future_rent_high=future_high,
        basis_to_rent_framing=basis_framing,
        owner_occupy_then_rent=owner_path,
        zillow_market_rent=float(market_anchor) if isinstance(market_anchor, (int, float)) else None,
        zillow_market_rent_low=float(low_anchor) if isinstance(low_anchor, (int, float)) else None,
        zillow_market_rent_high=float(high_anchor) if isinstance(high_anchor, (int, float)) else None,
        zillow_rental_comp_count=int(zillow_market.get("rental_comp_count")) if zillow_market else 0,
        burn_chart_payload={
            "series": burn_points,
            "title": "Rent burn chart",
            "monthly_obligation": round(monthly_obligation) if isinstance(monthly_obligation, (int, float)) else None,
        },
        confidence_notes=notes,
    )


# ---------- get_risk_profile ----------


def get_risk_profile(property_id: str, *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Surface risk drivers from risk_model + unified.trust_flags + projection bear case."""
    from briarwood.agent.overrides import inputs_with_overrides
    from briarwood.runner_routed import run_routed_report

    inputs_path = SAVED_PROPERTIES_DIR / property_id / "inputs.json"
    if not inputs_path.exists():
        raise ToolUnavailable(f"no inputs.json for property '{property_id}'")

    with inputs_with_overrides(inputs_path, overrides or {}) as effective_path:
        result = run_routed_report(effective_path, user_input="deep dive stress test full analysis risk")
    outputs = getattr(result.engine_output, "outputs", {}) or {}
    unified = result.unified_output.model_dump()

    def _metrics(mod: str) -> dict[str, Any]:
        entry = outputs.get(mod)
        if entry is None:
            return {}
        data = getattr(entry, "data", None)
        if data is None and isinstance(entry, dict):
            data = entry.get("data")
        return (data or {}).get("metrics") or {}

    risk = _metrics("risk_model")
    scen = _metrics("resale_scenario") or _metrics("bull_base_bear")
    flags_raw = risk.get("risk_flags") or ""
    risk_flags = [f.strip() for f in flags_raw.split(",") if f.strip()] if isinstance(flags_raw, str) else []
    return {
        "property_id": property_id,
        "risk_flags": risk_flags,
        "risk_count": risk.get("risk_count"),
        "total_penalty": risk.get("total_penalty"),
        "total_credit": risk.get("total_credit"),
        "flood_risk": risk.get("flood_risk"),
        "trust_flags": unified.get("trust_flags") or [],
        "key_risks": unified.get("key_risks") or [],
        "ask_price": unified.get("value_position", {}).get("ask_price"),
        "bear_case_value": scen.get("bear_case_value"),
        "stress_case_value": scen.get("stress_case_value"),
        "decision_stance": (unified.get("decision_stance").value
                            if hasattr(unified.get("decision_stance"), "value")
                            else unified.get("decision_stance")),
    }


# ---------- get_value_thesis ----------


def get_value_thesis(property_id: str, *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Explain WHERE the value is: valuation anchors, discount/premium, drivers."""
    from briarwood.agent.overrides import inputs_with_overrides
    from briarwood.runner_routed import run_routed_report

    inputs_path = SAVED_PROPERTIES_DIR / property_id / "inputs.json"
    if not inputs_path.exists():
        raise ToolUnavailable(f"no inputs.json for property '{property_id}'")

    with inputs_with_overrides(inputs_path, overrides or {}) as effective_path:
        result = run_routed_report(effective_path)
    outputs = getattr(result.engine_output, "outputs", {}) or {}
    unified = result.unified_output.model_dump()

    def _metrics(mod: str) -> dict[str, Any]:
        entry = outputs.get(mod)
        if entry is None:
            return {}
        data = getattr(entry, "data", None)
        if data is None and isinstance(entry, dict):
            data = entry.get("data")
        return (data or {}).get("metrics") or {}

    val = _metrics("valuation")
    vp = unified.get("value_position") or {}
    return {
        "property_id": property_id,
        "ask_price": vp.get("ask_price"),
        "fair_value_base": vp.get("fair_value_base"),
        "value_low": vp.get("value_low"),
        "value_high": vp.get("value_high"),
        "premium_discount_pct": vp.get("premium_discount_pct"),
        "mispricing_amount": val.get("mispricing_amount"),
        "mispricing_pct": val.get("mispricing_pct"),
        "pricing_view": val.get("pricing_view"),
        "value_drivers": val.get("value_drivers"),
        "net_opportunity_delta_value": val.get("net_opportunity_delta_value"),
        "net_opportunity_delta_pct": val.get("net_opportunity_delta_pct"),
        "primary_value_source": unified.get("primary_value_source"),
        "key_value_drivers": unified.get("key_value_drivers") or [],
        "what_must_be_true": unified.get("what_must_be_true") or [],
    }


def get_cma(property_id: str, *, overrides: dict[str, Any] | None = None) -> CMAResult:
    """Return a first-class CMA contract built from subject value plus nearby saved comps."""
    summary = get_property_summary(property_id)
    thesis = get_value_thesis(property_id, overrides=overrides)
    filters: dict[str, Any] = {}
    if summary.get("town"):
        filters["town"] = summary.get("town")
    if summary.get("state"):
        filters["state"] = summary.get("state")
    if isinstance(summary.get("beds"), int):
        filters["beds"] = summary.get("beds")
    nearby = [row for row in search_listings(filters) if row.get("property_id") != property_id] if filters else []
    subject_ask = thesis.get("ask_price")

    def _rank_key(row: dict[str, Any]) -> tuple[int, float]:
        same_baths = 0
        if summary.get("baths") is not None and row.get("baths") == summary.get("baths"):
            same_baths = -1
        ask = row.get("ask_price")
        if isinstance(subject_ask, (int, float)) and isinstance(ask, (int, float)):
            return (same_baths, abs(float(ask) - float(subject_ask)))
        return (same_baths, float("inf"))

    nearby.sort(key=_rank_key)
    selected = nearby[:4]
    comps = [
        ComparableProperty(
            property_id=str(row.get("property_id") or ""),
            address=row.get("address"),
            town=row.get("town"),
            state=row.get("state"),
            beds=row.get("beds") if isinstance(row.get("beds"), int) else None,
            baths=row.get("baths") if isinstance(row.get("baths"), (int, float)) else None,
            ask_price=row.get("ask_price") if isinstance(row.get("ask_price"), (int, float)) else None,
            blocks_to_beach=row.get("blocks_to_beach") if isinstance(row.get("blocks_to_beach"), (int, float)) else None,
            selection_rationale="same town and bedroom count, ranked toward the subject's pricing and layout",
        )
        for row in selected
    ]
    confidence_notes = []
    missing_fields = []
    if not comps:
        confidence_notes.append("No nearby saved-property comps matched the current CMA filters.")
    if thesis.get("fair_value_base") is None:
        missing_fields.append("fair_value_base")
    if thesis.get("ask_price") is None:
        missing_fields.append("ask_price")
    return CMAResult(
        property_id=property_id,
        address=summary.get("address"),
        town=summary.get("town"),
        state=summary.get("state"),
        ask_price=thesis.get("ask_price") if isinstance(thesis.get("ask_price"), (int, float)) else None,
        fair_value_base=thesis.get("fair_value_base") if isinstance(thesis.get("fair_value_base"), (int, float)) else None,
        value_low=thesis.get("value_low") if isinstance(thesis.get("value_low"), (int, float)) else None,
        value_high=thesis.get("value_high") if isinstance(thesis.get("value_high"), (int, float)) else None,
        pricing_view=thesis.get("pricing_view"),
        primary_value_source=thesis.get("primary_value_source"),
        comp_selection_summary="Same-town saved comps, filtered by bedroom count and ranked toward subject pricing.",
        comps=comps,
        confidence_notes=confidence_notes,
        missing_fields=missing_fields,
    )


# ---------- get_strategy_fit ----------


def get_strategy_fit(property_id: str, *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Best-path read: rental profile + valuation stance + unified best_path."""
    from briarwood.agent.overrides import inputs_with_overrides
    from briarwood.runner_routed import run_routed_report

    inputs_path = SAVED_PROPERTIES_DIR / property_id / "inputs.json"
    if not inputs_path.exists():
        raise ToolUnavailable(f"no inputs.json for property '{property_id}'")

    with inputs_with_overrides(inputs_path, overrides or {}) as effective_path:
        result = run_routed_report(effective_path, user_input="best strategy flip rent hold primary")
    outputs = getattr(result.engine_output, "outputs", {}) or {}
    unified = result.unified_output.model_dump()

    def _metrics(mod: str) -> dict[str, Any]:
        entry = outputs.get(mod)
        if entry is None:
            return {}
        data = getattr(entry, "data", None)
        if data is None and isinstance(entry, dict):
            data = entry.get("data")
        return (data or {}).get("metrics") or {}

    rental = _metrics("rental_option")
    carry = _metrics("carry_cost")
    val = _metrics("valuation")
    return {
        "property_id": property_id,
        "best_path": unified.get("best_path"),
        "recommendation": unified.get("recommendation"),
        "primary_value_source": unified.get("primary_value_source"),
        "pricing_view": val.get("pricing_view"),
        "rental_ease_label": rental.get("rental_ease_label"),
        "rental_ease_score": rental.get("rental_ease_score"),
        "rent_support_score": rental.get("rent_support_score"),
        "liquidity_score": rental.get("liquidity_score"),
        "monthly_cash_flow": carry.get("monthly_cash_flow"),
        "cash_on_cash_return": carry.get("cash_on_cash_return"),
        "annual_noi": carry.get("annual_noi"),
    }


# ---------- registry ----------


def render_chart(
    kind: str,
    property_id: str,
    *,
    session_id: str = "default",
    fmt: str = "html",
) -> dict[str, Any]:
    """Run analyze_property, build the requested chart, write it to disk, return its path."""
    from briarwood.agent.rendering import ChartUnavailable, render_chart as _render

    try:
        if kind == "risk_bar":
            payload = get_risk_profile(property_id)
        elif kind == "scenario_fan":
            payload = get_projection(property_id)
        else:
            payload = analyze_property(property_id)
    except ToolUnavailable as exc:
        raise ChartUnavailable(str(exc)) from exc
    path = _render(kind, payload, session_id=session_id, fmt=fmt)
    return {"property_id": property_id, "kind": kind, "path": str(path.resolve()), "format": fmt}


def get_property_enrichment(
    property_id: str,
    *,
    include_town_research: bool = True,
    save_artifact: bool = True,
) -> dict[str, Any]:
    """Build or refresh the post-promotion enrichment bundle for a saved property."""
    from briarwood.pipeline.enrichment import enrich_property

    bundle = enrich_property(
        property_id,
        include_town_research=include_town_research,
        save_artifact=save_artifact,
    )
    return asdict(bundle)


def get_property_presentation(
    property_id: str,
    *,
    include_town_research: bool = False,
    include_risk: bool = True,
    brief: PropertyBrief | None = None,
    enrichment: dict[str, Any] | None = None,
    risk: dict[str, Any] | None = None,
    cma: CMAResult | None = None,
    rent_outlook: RentOutlook | None = None,
    town_read: TownMarketRead | None = None,
    investment_screen: InvestmentScreenResult | None = None,
    contract_type: str = "property_brief",
    analysis_mode: str = "browse",
) -> dict[str, Any]:
    """Build a UI-ready presentation payload from backend model outputs.

    Callers that have already computed ``brief``, ``enrichment``, or ``risk``
    should pass them in to avoid re-running the routed pipeline. Browse flows
    pass ``include_risk=False`` to skip the risk bar chart entirely.
    """
    from briarwood.pipeline.presentation import build_property_presentation

    if brief is None:
        brief = get_property_brief(property_id)
    if enrichment is None:
        try:
            enrichment = get_property_enrichment(
                property_id,
                include_town_research=include_town_research,
                save_artifact=True,
            )
        except Exception:
            enrichment = {}
    if risk is None and include_risk:
        try:
            risk = get_risk_profile(property_id)
        except Exception:
            risk = None

    payload = build_property_presentation(
        property_id,
        brief=brief,
        enrichment=enrichment,
        risk=risk,
        cma=cma,
        rent_outlook=rent_outlook,
        town_read=town_read,
        investment_screen=investment_screen,
        contract_type=contract_type,
        analysis_mode=analysis_mode,
    )
    return asdict(payload)


TOOL_ALLOWED_FOR: dict[str, set[AnswerType]] = {
    "get_property_summary": {AnswerType.LOOKUP, AnswerType.SEARCH, AnswerType.BROWSE, AnswerType.CHITCHAT},
    "analyze_property": {AnswerType.DECISION, AnswerType.COMPARISON, AnswerType.VISUALIZE},
    "search_listings": {AnswerType.SEARCH, AnswerType.BROWSE},
    "underwrite_matches": {AnswerType.SEARCH, AnswerType.COMPARISON},
    "research_town": {AnswerType.RESEARCH, AnswerType.DECISION},
    "render_chart": {AnswerType.VISUALIZE},
    "get_rent_estimate": {AnswerType.RENT_LOOKUP},
    "get_rent_outlook": {AnswerType.RENT_LOOKUP},
    "get_projection": {AnswerType.PROJECTION},
    "get_renovation_resale_outlook": {AnswerType.PROJECTION},
    "get_risk_profile": {AnswerType.RISK, AnswerType.DECISION},
    "get_value_thesis": {AnswerType.EDGE, AnswerType.DECISION},
    "get_cma": {AnswerType.EDGE},
    "get_town_market_read": {AnswerType.RESEARCH},
    "get_investment_screen": {AnswerType.SEARCH},
    "get_strategy_fit": {AnswerType.STRATEGY, AnswerType.DECISION},
    "get_property_enrichment": {AnswerType.BROWSE, AnswerType.DECISION, AnswerType.RESEARCH},
    "get_property_presentation": {AnswerType.BROWSE, AnswerType.DECISION, AnswerType.VISUALIZE},
    "screen_saved_listings_by_cap_rate": {AnswerType.SEARCH},
}


def tool_allowed(tool_name: str, answer_type: AnswerType) -> bool:
    return answer_type in TOOL_ALLOWED_FOR.get(tool_name, set())
