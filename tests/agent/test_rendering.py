"""Chart-on-demand rendering: figure builders + dispatcher gate."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from briarwood.agent.dispatch import handle_visualize
from briarwood.agent import rendering as rendering_mod
from briarwood.agent.rendering import ChartUnavailable, render_chart
from briarwood.agent.router import AnswerType, RouterDecision, classify
from briarwood.agent.session import Session


_UNIFIED = {
    "decision_stance": "buy_if_price_improves",
    "primary_value_source": "current_value",
    "trust_flags": ["weak_town_context"],
    "value_position": {
        "fair_value_base": 1_379_080,
        "ask_price": 1_524_000,
        "premium_discount_pct": 0.08,
        "value_low": 1_250_000,
        "value_high": 1_500_000,
    },
}


class RenderChartTests(unittest.TestCase):
    def setUp(self) -> None:
        if rendering_mod.go is None:
            self.skipTest("plotly is not installed")

    def test_value_opportunity_writes_html(self) -> None:
        with TemporaryDirectory() as tmp, patch(
            "briarwood.agent.rendering.ARTIFACTS_ROOT", Path(tmp)
        ):
            path = render_chart("value_opportunity", _UNIFIED, session_id="t")
            self.assertTrue(path.exists())
            self.assertTrue(path.name.endswith(".html"))
            body = path.read_text()
            self.assertIn("Ask $1,524,000", body)
            self.assertIn("Fair $1,379,080", body)

    def test_verdict_gauge_writes_html(self) -> None:
        with TemporaryDirectory() as tmp, patch(
            "briarwood.agent.rendering.ARTIFACTS_ROOT", Path(tmp)
        ):
            path = render_chart("verdict_gauge", _UNIFIED, session_id="t")
            self.assertTrue(path.exists())
            body = path.read_text()
            # Stance label (verdict) + premium datapoint must both render —
            # "file exists" is too weak; an empty figure would pass that.
            self.assertIn("buy_if_price_improves", body)
            self.assertIn('"value":8', body)  # premium_discount_pct 0.08 -> 8%

    def test_unknown_kind_raises(self) -> None:
        with self.assertRaises(ChartUnavailable):
            render_chart("bogus_kind", _UNIFIED)

    def test_missing_premium_raises(self) -> None:
        with self.assertRaises(ChartUnavailable):
            render_chart("verdict_gauge", {"value_position": {}})

    def test_rent_burn_writes_html(self) -> None:
        payload = {
            "series": [
                {"year": 0, "rent_base": 3600, "rent_bull": 3800, "rent_bear": 3400, "monthly_obligation": 4100},
                {"year": 1, "rent_base": 3708, "rent_bull": 3990, "rent_bear": 3434, "monthly_obligation": 4100},
            ],
            "title": "Rent burn chart",
        }
        with TemporaryDirectory() as tmp, patch(
            "briarwood.agent.rendering.ARTIFACTS_ROOT", Path(tmp)
        ):
            path = render_chart("rent_burn", payload, session_id="t")
            self.assertTrue(path.exists())
            body = path.read_text()
            self.assertIn("Rent burn chart", body)
            self.assertIn("Monthly obligation", body)


class _VisualizeLLM:
    """Scripted LLM that always returns VISUALIZE — simulates the LLM seeing
    a chart-command phrase and routing correctly (post-plan C2 the router no
    longer caches visualize keywords)."""

    def complete(self, *, system, user, max_tokens=400):  # pragma: no cover
        raise AssertionError("router should use complete_structured")

    def complete_structured(self, *, system, user, schema, model=None, max_tokens=600):
        return schema(answer_type=AnswerType.VISUALIZE, reason="scripted-visualize")


class VisualizeRouterTests(unittest.TestCase):
    def test_show_value_picture_routes_to_visualize(self) -> None:
        decision = classify("show me the value picture on 526-west-end-ave", client=_VisualizeLLM())
        self.assertEqual(decision.answer_type, AnswerType.VISUALIZE)
        self.assertIn("526-west-end-ave", decision.target_refs)

    def test_chart_keyword_routes_to_visualize(self) -> None:
        decision = classify("can you chart the verdict gauge for 526-west-end-ave", client=_VisualizeLLM())
        self.assertEqual(decision.answer_type, AnswerType.VISUALIZE)

    def test_lookup_shape_does_not_route_to_visualize(self) -> None:
        decision = classify("what's the address of 526-west-end-ave")
        self.assertEqual(decision.answer_type, AnswerType.LOOKUP)


class VisualizeHandlerTests(unittest.TestCase):
    def test_handler_builds_chart_and_returns_file_url(self) -> None:
        decision = RouterDecision(
            AnswerType.VISUALIZE, confidence=0.9, target_refs=["any-saved-id"]
        )
        with patch("briarwood.agent.dispatch.render_chart") as mock_render, patch(
            "briarwood.agent.dispatch._SAVED_DIR_EXISTS", return_value=True
        ), patch(
            "briarwood.agent.dispatch.saved_property_has_valid_location", return_value=True
        ):
            mock_render.return_value = {
                "property_id": "any-saved-id",
                "kind": "value_opportunity",
                "path": "/tmp/out.html",
                "format": "html",
            }
            out = handle_visualize(
                "show me the value picture", decision, Session(), llm=None
            )
        mock_render.assert_called_once()
        args, kwargs = mock_render.call_args
        self.assertEqual(args[0], "value_opportunity")
        self.assertEqual(args[1], "any-saved-id")
        self.assertIn("file:///tmp/out.html", out)

    def test_handler_returns_prompt_when_no_property(self) -> None:
        decision = RouterDecision(AnswerType.VISUALIZE, confidence=0.9, target_refs=[])
        out = handle_visualize("show me the chart", decision, Session(), llm=None)
        self.assertIn("Which property", out)


if __name__ == "__main__":
    unittest.main()
