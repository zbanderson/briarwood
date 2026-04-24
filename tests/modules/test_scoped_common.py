"""Unit tests for the scoped-wrapper error-contract helpers.

These cover the two canonical entry points that every scoped wrapper uses
on failure: ``module_payload_from_error`` (caught internal exceptions) and
``module_payload_from_missing_prior`` (composite wrappers whose required
prior outputs are absent or degraded). See the 2026-04-24 "Scoped wrapper
error contract" entry in DECISIONS.md.
"""

from __future__ import annotations

import unittest

from briarwood.execution.context import ExecutionContext
from briarwood.modules.scoped_common import (
    module_payload_from_error,
    module_payload_from_missing_prior,
)


class ModulePayloadFromErrorTests(unittest.TestCase):
    def test_fallback_mode_and_default_confidence(self) -> None:
        payload = module_payload_from_error(
            module_name="carry_cost",
            summary="Carry cost is provisional because core inputs are incomplete.",
            warnings=["Carry-cost fallback: KeyError: 'purchase_price'"],
        )

        self.assertEqual(payload.mode, "fallback")
        self.assertAlmostEqual(payload.confidence or 0.0, 0.08)
        self.assertEqual(payload.module_name, "carry_cost")
        self.assertEqual(payload.data["metrics"], {})
        self.assertIn("Carry-cost fallback", payload.warnings[0])

    def test_extra_data_merges_into_data(self) -> None:
        payload = module_payload_from_error(
            module_name="arv_model",
            summary="test",
            extra_data={"arv_snapshot": {}},
        )
        self.assertEqual(payload.data["arv_snapshot"], {})
        self.assertEqual(payload.data["metrics"], {})


class ModulePayloadFromMissingPriorTests(unittest.TestCase):
    def test_error_mode_and_null_confidence(self) -> None:
        payload = module_payload_from_missing_prior(
            module_name="arv_model",
            missing=["valuation", "renovation_impact"],
        )

        self.assertEqual(payload.mode, "error")
        self.assertIsNone(payload.confidence)
        self.assertEqual(payload.module_name, "arv_model")
        self.assertEqual(payload.missing_inputs, ["valuation", "renovation_impact"])
        self.assertEqual(payload.data["metrics"], {})
        self.assertEqual(payload.confidence_band, "Speculative")

    def test_warnings_use_canonical_prefix(self) -> None:
        payload = module_payload_from_missing_prior(
            module_name="margin_sensitivity",
            missing=["arv_model", "renovation_impact", "carry_cost"],
        )
        self.assertEqual(
            payload.warnings,
            [
                "Missing prior module output: arv_model",
                "Missing prior module output: renovation_impact",
                "Missing prior module output: carry_cost",
            ],
        )

    def test_auto_summary_names_the_missing_priors(self) -> None:
        payload = module_payload_from_missing_prior(
            module_name="hold_to_rent",
            missing=["rent_stabilization"],
        )
        self.assertIn("hold_to_rent", payload.data["summary"])
        self.assertIn("rent_stabilization", payload.data["summary"])

    def test_custom_summary_overrides_auto(self) -> None:
        payload = module_payload_from_missing_prior(
            module_name="arv_model",
            missing=["valuation"],
            summary="ARV snapshot unavailable.",
        )
        self.assertEqual(payload.data["summary"], "ARV snapshot unavailable.")

    def test_extra_data_and_assumptions_are_preserved(self) -> None:
        payload = module_payload_from_missing_prior(
            module_name="arv_model",
            missing=["valuation", "renovation_impact"],
            extra_data={"arv_snapshot": {}},
            assumptions_used={"composite_from_prior_outputs": True},
        )
        self.assertEqual(payload.data["arv_snapshot"], {})
        self.assertTrue(payload.assumptions_used["composite_from_prior_outputs"])
        self.assertEqual(
            payload.assumptions_used["required_prior_modules"],
            ["valuation", "renovation_impact"],
        )

    def test_accepts_execution_context(self) -> None:
        """The helper tolerates an ExecutionContext argument even if it doesn't need it today."""
        ctx = ExecutionContext(property_id="test")
        payload = module_payload_from_missing_prior(
            module_name="arv_model",
            context=ctx,
            missing=["valuation"],
        )
        self.assertEqual(payload.mode, "error")


if __name__ == "__main__":
    unittest.main()
