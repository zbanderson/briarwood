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


if __name__ == "__main__":
    unittest.main()
