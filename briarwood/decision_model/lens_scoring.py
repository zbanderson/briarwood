"""
Multi-lens scoring: perspective-specific property evaluation.

Instead of one universal score, provides 4 views:
  - Risk Assessment (universal — everyone cares about risk)
  - Investor Lens (cash flow, rental yield)
  - Owner-Occupant Lens (lifestyle, appreciation, location)
  - Developer Lens (optionality, upside, lot potential)

Each lens re-weights the SAME underlying data for its buyer persona.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from briarwood.decision_model.scoring import CategoryScore
from briarwood.schemas import AnalysisReport, ModuleResult, PropertyInput


@dataclass(slots=True)
class LensDetail:
    score: float
    components: dict[str, float]  # component_name → score (1-5)
    verdicts: dict[str, str]      # component_name → verdict text
    narrative: str = ""
    recommendation: str = ""


@dataclass(slots=True)
class LensScores:
    risk_score: float                  # 1-5, lower = safer
    risk_narrative: str = ""

    investor_score: float | None = None
    investor_narrative: str = ""
    investor_detail: LensDetail | None = None

    owner_score: float | None = None
    owner_narrative: str = ""
    owner_detail: LensDetail | None = None

    developer_score: float | None = None
    developer_narrative: str = ""
    developer_detail: LensDetail | None = None

    recommended_lens: str = ""
    recommendation_reason: str = ""


def _clamp(v: float) -> float:
    return max(1.0, min(5.0, v))


def _get(m: dict, key: str, default: float = 0.0) -> float:
    v = m.get(key)
    return float(v) if v is not None else default


# ═══════════════════════════════════════════════════════════════════════════════
# RISK ASSESSMENT (universal)
# ═══════════════════════════════════════════════════════════════════════════════


def _risk_assessment(cats: dict[str, CategoryScore]) -> tuple[float, str]:
    """Lower score = lower risk. Inverts the existing category scores."""
    risk = cats.get("risk_layer")
    market = cats.get("market_position")
    price = cats.get("price_context")

    risk_val = 6.0 - (risk.score if risk else 3.0)
    market_val = 6.0 - (market.score if market else 3.0)
    price_val = 6.0 - (price.score if price else 3.0)

    score = _clamp(risk_val * 0.40 + market_val * 0.30 + price_val * 0.30)

    if score < 2.0:
        narr = "Very Low Risk: strong fundamentals across all dimensions."
    elif score < 3.0:
        narr = "Low Risk: solid fundamentals with minor concerns."
    elif score < 3.5:
        narr = "Moderate Risk: some areas need attention."
    elif score < 4.0:
        narr = "Elevated Risk: multiple risk factors present."
    else:
        narr = "High Risk: significant concerns across multiple dimensions."
    return score, narr


# ═══════════════════════════════════════════════════════════════════════════════
# INVESTOR LENS (cash flow focus)
# ═══════════════════════════════════════════════════════════════════════════════


def _investor_lens(mods: dict[str, ModuleResult]) -> LensDetail:
    inc = (mods.get("income_support") or ModuleResult(module_name="income_support")).metrics
    re = (mods.get("rental_ease") or ModuleResult(module_name="rental_ease")).metrics

    cash_flow = _get(inc, "monthly_cash_flow")
    ptr = _get(inc, "price_to_rent", 999)
    isr = _get(inc, "income_support_ratio")
    ease = _get(re, "rental_ease_score", 50) / 20  # scale 0-100 → 0-5

    # Cash flow scoring
    if cash_flow > 500:
        cf_s, cf_v = 5.0, f"Strong positive cash flow (+${cash_flow:,.0f}/mo)"
    elif cash_flow > 200:
        cf_s, cf_v = 4.0, f"Positive cash flow (+${cash_flow:,.0f}/mo)"
    elif cash_flow > 0:
        cf_s, cf_v = 3.5, f"Slight positive cash flow (+${cash_flow:,.0f}/mo)"
    elif cash_flow > -500:
        cf_s, cf_v = 2.5, f"Minor negative carry (${abs(cash_flow):,.0f}/mo)"
    elif cash_flow > -1000:
        cf_s, cf_v = 2.0, f"Moderate negative carry (${abs(cash_flow):,.0f}/mo)"
    elif cash_flow > -2000:
        cf_s, cf_v = 1.5, f"Heavy negative carry (${abs(cash_flow):,.0f}/mo)"
    else:
        cf_s, cf_v = 1.0, f"Severe negative carry (${abs(cash_flow):,.0f}/mo)"

    # PTR scoring
    if ptr < 12:
        ptr_s, ptr_v = 5.0, f"Strong price-to-rent ({ptr:.1f}x)"
    elif ptr < 15:
        ptr_s, ptr_v = 4.0, f"Favorable price-to-rent ({ptr:.1f}x)"
    elif ptr < 20:
        ptr_s, ptr_v = 3.0, f"Moderate price-to-rent ({ptr:.1f}x)"
    elif ptr < 25:
        ptr_s, ptr_v = 2.0, f"Stretched price-to-rent ({ptr:.1f}x)"
    else:
        ptr_s, ptr_v = 1.0, f"Disconnected price-to-rent ({ptr:.1f}x)"

    ease_s = _clamp(ease)
    ease_v = f"Rental ease {_get(re, 'rental_ease_score', 50):.0f}/100"

    score = _clamp(cf_s * 0.50 + ptr_s * 0.30 + ease_s * 0.20)

    if score >= 4.0:
        rec = "The cash flow math works — this property carries itself as a rental."
    elif score >= 3.0:
        rec = "The investment case is thin — only viable with an appreciation thesis."
    elif score >= 2.0:
        rec = "The numbers don't support a rental hold at this price."
    else:
        rec = "Pass for income investors — the carry overwhelms the return."

    narr = f"{cf_v}. {ptr_v}. {rec}"

    return LensDetail(
        score=score,
        components={"cash_flow": cf_s, "price_to_rent": ptr_s, "rental_ease": ease_s},
        verdicts={"cash_flow": cf_v, "price_to_rent": ptr_v, "rental_ease": ease_v},
        narrative=narr,
        recommendation=rec,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# OWNER-OCCUPANT LENS (lifestyle + appreciation)
# ═══════════════════════════════════════════════════════════════════════════════


def _owner_lens(cats: dict[str, CategoryScore], mods: dict[str, ModuleResult], pi: PropertyInput | None) -> LensDetail:
    market = cats.get("market_position")
    bbb = (mods.get("bull_base_bear") or ModuleResult(module_name="bull_base_bear")).metrics
    ss = (mods.get("scarcity_support") or ModuleResult(module_name="scarcity_support")).metrics

    location_s = _clamp(market.score if market else 3.0)
    if location_s >= 4.5:
        loc_v = "Premier location — hard to replicate"
    elif location_s >= 4.0:
        loc_v = "Strong location fundamentals"
    elif location_s >= 3.5:
        loc_v = "Solid location — above average"
    else:
        loc_v = "Location is serviceable but unremarkable"

    # Appreciation from bull case
    ask = _get(bbb, "ask_price")
    bull = _get(bbb, "bull_case_value")
    if ask > 0 and bull > 0:
        upside_pct = ((bull - ask) / ask) * 100
    else:
        upside_pct = 0

    if upside_pct > 40:
        app_s, app_v = 5.0, f"Exceptional upside (+{upside_pct:.0f}%)"
    elif upside_pct > 30:
        app_s, app_v = 4.5, f"Strong appreciation potential (+{upside_pct:.0f}%)"
    elif upside_pct > 20:
        app_s, app_v = 4.0, f"Good appreciation potential (+{upside_pct:.0f}%)"
    elif upside_pct > 10:
        app_s, app_v = 3.5, f"Moderate appreciation potential (+{upside_pct:.0f}%)"
    else:
        app_s, app_v = 2.5, f"Limited appreciation potential (+{upside_pct:.0f}%)"

    scarcity_raw = _get(ss, "scarcity_support_score", 50)
    scarcity_s = _clamp(scarcity_raw / 20)  # 0-100 → 0-5
    scarcity_v = f"Scarcity {scarcity_raw:.0f}/100"

    score = _clamp(location_s * 0.35 + app_s * 0.35 + scarcity_s * 0.30)

    if score >= 4.0:
        rec = "This property makes sense to live in — the location and trajectory support the price."
    elif score >= 3.5:
        rec = "Lifestyle value is present — location and appreciation support the basis."
    elif score >= 3.0:
        rec = "Livable but unremarkable — compare alternatives before committing."
    else:
        rec = "The lifestyle case is thin at this price point."

    narr = f"{loc_v}. {app_v}. {rec}"

    return LensDetail(
        score=score,
        components={"location": location_s, "appreciation": app_s, "scarcity": scarcity_s},
        verdicts={"location": loc_v, "appreciation": app_v, "scarcity": scarcity_v},
        narrative=narr,
        recommendation=rec,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# DEVELOPER LENS (optionality + upside)
# ═══════════════════════════════════════════════════════════════════════════════


def _developer_lens(cats: dict[str, CategoryScore], mods: dict[str, ModuleResult], pi: PropertyInput | None) -> LensDetail:
    opt = cats.get("optionality")
    bbb = (mods.get("bull_base_bear") or ModuleResult(module_name="bull_base_bear")).metrics

    opt_s = _clamp(opt.score if opt else 3.0)
    if opt_s >= 4.5:
        opt_v = "High optionality — multiple development paths available"
    elif opt_s >= 4.0:
        opt_v = "Clear value-add opportunities"
    elif opt_s >= 3.0:
        opt_v = "Some development upside, but selective"
    else:
        opt_v = "Limited development options at this basis"

    # Bull upside
    ask = _get(bbb, "ask_price")
    bull = _get(bbb, "bull_case_value")
    upside_pct = ((bull - ask) / ask * 100) if ask > 0 and bull > 0 else 0

    if upside_pct > 50:
        bull_s, bull_v = 5.0, f"Exceptional upside (+{upside_pct:.0f}%)"
    elif upside_pct > 35:
        bull_s, bull_v = 4.5, f"Strong upside (+{upside_pct:.0f}%)"
    elif upside_pct > 20:
        bull_s, bull_v = 4.0, f"Good upside (+{upside_pct:.0f}%)"
    elif upside_pct > 10:
        bull_s, bull_v = 3.5, f"Moderate upside (+{upside_pct:.0f}%)"
    else:
        bull_s, bull_v = 3.0, f"Limited upside (+{upside_pct:.0f}%)"

    # Lot potential
    lot_acres = pi.lot_size if pi and pi.lot_size else None
    lot_sqft = lot_acres * 43560 if lot_acres else None
    if lot_sqft and lot_sqft > 8000:
        lot_s, lot_v = 5.0, f"Large lot ({lot_sqft:,.0f}sf)"
    elif lot_sqft and lot_sqft > 6000:
        lot_s, lot_v = 4.0, f"Above-average lot ({lot_sqft:,.0f}sf)"
    elif lot_sqft and lot_sqft > 4000:
        lot_s, lot_v = 3.5, f"Standard lot ({lot_sqft:,.0f}sf)"
    elif lot_sqft and lot_sqft > 2000:
        lot_s, lot_v = 3.0, f"Small lot ({lot_sqft:,.0f}sf)"
    else:
        lot_s, lot_v = 2.5, "Lot data unavailable or very small"

    score = _clamp(opt_s * 0.45 + bull_s * 0.35 + lot_s * 0.20)

    if score >= 4.0:
        rec = "The property can physically become more — renovation or expansion pencils."
    elif score >= 3.0:
        rec = "Development upside exists but isn't commanding — consider hold-and-develop."
    else:
        rec = "Limited development potential — better suited for a buy-and-hold thesis."

    narr = f"{opt_v}. {bull_v}. {rec}"

    return LensDetail(
        score=score,
        components={"optionality": opt_s, "bull_upside": bull_s, "lot_potential": lot_s},
        verdicts={"optionality": opt_v, "bull_upside": bull_v, "lot_potential": lot_v},
        narrative=narr,
        recommendation=rec,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# RECOMMENDATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════


_LENS_LABELS = {
    "investor": "Cash Flow Investor",
    "owner": "Owner-Occupant",
    "developer": "Developer / Value-Add",
}


def _recommend(inv: float | None, own: float | None, dev: float | None) -> tuple[str, str]:
    candidates = {}
    if inv is not None:
        candidates["investor"] = inv
    if own is not None:
        candidates["owner"] = own
    if dev is not None:
        candidates["developer"] = dev
    if not candidates:
        return "risk_only", "Insufficient data for perspective-specific scoring."

    best_key = max(candidates, key=candidates.get)  # type: ignore[arg-type]
    best_val = candidates[best_key]
    others = sorted(((k, v) for k, v in candidates.items() if k != best_key), key=lambda x: -x[1])

    best_label = _LENS_LABELS.get(best_key, best_key)
    reason = f"Most compelling as {best_label} ({best_val:.1f}/5)."

    if others:
        second_key, second_val = others[0]
        gap = best_val - second_val
        strength = "clearly" if gap > 1.0 else "moderately" if gap > 0.5 else "slightly"
        second_label = _LENS_LABELS.get(second_key, second_key)
        reason += f" {strength.title()} ahead of {second_label} ({second_val:.1f}/5)."

    if best_key == "investor":
        reason += " The cash flow fundamentals carry the thesis."
    elif best_key == "owner":
        reason += " Location and appreciation outweigh carry costs for lifestyle buyers."
    elif best_key == "developer":
        reason += " The value-add potential justifies the basis."

    return best_key, reason


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════


def calculate_lens_scores(report: AnalysisReport, category_scores: dict[str, CategoryScore] | None) -> LensScores:
    """Calculate all lens scores from a completed AnalysisReport."""
    cats = category_scores or {}
    mods = report.module_results
    pi = report.property_input

    risk_score, risk_narr = _risk_assessment(cats)
    inv = _investor_lens(mods)
    own = _owner_lens(cats, mods, pi)
    dev = _developer_lens(cats, mods, pi)

    best_lens, rec_reason = _recommend(inv.score, own.score, dev.score)

    return LensScores(
        risk_score=risk_score,
        risk_narrative=risk_narr,
        investor_score=inv.score,
        investor_narrative=inv.narrative,
        investor_detail=inv,
        owner_score=own.score,
        owner_narrative=own.narrative,
        owner_detail=own,
        developer_score=dev.score,
        developer_narrative=dev.narrative,
        developer_detail=dev,
        recommended_lens=best_lens,
        recommendation_reason=rec_reason,
    )
