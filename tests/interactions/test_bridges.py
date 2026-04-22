"""Phase 4 tests: interaction bridges fire correctly and produce adjustments.

These tests use the scoped-module runners directly to build a realistic
``ModuleOutputs`` dict, then run each bridge against it. Bridges are pure
functions so we don't need the full orchestrator to exercise them.
"""

from __future__ import annotations

import unittest

from briarwood.interactions import InteractionTrace, run_all_bridges
from briarwood.interactions import primary_value_source
from briarwood.interactions.bridge import BridgeRecord
from briarwood.modules.carry_cost import run_carry_cost
from briarwood.modules.risk_model import run_risk_model
from briarwood.modules.strategy_classifier import run_strategy_classifier
from briarwood.modules.valuation import run_valuation

from tests.modules._phase2_fixtures import (
    context_fragile,
    context_normal,
    context_unique,
)


def _build_module_outputs(ctx) -> dict[str, dict]:
    """Run the subset of scoped modules the bridges depend on."""
    outputs: dict[str, dict] = {}
    outputs["valuation"] = run_valuation(ctx)
    outputs["risk_model"] = run_risk_model(ctx)
    outputs["carry_cost"] = run_carry_cost(ctx)
    outputs["strategy_classifier"] = run_strategy_classifier(ctx)
    return outputs


class BridgeRegistryTests(unittest.TestCase):
    def test_all_bridges_run_without_error_on_normal_property(self) -> None:
        outputs = _build_module_outputs(context_normal())
        trace = run_all_bridges(outputs)
        self.assertIsInstance(trace, InteractionTrace)
        # 8 bridges register regardless of whether they fire.
        self.assertEqual(len(trace.records), 9)
        for record in trace.records:
            self.assertIsInstance(record, BridgeRecord)

    def test_at_least_four_bridges_fire_on_normal_property(self) -> None:
        """Phase 4 gate: a typical property should trigger ≥ 4 bridges."""
        outputs = _build_module_outputs(context_normal())
        trace = run_all_bridges(outputs)
        fired = [r.name for r in trace.fired]
        self.assertGreaterEqual(
            len(fired), 4,
            f"Only {len(fired)} bridges fired: {fired}",
        )

    def test_valuation_x_risk_fires_when_risk_flags_present(self) -> None:
        outputs = _build_module_outputs(context_fragile())
        trace = run_all_bridges(outputs)
        record = trace.get("valuation_x_risk")
        self.assertIsNotNone(record)
        # Fragile fixture has higher_vacancy → should fire a discount demand.
        self.assertTrue(record.fired)
        self.assertGreater(record.adjustments["extra_discount_demanded_pct"], 0)

    def test_rent_x_cost_produces_carry_offset_ratio(self) -> None:
        outputs = _build_module_outputs(context_normal())
        trace = run_all_bridges(outputs)
        record = trace.get("rent_x_cost")
        self.assertIsNotNone(record)
        if record.fired:
            self.assertIn("carry_offset_ratio", record.adjustments)
            self.assertIn("required_occupancy", record.adjustments)

    def test_primary_value_source_classifies(self) -> None:
        outputs = _build_module_outputs(context_normal())
        trace = run_all_bridges(outputs)
        record = trace.get("primary_value_source")
        self.assertIsNotNone(record)
        self.assertTrue(record.fired)
        self.assertIn(
            record.adjustments["primary_value_source"],
            {"current_value", "income", "repositioning", "optionality", "scarcity"},
        )

    def test_conflict_detector_runs_on_unique_property(self) -> None:
        outputs = _build_module_outputs(context_unique())
        trace = run_all_bridges(outputs)
        record = trace.get("conflict_detector")
        self.assertIsNotNone(record)
        # Record always exists; fired status depends on whether a conflict hit.
        self.assertIsInstance(record.adjustments["conflicts"], list)

    def test_interaction_trace_is_serializable(self) -> None:
        outputs = _build_module_outputs(context_normal())
        trace = run_all_bridges(outputs)
        serialized = trace.to_dict()
        self.assertIn("records", serialized)
        self.assertIn("fired_count", serialized)
        self.assertEqual(serialized["total_count"], 9)

    def test_primary_value_source_logs_unknown_path(self) -> None:
        """NEW-V-005: when no signals fire, the bridge emits an INFO log
        summarizing which signals were checked and absent, so the blank
        'unknown' classification is traceable in production logs."""
        empty_outputs: dict[str, dict] = {}
        with self.assertLogs(primary_value_source.__name__, level="DEBUG") as captured:
            record = primary_value_source.run(empty_outputs)

        self.assertFalse(record.fired)
        self.assertEqual(record.adjustments["primary_value_source"], "unknown")
        # DEBUG logs for all four branches fired=False, plus one INFO log at the tail.
        messages = [entry.getMessage() for entry in captured.records]
        self.assertTrue(
            any("strategy_check" in m and "fired=False" in m for m in messages)
        )
        self.assertTrue(
            any("valuation_mispricing_check" in m and "fired=False" in m for m in messages)
        )
        self.assertTrue(
            any("carry_offset_check" in m and "fired=False" in m for m in messages)
        )
        self.assertTrue(
            any("scenario_check" in m and "fired=False" in m for m in messages)
        )
        info_records = [r for r in captured.records if r.levelname == "INFO"]
        self.assertEqual(len(info_records), 1)
        self.assertIn("primary_value_source.unknown", info_records[0].getMessage())

    def test_bridge_exception_does_not_kill_run(self) -> None:
        # Pass a broken outputs dict that might trip a bridge; the registry
        # catches exceptions and records them rather than propagating.
        bogus: dict[str, dict] = {"valuation": {"data": "not a dict"}}
        trace = run_all_bridges(bogus)  # should not raise
        self.assertEqual(len(trace.records), 9)


if __name__ == "__main__":
    unittest.main()
