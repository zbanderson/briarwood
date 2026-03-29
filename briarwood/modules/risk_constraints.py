from __future__ import annotations

from briarwood.evidence import build_section_evidence
from briarwood.schemas import ModuleResult, PropertyInput
from briarwood.settings import DEFAULT_RISK_SETTINGS, RiskSettings
from briarwood.scoring import clamp_score
from briarwood.utils import current_year


class RiskConstraintsModule:
    name = "risk_constraints"

    def __init__(self, settings: RiskSettings | None = None) -> None:
        self.settings = settings or DEFAULT_RISK_SETTINGS

    def run(self, property_input: PropertyInput) -> ModuleResult:
        risk_flags: list[str] = []

        if (
            property_input.year_built
            and current_year() - property_input.year_built > self.settings.older_home_age_threshold
        ):
            risk_flags.append("older_housing_stock")
        if property_input.taxes and property_input.taxes > self.settings.high_tax_threshold:
            risk_flags.append("high_property_taxes")
        if property_input.vacancy_rate and property_input.vacancy_rate > self.settings.high_vacancy_threshold:
            risk_flags.append("higher_vacancy")
        if property_input.flood_risk in self.settings.elevated_flood_risk_levels:
            risk_flags.append("flood_exposure")
        if (
            property_input.days_on_market
            and property_input.days_on_market > self.settings.long_days_on_market_threshold
        ):
            risk_flags.append("long_marketing_period")

        score = clamp_score(
            self.settings.base_score - len(risk_flags) * self.settings.score_penalty_per_flag
        )
        metrics = {
            "risk_flags": ", ".join(risk_flags) if risk_flags else "none",
            "risk_count": len(risk_flags),
            "flood_risk": property_input.flood_risk,
            "vacancy_rate": property_input.vacancy_rate,
        }
        summary = (
            "No major red flags detected."
            if not risk_flags
            else f"Primary constraints: {', '.join(risk_flags)}."
        )
        return ModuleResult(
            module_name=self.name,
            metrics=metrics,
            score=score,
            confidence=0.72,
            summary=summary,
            section_evidence=build_section_evidence(
                property_input,
                categories=["flood_risk", "taxes", "liquidity_signal"],
                notes=["Risk constraints are deterministic and should be read as a guardrail layer, not a full risk model."],
            ),
        )
