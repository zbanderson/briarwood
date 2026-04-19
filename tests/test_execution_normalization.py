from __future__ import annotations

import unittest

from briarwood.execution.normalization import normalize_execution_inputs
from briarwood.modules.scoped_common import build_property_input_from_context
from briarwood.execution.context import ExecutionContext


class ExecutionNormalizationTests(unittest.TestCase):
    def test_normalizer_keeps_ask_price_out_of_canonical_facts(self) -> None:
        normalized = normalize_execution_inputs(
            property_data={
                "property_id": "pid-1",
                "facts": {
                    "address": "1008 14th Ave",
                    "town": "Belmar",
                    "state": "NJ",
                    "beds": 3,
                    "baths": 1.0,
                    "sqft": 960,
                    "purchase_price": 767000.0,
                },
            },
            property_summary={"ask_price": 767000.0},
            assumptions={},
        )
        self.assertNotIn("ask_price", normalized.property_data["facts"])
        self.assertEqual(normalized.property_data.get("ask_price"), 767000.0)

    def test_property_input_builds_from_normalized_context(self) -> None:
        normalized = normalize_execution_inputs(
            property_data={
                "property_id": "pid-1",
                "facts": {
                    "address": "1008 14th Ave",
                    "town": "Belmar",
                    "state": "NJ",
                    "beds": 3,
                    "baths": 1.0,
                    "sqft": 960,
                    "purchase_price": 767000.0,
                },
            },
            property_summary={"ask_price": 767000.0},
            assumptions={},
        )
        context = ExecutionContext(
            property_id="pid-1",
            property_data=normalized.property_data,
            assumptions=normalized.assumptions,
            field_provenance=normalized.field_provenance,
            missing_data_registry=normalized.missing_data_registry,
            normalized_context=normalized.model_dump(),
        )
        property_input = build_property_input_from_context(context)
        self.assertEqual(property_input.purchase_price, 767000.0)
        self.assertEqual(property_input.address, "1008 14th Ave")


if __name__ == "__main__":
    unittest.main()
