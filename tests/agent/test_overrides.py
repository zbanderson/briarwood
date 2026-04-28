"""What-if override parser — trigger discrimination + dollar normalization."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile

from briarwood.agent.overrides import (
    inputs_with_overrides,
    parse_overrides,
    summarize,
)


class TriggerDiscriminationTests(unittest.TestCase):
    """The trigger must NOT fire on incidental digits (bed counts, street #)."""

    def test_street_number_alone_is_not_a_price(self) -> None:
        self.assertEqual(parse_overrides("tell me about 526"), {})
        self.assertEqual(parse_overrides("for 526"), {})

    def test_bed_count_is_not_a_price(self) -> None:
        self.assertEqual(parse_overrides("show me 4-bed homes"), {})
        self.assertEqual(parse_overrides("Search for 4-bed homes"), {})
        self.assertEqual(parse_overrides("at 3 bedrooms"), {})

    def test_chart_command_does_not_trigger(self) -> None:
        self.assertEqual(
            parse_overrides("can you chart the verdict gauge for 526-west-end-ave"),
            {},
        )


class PricePhrasingTests(unittest.TestCase):
    """Real what-if phrasing must produce an ask_price override."""

    def test_unit_suffix_m(self) -> None:
        self.assertEqual(parse_overrides("paid 1.3m"), {"ask_price": 1_300_000.0})

    def test_unit_word_million(self) -> None:
        self.assertEqual(
            parse_overrides("bought it for 1.35 million"),
            {"ask_price": 1_350_000.0},
        )

    def test_dollar_sign_with_commas(self) -> None:
        self.assertEqual(
            parse_overrides("at $1,300,000"), {"ask_price": 1_300_000.0}
        )

    def test_what_if_bought_at_m(self) -> None:
        self.assertEqual(
            parse_overrides("what if I bought at 1.3M"),
            {"ask_price": 1_300_000.0},
        )

    def test_renovate_mode_with_price(self) -> None:
        result = parse_overrides("renovate and price it at $1.35m")
        self.assertEqual(result["ask_price"], 1_350_000.0)
        self.assertEqual(result["mode"], "renovated")

    def test_bare_renovation_sets_mode_but_no_other_overrides(self) -> None:
        """parse_overrides sets mode=renovated whenever _RENO_RE matches —
        kept unchanged so downstream consumers (`inputs_with_overrides`)
        still receive the renovation hint when the user asks about
        scenarios. The router's what-if-price-override short-circuit was
        tightened separately (Round 2 Cycle 2, 2026-04-28) to require a
        material override (`ask_price` or `repair_capex_budget`) — see
        tests/agent/test_router.py
        ::PrecedenceTests::test_bare_renovation_does_not_trigger_what_if_override."""
        self.assertEqual(
            parse_overrides("Run renovation scenarios"),
            {"mode": "renovated"},
        )

    def test_capex_budget_implies_renovation_override(self) -> None:
        result = parse_overrides("what if we invested 100k into it")
        self.assertEqual(
            result,
            {"repair_capex_budget": 100_000.0, "mode": "renovated"},
        )

    def test_percentage_price_cut_uses_reference_price(self) -> None:
        self.assertEqual(
            parse_overrides("What would a 10% price cut do?", reference_price=767000.0),
            {"ask_price": 690300.0, "price_cut_pct": 0.10},
        )


class InputsWithOverridesTests(unittest.TestCase):
    def test_passthrough_when_empty(self) -> None:
        with NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write('{"facts": {"purchase_price": 1_000_000}}')
            original = Path(f.name)
        try:
            with inputs_with_overrides(original, {}) as path:
                self.assertEqual(path, original)
        finally:
            original.unlink(missing_ok=True)

    def test_writes_ask_price_and_renovation_into_tmp_copy(self) -> None:
        with NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"facts": {"purchase_price": 1_000_000}}, f)
            original = Path(f.name)
        try:
            with inputs_with_overrides(
                original, {"ask_price": 1_300_000.0, "mode": "renovated"}
            ) as path:
                self.assertNotEqual(path, original)
                data = json.loads(path.read_text())
                self.assertEqual(data["facts"]["purchase_price"], 1_300_000.0)
                self.assertEqual(data["facts"]["renovation_mode"], "will_renovate")
            # Tmp file cleaned up after the with block.
            self.assertFalse(path.exists())
        finally:
            original.unlink(missing_ok=True)

    def test_writes_capex_budget_into_user_assumptions(self) -> None:
        with NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"facts": {"purchase_price": 1_000_000}, "user_assumptions": {}}, f)
            original = Path(f.name)
        try:
            with inputs_with_overrides(
                original, {"repair_capex_budget": 100_000.0, "mode": "renovated"}
            ) as path:
                data = json.loads(path.read_text())
                self.assertEqual(data["user_assumptions"]["repair_capex_budget"], 100_000.0)
                self.assertTrue(data["user_assumptions"]["capex_confirmed"])
                self.assertEqual(data["facts"]["renovation_mode"], "will_renovate")
                self.assertEqual(data["user_assumptions"]["condition_profile_override"], "renovated")
                self.assertTrue(data["user_assumptions"]["condition_confirmed"])
                self.assertEqual(
                    data["renovation_scenario"],
                    {
                        "enabled": True,
                        "renovation_budget": 100_000.0,
                        "target_condition": "renovated",
                    },
                )
        finally:
            original.unlink(missing_ok=True)

    def test_merges_manual_comp_inputs_with_existing_assumptions(self) -> None:
        with NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "facts": {"purchase_price": 1_000_000},
                    "user_assumptions": {
                        "manual_comp_inputs": [
                            {
                                "address": "10 A St",
                                "sale_date": "2025-01-01",
                                "source_ref": "saved-10-a",
                                "sale_price": 700000,
                            }
                        ]
                    },
                },
                f,
            )
            original = Path(f.name)
        try:
            with inputs_with_overrides(
                original,
                {
                    "manual_comp_inputs": [
                        {
                            "address": "12 A St",
                            "sale_date": "2025-02-01",
                            "source_ref": "user-12-a",
                            "sale_price": 720000,
                        }
                    ]
                },
            ) as path:
                data = json.loads(path.read_text())
                manual_comps = data["user_assumptions"]["manual_comp_inputs"]
                self.assertEqual(len(manual_comps), 2)
                self.assertEqual(manual_comps[0]["address"], "10 A St")
                self.assertEqual(manual_comps[1]["address"], "12 A St")
        finally:
            original.unlink(missing_ok=True)


class SummarizeTests(unittest.TestCase):
    def test_empty_overrides_empty_string(self) -> None:
        self.assertEqual(summarize({}), "")

    def test_price_only(self) -> None:
        self.assertEqual(
            summarize({"ask_price": 1_300_000}),
            "overrides applied: entry basis $1,300,000",
        )

    def test_price_plus_mode(self) -> None:
        self.assertEqual(
            summarize({"ask_price": 1_500_000, "mode": "renovated"}),
            "overrides applied: entry basis $1,500,000, full renovation",
        )

    def test_capex_budget_summary(self) -> None:
        self.assertEqual(
            summarize({"repair_capex_budget": 100_000, "mode": "renovated"}),
            "overrides applied: full renovation, renovation budget $100,000",
        )


if __name__ == "__main__":
    unittest.main()
