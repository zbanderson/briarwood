"""Tests for ``briarwood.claims.pipeline.build_claim_for_property``.

Covers the gap the golden test missed: the orchestrator's
``module_results.outputs`` does not include a ``comparable_sales`` entry at
runtime (scoped registry doesn't route it), so the claim pipeline has to
graft one on before calling the synthesizer. Without that graft, every
production call produces zero scenarios.
"""
from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from briarwood.claims.pipeline import _inject_comparable_sales
from briarwood.schemas import ModuleResult, PropertyInput
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


class InjectComparableSalesTests(unittest.TestCase):
    def test_grafts_comparable_sales_when_absent(self) -> None:
        module_results: dict[str, Any] = {"outputs": {"valuation": {"data": {}}}}
        canned = ModuleResult(
            module_name="comparable_sales",
            payload=comparable_sales_output(),
            metrics={"comp_count": 3},
            summary="canned",
        )

        with patch(
            "briarwood.claims.pipeline.ComparableSalesModule"
        ) as module_cls:
            module_cls.return_value.run.return_value = canned
            _inject_comparable_sales(module_results, _property_stub())

        outputs = module_results["outputs"]
        self.assertIn("comparable_sales", outputs)
        entry = outputs["comparable_sales"]
        self.assertIs(entry["payload"], canned.payload)
        self.assertEqual(entry["metrics"], {"comp_count": 3})

    def test_leaves_existing_comparable_sales_untouched(self) -> None:
        sentinel = {"payload": "already-there"}
        module_results: dict[str, Any] = {
            "outputs": {"comparable_sales": sentinel}
        }

        with patch(
            "briarwood.claims.pipeline.ComparableSalesModule"
        ) as module_cls:
            _inject_comparable_sales(module_results, _property_stub())
            module_cls.assert_not_called()

        self.assertIs(module_results["outputs"]["comparable_sales"], sentinel)

    def test_swallows_module_exception(self) -> None:
        module_results: dict[str, Any] = {"outputs": {}}
        with patch(
            "briarwood.claims.pipeline.ComparableSalesModule"
        ) as module_cls:
            module_cls.return_value.run.side_effect = RuntimeError("boom")
            _inject_comparable_sales(module_results, _property_stub())

        self.assertNotIn("comparable_sales", module_results["outputs"])


if __name__ == "__main__":
    unittest.main()
