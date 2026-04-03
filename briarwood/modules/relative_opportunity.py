from __future__ import annotations

from briarwood.opportunity_metrics import infer_capex_amount
from briarwood.schemas import (
    AnalysisReport,
    LocalIntelligenceOutput,
    RelativeOpportunityComparison,
    RelativeOpportunityConfidence,
    RelativeOpportunityOutput,
    RelativeOpportunityProperty,
)
from briarwood.settings import DEFAULT_RELATIVE_OPPORTUNITY_SETTINGS, RelativeOpportunitySettings


class RelativeOpportunityModule:
    """Compare multiple analyzed properties for directional forward opportunity."""

    name = "relative_opportunity"

    def __init__(self, settings: RelativeOpportunitySettings | None = None) -> None:
        self.settings = settings or DEFAULT_RELATIVE_OPPORTUNITY_SETTINGS

    def compare(self, reports: list[AnalysisReport]) -> RelativeOpportunityOutput:
        if len(reports) < 2:
            raise ValueError("Relative opportunity comparison requires at least two analyzed properties.")

        properties = [self._property_view(report) for report in reports]
        comparison = RelativeOpportunityComparison(
            best_value_creation=_winner_label(properties, key="post_reno_value", descending=True),
            best_location=_winner_label(properties, key="relative_to_model_pct", descending=False),
            best_forward_return=_winner_label(properties, key="expected_return_pct", descending=True),
            highest_convergence=_winner_label(properties, key="convergence_score", descending=True),
        )
        winner = _winner_label(properties, key="expected_return_pct", descending=True)
        reasoning = self._reasoning(properties, comparison)
        confidence = self._confidence(reports, properties)
        return RelativeOpportunityOutput(
            properties=properties,
            comparison=comparison,
            winner=winner,
            reasoning=reasoning,
            confidence=confidence,
        )

    def _property_view(self, report: AnalysisReport) -> RelativeOpportunityProperty:
        property_input = report.property_input
        if property_input is None:
            raise ValueError("Relative opportunity requires reports with property_input attached.")

        current_value_result = report.module_results.get("current_value")
        bull_base_bear_result = report.module_results.get("bull_base_bear")
        location_result = report.module_results.get("location_intelligence")
        local_result = report.module_results.get("local_intelligence")
        scarcity_result = report.module_results.get("scarcity_support")

        current_metrics = current_value_result.metrics if current_value_result else {}
        forward_metrics = bull_base_bear_result.metrics if bull_base_bear_result else {}
        location_metrics = location_result.metrics if location_result else {}
        scarcity_metrics = scarcity_result.metrics if scarcity_result else {}
        local_payload = _local_payload(local_result.payload if local_result else None)

        purchase_price = property_input.purchase_price
        subject_ppsf = _safe_divide(purchase_price, property_input.sqft)
        implied_value = current_metrics.get("briarwood_current_value")
        implied_ppsf = _safe_divide(implied_value, property_input.sqft)
        relative_to_model_pct = _relative_pct(subject_ppsf, implied_ppsf)

        capex = _capex_amount(property_input)
        post_reno_value = None
        if implied_value is not None:
            post_reno_value = implied_value + _value_creation_uplift(property_input, capex)

        town_momentum_score = _town_momentum_score(local_payload)
        town_momentum_adjustment_pct = _town_momentum_adjustment_pct(town_momentum_score)
        forward_base = _float_or_none(forward_metrics.get("base_case_value"))
        base_anchor = post_reno_value if post_reno_value is not None else forward_base
        forward_value = (
            base_anchor * (1.0 + town_momentum_adjustment_pct)
            if base_anchor is not None and town_momentum_adjustment_pct is not None
            else None
        )
        expected_return_pct = _relative_pct(forward_value, purchase_price)
        convergence_score = _convergence_score(
            relative_to_model_pct=relative_to_model_pct,
            town_momentum_score=town_momentum_score,
            scarcity_score=_float_or_none(location_metrics.get("scarcity_score"))
            or _float_or_none(scarcity_metrics.get("scarcity_support_score")),
        )

        confidence = _property_confidence(
            current_value_confidence=current_value_result.confidence if current_value_result else 0.0,
            location_confidence=location_result.confidence if location_result else 0.0,
            local_confidence=local_result.confidence if local_result else 0.0,
        )

        notes = []
        if local_result is None:
            notes.append("Town momentum currently lacks local document support.")
        elif local_result.confidence < 0.5:
            notes.append("Town momentum is low-confidence because local document signals are thin.")
        if property_input.repair_capex_budget is None and property_input.capex_lane:
            notes.append("CapEx uses a lane-based heuristic because no explicit repair budget was entered.")

        return RelativeOpportunityProperty(
            property_id=report.property_id,
            label=report.address,
            subject_ppsf=_round_or_none(subject_ppsf, 2),
            implied_ppsf=_round_or_none(implied_ppsf, 2),
            relative_to_model_pct=_round_or_none(relative_to_model_pct, 4),
            purchase_price=_round_or_none(_float_or_none(purchase_price), 2),
            capex=_round_or_none(capex, 2),
            post_reno_value=_round_or_none(post_reno_value, 2),
            town_momentum_score=_round_or_none(town_momentum_score, 1),
            town_momentum_adjustment_pct=_round_or_none(town_momentum_adjustment_pct, 4),
            forward_value=_round_or_none(forward_value, 2),
            expected_return_pct=_round_or_none(expected_return_pct, 4),
            convergence_score=_round_or_none(convergence_score, 1),
            confidence=round(confidence, 2),
            notes=notes,
        )

    def _reasoning(
        self,
        properties: list[RelativeOpportunityProperty],
        comparison: RelativeOpportunityComparison,
    ) -> list[str]:
        notes: list[str] = []
        if comparison.best_forward_return:
            notes.append(
                f"{comparison.best_forward_return} currently screens as the strongest forward-return candidate once Briarwood layers value creation and town momentum together."
            )
        if comparison.best_value_creation and comparison.best_value_creation != comparison.best_forward_return:
            notes.append(
                f"{comparison.best_value_creation} looks strongest on post-renovation value creation, even if that does not fully translate into the highest forward return."
            )
        if comparison.highest_convergence:
            notes.append(
                f"{comparison.highest_convergence} shows the best convergence profile based on discount-to-model, town momentum, and scarcity support."
            )
        lowest_confidence = min(properties, key=lambda item: item.confidence)
        if lowest_confidence.confidence < 0.5:
            notes.append(
                f"{lowest_confidence.label} remains low-confidence because the comparison still leans on assumptions or weak supporting evidence."
            )
        return notes[:4]

    def _confidence(
        self,
        reports: list[AnalysisReport],
        properties: list[RelativeOpportunityProperty],
    ) -> RelativeOpportunityConfidence:
        s = self.settings
        notes: list[str] = []
        confidence = sum(item.confidence for item in properties) / len(properties)
        if any(report.module_results.get("local_intelligence") is None for report in reports):
            notes.append("Some properties are missing local document intelligence, so town momentum is only partially supported.")
            confidence = min(confidence, s.confidence_cap_no_local_intel)
        if any(item.capex is None for item in properties):
            notes.append("Some value-creation paths rely on capex heuristics rather than explicit budgets.")
            confidence = min(confidence, s.confidence_cap_capex_heuristics)
        return RelativeOpportunityConfidence(score=round(confidence, 2), notes=notes)


def _local_payload(payload: object) -> LocalIntelligenceOutput | None:
    return payload if isinstance(payload, LocalIntelligenceOutput) else None


def _winner_label(
    properties: list[RelativeOpportunityProperty],
    *,
    key: str,
    descending: bool,
) -> str | None:
    ranked = [item for item in properties if getattr(item, key) is not None]
    if not ranked:
        return None
    ranked.sort(key=lambda item: getattr(item, key), reverse=descending)
    return ranked[0].label


def _safe_divide(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator in (None, 0) or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def _relative_pct(left: float | None, right: float | None) -> float | None:
    if left is None or right in (None, 0):
        return None
    return (left / right) - 1.0


def _capex_amount(property_input) -> float | None:
    capex, _ = infer_capex_amount(property_input)
    return capex


def _value_creation_uplift(property_input, capex: float | None) -> float:
    if capex is None:
        return 0.0
    lane = (property_input.capex_lane or "").strip().lower()
    multiplier = 1.15
    if lane == "moderate":
        multiplier = 1.22
    elif lane == "heavy":
        multiplier = 1.3
    elif property_input.condition_profile in {"renovated", "updated"}:
        multiplier = 1.05
    return capex * multiplier


def _town_momentum_score(local_payload: LocalIntelligenceOutput | None) -> float | None:
    if local_payload is None:
        return None
    scores = local_payload.scores
    return round(
        (0.45 * scores.development_activity_score)
        + (0.35 * scores.regulatory_trend_score)
        + (0.20 * (100.0 - scores.supply_pipeline_score)),
        1,
    )


def _town_momentum_adjustment_pct(score: float | None) -> float | None:
    if score is None:
        return None
    if score < 35:
        return 0.02
    if score < 60:
        return 0.02 + ((score - 35) / 25) * 0.03
    return min(0.05 + ((score - 60) / 40) * 0.05, 0.10)


def _convergence_score(
    *,
    relative_to_model_pct: float | None,
    town_momentum_score: float | None,
    scarcity_score: float | None,
) -> float | None:
    if relative_to_model_pct is None and town_momentum_score is None and scarcity_score is None:
        return None
    discount_component = 0.0
    if relative_to_model_pct is not None:
        discount_component = max(0.0, min(100.0, (-relative_to_model_pct) * 250))
    momentum_component = town_momentum_score or 50.0
    scarcity_component = scarcity_score or 50.0
    return round((0.4 * discount_component) + (0.35 * momentum_component) + (0.25 * scarcity_component), 1)


def _property_confidence(
    *,
    current_value_confidence: float,
    location_confidence: float,
    local_confidence: float,
) -> float:
    values = [current_value_confidence]
    if location_confidence:
        values.append(location_confidence)
    if local_confidence:
        values.append(local_confidence)
    return sum(values) / len(values)


def _round_or_none(value: float | None, digits: int) -> float | None:
    return round(value, digits) if value is not None else None


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
