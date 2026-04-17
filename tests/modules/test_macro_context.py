"""Tests for the macro-context layer that threads FRED into specialty models.

Locks in two invariants:
1. When a property's county+state match the FRED fixture, the macro slice
   populates ``ExecutionContext.macro_context`` with dimensional signals.
2. Specialty modules apply a bounded nudge from macro data — the macro
   signal cannot dominate the module's own output.
"""
from __future__ import annotations

import unittest

from briarwood.execution.macro_context import (
    MacroContextSlice,
    resolve_macro_context,
)
from briarwood.modules.macro_reader import (
    DEFAULT_MAX_NUDGE,
    apply_macro_nudge,
    read_macro,
)
from briarwood.modules.risk_model import MACRO_MAX_NUDGE as RISK_MAX_NUDGE
from briarwood.modules.risk_model import run_risk_model
from briarwood.modules.valuation import MACRO_MAX_NUDGE as VAL_MAX_NUDGE
from briarwood.modules.valuation import run_valuation
from briarwood.modules.resale_scenario_scoped import (
    MACRO_MAX_NUDGE as RESALE_MAX_NUDGE,
)
from briarwood.modules.resale_scenario_scoped import run_resale_scenario
from briarwood.modules.rental_option_scoped import (
    MACRO_MAX_NUDGE as RENTAL_MAX_NUDGE,
)
from briarwood.modules.rental_option_scoped import run_rental_option

from tests.modules._phase2_fixtures import (
    assert_payload_contract,
    context_normal,
)


def _macro_slice(
    *,
    employment: float | None = None,
    hpi: float | None = None,
    liquidity: float | None = None,
    overall: float | None = None,
) -> dict[str, object]:
    return MacroContextSlice(
        county="Monmouth",
        state="NJ",
        as_of="2026-02-13",
        employment_signal=employment,
        hpi_momentum_signal=hpi,
        liquidity_signal=liquidity,
        overall_sentiment=overall,
    ).model_dump()


class MacroContextResolutionTests(unittest.TestCase):
    def test_resolves_monmouth_from_fixture(self) -> None:
        payload = resolve_macro_context(county="Monmouth", state="NJ")
        self.assertIsNotNone(payload)
        slice_ = MacroContextSlice.model_validate(payload)
        self.assertEqual(slice_.county, "Monmouth")
        self.assertEqual(slice_.state, "NJ")
        self.assertIsNotNone(slice_.employment_signal)
        self.assertIsNotNone(slice_.hpi_momentum_signal)
        self.assertIsNotNone(slice_.liquidity_signal)
        self.assertIsNotNone(slice_.overall_sentiment)

    def test_missing_county_returns_none(self) -> None:
        self.assertIsNone(resolve_macro_context(county=None, state="NJ"))
        self.assertIsNone(resolve_macro_context(county="Nowhere", state="NJ"))


class MacroReaderBoundsTests(unittest.TestCase):
    def test_no_macro_returns_base_unchanged(self) -> None:
        context = context_normal()
        result = apply_macro_nudge(
            base_confidence=0.7, context=context, dimension="hpi_momentum"
        )
        self.assertEqual(result.adjusted_confidence, 0.7)
        self.assertEqual(result.applied_nudge, 0.0)

    def test_strong_signal_caps_at_max_nudge(self) -> None:
        context = context_normal(macro_context=_macro_slice(hpi=1.0))
        result = apply_macro_nudge(
            base_confidence=0.5,
            context=context,
            dimension="hpi_momentum",
            max_nudge=0.05,
        )
        self.assertAlmostEqual(result.applied_nudge, 0.05, places=4)
        self.assertAlmostEqual(result.adjusted_confidence, 0.55, places=4)

    def test_weak_signal_caps_at_negative_max_nudge(self) -> None:
        context = context_normal(macro_context=_macro_slice(hpi=0.0))
        result = apply_macro_nudge(
            base_confidence=0.5,
            context=context,
            dimension="hpi_momentum",
            max_nudge=0.05,
        )
        self.assertAlmostEqual(result.applied_nudge, -0.05, places=4)
        self.assertAlmostEqual(result.adjusted_confidence, 0.45, places=4)

    def test_neutral_signal_is_zero_nudge(self) -> None:
        context = context_normal(macro_context=_macro_slice(hpi=0.5))
        result = apply_macro_nudge(
            base_confidence=0.6, context=context, dimension="hpi_momentum"
        )
        self.assertEqual(result.applied_nudge, 0.0)
        self.assertEqual(result.adjusted_confidence, 0.6)

    def test_read_macro_returns_typed_slice(self) -> None:
        context = context_normal(macro_context=_macro_slice(overall=0.7))
        slice_ = read_macro(context)
        self.assertIsInstance(slice_, MacroContextSlice)
        self.assertEqual(slice_.overall_sentiment, 0.7)


class MacroWiringBoundedInModulesTests(unittest.TestCase):
    """For each wired module, flipping macro from strongest to weakest
    moves confidence by at most 2 * max_nudge — macro can never dominate."""

    def _confidence_delta(self, run, dimension_key: str, module_max_nudge: float) -> float:
        bull = run(
            context_normal(macro_context=_macro_slice(**{dimension_key: 1.0}))
        )["confidence"]
        bear = run(
            context_normal(macro_context=_macro_slice(**{dimension_key: 0.0}))
        )["confidence"]
        self.assertIsNotNone(bull)
        self.assertIsNotNone(bear)
        return abs(float(bull) - float(bear))

    def test_risk_model_macro_bounded(self) -> None:
        delta = self._confidence_delta(run_risk_model, "liquidity", RISK_MAX_NUDGE)
        self.assertLessEqual(delta, 2 * RISK_MAX_NUDGE + 1e-6)
        self.assertGreater(delta, 0.0)

    def test_valuation_macro_bounded(self) -> None:
        delta = self._confidence_delta(run_valuation, "hpi", VAL_MAX_NUDGE)
        self.assertLessEqual(delta, 2 * VAL_MAX_NUDGE + 1e-6)
        self.assertGreater(delta, 0.0)

    def test_resale_scenario_macro_bounded(self) -> None:
        delta = self._confidence_delta(run_resale_scenario, "hpi", RESALE_MAX_NUDGE)
        self.assertLessEqual(delta, 2 * RESALE_MAX_NUDGE + 1e-6)
        self.assertGreater(delta, 0.0)

    def test_rental_option_macro_bounded(self) -> None:
        delta = self._confidence_delta(
            run_rental_option, "employment", RENTAL_MAX_NUDGE
        )
        self.assertLessEqual(delta, 2 * RENTAL_MAX_NUDGE + 1e-6)
        self.assertGreater(delta, 0.0)


class MacroWiringEmitsMetaTests(unittest.TestCase):
    def test_risk_model_emits_macro_nudge_meta(self) -> None:
        context = context_normal(macro_context=_macro_slice(liquidity=0.8))
        payload = assert_payload_contract(run_risk_model(context))
        meta = payload.data.get("macro_nudge")
        self.assertIsNotNone(meta)
        self.assertEqual(meta.get("dimension"), "liquidity")
        self.assertEqual(meta.get("macro_county"), "Monmouth")
        self.assertTrue(payload.assumptions_used.get("macro_context_used"))

    def test_valuation_emits_macro_nudge_meta_when_absent(self) -> None:
        payload = assert_payload_contract(run_valuation(context_normal()))
        meta = payload.data.get("macro_nudge")
        self.assertIsNotNone(meta)
        self.assertIsNone(meta.get("signal"))
        self.assertEqual(meta.get("applied_nudge"), 0.0)
        self.assertFalse(payload.assumptions_used.get("macro_context_used"))


if __name__ == "__main__":
    unittest.main()
