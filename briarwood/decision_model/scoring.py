"""Briarwood scoring metric helpers.

Historical context: this file once housed the full `calculate_final_score`
investment-scoring pipeline (aggregator + category builders + 20+ sub-factor
scorers + narrative generation). That chain was deprecated in Handoff 4 on
2026-04-24 after verification that nothing in production synthesis called
it. See DECISIONS.md 2026-04-24 "PROMOTION_PLAN.md entry 15 scope-limit
paragraph corrected" for the full deprecation rationale.

What remains:
- ``estimate_comp_renovation_premium`` — called 7x from ``briarwood/components.py``
  to estimate a town-level renovation premium from comp condition data.
- ``extract_scoring_metrics`` — flattener that reads across module results
  into a single metrics dict; preserved per the DECISIONS.md amendment.
- Utility helpers: ``_get_metrics``, ``_get_confidence``, ``_get_payload``,
  ``_prop``, ``_clamp``, ``_lerp_score``, ``_safe_ratio``.
"""
from __future__ import annotations

from typing import Any

from briarwood.decision_model.scoring_config import MAX_SCORE, MIN_SCORE
from briarwood.modules.town_aggregation_diagnostics import get_town_context
from briarwood.schemas import AnalysisReport, PropertyInput


# ── Metric extraction ──────────────────────────────────────────────────────────


def _get_metrics(report: AnalysisReport, module_name: str) -> dict[str, Any]:
    result = report.module_results.get(module_name)
    if result is None:
        return {}
    return result.metrics


def _get_confidence(report: AnalysisReport, module_name: str) -> float:
    result = report.module_results.get(module_name)
    return result.confidence if result else 0.0


def _get_payload(report: AnalysisReport, module_name: str) -> Any:
    result = report.module_results.get(module_name)
    return result.payload if result else None


def _prop(report: AnalysisReport) -> PropertyInput | None:
    return report.property_input


def estimate_comp_renovation_premium(report: AnalysisReport) -> dict[str, Any]:
    """Estimate renovation premium from comp condition data.

    Compares median $/sqft of renovated/updated comps vs dated/needs_work comps.
    First tries the matched comp set; if insufficient condition data, falls back
    to the full comp database filtered to the subject's town.
    Returns a dict with premium_pct, estimated_renovated_value, sample counts,
    and a narrative snippet.  Empty dict if insufficient data.
    """
    import statistics
    from pathlib import Path

    pi = report.property_input
    subject_town = (pi.town or "").lower() if pi else ""

    upper: list[float] = []   # renovated / updated comps — $/sqft
    lower: list[float] = []   # dated / needs_work comps — $/sqft
    upper_count = 0
    lower_count = 0
    source = "matched"

    # First: try matched comps
    comp_payload = _get_payload(report, "comparable_sales")
    if comp_payload is not None and hasattr(comp_payload, "comps_used"):
        for c in (comp_payload.comps_used or []):
            cond = (getattr(c, "condition_profile", None) or "").lower()
            sqft = getattr(c, "sqft", None)
            adj_price = getattr(c, "adjusted_price", None)
            if adj_price is None or not sqft or sqft <= 0:
                continue
            ppsf = adj_price / sqft
            if cond in ("renovated", "updated"):
                upper.append(ppsf)
                upper_count += 1
            elif cond in ("dated", "needs_work"):
                lower.append(ppsf)
                lower_count += 1

    # Fallback: scan the full comp database for the same town
    if (not upper or not lower) and subject_town:
        source = "database"
        try:
            import json
            db_path = Path(__file__).resolve().parents[2] / "data" / "comps" / "sales_comps.json"
            if db_path.exists():
                with open(db_path) as f:
                    db = json.load(f)
                sales = db.get("sales", []) if isinstance(db, dict) else db
                upper = []
                lower = []
                upper_count = 0
                lower_count = 0
                for sale in sales:
                    if not isinstance(sale, dict):
                        continue
                    town = (sale.get("town") or "").lower()
                    if town != subject_town:
                        continue
                    cond = (sale.get("condition_profile") or "").lower()
                    sqft = sale.get("sqft")
                    price = sale.get("sale_price")
                    if price is None or not sqft or sqft <= 0:
                        continue
                    ppsf = price / sqft
                    if cond in ("renovated", "updated"):
                        upper.append(ppsf)
                        upper_count += 1
                    elif cond in ("dated", "needs_work", "maintained"):
                        lower.append(ppsf)
                        lower_count += 1
        except Exception:
            pass

    result: dict[str, Any] = {
        "renovated_comp_count": upper_count,
        "dated_comp_count": lower_count,
        "renovation_premium_source": source,
    }

    if not upper or not lower:
        return result

    median_upper = statistics.median(upper)
    median_lower = statistics.median(lower)

    if median_lower <= 0:
        return result

    premium_pct = (median_upper - median_lower) / median_lower

    # Estimate what the subject would be worth renovated
    bcv_metrics = _get_metrics(report, "current_value")
    bcv = bcv_metrics.get("briarwood_current_value")

    estimated_renovated_value = None
    estimated_value_creation = None
    if bcv and premium_pct > 0:
        estimated_renovated_value = round(bcv * (1 + premium_pct))
        estimated_value_creation = estimated_renovated_value - bcv

    result.update({
        "renovation_premium_pct": round(premium_pct, 3),
        "median_renovated_ppsf": round(median_upper, 2),
        "median_dated_ppsf": round(median_lower, 2),
        "estimated_renovated_value": estimated_renovated_value,
        "estimated_value_creation": estimated_value_creation,
    })
    return result


def extract_scoring_metrics(report: AnalysisReport) -> dict[str, Any]:
    """Flatten all module metrics into a single dict for scoring functions."""
    m: dict[str, Any] = {}
    pi = _prop(report)

    # ── current_value ──
    cv = _get_metrics(report, "current_value")
    m["bcv"] = cv.get("briarwood_current_value")
    m["mispricing_pct"] = cv.get("mispricing_pct")
    m["all_in_basis"] = cv.get("all_in_basis")
    m["capex_basis_used"] = cv.get("capex_basis_used")
    m["capex_basis_source"] = cv.get("capex_basis_source")
    m["net_opportunity_delta_value"] = cv.get("net_opportunity_delta_value")
    m["net_opportunity_delta_pct"] = cv.get("net_opportunity_delta_pct")
    m["pricing_view"] = cv.get("pricing_view")
    m["comparable_sales_value"] = cv.get("comparable_sales_value")
    m["income_supported_value"] = cv.get("income_supported_value")
    m["cv_confidence"] = _get_confidence(report, "current_value")

    # ── comparable_sales ──
    cs = _get_metrics(report, "comparable_sales")
    m["comp_count"] = cs.get("comp_count", 0)
    m["comparable_value"] = cs.get("comparable_value")
    m["comp_confidence"] = cs.get("comp_confidence", 0.0)

    # ── bull_base_bear ──
    bbb = _get_metrics(report, "bull_base_bear")
    m["ask_price"] = bbb.get("ask_price")
    m["base_case_value"] = bbb.get("base_case_value")
    m["bull_case_value"] = bbb.get("bull_case_value")
    m["bear_case_value"] = bbb.get("bear_case_value")
    m["stress_case_value"] = bbb.get("stress_case_value")
    m["base_growth_rate"] = bbb.get("base_growth_rate")
    m["bear_growth_rate"] = bbb.get("bear_growth_rate")
    m["bcv_anchor"] = bbb.get("bcv_anchor")
    m["base_market_drift_pct"] = bbb.get("base_market_drift_pct")
    m["inputs_trailing_1yr"] = bbb.get("inputs_trailing_1yr")
    m["inputs_trailing_3yr_cagr"] = bbb.get("inputs_trailing_3yr_cagr")
    m["inputs_trailing_5yr_cagr"] = bbb.get("inputs_trailing_5yr_cagr")
    m["inputs_town_score"] = bbb.get("inputs_town_score")
    m["inputs_risk_score"] = bbb.get("inputs_risk_score")
    m["inputs_scarcity_score"] = bbb.get("inputs_scarcity_score")

    # ── risk_constraints ──
    rc = _get_metrics(report, "risk_constraints")
    m["risk_flags"] = rc.get("risk_flags", "none")
    m["risk_count"] = rc.get("risk_count", 0)
    m["total_penalty"] = rc.get("total_penalty", 0.0)
    m["risk_score"] = report.module_results.get("risk_constraints", type("", (), {"score": 0.0})).score  # type: ignore[arg-type]
    m["flood_risk"] = rc.get("flood_risk")
    m["vacancy_rate"] = rc.get("vacancy_rate")
    m["data_dimensions_present"] = rc.get("data_dimensions_present", 0)

    # ── income_support ──
    inc = _get_metrics(report, "income_support")
    m["income_support_ratio"] = inc.get("income_support_ratio")
    m["price_to_rent"] = inc.get("price_to_rent")
    m["monthly_cash_flow"] = inc.get("monthly_cash_flow")
    m["operating_cash_flow"] = inc.get("operating_monthly_cash_flow")
    m["downside_burden"] = inc.get("downside_burden")
    m["rent_source_type"] = inc.get("rent_source_type")
    m["risk_view"] = inc.get("risk_view")
    m["financing_complete"] = inc.get("financing_complete", False)
    m["carrying_cost_complete"] = inc.get("carrying_cost_complete", False)

    # ── rental_ease ──
    re = _get_metrics(report, "rental_ease")
    m["rental_ease_score"] = re.get("rental_ease_score")
    m["rental_ease_label"] = re.get("rental_ease_label")
    m["rental_liquidity_score"] = re.get("liquidity_score")
    m["demand_depth_score"] = re.get("demand_depth_score")
    m["estimated_days_to_rent"] = re.get("estimated_days_to_rent")

    # ── liquidity_signal ──
    ls = _get_metrics(report, "liquidity_signal")
    m["liquidity_score"] = ls.get("liquidity_score")
    m["liquidity_label"] = ls.get("liquidity_label")
    m["market_liquidity_score"] = ls.get("market_liquidity_score")
    m["comp_depth_score"] = ls.get("comp_depth_score")

    # ── town_county_outlook ──
    tco = _get_metrics(report, "town_county_outlook")
    m["town_county_score"] = tco.get("town_county_score")
    m["location_thesis_label"] = tco.get("location_thesis_label")
    m["appreciation_support_view"] = tco.get("appreciation_support_view")
    m["liquidity_view"] = tco.get("liquidity_view")

    # ── scarcity_support ──
    ss = _get_metrics(report, "scarcity_support")
    m["scarcity_support_score"] = ss.get("scarcity_support_score")
    m["scarcity_label"] = ss.get("scarcity_label")

    # ── location_intelligence ──
    li = _get_metrics(report, "location_intelligence")
    m["location_score"] = li.get("location_score")
    m["location_scarcity_score"] = li.get("scarcity_score")
    m["location_premium_pct"] = li.get("location_premium_pct")

    # ── local_intelligence ──
    loc = _get_metrics(report, "local_intelligence")
    m["development_activity_score"] = loc.get("development_activity_score")
    m["supply_pipeline_score"] = loc.get("supply_pipeline_score")
    m["regulatory_trend_score"] = loc.get("regulatory_trend_score")

    # ── market_momentum_signal ──
    mm = _get_metrics(report, "market_momentum_signal")
    m["market_momentum_score"] = mm.get("market_momentum_score")
    m["market_momentum_label"] = mm.get("market_momentum_label")

    # ── market_value_history ──
    mvh = _get_metrics(report, "market_value_history")
    m["zhvi_1yr_change"] = mvh.get("one_year_change_pct")
    m["zhvi_3yr_change"] = mvh.get("three_year_change_pct")

    # ── renovation_scenario ──
    reno = _get_metrics(report, "renovation_scenario")
    m["reno_enabled"] = reno.get("enabled", False)
    m["reno_roi_pct"] = reno.get("roi_pct")
    m["reno_net_value_creation"] = reno.get("net_value_creation")

    # ── comp-derived renovation premium ──
    reno_premium = estimate_comp_renovation_premium(report)
    m["comp_renovation_premium_pct"] = reno_premium.get("renovation_premium_pct")
    m["comp_renovated_comp_count"] = reno_premium.get("renovated_comp_count", 0)
    m["comp_dated_comp_count"] = reno_premium.get("dated_comp_count", 0)
    m["comp_median_renovated_ppsf"] = reno_premium.get("median_renovated_ppsf")
    m["comp_median_dated_ppsf"] = reno_premium.get("median_dated_ppsf")
    m["comp_estimated_renovated_value"] = reno_premium.get("estimated_renovated_value")
    m["comp_estimated_value_creation"] = reno_premium.get("estimated_value_creation")

    # ── teardown_scenario ──
    td = _get_metrics(report, "teardown_scenario")
    m["teardown_enabled"] = td.get("enabled", False)
    m["teardown_annualized_roi"] = td.get("annualized_roi_pct")

    # ── property_input fields ──
    if pi:
        m["purchase_price"] = pi.purchase_price
        m["sqft"] = pi.sqft
        m["beds"] = pi.beds
        m["baths"] = pi.baths
        m["lot_size"] = pi.lot_size
        m["year_built"] = pi.year_built
        m["days_on_market"] = pi.days_on_market
        m["condition_profile"] = pi.condition_profile
        m["capex_lane"] = pi.capex_lane
        m["condition_confirmed"] = pi.condition_confirmed
        m["capex_confirmed"] = pi.capex_confirmed
        m["repair_capex_budget"] = pi.repair_capex_budget
        m["has_back_house"] = pi.has_back_house
        m["adu_type"] = pi.adu_type
        m["has_basement"] = pi.has_basement
        m["has_pool"] = pi.has_pool
        m["garage_spaces"] = pi.garage_spaces
        m["corner_lot"] = pi.corner_lot
        m["property_type"] = pi.property_type
        m["taxes"] = pi.taxes
        m["rent_confidence_override"] = pi.rent_confidence_override
        m["strategy_intent"] = pi.strategy_intent
        m["hold_period_years"] = pi.hold_period_years
        m["risk_tolerance"] = pi.risk_tolerance
        town_context = get_town_context(pi.town)
        if town_context is not None:
            ask_price = pi.purchase_price or m.get("ask_price")
            subject_ppsf = (ask_price / pi.sqft) if ask_price and pi.sqft else None
            town_price_anchor = town_context.median_price
            m["town_price_index"] = town_context.town_price_index
            m["town_ppsf_index"] = town_context.town_ppsf_index
            m["town_lot_index"] = town_context.town_lot_index
            m["town_liquidity_index"] = town_context.town_liquidity_index
            m["town_baseline_median_price"] = town_price_anchor
            m["town_baseline_median_ppsf"] = town_context.median_ppsf
            m["town_baseline_median_sqft"] = town_context.median_sqft
            m["town_baseline_median_lot_size"] = town_context.median_lot_size
            m["town_context_confidence"] = town_context.context_confidence
            m["town_context_flags"] = list(town_context.qa_flags)
            m["town_low_sample_flag"] = town_context.low_sample_flag
            m["town_high_missingness_flag"] = town_context.high_missingness_flag
            m["town_high_dispersion_flag"] = town_context.high_dispersion_flag
            m["town_outlier_heavy_flag"] = town_context.outlier_heavy_flag
            m["town_low_confidence_flag"] = town_context.low_confidence_flag
            m["subject_ppsf_vs_town"] = _safe_ratio(subject_ppsf, town_context.median_ppsf)
            m["subject_price_vs_town"] = _safe_ratio(ask_price, town_price_anchor)
            m["subject_lot_vs_town"] = _safe_ratio(pi.lot_size, town_context.median_lot_size)
            # Positive means the subject screens cheaper than the town's typical PPSF.
            m["town_adjusted_value_gap"] = (
                ((town_context.median_ppsf - subject_ppsf) / subject_ppsf)
                if subject_ppsf not in (None, 0) and town_context.median_ppsf not in (None, 0)
                else None
            )
    else:
        m["purchase_price"] = m.get("ask_price")

    return m


# ── Utility ────────────────────────────────────────────────────────────────────


def _clamp(score: float) -> float:
    return max(MIN_SCORE, min(MAX_SCORE, score))


def _lerp_score(value: float, lo: float, hi: float, score_at_lo: float, score_at_hi: float) -> float:
    """Linearly interpolate a score between two anchor points."""
    if hi == lo:
        return score_at_lo
    t = (value - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))
    return score_at_lo + t * (score_at_hi - score_at_lo)


def _safe_ratio(value: float | None, baseline: float | None) -> float | None:
    if value in (None, 0) or baseline in (None, 0):
        return None
    return float(value) / float(baseline)


