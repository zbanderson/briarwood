from __future__ import annotations

from briarwood.evidence import build_section_evidence
from briarwood.schemas import ModuleResult, PropertyInput
from briarwood.decision_model.scoring_config import DEFAULT_RISK_SETTINGS, RiskSettings
from briarwood.scoring import clamp_score
from briarwood.utils import current_year


class RiskConstraintsModule:
    name = "risk_constraints"

    def __init__(self, settings: RiskSettings | None = None) -> None:
        self.settings = settings or DEFAULT_RISK_SETTINGS

    def run(self, property_input: PropertyInput) -> ModuleResult:
        s = self.settings
        penalties: dict[str, float] = {}
        credits: dict[str, float] = {}
        data_present = 0

        # --- Flood risk: graduated by tier ---
        if property_input.flood_risk is not None:
            data_present += 1
            flood = property_input.flood_risk.strip().lower()
            if flood == "high":
                penalties["flood_high"] = s.flood_risk_high_penalty
            elif flood == "medium":
                penalties["flood_medium"] = s.flood_risk_medium_penalty
            elif flood in ("low", "none", "minimal"):
                credits["low_flood"] = s.low_flood_credit

        # --- Older housing stock: flat penalty ---
        if property_input.year_built is not None:
            data_present += 1
            if current_year() - property_input.year_built > s.older_home_age_threshold:
                penalties["older_housing_stock"] = s.older_home_penalty

        # --- Property taxes: graduated linear interpolation ---
        if property_input.taxes is not None:
            data_present += 1
            tax_penalty = _graduated_tax_penalty(property_input.taxes, s)
            if tax_penalty > 0:
                penalties["high_property_taxes"] = tax_penalty
            elif property_input.taxes <= s.low_tax_credit_threshold:
                credits["low_taxes"] = s.low_tax_credit

        # --- Vacancy: Bug 5 — graduated instead of binary threshold ---
        if property_input.vacancy_rate is not None:
            data_present += 1
            vacancy_penalty = _graduated_vacancy_penalty(property_input.vacancy_rate, s)
            if vacancy_penalty > 0:
                penalties["higher_vacancy"] = vacancy_penalty

        # --- Days on market: Bug 4 — smooth ramp starting at 15 days ---
        if property_input.days_on_market is not None:
            data_present += 1
            dom_penalty = _graduated_dom_penalty(property_input.days_on_market, s)
            if dom_penalty > 0:
                penalties["long_marketing_period"] = dom_penalty
            elif property_input.days_on_market < s.fast_dom_credit_threshold:
                credits["fast_absorption"] = s.fast_dom_credit

        total_penalty = sum(penalties.values())
        total_credit = min(sum(credits.values()), s.max_positive_credit)
        score = clamp_score(s.base_score - total_penalty + total_credit)

        # Confidence scales with how many of the 5 dimensions have real data.
        confidence = _data_completeness_confidence(data_present, s)

        risk_flag_names = list(penalties.keys())
        metrics = {
            "risk_flags": ", ".join(risk_flag_names) if risk_flag_names else "none",
            "risk_count": len(risk_flag_names),
            "total_penalty": round(total_penalty, 1),
            "total_credit": round(total_credit, 1),
            "flood_risk": property_input.flood_risk,
            "vacancy_rate": property_input.vacancy_rate,
            "data_dimensions_present": data_present,
        }
        summary = (
            "No major red flags detected."
            if not risk_flag_names
            else f"Primary constraints: {', '.join(risk_flag_names)}."
        )
        return ModuleResult(
            module_name=self.name,
            metrics=metrics,
            score=score,
            confidence=confidence,
            summary=summary,
            section_evidence=build_section_evidence(
                property_input,
                categories=["flood_risk", "taxes", "liquidity_signal"],
                notes=["Risk constraints use graduated scoring. Confidence reflects data completeness across 5 dimensions."],
            ),
        )


def _graduated_tax_penalty(taxes: float, s: RiskSettings) -> float:
    """Linear interpolation across three tax penalty tiers."""
    if taxes <= s.tax_penalty_tier1_threshold:
        return 0.0
    if taxes <= s.tax_penalty_tier1_max:
        # $10K–$12K: interpolate 0 → 12
        return _lerp(taxes, s.tax_penalty_tier1_threshold, s.tax_penalty_tier1_max, 0.0, 12.0)
    if taxes <= s.tax_penalty_tier2_threshold:
        # $12K–$15K: constant 12 (tier boundary — already past tier 1 cap)
        return 12.0
    if taxes <= s.tax_penalty_tier2_max:
        # $15K–$20K: interpolate 12 → 20
        return _lerp(taxes, s.tax_penalty_tier2_threshold, s.tax_penalty_tier2_max, 12.0, 20.0)
    # $20K+ → capped at 20 (or tax_penalty_cap for safety)
    return s.tax_penalty_cap


def _graduated_dom_penalty(dom: int, s: RiskSettings) -> float:
    """Bug 4: smooth ramp starting at 15 days instead of cliff at 30.
    0-14: no penalty. 15-30: ramp 0→5. 31-60: ramp 5→15. 61-90: ramp 15→25. 90+: cap 25."""
    if dom <= s.dom_penalty_start:
        return 0.0
    if dom <= s.dom_penalty_tier1_end:
        return _lerp(dom, s.dom_penalty_start, s.dom_penalty_tier1_end, 0.0, s.dom_penalty_tier1_max)
    if dom <= s.dom_penalty_tier2_end:
        return _lerp(dom, s.dom_penalty_tier1_end, s.dom_penalty_tier2_end, s.dom_penalty_tier1_max, s.dom_penalty_tier2_max)
    if dom <= s.dom_penalty_tier3_end:
        return _lerp(dom, s.dom_penalty_tier2_end, s.dom_penalty_tier3_end, s.dom_penalty_tier2_max, s.dom_penalty_cap)
    return s.dom_penalty_cap


def _graduated_vacancy_penalty(vacancy_rate: float, s: RiskSettings) -> float:
    """Bug 5: graduated vacancy penalty instead of binary threshold.
    0-5%: no penalty. 5-8%: ramp 0→5. 8-12%: ramp 5→10. 12-20%: ramp 10→20. 20+%: cap 20."""
    if vacancy_rate <= s.vacancy_tier1_start:
        return 0.0
    if vacancy_rate <= s.vacancy_tier1_end:
        return _lerp(vacancy_rate, s.vacancy_tier1_start, s.vacancy_tier1_end, 0.0, s.vacancy_tier1_max_penalty)
    if vacancy_rate <= s.vacancy_tier2_end:
        return _lerp(vacancy_rate, s.vacancy_tier1_end, s.vacancy_tier2_end, s.vacancy_tier1_max_penalty, s.vacancy_tier2_max_penalty)
    if vacancy_rate <= s.vacancy_tier3_end:
        return _lerp(vacancy_rate, s.vacancy_tier2_end, s.vacancy_tier3_end, s.vacancy_tier2_max_penalty, s.vacancy_tier3_max_penalty)
    return s.vacancy_penalty_cap


def _lerp(value: float, lo: float, hi: float, out_lo: float, out_hi: float) -> float:
    """Map value in [lo, hi] to [out_lo, out_hi] via linear interpolation."""
    if hi == lo:
        return out_lo
    t = (value - lo) / (hi - lo)
    return out_lo + t * (out_hi - out_lo)


def _data_completeness_confidence(data_present: int, s: RiskSettings) -> float:
    if data_present >= 5:
        return s.confidence_tier_full
    if data_present >= 3:
        return s.confidence_tier_medium
    return s.confidence_tier_low
