"""Resolver safety — street-number verification.

Zero-hallucination guardrail: when a user types "1223 Briarwood Road in
Belmar", we must not silently resolve to a saved "1232 Briarwood Road"
simply because the street and town tokens line up.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


def _seed(dir_: Path, pid: str, address: str) -> None:
    (dir_ / pid).mkdir(parents=True, exist_ok=True)
    (dir_ / pid / "inputs.json").write_text(
        json.dumps({"property_id": pid, "facts": {"address": address}})
    )


class ResolverStreetNumberSafetyTests(unittest.TestCase):
    def _resolve(self, text: str, seeded: dict[str, str]):
        from briarwood.agent import resolver, tools

        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            for pid, address in seeded.items():
                _seed(base, pid, address)
            with patch.object(tools, "SAVED_PROPERTIES_DIR", base), patch.object(
                resolver, "SAVED_PROPERTIES_DIR", base
            ):
                return resolver.resolve_property_id(text)

    def test_number_mismatch_rejects_wrong_property(self) -> None:
        """1223 Briarwood must not fuzzy-match a saved 1232 Briarwood."""

        pid, ranked = self._resolve(
            "what do you think of 1223 briarwood road in belmar?",
            {"1232-briarwood-road-belmar-nj": "1232 Briarwood Road, Belmar, NJ"},
        )
        self.assertIsNone(pid)
        self.assertEqual(ranked, [])

    def test_number_match_resolves(self) -> None:
        """Same street, matching number → resolves even when the slug has no number."""

        pid, _ = self._resolve(
            "what do you think of 1223 briarwood road in belmar?",
            {"briarwood-rd-belmar": "1223 Briarwood Rd, Belmar, NJ 07719"},
        )
        self.assertEqual(pid, "briarwood-rd-belmar")

    def test_number_match_picks_correct_neighbor(self) -> None:
        """Both 1223 and 1232 saved — resolver picks the one that actually matches."""

        pid, _ = self._resolve(
            "is 1223 briarwood road a buy?",
            {
                "briarwood-rd-belmar": "1223 Briarwood Rd, Belmar, NJ 07719",
                "1232-briarwood-road-belmar-nj": "1232 Briarwood Road, Belmar, NJ",
            },
        )
        self.assertEqual(pid, "briarwood-rd-belmar")

    def test_query_without_number_still_resolves(self) -> None:
        """Backwards compatible: no street number in query → existing behavior."""

        pid, _ = self._resolve(
            "briarwood road belmar",
            {"briarwood-rd-belmar": "1223 Briarwood Rd, Belmar, NJ 07719"},
        )
        self.assertEqual(pid, "briarwood-rd-belmar")

    def test_extract_street_number_pulls_leading_digits(self) -> None:
        from briarwood.agent.resolver import _extract_street_number

        self.assertEqual(_extract_street_number("1223 Briarwood Road"), "1223")
        self.assertEqual(
            _extract_street_number("what do you think of 526 W End Ave?"), "526"
        )
        self.assertIsNone(_extract_street_number("briarwood road belmar"))


if __name__ == "__main__":
    unittest.main()
