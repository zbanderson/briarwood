from __future__ import annotations

import unittest

from briarwood.agent.llm_observability import get_llm_ledger
from briarwood.agent.presentation_advisor import (
    SectionAdvice,
    VisualAdvice,
    advise_visual_surfaces,
    compose_browse_surface,
    compose_section_followup,
)


class _ScriptedStructuredLLM:
    """Fake client for the AUDIT 1.2.2 structured path. Returns a pre-baked
    `VisualAdvice` instance to the advisor."""

    def __init__(self, advice: VisualAdvice | None) -> None:
        self._advice = advice
        self.calls: list[str] = []

    def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
        raise AssertionError("advise_visual_surfaces must go through complete_structured")

    def complete_structured(self, *, system, user, schema, model=None, max_tokens=600):
        self.calls.append(user)
        return self._advice


class PresentationAdvisorTests(unittest.TestCase):
    def test_advise_visual_surfaces_returns_bounded_sections(self) -> None:
        """The advisor should flatten a Pydantic `VisualAdvice` into the
        `{section: {field: str}}` shape callers expect."""
        advice = VisualAdvice(
            value=SectionAdvice(
                title="Ask vs fair value",
                summary="The ask is running ahead of the current fair value read.",
                companion="Pair this with the comp set.",
                preferred_surface="chart_first",
            )
        )
        llm = _ScriptedStructuredLLM(advice)
        out = advise_visual_surfaces(llm=llm, payload={"anything": 1})
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["value"]["title"], "Ask vs fair value")
        self.assertEqual(out["value"]["preferred_surface"], "chart_first")
        # Sections the advisor skipped must not appear.
        self.assertNotIn("cma", out)

    def test_advise_visual_surfaces_returns_none_on_validation_failure(self) -> None:
        """Strict-mode failure surfaces as `None` from complete_structured;
        the advisor propagates that so callers can skip visual advice."""
        llm = _ScriptedStructuredLLM(advice=None)
        out = advise_visual_surfaces(llm=llm, payload={"anything": 1})
        self.assertIsNone(out)

    def test_advise_visual_surfaces_drops_empty_sections(self) -> None:
        """A section with only whitespace fields shouldn't reach callers."""
        advice = VisualAdvice(value=SectionAdvice(title="   ", summary=""))
        llm = _ScriptedStructuredLLM(advice)
        out = advise_visual_surfaces(llm=llm, payload={"anything": 1})
        self.assertIsNone(out)

    def test_advise_visual_surfaces_records_call_in_ledger(self) -> None:
        """Routing through `complete_structured_observed` must surface the call
        in the shared LLM ledger so it appears in the per-turn manifest."""
        ledger = get_llm_ledger()
        ledger.clear()
        advice = VisualAdvice(value=SectionAdvice(title="Ask vs fair value"))
        llm = _ScriptedStructuredLLM(advice)
        out = advise_visual_surfaces(llm=llm, payload={"anything": 1})
        self.assertIsNotNone(out)
        surfaces = [record.surface for record in ledger.records]
        self.assertIn("presentation_advisor.advise", surfaces)

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
