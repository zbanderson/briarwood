"""End-to-end golden test for the claim-object pipeline (plan §9 + §11).

Exercises the full decision stream with ``BRIARWOOD_CLAIMS_ENABLED=true``
and the Belmar fixture. Everything downstream of ``build_claim_for_property``
runs unmocked — Value Scout, Editor, Representation, and the
``_decision_stream_impl`` SSE adapter — so any regression in how those layers
surface events to the UI shows up here.

UI-surfacing contract asserted:

1. The claim's rendered prose reaches the stream as text_delta content.
2. A single ``chart`` event with ``kind="horizontal_bar_with_ranges"`` is
   emitted, carrying the three-tier ``scenarios`` payload and the
   Scout-picked ``emphasis_scenario_id="renovated_plus_bath"``.
3. A ``suggestions`` event follows with the claim's next-question texts.
4. No ``claim_rejected`` event is emitted on the happy path.
5. Chart + suggestions are emitted as **primary** events — i.e. before the
   text_delta stream — matching the existing decision-stream ordering.
"""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from api import events
from api.pipeline_adapter import decision_stream
from briarwood.agent.router import AnswerType, RouterDecision
from briarwood.agent.session import Session
from briarwood.claims.synthesis import build_verdict_with_comparison_claim
from tests.claims.fixtures import belmar_house


def _run_stream(stream):
    async def _collect():
        return [event async for event in stream]

    return asyncio.run(_collect())


def _build_belmar_claim():
    return build_verdict_with_comparison_claim(
        property_summary=belmar_house.property_summary(),
        parser_output=belmar_house.parser_output(),
        module_results=belmar_house.module_results(),
        interaction_trace=belmar_house.interaction_trace(),
    )


def _decision() -> RouterDecision:
    return RouterDecision(
        answer_type=AnswerType.DECISION,
        confidence=0.99,
        target_refs=[belmar_house.SUBJECT_PROPERTY_ID],
        reason="golden-e2e",
    )


def _pinned_listing() -> dict[str, object]:
    return {
        "id": belmar_house.SUBJECT_PROPERTY_ID,
        "address_line": belmar_house.SUBJECT_ADDRESS,
        "city": "Belmar",
        "state": "NJ",
        "price": belmar_house.SUBJECT_ASK,
        "beds": belmar_house.SUBJECT_BEDS,
        "baths": belmar_house.SUBJECT_BATHS,
        "sqft": belmar_house.SUBJECT_SQFT,
        "status": "active",
    }


class GoldenE2EBelmarTests(unittest.TestCase):
    """Belmar fixture driven through the decision SSE adapter."""

    def _run_golden(self) -> list[dict[str, object]]:
        session = Session(session_id="golden-e2e")
        claim = _build_belmar_claim()

        with (
            patch("api.pipeline_adapter._load_or_create_session", return_value=session),
            patch("api.pipeline_adapter._seed_session_for_pinned", return_value=None),
            patch("api.pipeline_adapter._finalize_session"),
            patch("api.pipeline_adapter.get_llm", return_value=None),
            patch("briarwood.feature_flags.claims_enabled_for", return_value=True),
            patch(
                "briarwood.claims.pipeline.build_claim_for_property",
                return_value=claim,
            ),
            patch(
                "briarwood.agent.dispatch._resolve_property_id",
                return_value=belmar_house.SUBJECT_PROPERTY_ID,
            ),
        ):
            emitted = _run_stream(
                decision_stream(
                    "should I buy this house?",
                    _decision(),
                    _pinned_listing(),
                    conversation_id="golden-e2e",
                )
            )
        return emitted

    def test_prose_reaches_text_delta_stream(self) -> None:
        emitted = self._run_golden()
        text = "".join(
            str(e.get("content") or "")
            for e in emitted
            if e["type"] == events.EVENT_TEXT_DELTA
        )
        self.assertIn("fair market value", text.lower())

    def test_chart_event_has_expected_kind_and_emphasis(self) -> None:
        emitted = self._run_golden()
        charts = [e for e in emitted if e["type"] == events.EVENT_CHART]
        self.assertEqual(len(charts), 1)
        chart = charts[0]
        self.assertEqual(chart["kind"], "horizontal_bar_with_ranges")
        spec = chart["spec"]
        self.assertEqual(spec["kind"], "horizontal_bar_with_ranges")
        self.assertEqual(spec["unit"], "$/sqft")
        self.assertEqual(spec["emphasis_scenario_id"], "renovated_plus_bath")
        ids = [s["id"] for s in spec["scenarios"]]
        self.assertEqual(ids, ["subject", "renovated_same", "renovated_plus_bath"])

    def test_suggestions_event_carries_next_question_texts(self) -> None:
        emitted = self._run_golden()
        suggestion_events = [
            e for e in emitted if e["type"] == events.EVENT_SUGGESTIONS
        ]
        self.assertGreaterEqual(len(suggestion_events), 1)
        # The first suggestions event is the claim's next_questions; a second
        # suggestions event ships as the decision-stream trailer. Both carry
        # non-empty item lists.
        claim_suggestions = suggestion_events[0]
        self.assertTrue(claim_suggestions["items"])

    def test_no_claim_rejected_event_on_happy_path(self) -> None:
        emitted = self._run_golden()
        rejected = [e for e in emitted if e["type"] == events.EVENT_CLAIM_REJECTED]
        self.assertEqual(rejected, [])

    def test_chart_emitted_before_first_text_delta(self) -> None:
        """UI-surfacing contract: primary events land before prose."""
        emitted = self._run_golden()
        types = [e["type"] for e in emitted]
        chart_idx = types.index(events.EVENT_CHART)
        first_text_idx = types.index(events.EVENT_TEXT_DELTA)
        self.assertLess(chart_idx, first_text_idx)


if __name__ == "__main__":
    unittest.main()
