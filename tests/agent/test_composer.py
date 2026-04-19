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


class DecisionCriticTests(unittest.TestCase):
    """AUDIT 1.3.3: generate→critique ensemble on decision_summary.

    Three env states — off / shadow / on. off skips entirely; shadow logs
    what the critic would have done without changing the draft; on applies
    revisions but only when the numeric-preservation check passes."""

    def setUp(self) -> None:
        composer.reset_narrative_client_cache()
        composer.reset_critic_client_cache()

    def tearDown(self) -> None:
        composer.reset_narrative_client_cache()
        composer.reset_critic_client_cache()

    def _inputs(self) -> dict[str, object]:
        return {
            "decision_stance": "pass",
            "ask_price": 820000,
            "ask_premium_pct": 0.15,
            "trust_flags": [],
        }

    def _baseline_env(self, mode: str) -> dict[str, str]:
        """Env that activates the narrative Anthropic path AND the critic
        at the given mode. Narrative path is needed so the draft is routed
        to our stub `narrative_llm` (not OpenAI)."""
        return {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            composer.CRITIC_MODE_ENV: mode,
        }

    def _run_with_critic(
        self,
        *,
        draft: str,
        review: composer.DecisionCriticReview | None,
        mode: str,
    ) -> tuple[str, dict]:
        """Shared harness. Stubs the narrative client to return ``draft``
        and stubs the critic client's ``complete_structured`` to return
        ``review``. Runs ``complete_and_verify`` with tier=decision_summary."""
        openai_llm = _mock_llm(["openai fallback — should not be used"])
        narrative_llm = _mock_llm([draft])

        critic_client = MagicMock()
        critic_client.complete_structured.return_value = review

        def _anth_ctor(*_args: object, **_kwargs: object) -> MagicMock:
            # First call returns the narrative client; second returns the
            # critic client. Matches the composer's resolution order.
            return next(_anth_ctor.queue)

        _anth_ctor.queue = iter([narrative_llm, critic_client])

        env = self._baseline_env(mode)
        with patch.dict("os.environ", env, clear=False), patch(
            "briarwood.agent.llm.AnthropicChatClient", side_effect=_anth_ctor
        ):
            text, report = composer.complete_and_verify(
                llm=openai_llm,
                system="sys",
                user="u",
                structured_inputs=self._inputs(),
                tier="decision_summary",
            )
        return text, report

    def test_mode_off_skips_critic_entirely(self) -> None:
        """Default: critic doesn't run, no telemetry, draft ships unchanged."""
        openai_llm = _mock_llm(["Draft verdict: pass. Ask $820,000 is 15% over fair."])
        narrative_llm = _mock_llm(
            ["Draft verdict: pass. Ask $820,000 is 15% over fair."]
        )
        critic_ctor = MagicMock()

        def _anth_ctor(*_args: object, **_kwargs: object) -> MagicMock:
            # Only called once (for the narrative client) since critic is off.
            return narrative_llm

        env = {"ANTHROPIC_API_KEY": "sk-ant-test"}  # no CRITIC_MODE_ENV
        with patch.dict("os.environ", env, clear=False), patch(
            "briarwood.agent.llm.AnthropicChatClient", side_effect=_anth_ctor
        ):
            text, report = composer.complete_and_verify(
                llm=openai_llm,
                system="sys",
                user="u",
                structured_inputs=self._inputs(),
                tier="decision_summary",
            )
        self.assertIn("pass", text)
        self.assertNotIn("critic", report)

    def test_mode_shadow_runs_critic_but_ships_draft(self) -> None:
        """Shadow: critic runs, verdict logged in telemetry, draft unchanged
        even when verdict is revise. This is the signal-collection mode."""
        draft = "Could be worth a closer look at $820,000."
        review = composer.DecisionCriticReview(
            verdict="revise",
            rewritten_text="Pass — ask $820,000 is 15% over fair value.",
            notes="softening: ask_premium_pct=0.15 supports a clear pass",
        )
        text, report = self._run_with_critic(draft=draft, review=review, mode="shadow")

        self.assertEqual(text, draft)  # draft unchanged in shadow mode
        self.assertEqual(report["critic"]["mode"], "shadow")
        self.assertEqual(report["critic"]["verdict"], "revise")
        self.assertFalse(report["critic"]["applied_rewrite"])
        # Numeric check still logged in shadow — signal for "would this have been safe?"
        self.assertTrue(report["critic"]["numeric_check"]["ok"])

    def test_mode_on_keep_verdict_ships_draft(self) -> None:
        """Critic says keep → draft ships unchanged, telemetry reflects keep."""
        draft = "Pass — ask $820,000 is 15% over fair value."
        review = composer.DecisionCriticReview(
            verdict="keep", rewritten_text=None, notes="stance is appropriately bearish"
        )
        text, report = self._run_with_critic(draft=draft, review=review, mode="on")

        self.assertEqual(text, draft)
        self.assertEqual(report["critic"]["verdict"], "keep")
        self.assertFalse(report["critic"]["applied_rewrite"])
        self.assertNotIn("numeric_check", report["critic"])

    def test_mode_on_flag_only_ships_draft_and_records_flag(self) -> None:
        """flag_only → draft ships unchanged, flag preserved in telemetry."""
        draft = "Could be interesting at $820,000."
        review = composer.DecisionCriticReview(
            verdict="flag_only",
            rewritten_text=None,
            notes="possible softening but not confident in rewrite",
        )
        text, report = self._run_with_critic(draft=draft, review=review, mode="on")

        self.assertEqual(text, draft)
        self.assertEqual(report["critic"]["verdict"], "flag_only")
        self.assertFalse(report["critic"]["applied_rewrite"])
        self.assertIn("not confident", report["critic"]["notes"])

    def test_mode_on_revise_with_numbers_preserved_applies_rewrite(self) -> None:
        """The happy path: revise + all numbers preserved → rewrite shipped."""
        draft = "Could be worth a closer look at $820,000 despite 15% ask premium."
        rewrite = "Pass — ask $820,000 sits 15% over fair value."
        review = composer.DecisionCriticReview(
            verdict="revise",
            rewritten_text=rewrite,
            notes="softening: 15% premium warrants a confident pass",
        )
        text, report = self._run_with_critic(draft=draft, review=review, mode="on")

        self.assertEqual(text, rewrite)
        self.assertEqual(report["critic"]["verdict"], "revise")
        self.assertTrue(report["critic"]["applied_rewrite"])
        self.assertTrue(report["critic"]["numeric_check"]["ok"])
        self.assertEqual(report["critic"]["numeric_check"]["missing"], [])

    def test_mode_on_revise_dropping_number_falls_back_to_draft(self) -> None:
        """The critical safety net: critic rewrite silently loses a number
        → preservation check fires, draft ships, flag in telemetry."""
        draft = "Pass — ask $820,000 sits 15% over fair value."
        # Rewrite drops the $820,000 figure (mutated to "high ask")
        rewrite = "Pass — 15% over fair is a confident avoid."
        review = composer.DecisionCriticReview(
            verdict="revise",
            rewritten_text=rewrite,
            notes="strengthened stance",
        )
        text, report = self._run_with_critic(draft=draft, review=review, mode="on")

        self.assertEqual(text, draft)  # draft wins, not rewrite
        self.assertFalse(report["critic"]["applied_rewrite"])
        self.assertFalse(report["critic"]["numeric_check"]["ok"])
        self.assertIn("820000", report["critic"]["numeric_check"]["missing"])

    def test_critic_returns_none_on_refusal_no_telemetry_pollution(self) -> None:
        """Critic refusal (SDK returned None) → draft ships, telemetry shows
        ran=False. No verdict key, no numeric_check — nothing to report."""
        draft = "Pass — ask $820,000 is 15% over fair value."
        text, report = self._run_with_critic(draft=draft, review=None, mode="on")

        self.assertEqual(text, draft)
        self.assertFalse(report["critic"]["ran"])
        self.assertNotIn("verdict", report["critic"])

    def test_non_decision_summary_tier_never_runs_critic(self) -> None:
        """edge, risk, projection, etc. — critic is scoped to decision_summary
        only. Even with mode=on, other tiers skip critic entirely."""
        openai_llm = _mock_llm(["edge draft prose"])
        narrative_llm = _mock_llm(["edge draft prose"])
        critic_ctor = MagicMock()

        call_log: list[str] = []

        def _anth_ctor(*_args: object, **_kwargs: object) -> MagicMock:
            call_log.append("init")
            return narrative_llm

        env = {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            composer.CRITIC_MODE_ENV: "on",
        }
        with patch.dict("os.environ", env, clear=False), patch(
            "briarwood.agent.llm.AnthropicChatClient", side_effect=_anth_ctor
        ):
            text, report = composer.complete_and_verify(
                llm=openai_llm,
                system="sys",
                user="u",
                structured_inputs=self._inputs(),
                tier="edge",
            )
        self.assertIn("edge draft", text)
        self.assertNotIn("critic", report)
        # Exactly one Anthropic init — the narrative client, not the critic.
        self.assertEqual(len(call_log), 1)

    def test_mode_on_but_no_key_records_ran_false(self) -> None:
        """ANTHROPIC_API_KEY missing → critic short-circuits (no init).
        Ships the draft unchanged. Telemetry records ``ran=False`` so the
        dev tooling can distinguish 'critic skipped by mode=off' from
        'mode=on but no key present' — those are different ops signals."""
        openai_llm = _mock_llm(["openai decision draft at $820,000"])

        env = {composer.CRITIC_MODE_ENV: "on"}
        env_without_key = {
            k: v for k, v in __import__("os").environ.items() if k != "ANTHROPIC_API_KEY"
        }
        env_without_key.update(env)
        with patch.dict("os.environ", env_without_key, clear=True):
            text, report = composer.complete_and_verify(
                llm=openai_llm,
                system="sys",
                user="u",
                structured_inputs=self._inputs(),
                tier="decision_summary",
            )
        self.assertIn("820,000", text)
        self.assertEqual(report["critic"]["mode"], "on")
        self.assertFalse(report["critic"]["ran"])
        self.assertNotIn("verdict", report["critic"])


class NumericPreservationCheckTests(unittest.TestCase):
    """AUDIT 1.3.3: the ten-line safety net that catches critics silently
    mutating numbers. Unit tests on the helper so the behavior is pinned
    independent of the critic orchestration."""

    def test_identical_text_passes(self) -> None:
        ok, missing = composer._numbers_preserved("$820,000 at 15%", "$820,000 at 15%")
        self.assertTrue(ok)
        self.assertEqual(missing, [])

    def test_normalized_equivalents_pass(self) -> None:
        """`$820,000` / `820,000` / `820000` all normalize to the same token."""
        ok, _ = composer._numbers_preserved("$820,000 at 15%", "820000 at 15%")
        self.assertTrue(ok)

    def test_dropped_number_fails(self) -> None:
        ok, missing = composer._numbers_preserved("$820,000 at 15%", "pass, high ask")
        self.assertFalse(ok)
        self.assertIn("820000", missing)
        self.assertIn("15%", missing)

    def test_mutated_number_fails(self) -> None:
        """Critic changes 820,000 to 800,000 — the original token is missing."""
        ok, missing = composer._numbers_preserved("$820,000", "$800,000")
        self.assertFalse(ok)
        self.assertIn("820000", missing)

    def test_new_numbers_in_rewrite_are_allowed(self) -> None:
        """Adding a number in rewrite isn't flagged (only missing originals
        are). This is intentional — over-strict would block legitimate
        cleanups that surface an implicit figure from structured_inputs."""
        ok, _ = composer._numbers_preserved("$820,000", "$820,000 vs $700,000 fair")
        self.assertTrue(ok)


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
