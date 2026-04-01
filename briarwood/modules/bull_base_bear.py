from __future__ import annotations

from math import pow

from briarwood.evidence import build_section_evidence
from briarwood.modules.current_value import CurrentValueModule, get_current_value_payload
from briarwood.modules.market_value_history import MarketValueHistoryModule
from briarwood.modules.risk_constraints import RiskConstraintsModule
from briarwood.modules.scarcity_support import ScarcitySupportModule, get_scarcity_support_payload
from briarwood.modules.town_county_outlook import TownCountyOutlookModule
from briarwood.schemas import ModuleResult, PropertyInput, ScenarioOutput
from briarwood.settings import BullBaseBearSettings, DEFAULT_BULL_BASE_BEAR_SETTINGS
from briarwood.scoring import clamp_score


class BullBaseBearModule:
    name = "bull_base_bear"

    def __init__(
        self,
        settings: BullBaseBearSettings | None = None,
        *,
        current_value_module: CurrentValueModule | None = None,
        market_value_history_module: MarketValueHistoryModule | None = None,
        town_county_outlook_module: TownCountyOutlookModule | None = None,
        risk_constraints_module: RiskConstraintsModule | None = None,
        scarcity_support_module: ScarcitySupportModule | None = None,
    ) -> None:
        self.settings = settings or DEFAULT_BULL_BASE_BEAR_SETTINGS
        self.current_value_module = current_value_module or CurrentValueModule()
        self.market_value_history_module = market_value_history_module or MarketValueHistoryModule()
        self.town_county_outlook_module = town_county_outlook_module or TownCountyOutlookModule()
        self.risk_constraints_module = risk_constraints_module or RiskConstraintsModule()
        self.scarcity_support_module = scarcity_support_module or ScarcitySupportModule()

    def run(
        self,
        property_input: PropertyInput,
        prior_results: dict[str, ModuleResult] | None = None,
    ) -> ModuleResult:
        price = float(property_input.purchase_price or 0.0)
        if price <= 0:
            scenario_output = ScenarioOutput(
                ask_price=0.0,
                bull_case_value=0.0,
                base_case_value=0.0,
                bear_case_value=0.0,
                spread=0.0,
            )
            return ModuleResult(
                module_name=self.name,
                metrics=scenario_output.to_metrics(),
                score=0.0,
                confidence=0.0,
                summary="Scenario range could not be calculated because purchase price is missing.",
                payload=scenario_output,
                section_evidence=build_section_evidence(
                    property_input,
                    categories=["price_ask", "market_history", "comp_support", "scarcity_inputs"],
                    extra_missing_inputs=["price_ask"],
                    notes=["Forward scenarios require an ask price anchor."],
                ),
            )

        # Pull pre-computed results from prior_results if available; otherwise run modules.
        # This avoids doubling computation when the engine has already run the dependencies.
        if prior_results is not None and "current_value" in prior_results:
            current_value_result = prior_results["current_value"]
        else:
            current_value_result = self.current_value_module.run(property_input)

        if prior_results is not None and "market_value_history" in prior_results:
            history_result = prior_results["market_value_history"]
        else:
            history_result = self.market_value_history_module.run(property_input)

        if prior_results is not None and "town_county_outlook" in prior_results:
            outlook_result = prior_results["town_county_outlook"]
        else:
            outlook_result = self.town_county_outlook_module.run(property_input)

        if prior_results is not None and "risk_constraints" in prior_results:
            risk_result = prior_results["risk_constraints"]
        else:
            risk_result = self.risk_constraints_module.run(property_input)

        if prior_results is not None and "scarcity_support" in prior_results:
            scarcity_result = prior_results["scarcity_support"]
        else:
            scarcity_result = self.scarcity_support_module.run(property_input)

        s = self.settings
        current_value = get_current_value_payload(current_value_result)
        scarcity = get_scarcity_support_payload(scarcity_result)
        bcv = current_value.briarwood_current_value

        # --- Input signals ---
        trailing_1yr = self._as_float(history_result.metrics.get("one_year_change_pct"))
        trailing_3yr_raw = self._as_float(history_result.metrics.get("three_year_change_pct"))
        trailing_5yr_raw = self._as_float(history_result.metrics.get("five_year_change_pct"))
        trailing_3yr_cagr = self._annualize(trailing_3yr_raw, years=3)
        trailing_5yr_cagr = self._annualize(trailing_5yr_raw, years=5)
        history_points_count = int(history_result.metrics.get("history_points") or 0)

        town_score = float(outlook_result.score)
        risk_score = float(risk_result.score)
        scarcity_score = float(scarcity.scarcity_support_score)

        # --- Market drift per scenario ---
        bull_drift, base_drift, bear_drift = self._market_drift_components(
            trailing_1yr=trailing_1yr,
            trailing_3yr_cagr=trailing_3yr_cagr,
            trailing_5yr_cagr=trailing_5yr_cagr,
        )

        # --- Location adjustment per scenario ---
        bull_location_pct, base_location_pct, bear_location_pct = self._location_components(town_score, s)

        # --- Risk adjustment per scenario ---
        bull_risk_pct, base_risk_pct, bear_risk_pct = self._risk_components(risk_score, s)

        # --- Optionality (bull/base only) ---
        bull_optionality_pct = (scarcity_score / 100.0) * s.bbb_max_optionality_premium
        base_optionality_pct = bull_optionality_pct * s.bbb_optionality_base_attenuation
        bear_optionality_pct = 0.0

        # --- Scenario values: BCV × (1 + components) ---
        bull_total = bull_drift + bull_location_pct + bull_risk_pct + bull_optionality_pct
        base_total = base_drift + base_location_pct + base_risk_pct + base_optionality_pct
        bear_total = bear_drift + bear_location_pct + bear_risk_pct + bear_optionality_pct

        bull_value = bcv * (1.0 + bull_total)
        base_value = bcv * (1.0 + base_total)
        bear_value = max(0.0, bcv * (1.0 + bear_total))

        # Enforce ordering: bull >= base >= bear
        bull_value = max(bull_value, base_value)
        bear_value = min(bear_value, base_value)

        # --- Stress scenario ---
        stress_case_value: float | None = None
        stress_drawdown_pct: float | None = None
        if s.bear_tail_risk_enabled:
            flood = (property_input.flood_risk or "").strip().lower()
            if flood == "high":
                stress_drawdown_pct = s.bbb_stress_drawdown_flood_high
            elif flood == "medium":
                stress_drawdown_pct = s.bbb_stress_drawdown_flood_medium
            else:
                stress_drawdown_pct = s.bbb_stress_drawdown_default
            stress_case_value = bcv * (1.0 - stress_drawdown_pct)

        # --- Growth rates vs ask ---
        bull_growth_rate = (bull_value - price) / price
        base_growth_rate = (base_value - price) / price
        bear_growth_rate = (bear_value - price) / price
        stress_growth_rate = (stress_case_value - price) / price if stress_case_value is not None else None

        spread = bull_value - bear_value

        scenario_output = ScenarioOutput(
            ask_price=float(price),
            bull_case_value=float(bull_value),
            base_case_value=float(base_value),
            bear_case_value=float(bear_value),
            spread=float(spread),
            stress_case_value=float(stress_case_value) if stress_case_value is not None else None,
        )

        # --- Confidence ---
        confidence, confidence_notes = self._compute_confidence(
            bcv_confidence=current_value_result.confidence,
            history_points_count=history_points_count,
            town_confidence=outlook_result.confidence,
            risk_confidence=risk_result.confidence,
            scarcity_confidence=scarcity_result.confidence,
            s=s,
        )

        # --- Score ---
        spread_pct = spread / price if price > 0 else 0.0
        score = clamp_score(s.base_score + spread_pct * 25.0)

        # --- Stress rationale ---
        if stress_drawdown_pct is not None:
            flood_tag = (property_input.flood_risk or "none").lower()
            if flood_tag == "high":
                stress_rationale = f"Based on 2007–2011 NJ coastal correction. High flood exposure applies elevated -{stress_drawdown_pct:.0%} drawdown."
            elif flood_tag == "medium":
                stress_rationale = f"Based on 2007–2011 NJ coastal correction. Medium flood exposure applies -{stress_drawdown_pct:.0%} drawdown."
            else:
                stress_rationale = f"Based on 2007–2011 NJ coastal correction of 25–35% peak-to-trough. Standard -{stress_drawdown_pct:.0%} drawdown applied."
        else:
            stress_rationale = "Stress scenario disabled."

        methodology_note = (
            "Scenarios are based on BCV adjusted for market momentum (ZHVI trailing rates), location strength, "
            "risk exposure, and optionality. Stress case reflects historical peak-to-trough correction for NJ coastal markets. "
            "12-month forward horizon."
        )

        summary = (
            f"Base case ${base_value:,.0f} (BCV ${bcv:,.0f} × {1 + base_total:+.1%}). "
            f"Bull ${bull_value:,.0f} / Bear ${bear_value:,.0f} gives a {spread_pct:.0%} spread. "
        )
        if stress_case_value is not None:
            summary += f"Stress case ${stress_case_value:,.0f} ({stress_rationale})"

        return ModuleResult(
            module_name=self.name,
            metrics={
                **scenario_output.to_metrics(),
                # Growth rates vs ask
                "base_growth_rate": round(base_growth_rate, 4),
                "bull_growth_rate": round(bull_growth_rate, 4),
                "bear_growth_rate": round(bear_growth_rate, 4),
                "stress_growth_rate": round(stress_growth_rate, 4) if stress_growth_rate is not None else None,
                "stress_macro_shock_pct": stress_drawdown_pct,
                # BCV anchor
                "bcv_anchor": round(bcv, 2),
                # Component breakdown — bull
                "bull_market_drift_pct": round(bull_drift, 4),
                "bull_location_pct": round(bull_location_pct, 4),
                "bull_risk_pct": round(bull_risk_pct, 4),
                "bull_optionality_pct": round(bull_optionality_pct, 4),
                "bull_total_adjustment_pct": round(bull_total, 4),
                # Component breakdown — base
                "base_market_drift_pct": round(base_drift, 4),
                "base_location_pct": round(base_location_pct, 4),
                "base_risk_pct": round(base_risk_pct, 4),
                "base_optionality_pct": round(base_optionality_pct, 4),
                "base_total_adjustment_pct": round(base_total, 4),
                # Component breakdown — bear
                "bear_market_drift_pct": round(bear_drift, 4),
                "bear_location_pct": round(bear_location_pct, 4),
                "bear_risk_pct": round(bear_risk_pct, 4),
                "bear_total_adjustment_pct": round(bear_total, 4),
                # Input traceability
                "inputs_trailing_1yr": trailing_1yr,
                "inputs_trailing_3yr_cagr": round(trailing_3yr_cagr, 4) if trailing_3yr_cagr is not None else None,
                "inputs_trailing_5yr_cagr": round(trailing_5yr_cagr, 4) if trailing_5yr_cagr is not None else None,
                "inputs_town_score": round(town_score, 1),
                "inputs_risk_score": round(risk_score, 1),
                "inputs_scarcity_score": round(scarcity_score, 1),
                # Legacy fields used by case_columns_section
                "market_drift": round(bcv * base_drift, 2),
                "location_premium": round(bcv * base_location_pct, 2),
                "risk_discount": round(bcv * abs(base_risk_pct), 2),
                "optionality_premium": round(bcv * base_optionality_pct, 2),
                "location_score": round(town_score, 2),
                "risk_score": round(risk_score, 2),
                "optionality_score": round(scarcity_score, 2),
                "market_history_confidence": history_result.confidence,
            },
            score=score,
            confidence=confidence,
            summary=summary,
            payload=scenario_output,
            section_evidence=build_section_evidence(
                property_input,
                categories=["price_ask", "market_history", "comp_support", "scarcity_inputs", "liquidity_signal"],
                notes=[methodology_note],
            ),
        )

    def _market_drift_components(
        self,
        *,
        trailing_1yr: float | None,
        trailing_3yr_cagr: float | None,
        trailing_5yr_cagr: float | None,
    ) -> tuple[float, float, float]:
        s = self.settings
        # Default to 0 if no data
        t1 = trailing_1yr if trailing_1yr is not None else 0.0
        t3 = trailing_3yr_cagr if trailing_3yr_cagr is not None else t1
        t5 = trailing_5yr_cagr if trailing_5yr_cagr is not None else t3

        if t1 >= 0:
            bull_drift = max(t1, t3)
            base_drift = t3
            bear_drift = min(t1, t5) * 0.5
        else:
            # Declining market
            bull_drift = t3 * 0.5
            base_drift = t1 * 0.5
            bear_drift = t1 * 1.5

        bull_drift = min(bull_drift, s.bbb_market_drift_bull_cap)
        bear_drift = max(bear_drift, s.bbb_market_drift_bear_floor)
        return bull_drift, base_drift, bear_drift

    def _location_components(
        self,
        town_score: float,
        s: BullBaseBearSettings,
    ) -> tuple[float, float, float]:
        location_delta = (town_score - 50.0) / 50.0  # -1 to +1

        if location_delta >= 0:
            # Good location: bull gets full premium, base gets half, bear gets nothing
            bull_loc = min(location_delta * s.bbb_location_good_bull_scale, s.bbb_location_premium_cap)
            base_loc = location_delta * s.bbb_location_good_base_scale
            bear_loc = 0.0
        else:
            # Weak location: bull unaffected, base takes moderate discount, bear takes full discount
            bull_loc = 0.0
            base_loc = max(location_delta * s.bbb_location_bad_base_scale, s.bbb_location_discount_floor)
            bear_loc = max(location_delta * s.bbb_location_bad_bear_scale, s.bbb_location_discount_floor)

        return bull_loc, base_loc, bear_loc

    def _risk_components(
        self,
        risk_score: float,
        s: BullBaseBearSettings,
    ) -> tuple[float, float, float]:
        # Compute base risk penalty (negative value representing the full bear-case impact)
        t1 = s.bbb_risk_tier_1_threshold
        t2 = s.bbb_risk_tier_2_threshold
        t3 = s.bbb_risk_tier_3_threshold

        if risk_score >= t1:
            base_risk_penalty = 0.0
        elif risk_score >= t2:
            # Linear from 0 at t1 to tier_1_max at t2
            frac = (t1 - risk_score) / (t1 - t2)
            base_risk_penalty = frac * s.bbb_risk_tier_1_max_penalty
        elif risk_score >= t3:
            # Linear from tier_1_max at t2 to tier_2_max at t3
            frac = (t2 - risk_score) / (t2 - t3)
            base_risk_penalty = s.bbb_risk_tier_1_max_penalty + frac * (
                s.bbb_risk_tier_2_max_penalty - s.bbb_risk_tier_1_max_penalty
            )
        else:
            # Linear from tier_2_max at t3 to tier_3_max at score 0
            frac = (t3 - risk_score) / t3 if t3 > 0 else 1.0
            base_risk_penalty = s.bbb_risk_tier_2_max_penalty + frac * (
                s.bbb_risk_tier_3_max_penalty - s.bbb_risk_tier_2_max_penalty
            )

        # Apply scenario attenuation (penalty is negative, so multiply by negative attenuation)
        bull_risk = -base_risk_penalty * s.bbb_risk_bull_attenuation
        base_risk = -base_risk_penalty * s.bbb_risk_base_attenuation
        bear_risk = -base_risk_penalty * s.bbb_risk_bear_attenuation
        return bull_risk, base_risk, bear_risk

    def _compute_confidence(
        self,
        *,
        bcv_confidence: float,
        history_points_count: int,
        town_confidence: float,
        risk_confidence: float,
        scarcity_confidence: float,
        s: BullBaseBearSettings,
    ) -> tuple[float, list[str]]:
        confidence = s.bbb_confidence_base
        notes: list[str] = []

        if bcv_confidence < 0.60:
            confidence -= s.bbb_confidence_deduction_bcv_low
            notes.append(f"BCV confidence is {bcv_confidence:.0%} — scenario anchor is uncertain.")

        # Monthly ZHVI points: 12/year
        if history_points_count < 12:
            confidence -= s.bbb_confidence_deduction_history_very_short
            notes.append("Less than 1 year of market history available — using limited trend data.")
        elif history_points_count < 24:
            confidence -= s.bbb_confidence_deduction_history_short
            notes.append("Less than 2 years of market history — market drift is less reliable.")

        if town_confidence < 0.70:
            confidence -= s.bbb_confidence_deduction_town_weak
            notes.append("Town/county outlook confidence is below 0.70.")

        if risk_confidence < 0.70:
            confidence -= s.bbb_confidence_deduction_risk_weak
            notes.append("Risk score confidence is below 0.70 — some risk dimensions have missing data.")

        if scarcity_confidence < 0.60:
            confidence -= s.bbb_confidence_deduction_scarcity_weak
            notes.append("Scarcity confidence is below 0.60.")

        confidence = max(confidence, s.bbb_confidence_floor)
        return round(confidence, 2), notes

    def _annualize(self, cumulative_change: float | None, *, years: int) -> float | None:
        if cumulative_change is None or cumulative_change <= -1:
            return None
        return pow(1.0 + cumulative_change, 1.0 / years) - 1.0

    def _as_float(self, value: object) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None
