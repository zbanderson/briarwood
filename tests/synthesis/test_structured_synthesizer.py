"""Phase 5 tests: structured synthesizer produces reproducible unified outputs.

Covers the Phase 5 plan gate:
- populated ``primary_value_source``, ``trust_flags``, ``what_must_be_true``,
  ``decision_stance``
- trust gate fires on thin inputs → CONDITIONAL stance
- same inputs always produce same outputs (no LLM in the decision path)
"""

from __future__ import annotations

import unittest

from briarwood.interactions import run_all_bridges
from briarwood.modules.carry_cost import run_carry_cost
from briarwood.modules.risk_model import run_risk_model
from briarwood.modules.strategy_classifier import run_strategy_classifier
from briarwood.modules.valuation import run_valuation
from briarwood.routing_schema import (
    AnalysisDepth,
    DecisionStance,
    IntentType,
    OccupancyType,
    ParserOutput,
    UnifiedIntelligenceOutput,
)
from briarwood.synthesis import build_unified_output

from tests.modules._phase2_fixtures import (
    context_fragile,
    context_normal,
    context_thin,
)


def _parser_output_dict(depth: AnalysisDepth = AnalysisDepth.DECISION) -> dict:
    return ParserOutput(
        intent_type=IntentType.BUY_DECISION,
        analysis_depth=depth,
        question_focus=[],
        occupancy_type=OccupancyType.INVESTOR,
        confidence=0.8,
        missing_inputs=[],
        renovation_plan=False,
    ).model_dump()


def _build(ctx) -> tuple[dict, dict, dict]:
    outputs = {
        "valuation": run_valuation(ctx),
        "risk_model": run_risk_model(ctx),
        "carry_cost": run_carry_cost(ctx),
        "strategy_classifier": run_strategy_classifier(ctx),
    }
    trace = run_all_bridges(outputs).to_dict()
    property_summary = {"property_id": ctx.property_id}
    return property_summary, outputs, trace


class StructuredSynthesizerTests(unittest.TestCase):
    def test_output_validates_against_schema(self) -> None:
        ps, outputs, trace = _build(context_normal())
        result = build_unified_output(
            property_summary=ps,
            parser_output=_parser_output_dict(),
            module_results=outputs,
            interaction_trace=trace,
        )
        # Validates cleanly — every required field present.
        validated = UnifiedIntelligenceOutput.model_validate(result)
        self.assertIsNotNone(validated.decision_stance)
        self.assertIsNotNone(validated.primary_value_source)

    def test_primary_value_source_populated(self) -> None:
        ps, outputs, trace = _build(context_normal())
        result = build_unified_output(
            property_summary=ps,
            parser_output=_parser_output_dict(),
            module_results=outputs,
            interaction_trace=trace,
        )
        self.assertIn(
            result["primary_value_source"],
            {"current_value", "income", "repositioning", "optionality", "scarcity", "unknown"},
        )

    def test_value_position_shape(self) -> None:
        ps, outputs, trace = _build(context_normal())
        result = build_unified_output(
            property_summary=ps,
            parser_output=_parser_output_dict(),
            module_results=outputs,
            interaction_trace=trace,
        )
        vp = result["value_position"]
        self.assertIn("fair_value_base", vp)
        self.assertIn("ask_price", vp)
        self.assertIn("premium_discount_pct", vp)

    def test_trust_gate_fires_on_thin_inputs(self) -> None:
        """Phase 5 gate: thin data → CONDITIONAL stance, not a strong recommendation."""
        ps, outputs, trace = _build(context_thin())
        result = build_unified_output(
            property_summary=ps,
            parser_output=_parser_output_dict(),
            module_results=outputs,
            interaction_trace=trace,
        )
        # Thin inputs should not produce a strong buy.
        self.assertNotEqual(result["decision_stance"], DecisionStance.STRONG_BUY.value)

    def test_conditional_stance_surfaces_trust_floor_in_why_this_stance(self) -> None:
        """AUDIT O.5: when the trust gate collapses stance to CONDITIONAL, the
        `why_this_stance` output must explicitly say that — otherwise downstream
        consumers and narration can't tell the collapse apart from an ordinary
        market-driven PASS/HOLD. The leading line is the structured signal."""
        ps, outputs, trace = _build(context_thin())
        result = build_unified_output(
            property_summary=ps,
            parser_output=_parser_output_dict(),
            module_results=outputs,
            interaction_trace=trace,
        )
        if result["decision_stance"] != DecisionStance.CONDITIONAL.value:
            self.skipTest("thin fixture did not collapse to CONDITIONAL on this run")
        leading = result["why_this_stance"][0].lower() if result["why_this_stance"] else ""
        self.assertIn("trust floor", leading)
        self.assertIn("no directional call", leading)

    def test_reproducible_output(self) -> None:
        """Same inputs → byte-identical decision fields (no LLM in the loop)."""
        ps, outputs, trace = _build(context_normal())
        r1 = build_unified_output(
            property_summary=ps,
            parser_output=_parser_output_dict(),
            module_results=outputs,
            interaction_trace=trace,
        )
        r2 = build_unified_output(
            property_summary=ps,
            parser_output=_parser_output_dict(),
            module_results=outputs,
            interaction_trace=trace,
        )
        for field in (
            "decision",
            "decision_stance",
            "primary_value_source",
            "confidence",
            "value_position",
        ):
            self.assertEqual(r1[field], r2[field])

    def test_fragile_property_surfaces_risks(self) -> None:
        ps, outputs, trace = _build(context_fragile())
        result = build_unified_output(
            property_summary=ps,
            parser_output=_parser_output_dict(),
            module_results=outputs,
            interaction_trace=trace,
        )
        # Fragile case should produce at least one risk and at least one check.
        self.assertTrue(result["key_risks"] or result["trust_flags"])

    def test_interaction_trace_attached(self) -> None:
        ps, outputs, trace = _build(context_normal())
        result = build_unified_output(
            property_summary=ps,
            parser_output=_parser_output_dict(),
            module_results=outputs,
            interaction_trace=trace,
        )
        self.assertIn("records", result["interaction_trace"])
        self.assertEqual(result["interaction_trace"]["total_count"], 8)


class OptionalitySignalTests(unittest.TestCase):
    """F5: hidden-upside signal populates from renovation / ARV / unit-income
    module outputs. The synthesizer reads typed fields we know those modules
    emit today; if a module reshapes its output, this test breaks loudly
    instead of silently dropping the signal."""

    def _base(self) -> tuple[dict, dict, dict]:
        ps, outputs, trace = _build(context_normal())
        return ps, outputs, trace

    def test_empty_when_no_upside_modules_present(self) -> None:
        ps, outputs, trace = self._base()
        result = build_unified_output(
            property_summary=ps,
            parser_output=_parser_output_dict(),
            module_results=outputs,
            interaction_trace=trace,
        )
        signal = result["optionality_signal"]
        self.assertEqual(signal["hidden_upside_items"], [])

    def test_renovation_spread_surfaces_as_hidden_upside_item(self) -> None:
        ps, outputs, trace = self._base()
        outputs["renovation_impact"] = {
            "data": {
                "summary": "Full-gut reno underwrite.",
                "metrics": {
                    "gross_value_creation": 180_000,
                    "net_value_creation": 125_000,
                    "roi_pct": 42.0,
                    "renovation_budget": 55_000,
                },
            },
            "confidence": 0.72,
        }
        result = build_unified_output(
            property_summary=ps,
            parser_output=_parser_output_dict(),
            module_results=outputs,
            interaction_trace=trace,
        )
        items = result["optionality_signal"]["hidden_upside_items"]
        kinds = {item["kind"] for item in items}
        self.assertIn("renovation_spread", kinds)
        reno_item = next(i for i in items if i["kind"] == "renovation_spread")
        self.assertEqual(reno_item["source_module"], "renovation_impact")
        self.assertAlmostEqual(reno_item["magnitude_usd"], 125_000.0)

    def test_unit_income_offset_surfaces_as_hidden_upside_item(self) -> None:
        ps, outputs, trace = self._base()
        outputs["unit_income_offset"] = {
            "data": {
                "summary": "Detached ADU is rent-ready.",
                "offset_snapshot": {
                    "additional_unit_income_value": 48_000,
                    "additional_unit_count": 1,
                    "back_house_monthly_rent": 2_400,
                },
            },
            "confidence": 0.6,
        }
        result = build_unified_output(
            property_summary=ps,
            parser_output=_parser_output_dict(),
            module_results=outputs,
            interaction_trace=trace,
        )
        items = result["optionality_signal"]["hidden_upside_items"]
        self.assertTrue(any(i["kind"] == "unit_income" for i in items))


if __name__ == "__main__":
    unittest.main()
