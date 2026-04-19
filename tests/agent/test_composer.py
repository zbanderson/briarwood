"""Composer strict-regen flow — BRIARWOOD_STRICT_REGEN flag behavior.

Step 7 ships the flag-gated strip + single-retry pipeline in composer.py. The
advisory path is already covered by test_guardrails.py; these tests focus on
the strip/regen orchestration.

AUDIT 1.1.10: default is now **on** — unset env → strict mode. An explicit
`BRIARWOOD_STRICT_REGEN=0` (or `false`/`off`) reverts to the advisory path.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from briarwood.agent import composer


def _mock_llm(responses: list[str]) -> MagicMock:
    """Return a MagicMock LLMClient whose `complete` call yields successive
    replies from the list. If the test over-calls, the last reply repeats."""
    llm = MagicMock()
    it = iter(responses)
    last = {"v": responses[-1] if responses else ""}

    def _complete(**_kwargs: object) -> str:
        try:
            nxt = next(it)
        except StopIteration:
            return last["v"]
        last["v"] = nxt
        return nxt

    llm.complete.side_effect = _complete
    return llm


class StrictRegenFlagOffTests(unittest.TestCase):
    """Explicit opt-out path (AUDIT 1.1.10): with `BRIARWOOD_STRICT_REGEN=0`
    the verifier runs in advisory mode — report is emitted, text unchanged
    aside from marker stripping."""

    def test_dirty_draft_passes_through_when_flag_explicit_off(self) -> None:
        llm = _mock_llm(["Fair value $820,000. Upside is $700,000."])
        with patch.dict("os.environ", {composer.STRICT_REGEN_FLAG: "0"}):
            text, report = composer.complete_and_verify(
                llm=llm,
                system="sys",
                user="u",
                structured_inputs={"fair_value_base": 820000},
                tier="decision_summary",
            )
        self.assertIn("$700,000", text)
        self.assertNotIn("strict_regen", report)
        self.assertGreaterEqual(report["sentences_with_violations"], 1)
        self.assertEqual(llm.complete.call_count, 1)

    def test_explicit_false_also_disables(self) -> None:
        """Accept `false` / `off` as opt-out synonyms in addition to `0`."""
        for val in ("false", "off", "no", "FALSE"):
            llm = _mock_llm(["Fair value $820,000. Upside is $700,000."])
            with patch.dict("os.environ", {composer.STRICT_REGEN_FLAG: val}):
                _, report = composer.complete_and_verify(
                    llm=llm,
                    system="sys",
                    user="u",
                    structured_inputs={"fair_value_base": 820000},
                    tier="decision_summary",
                )
            self.assertNotIn("strict_regen", report, f"{val!r} should disable")


class StrictRegenDefaultOnTests(unittest.TestCase):
    """AUDIT 1.1.10: unset env must behave like the flag is on. Prior to the
    audit, default was off and the verifier accumulated violation telemetry
    without suppressing bad output. Regression-guard here pins default-on."""

    def test_unset_env_triggers_strict_strip(self) -> None:
        llm = _mock_llm(["Fair value $820,000. Upside is $700,000."])
        with patch.dict("os.environ", {}, clear=True):
            text, report = composer.complete_and_verify(
                llm=llm,
                system="sys",
                user="u",
                structured_inputs={"fair_value_base": 820000},
                tier="decision_summary",
            )
        # $820,000 grounded → kept. $700,000 ungrounded → stripped.
        self.assertIn("$820,000", text)
        self.assertNotIn("$700,000", text)
        strict = report["strict_regen"]
        self.assertTrue(strict["enabled"])
        self.assertEqual(strict["sentences_stripped"], 1)


class StrictRegenFlagOnTests(unittest.TestCase):
    """Flag-on behavior: strip below threshold, strip + regen at/above."""

    def test_below_threshold_strips_without_regen(self) -> None:
        # One ungrounded sentence — under STRICT_REGEN_THRESHOLD (2).
        llm = _mock_llm(["Fair value $820,000. Upside is $700,000."])
        with patch.dict("os.environ", {composer.STRICT_REGEN_FLAG: "1"}):
            text, report = composer.complete_and_verify(
                llm=llm,
                system="sys",
                user="u",
                structured_inputs={"fair_value_base": 820000},
                tier="decision_summary",
            )
        self.assertIn("$820,000", text)
        self.assertNotIn("$700,000", text)
        strict = report["strict_regen"]
        self.assertTrue(strict["enabled"])
        self.assertEqual(strict["sentences_stripped"], 1)
        self.assertFalse(strict["regen_attempted"])
        self.assertEqual(llm.complete.call_count, 1)

    def test_at_threshold_triggers_regen_and_keeps_cleaner_result(self) -> None:
        dirty = (
            "Fair value $820,000. Upside is $700,000. Stress is $123,456. "
            "Bull is $999,999."
        )
        clean = "Fair value $820,000 — on the money."
        llm = _mock_llm([dirty, clean])
        with patch.dict("os.environ", {composer.STRICT_REGEN_FLAG: "1"}):
            text, report = composer.complete_and_verify(
                llm=llm,
                system="sys",
                user="u",
                structured_inputs={"fair_value_base": 820000},
                tier="decision_summary",
            )
        self.assertEqual(llm.complete.call_count, 2)
        self.assertIn("Fair value $820,000", text)
        self.assertNotIn("$700,000", text)
        self.assertNotIn("$999,999", text)
        strict = report["strict_regen"]
        self.assertTrue(strict["regen_attempted"])
        # Regen was clean — final report reflects the regen pass.
        self.assertEqual(report["sentences_with_violations"], 0)

    def test_regen_worse_than_original_keeps_original(self) -> None:
        # Original has 3 bad; regen has 4. Should keep original (stripped).
        original = "A $111. B $222. C $333."
        worse = "D $444. E $555. F $666. G $777."
        llm = _mock_llm([original, worse])
        with patch.dict("os.environ", {composer.STRICT_REGEN_FLAG: "1"}):
            text, report = composer.complete_and_verify(
                llm=llm,
                system="sys",
                user="u",
                structured_inputs={},
                tier="lookup",
            )
        self.assertEqual(llm.complete.call_count, 2)
        # After stripping all 3 bad sentences the draft would be empty, so
        # we preserve the original (flawed) draft — the fallback rule.
        self.assertIn("$111", text)
        # Regen content must NOT leak in.
        self.assertNotIn("$444", text)
        self.assertNotIn("$777", text)
        strict = report["strict_regen"]
        self.assertTrue(strict["regen_attempted"])
        # Report tracks the *kept* draft (original), so it still has 3 bad.
        self.assertEqual(report["sentences_with_violations"], 3)

    def test_empty_structured_inputs_skips_verifier(self) -> None:
        llm = _mock_llm(["Anything goes $12345."])
        with patch.dict("os.environ", {composer.STRICT_REGEN_FLAG: "1"}):
            text, report = composer.compose_structured_response(
                llm=llm,
                system="sys",
                user="u",
                fallback=lambda: "fallback",
                structured_inputs=None,
                tier=None,
            )
        self.assertIsNone(report)
        self.assertIn("$12345", text)


class StripEdgeCaseTests(unittest.TestCase):
    def test_fallback_used_when_llm_returns_empty(self) -> None:
        llm = _mock_llm([""])
        with patch.dict("os.environ", {composer.STRICT_REGEN_FLAG: "1"}):
            text, report = composer.compose_structured_response(
                llm=llm,
                system="sys",
                user="u",
                fallback=lambda: "fallback-text",
                structured_inputs={"ask_price": 820000},
                tier="lookup",
            )
        self.assertEqual(text, "fallback-text")
        self.assertIsNotNone(report)


class BudgetExceededPropagationTests(unittest.TestCase):
    """AUDIT 1.2.3: budget-exhausted fallbacks must surface a structured
    signal on the verifier report so dispatch/UI can tell the user *why*
    they're seeing deterministic prose instead of the composed narrative."""

    def test_flag_surfaces_on_report_when_structured_inputs_present(self) -> None:
        from briarwood.cost_guard import BudgetExceeded

        llm = MagicMock()
        llm.complete.side_effect = BudgetExceeded("cap")
        with patch.dict("os.environ", {}, clear=True):
            text, report = composer.compose_structured_response(
                llm=llm,
                system="sys",
                user="u",
                fallback=lambda: "deterministic-text",
                structured_inputs={"ask_price": 820000},
                tier="lookup",
            )
        self.assertEqual(text, "deterministic-text")
        self.assertIsNotNone(report)
        self.assertTrue(report["budget_exceeded"])

    def test_flag_surfaces_when_structured_inputs_absent(self) -> None:
        """Without structured_inputs the verifier is normally skipped (report
        is None). Budget-exhaust must still return a minimal report so the
        signal isn't dropped."""
        from briarwood.cost_guard import BudgetExceeded

        llm = MagicMock()
        llm.complete.side_effect = BudgetExceeded("cap")
        with patch.dict("os.environ", {}, clear=True):
            text, report = composer.compose_structured_response(
                llm=llm,
                system="sys",
                user="u",
                fallback=lambda: "deterministic-text",
                structured_inputs=None,
                tier=None,
            )
        self.assertEqual(text, "deterministic-text")
        self.assertIsInstance(report, dict)
        self.assertTrue(report["budget_exceeded"])
        # Shape is SSE-compatible with verifier_report — zero-valued fields
        # but present so the frontend's type guards still pass.
        self.assertEqual(report["sentences_with_violations"], 0)
        self.assertEqual(report["anchors"], [])
        self.assertEqual(report["violations"], [])

    def test_flag_false_on_normal_call(self) -> None:
        """Default path must carry the flag explicitly (not absent) so
        consumers can rely on `report["budget_exceeded"]` being defined."""
        llm = _mock_llm(["Fair value $820,000."])
        with patch.dict("os.environ", {}, clear=True):
            _, report = composer.complete_and_verify(
                llm=llm,
                system="sys",
                user="u",
                structured_inputs={"fair_value_base": 820000},
                tier="decision_summary",
            )
        self.assertFalse(report["budget_exceeded"])

    def test_budget_on_regen_retry_flags_report(self) -> None:
        """Strict-regen path may hit the cap on the retry. Original draft is
        kept, and the report should flag budget_exceeded=True."""
        from briarwood.cost_guard import BudgetExceeded

        dirty = (
            "Fair value $820,000. Upside is $700,000. Stress is $123,456. "
            "Bull is $999,999."
        )
        llm = MagicMock()
        # First call returns dirty draft; second call raises budget.
        llm.complete.side_effect = [dirty, BudgetExceeded("cap")]
        with patch.dict("os.environ", {composer.STRICT_REGEN_FLAG: "1"}):
            text, report = composer.complete_and_verify(
                llm=llm,
                system="sys",
                user="u",
                structured_inputs={"fair_value_base": 820000},
                tier="decision_summary",
            )
        self.assertEqual(llm.complete.call_count, 2)
        self.assertTrue(report["budget_exceeded"])
        self.assertTrue(report["strict_regen"]["regen_attempted"])
        # Kept the original draft text (stripped); $820,000 survives.
        self.assertIn("$820,000", text)


class NarrativeTierAnthropicRoutingTests(unittest.TestCase):
    """AUDIT 1.3.5: decision_summary / edge / risk tiers route through
    Anthropic when ANTHROPIC_API_KEY is set; everything else keeps the
    injected OpenAI client. The injected client stays the fallback path
    when Anthropic isn't available — no silent agent disablement."""

    def setUp(self) -> None:
        composer.reset_narrative_client_cache()

    def tearDown(self) -> None:
        composer.reset_narrative_client_cache()

    def _structured_inputs(self) -> dict[str, object]:
        return {"fair_value_base": 820000}

    def test_decision_summary_routes_to_anthropic_when_key_present(self) -> None:
        openai_llm = _mock_llm(["openai draft"])
        anth_llm = _mock_llm(["anthropic draft"])
        env = {"ANTHROPIC_API_KEY": "sk-ant-test"}
        with patch.dict("os.environ", env, clear=False), patch(
            "briarwood.agent.llm.AnthropicChatClient", return_value=anth_llm
        ):
            text, _ = composer.complete_and_verify(
                llm=openai_llm,
                system="sys",
                user="u",
                structured_inputs=self._structured_inputs(),
                tier="decision_summary",
            )
        openai_llm.complete.assert_not_called()
        anth_llm.complete.assert_called()
        self.assertIn("anthropic", text)

    def test_edge_tier_routes_to_anthropic(self) -> None:
        openai_llm = _mock_llm(["openai draft"])
        anth_llm = _mock_llm(["anthropic draft"])
        env = {"ANTHROPIC_API_KEY": "sk-ant-test"}
        with patch.dict("os.environ", env, clear=False), patch(
            "briarwood.agent.llm.AnthropicChatClient", return_value=anth_llm
        ):
            composer.complete_and_verify(
                llm=openai_llm,
                system="sys",
                user="u",
                structured_inputs=self._structured_inputs(),
                tier="edge",
            )
        openai_llm.complete.assert_not_called()
        anth_llm.complete.assert_called()

    def test_risk_tier_routes_to_anthropic(self) -> None:
        openai_llm = _mock_llm(["openai draft"])
        anth_llm = _mock_llm(["anthropic draft"])
        env = {"ANTHROPIC_API_KEY": "sk-ant-test"}
        with patch.dict("os.environ", env, clear=False), patch(
            "briarwood.agent.llm.AnthropicChatClient", return_value=anth_llm
        ):
            composer.complete_and_verify(
                llm=openai_llm,
                system="sys",
                user="u",
                structured_inputs=self._structured_inputs(),
                tier="risk",
            )
        openai_llm.complete.assert_not_called()
        anth_llm.complete.assert_called()

    def test_non_narrative_tier_stays_on_injected_client(self) -> None:
        """projection / strategy / research / lookup / decision_value etc.
        keep the injected client even when Anthropic is available."""
        openai_llm = _mock_llm(["openai draft"])
        anth_ctor = MagicMock()
        env = {"ANTHROPIC_API_KEY": "sk-ant-test"}
        with patch.dict("os.environ", env, clear=False), patch(
            "briarwood.agent.llm.AnthropicChatClient", anth_ctor
        ):
            composer.complete_and_verify(
                llm=openai_llm,
                system="sys",
                user="u",
                structured_inputs=self._structured_inputs(),
                tier="projection",
            )
        openai_llm.complete.assert_called()
        anth_ctor.assert_not_called()

    def test_no_anthropic_key_keeps_injected_client_for_narrative_tiers(self) -> None:
        """Without a key, narrative tiers silently stay on OpenAI. No agent
        disablement, no surprise failure."""
        openai_llm = _mock_llm(["openai draft"])
        anth_ctor = MagicMock()
        env_without_key = {k: v for k, v in __import__("os").environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict("os.environ", env_without_key, clear=True), patch(
            "briarwood.agent.llm.AnthropicChatClient", anth_ctor
        ):
            composer.complete_and_verify(
                llm=openai_llm,
                system="sys",
                user="u",
                structured_inputs=self._structured_inputs(),
                tier="decision_summary",
            )
        openai_llm.complete.assert_called()
        anth_ctor.assert_not_called()

    def test_explicit_openai_override_forces_fallback(self) -> None:
        """`BRIARWOOD_NARRATIVE_PROVIDER=openai` forces OpenAI even when
        the Anthropic key is present — escape hatch for A/B or cost cap."""
        openai_llm = _mock_llm(["openai draft"])
        anth_ctor = MagicMock()
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            composer.NARRATIVE_PROVIDER_ENV: "openai",
        }
        with patch.dict("os.environ", env, clear=False), patch(
            "briarwood.agent.llm.AnthropicChatClient", anth_ctor
        ):
            composer.complete_and_verify(
                llm=openai_llm,
                system="sys",
                user="u",
                structured_inputs=self._structured_inputs(),
                tier="decision_summary",
            )
        openai_llm.complete.assert_called()
        anth_ctor.assert_not_called()

    def test_anthropic_init_failure_falls_back_to_openai(self) -> None:
        """SDK init raising (e.g., anthropic package not installed) must
        not break the turn — caller fallback is the injected client."""
        openai_llm = _mock_llm(["openai draft"])
        env = {"ANTHROPIC_API_KEY": "sk-ant-test"}
        with patch.dict("os.environ", env, clear=False), patch(
            "briarwood.agent.llm.AnthropicChatClient",
            side_effect=RuntimeError("sdk missing"),
        ):
            composer.complete_and_verify(
                llm=openai_llm,
                system="sys",
                user="u",
                structured_inputs=self._structured_inputs(),
                tier="decision_summary",
            )
        openai_llm.complete.assert_called()


if __name__ == "__main__":
    unittest.main()
