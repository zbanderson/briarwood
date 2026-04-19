from __future__ import annotations

import unittest

from briarwood.agent.presentation_advisor import (
    _parse_visual_advice,
    compose_browse_surface,
    compose_section_followup,
)


class PresentationAdvisorTests(unittest.TestCase):
    def test_parse_visual_advice_accepts_bounded_json(self) -> None:
        parsed = _parse_visual_advice(
            """
            {
              "value": {
                "title": "Ask vs fair value",
                "summary": "The ask is running ahead of the current fair value read.",
                "companion": "Pair this with the comp set.",
                "preferred_surface": "chart_first"
              },
              "bogus": {
                "title": "Ignore me"
              }
            }
            """
        )
        assert parsed is not None
        self.assertEqual(parsed["value"]["title"], "Ask vs fair value")
        self.assertNotIn("bogus", parsed)

    def test_compose_browse_surface_falls_back_without_llm(self) -> None:
        text, report = compose_browse_surface(
            llm=None,
            payload={"ask_price": 767000, "fair_value_base": 720644},
            fallback="Quick take: fallback browse summary.",
        )
        self.assertEqual(text, "Quick take: fallback browse summary.")
        self.assertIsNone(report)

    def test_compose_section_followup_falls_back_without_llm(self) -> None:
        text, report = compose_section_followup(
            llm=None,
            section="entry_point",
            question="What's a good entry point?",
            payload={"ask_price": 767000, "fair_value_base": 720644},
            fallback="Closer to fair value, not at ask.",
        )
        self.assertEqual(text, "Closer to fair value, not at ask.")
        self.assertIsNone(report)


if __name__ == "__main__":
    unittest.main()
