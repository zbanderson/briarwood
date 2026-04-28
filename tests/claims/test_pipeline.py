"""Tests for ``briarwood.claims.pipeline.build_claim_for_property``.

Covers the gap the golden test missed: the orchestrator's
``module_results.outputs`` does not include a ``comparable_sales`` entry at
runtime (scoped registry surfaces it only as an internal dependency of
``valuation``), so the claim pipeline has to graft one on before calling the
synthesizer. Without that graft, every production call produces zero
scenarios.

Phase 4a Cycle 6: the graft now goes through the canonical scoped runner
``run_comparable_sales`` instead of instantiating ``ComparableSalesModule``
directly. These tests pin the scoped-runner contract and the graft's
adapter behavior.
"""
from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from briarwood.claims.pipeline import _inject_comparable_sales
from briarwood.schemas import PropertyInput
from tests.claims.fixtures.belmar_house import comparable_sales_output


def _property_stub() -> PropertyInput:
    return PropertyInput(
        property_id="stub",
        address="fake",
        town="Belmar",
        state="NJ",
        beds=3,
        baths=2.0,
        sqft=1800,
    )


def _scoped_payload(
    *,
    legacy_payload: dict[str, Any] | None,
    metrics: dict[str, Any] | None = None,
    summary: str = "canned",
) -> dict[str, Any]:
    """Shape returned by ``run_comparable_sales`` (``ModulePayload.model_dump()``)."""
    data: dict[str, Any] = {
        "module_name": "comparable_sales",
        "summary": summary,
        "metrics": dict(metrics or {}),
    }
    if legacy_payload is not None:
        data["legacy_payload"] = legacy_payload
    return {
        "data": data,
        "module_name": "comparable_sales",
        "summary": summary,
    }


class InjectComparableSalesTests(unittest.TestCase):
    def test_grafts_comparable_sales_when_absent(self) -> None:
        module_results: dict[str, Any] = {"outputs": {"valuation": {"data": {}}}}
        fixture = comparable_sales_output()
        scoped = _scoped_payload(
            legacy_payload=fixture.model_dump(),
            metrics={"comp_count": 3},
        )

        with patch(
            "briarwood.claims.pipeline.run_comparable_sales",
            return_value=scoped,
        ):
            _inject_comparable_sales(module_results, _property_stub())

        outputs = module_results["outputs"]
        self.assertIn("comparable_sales", outputs)
        entry = outputs["comparable_sales"]
        # Payload is rebuilt via model_validate — equal-by-value, not by identity.
        self.assertEqual(entry["payload"].comp_count, fixture.comp_count)
        self.assertEqual(
            [c.address for c in entry["payload"].comps_used],
            [c.address for c in fixture.comps_used],
        )
        self.assertEqual(entry["metrics"], {"comp_count": 3})
        self.assertEqual(entry["module_name"], "comparable_sales")

    def test_leaves_existing_comparable_sales_untouched(self) -> None:
        sentinel = {"payload": "already-there"}
        module_results: dict[str, Any] = {
            "outputs": {"comparable_sales": sentinel}
        }

        with patch(
            "briarwood.claims.pipeline.run_comparable_sales",
        ) as runner:
            _inject_comparable_sales(module_results, _property_stub())
            runner.assert_not_called()

        self.assertIs(module_results["outputs"]["comparable_sales"], sentinel)

    def test_skips_when_scoped_returns_fallback(self) -> None:
        """Scoped fallback omits ``legacy_payload`` — nothing to graft."""
        module_results: dict[str, Any] = {"outputs": {}}
        scoped = _scoped_payload(legacy_payload=None, summary="fallback")

        with patch(
            "briarwood.claims.pipeline.run_comparable_sales",
            return_value=scoped,
        ):
            _inject_comparable_sales(module_results, _property_stub())

        self.assertNotIn("comparable_sales", module_results["outputs"])


if __name__ == "__main__":
    unittest.main()
