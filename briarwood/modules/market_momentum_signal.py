from __future__ import annotations

from briarwood.evidence import build_section_evidence
from briarwood.modules.bull_base_bear import BullBaseBearModule
from briarwood.modules.local_intelligence import LocalIntelligenceModule
from briarwood.modules.market_value_history import MarketValueHistoryModule
from briarwood.modules.town_county_outlook import TownCountyOutlookModule, get_town_county_outlook_payload
from briarwood.schemas import MarketMomentumOutput, ModuleResult, PropertyInput


class MarketMomentumSignalModule:
    """Canonical market momentum signal for the current underwriting stack."""

    name = "market_momentum_signal"

    def __init__(
        self,
        *,
        market_value_history_module: MarketValueHistoryModule | None = None,
        town_county_outlook_module: TownCountyOutlookModule | None = None,
        local_intelligence_module: LocalIntelligenceModule | None = None,
        bull_base_bear_module: BullBaseBearModule | None = None,
    ) -> None:
        self.market_value_history_module = market_value_history_module or MarketValueHistoryModule()
        self.town_county_outlook_module = town_county_outlook_module or TownCountyOutlookModule()
        self.local_intelligence_module = local_intelligence_module or LocalIntelligenceModule()
        self.bull_base_bear_module = bull_base_bear_module or BullBaseBearModule()

    def run(self, property_input: PropertyInput) -> ModuleResult:
        history_result = self.market_value_history_module.run(property_input)
        town_result = self.town_county_outlook_module.run(property_input)
        local_result = self.local_intelligence_module.run(property_input)
        scenario_result = self.bull_base_bear_module.run(property_input)

        history = history_result.metrics
        town = get_town_county_outlook_payload(town_result).score
        local = local_result.metrics
        scenario = scenario_result.metrics

        history_trend_score = _history_trend_score(
            history.get("one_year_change_pct"),
            history.get("three_year_change_pct"),
        )
        town_market_score = _town_market_score(
            town.town_county_score,
            town.appreciation_support_view,
        )
        local_activity_score = _local_activity_score(
            local.get("development_activity_score"),
            local.get("regulatory_trend_score"),
            local.get("supply_pipeline_score"),
            local.get("sentiment_score"),
        )
        scenario_drift_score = _scenario_drift_score(scenario.get("base_market_drift_pct"))

        weighted_components = []
        if history_trend_score is not None:
            weighted_components.append(("history", history_trend_score, 0.35))
        if town_market_score is not None:
            weighted_components.append(("town", town_market_score, 0.25))
        if local_activity_score is not None:
            weighted_components.append(("local", local_activity_score, 0.20))
        if scenario_drift_score is not None:
            weighted_components.append(("drift", scenario_drift_score, 0.20))

        total_weight = sum(weight for _, _, weight in weighted_components)
        score = (
            sum(component_score * weight for _, component_score, weight in weighted_components) / total_weight
            if total_weight
            else 50.0
        )
        score = round(max(0.0, min(score, 100.0)), 1)
        label = _momentum_label(score)
        confidence = _confidence(weighted_components, history_result.confidence, town_result.confidence, local_result.confidence, scenario_result.confidence)
        drivers = _drivers(
            history.get("one_year_change_pct"),
            local.get("development_activity_score"),
            local.get("regulatory_trend_score"),
            local.get("supply_pipeline_score"),
            scenario.get("base_market_drift_pct"),
            town.appreciation_support_view,
        )
        assumptions = _assumptions(weighted_components)
        unsupported_claims = _unsupported_claims(weighted_components)
        summary = _summary(label, history.get("one_year_change_pct"), scenario.get("base_market_drift_pct"), drivers)

        output = MarketMomentumOutput(
            market_momentum_score=score,
            market_momentum_label=label,
            confidence=confidence,
            summary=summary,
            history_trend_score=round(history_trend_score, 1) if history_trend_score is not None else None,
            town_market_score=round(town_market_score, 1) if town_market_score is not None else None,
            local_activity_score=round(local_activity_score, 1) if local_activity_score is not None else None,
            scenario_drift_score=round(scenario_drift_score, 1) if scenario_drift_score is not None else None,
            one_year_change_pct=history.get("one_year_change_pct"),
            three_year_change_pct=history.get("three_year_change_pct"),
            base_market_drift_pct=scenario.get("base_market_drift_pct"),
            drivers=drivers,
            assumptions=assumptions,
            unsupported_claims=unsupported_claims,
        )
        metrics = {
            "market_momentum_score": output.market_momentum_score,
            "market_momentum_label": output.market_momentum_label,
            "history_trend_score": output.history_trend_score,
            "town_market_score": output.town_market_score,
            "local_activity_score": output.local_activity_score,
            "scenario_drift_score": output.scenario_drift_score,
            "one_year_change_pct": output.one_year_change_pct,
            "three_year_change_pct": output.three_year_change_pct,
            "base_market_drift_pct": output.base_market_drift_pct,
        }
        return ModuleResult(
            module_name=self.name,
            metrics=metrics,
            score=float(output.market_momentum_score),
            confidence=float(output.confidence),
            summary=output.summary,
            payload=output,
            section_evidence=build_section_evidence(
                property_input,
                categories=["market_history", "liquidity_signal", "scarcity_inputs"],
                notes=["Canonical market momentum blends backward-looking history, town outlook, local development signals, and scenario market drift."],
                extra_missing_inputs=(["local_documents"] if not property_input.local_documents else []),
            ),
        )


def _history_trend_score(one_year_change_pct: float | None, three_year_change_pct: float | None) -> float | None:
    if one_year_change_pct is None and three_year_change_pct is None:
        return None
    score = 50.0
    if one_year_change_pct is not None:
        score += max(-25.0, min(one_year_change_pct * 400.0, 25.0))
    if three_year_change_pct is not None:
        score += max(-15.0, min(three_year_change_pct * 250.0, 15.0))
    return max(0.0, min(score, 100.0))


def _town_market_score(town_score: float | None, appreciation_support_view: str | None) -> float | None:
    if town_score is None:
        return None
    score = max(0.0, min(float(town_score), 100.0))
    view = (appreciation_support_view or "").lower()
    if "supportive" in view or "positive" in view:
        score = min(100.0, score + 5.0)
    elif "weak" in view or "negative" in view:
        score = max(0.0, score - 8.0)
    return score


def _local_activity_score(
    development_activity_score: float | None,
    regulatory_trend_score: float | None,
    supply_pipeline_score: float | None,
    sentiment_score: float | None,
) -> float | None:
    values = []
    if development_activity_score is not None:
        values.append((float(development_activity_score), 0.35))
    if regulatory_trend_score is not None:
        values.append((float(regulatory_trend_score), 0.30))
    if supply_pipeline_score is not None:
        values.append((100.0 - float(supply_pipeline_score), 0.20))
    if sentiment_score is not None:
        values.append((float(sentiment_score), 0.15))
    if not values:
        return None
    total_weight = sum(weight for _, weight in values)
    return sum(value * weight for value, weight in values) / total_weight


def _scenario_drift_score(base_market_drift_pct: float | None) -> float | None:
    if base_market_drift_pct is None:
        return None
    return max(0.0, min(50.0 + (float(base_market_drift_pct) * 500.0), 100.0))


def _momentum_label(score: float) -> str:
    if score >= 72:
        return "Supportive Momentum"
    if score >= 58:
        return "Constructive Momentum"
    if score >= 45:
        return "Mixed Momentum"
    return "Weak Momentum"


def _confidence(
    weighted_components: list[tuple[str, float, float]],
    history_confidence: float,
    town_confidence: float,
    local_confidence: float,
    scenario_confidence: float,
) -> float:
    if not weighted_components:
        return 0.35
    caps = {
        "history": history_confidence,
        "town": town_confidence,
        "local": local_confidence,
        "drift": scenario_confidence,
    }
    total_weight = sum(weight for key, _, weight in weighted_components)
    confidence = sum(caps.get(key, 0.5) * weight for key, _, weight in weighted_components) / total_weight
    if len(weighted_components) <= 2:
        confidence = min(confidence, 0.72)
    return round(max(0.35, min(confidence, 0.9)), 2)


def _drivers(
    one_year_change_pct: float | None,
    development_activity_score: float | None,
    regulatory_trend_score: float | None,
    supply_pipeline_score: float | None,
    base_market_drift_pct: float | None,
    appreciation_support_view: str | None,
) -> list[str]:
    drivers: list[str] = []
    if one_year_change_pct is not None:
        drivers.append(
            "positive recent price trend"
            if one_year_change_pct >= 0.03
            else "negative recent price trend"
            if one_year_change_pct <= -0.02
            else "flat recent price trend"
        )
    if development_activity_score is not None and development_activity_score >= 65:
        drivers.append("active redevelopment pipeline")
    if regulatory_trend_score is not None and regulatory_trend_score >= 65:
        drivers.append("supportive regulatory backdrop")
    if supply_pipeline_score is not None and supply_pipeline_score >= 65:
        drivers.append("meaningful new supply pipeline")
    if base_market_drift_pct is not None:
        drivers.append(
            "positive forward drift assumption"
            if base_market_drift_pct > 0.02
            else "negative forward drift assumption"
            if base_market_drift_pct < 0
            else "muted forward drift assumption"
        )
    if appreciation_support_view:
        drivers.append(appreciation_support_view.replace("_", " "))
    return drivers[:4]


def _assumptions(weighted_components: list[tuple[str, float, float]]) -> list[str]:
    notes: list[str] = []
    if not any(key == "local" for key, _, _ in weighted_components):
        notes.append("Local document intelligence is missing, so market momentum leans on history and town-level proxies.")
    if not any(key == "drift" for key, _, _ in weighted_components):
        notes.append("Forward drift contribution is missing, so momentum is more backward-looking than forward-looking.")
    return notes


def _unsupported_claims(weighted_components: list[tuple[str, float, float]]) -> list[str]:
    claims: list[str] = []
    if len(weighted_components) <= 2:
        claims.append("Market momentum relies on a limited evidence mix and should be treated as directional.")
    return claims


def _summary(
    label: str,
    one_year_change_pct: float | None,
    base_market_drift_pct: float | None,
    drivers: list[str],
) -> str:
    trend_text = f"1yr trend {one_year_change_pct:+.1%}" if one_year_change_pct is not None else "1yr trend unavailable"
    drift_text = f"base drift {base_market_drift_pct:+.1%}" if base_market_drift_pct is not None else "base drift unavailable"
    driver_text = ", ".join(drivers[:2]) if drivers else "limited market drivers"
    return f"{label}. Momentum blends {trend_text}, {drift_text}, and {driver_text}."
