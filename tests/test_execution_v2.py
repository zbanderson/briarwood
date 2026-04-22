from __future__ import annotations

import unittest

from briarwood.execution.context import ExecutionContext
from briarwood.execution.executor import build_module_cache_key, execute_plan
from briarwood.execution.planner import build_execution_plan
from briarwood.execution.registry import ModuleSpec, build_module_registry
from briarwood.orchestrator import build_cache_key, supports_scoped_execution
from briarwood.router import route_user_input
from briarwood.routing_schema import ModuleName, ParserOutput


class ExecutionPlannerTests(unittest.TestCase):
    def test_dependency_expansion_for_hold_to_rent(self) -> None:
        registry = build_module_registry()

        plan = build_execution_plan(["hold_to_rent"], registry)

        self.assertEqual(plan.selected_modules, ["hold_to_rent"])
        self.assertIn("carry_cost", plan.dependency_modules)
        self.assertIn("rent_stabilization", plan.dependency_modules)
        self.assertIn("hold_to_rent", plan.ordered_modules)

    def test_execution_ordering_for_margin_sensitivity(self) -> None:
        registry = build_module_registry()

        plan = build_execution_plan(["margin_sensitivity"], registry)

        self.assertLess(plan.ordered_modules.index("renovation_impact"), plan.ordered_modules.index("arv_model"))
        self.assertLess(plan.ordered_modules.index("arv_model"), plan.ordered_modules.index("margin_sensitivity"))

    def test_unknown_module_raises_clear_error(self) -> None:
        registry = build_module_registry()

        with self.assertRaisesRegex(ValueError, "Unknown module name: does_not_exist"):
            build_execution_plan(["does_not_exist"], registry)

    def test_circular_dependency_raises_clear_error(self) -> None:
        registry = {
            "alpha": ModuleSpec(name="alpha", depends_on=["beta"], runner=lambda _context: {"data": {}}),
            "beta": ModuleSpec(name="beta", depends_on=["alpha"], runner=lambda _context: {"data": {}}),
        }

        with self.assertRaisesRegex(ValueError, "Circular dependency detected"):
            build_execution_plan(["alpha"], registry)


class ScopedExecutorTests(unittest.TestCase):
    def test_scoped_executor_calls_only_ordered_modules_and_stores_outputs(self) -> None:
        calls: list[str] = []

        def run_base(context: ExecutionContext) -> dict[str, object]:
            calls.append("base")
            self.assertEqual(context.prior_outputs, {})
            return {
                "data": {"base_value": 1},
                "confidence": 0.8,
                "assumptions_used": {"source": "base"},
                "warnings": [],
            }

        def run_derived(context: ExecutionContext) -> dict[str, object]:
            calls.append("derived")
            self.assertIn("base", context.prior_outputs)
            return {
                "data": {"derived_value": context.prior_outputs["base"]["data"]["base_value"] + 1},
                "confidence": 0.7,
                "assumptions_used": {"source": "derived"},
                "warnings": [],
            }

        registry = {
            "base": ModuleSpec(
                name="base",
                required_context_keys=["property_data"],
                runner=run_base,
            ),
            "derived": ModuleSpec(
                name="derived",
                depends_on=["base"],
                required_context_keys=["property_data"],
                runner=run_derived,
            ),
            "unused": ModuleSpec(
                name="unused",
                required_context_keys=["property_data"],
                runner=lambda _context: {"data": {"unused": True}},
            ),
        }
        plan = build_execution_plan(["derived"], registry)
        context = ExecutionContext(
            property_id="prop-1",
            property_data={"property_id": "prop-1", "address": "1 Test St"},
        )

        result = execute_plan(plan, context, registry)

        self.assertEqual(calls, ["base", "derived"])
        self.assertIn("base", result["outputs"])
        self.assertIn("derived", result["outputs"])
        self.assertNotIn("unused", result["outputs"])
        self.assertIn("base", context.prior_outputs)
        self.assertIn("derived", context.prior_outputs)
        self.assertEqual(
            context.prior_outputs["derived"]["data"]["derived_value"],
            2,
        )

    def test_required_context_validation_raises_useful_error(self) -> None:
        registry = {
            "needs_property": ModuleSpec(
                name="needs_property",
                required_context_keys=["property_data"],
                runner=lambda _context: {"data": {"ok": True}},
            )
        }
        plan = build_execution_plan(["needs_property"], registry)
        context = ExecutionContext(property_id="prop-2")

        with self.assertRaisesRegex(
            ValueError,
            "Module 'needs_property' is missing required context keys: property_data",
        ):
            execute_plan(plan, context, registry)

    def test_partial_rerun_reuses_unchanged_modules_and_reruns_dependents(self) -> None:
        calls: list[str] = []
        module_cache: dict[str, dict[str, object]] = {}

        def run_carry_cost(context: ExecutionContext) -> dict[str, object]:
            calls.append("carry_cost")
            return {
                "data": {"carry_basis": context.assumptions.get("down_payment_percent")},
                "confidence": 0.8,
                "assumptions_used": {},
                "warnings": [],
            }

        def run_rent_stabilization(context: ExecutionContext) -> dict[str, object]:
            calls.append("rent_stabilization")
            return {
                "data": {"rent": context.assumptions.get("estimated_monthly_rent")},
                "confidence": 0.7,
                "assumptions_used": {},
                "warnings": [],
            }

        def run_hold_to_rent(context: ExecutionContext) -> dict[str, object]:
            calls.append("hold_to_rent")
            return {
                "data": {
                    "carry_basis": context.prior_outputs["carry_cost"]["data"]["carry_basis"],
                    "rent": context.prior_outputs["rent_stabilization"]["data"]["rent"],
                },
                "confidence": 0.6,
                "assumptions_used": {},
                "warnings": [],
            }

        registry = {
            "carry_cost": ModuleSpec(
                name="carry_cost",
                required_context_keys=["property_data", "assumptions"],
                runner=run_carry_cost,
            ),
            "rent_stabilization": ModuleSpec(
                name="rent_stabilization",
                required_context_keys=["property_data"],
                runner=run_rent_stabilization,
            ),
            "hold_to_rent": ModuleSpec(
                name="hold_to_rent",
                depends_on=["carry_cost", "rent_stabilization"],
                required_context_keys=["property_data", "assumptions"],
                runner=run_hold_to_rent,
            ),
        }
        plan = build_execution_plan(["hold_to_rent"], registry)

        first_context = ExecutionContext(
            property_id="prop-1",
            property_data={"property_id": "prop-1", "purchase_price": 700000},
            assumptions={"down_payment_percent": 0.2, "estimated_monthly_rent": 3000},
        )
        first = execute_plan(plan, first_context, registry, module_output_cache=module_cache)
        self.assertEqual(calls, ["carry_cost", "rent_stabilization", "hold_to_rent"])
        self.assertEqual([row["source"] for row in first["trace"]], ["run", "run", "run"])

        calls.clear()
        second_context = ExecutionContext(
            property_id="prop-1",
            property_data={"property_id": "prop-1", "purchase_price": 700000},
            assumptions={"down_payment_percent": 0.2, "estimated_monthly_rent": 3200},
        )
        second = execute_plan(plan, second_context, registry, module_output_cache=module_cache)

        self.assertEqual(calls, ["rent_stabilization", "hold_to_rent"])
        trace_by_module = {row["module"]: row for row in second["trace"]}
        self.assertEqual(trace_by_module["carry_cost"]["source"], "cache")
        self.assertEqual(trace_by_module["rent_stabilization"]["source"], "run")
        self.assertEqual(trace_by_module["hold_to_rent"]["source"], "run")
        self.assertEqual(
            second["outputs"]["hold_to_rent"]["data"]["rent"],
            3200,
        )

    def test_module_cache_key_changes_only_for_relevant_inputs(self) -> None:
        base_context = ExecutionContext(
            property_id="prop-2",
            property_data={"property_id": "prop-2", "purchase_price": 700000},
            assumptions={"down_payment_percent": 0.2, "estimated_monthly_rent": 3000},
        )
        changed_rent_context = ExecutionContext(
            property_id="prop-2",
            property_data={"property_id": "prop-2", "purchase_price": 700000},
            assumptions={"down_payment_percent": 0.2, "estimated_monthly_rent": 3200},
        )

        self.assertEqual(
            build_module_cache_key("carry_cost", base_context),
            build_module_cache_key("carry_cost", changed_rent_context),
        )
        self.assertNotEqual(
            build_module_cache_key("rent_stabilization", base_context),
            build_module_cache_key("rent_stabilization", changed_rent_context),
        )


class Wave1SupportTests(unittest.TestCase):
    def test_wave_1_buy_snapshot_path_supports_scoped_execution(self) -> None:
        routing_decision = route_user_input("Should I buy this?")

        supported, plan = supports_scoped_execution(routing_decision.selected_modules)

        self.assertTrue(supported)
        self.assertIsNotNone(plan)
        self.assertIn("valuation", plan.ordered_modules)
        self.assertIn("confidence", plan.ordered_modules)

    def test_hold_to_rent_path_is_scoped_supported(self) -> None:
        selected_modules = [
            ModuleName.VALUATION,
            ModuleName.CARRY_COST,
            ModuleName.RENT_STABILIZATION,
            ModuleName.HOLD_TO_RENT,
        ]

        supported, plan = supports_scoped_execution(selected_modules)

        self.assertTrue(supported)
        self.assertIsNotNone(plan)
        self.assertIn("hold_to_rent", plan.ordered_modules)
        self.assertIn("rent_stabilization", plan.ordered_modules)
        self.assertIn("carry_cost", plan.ordered_modules)

    def test_analysis_cache_key_changes_when_assumptions_change(self) -> None:
        parser_output = ParserOutput(
            intent_type="buy_decision",
            analysis_depth="decision",
            question_focus=["future_income"],
            occupancy_type="unknown",
            exit_options=["rent"],
            confidence=0.8,
            missing_inputs=[],
        )

        property_data_a = {
            "property_id": "prop-cache",
            "estimated_monthly_rent": 3000,
            "down_payment_percent": 0.2,
        }
        property_data_b = {
            "property_id": "prop-cache",
            "estimated_monthly_rent": 3200,
            "down_payment_percent": 0.2,
        }

        self.assertNotEqual(
            build_cache_key(property_data_a, parser_output),
            build_cache_key(property_data_b, parser_output),
        )


if __name__ == "__main__":
    unittest.main()
