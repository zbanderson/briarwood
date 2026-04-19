"""LLM client — default_client env-gated; budget guard short-circuits."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from briarwood.agent import llm as llm_mod


class DefaultClientTests(unittest.TestCase):
    def test_returns_none_without_api_key(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(llm_mod.default_client())

    def test_returns_none_when_openai_import_fails(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}), patch.object(
            llm_mod, "OpenAIChatClient", side_effect=RuntimeError("no openai pkg")
        ):
            self.assertIsNone(llm_mod.default_client())

    def test_returns_client_when_available(self) -> None:
        sentinel = MagicMock()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}), patch.object(
            llm_mod, "OpenAIChatClient", return_value=sentinel
        ):
            self.assertIs(llm_mod.default_client(), sentinel)

    def test_anthropic_selected_when_provider_env_and_key_set(self) -> None:
        """AUDIT 1.3.4: provider env flips selection without touching callers."""
        sentinel = MagicMock()
        env = {
            "BRIARWOOD_AGENT_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "OPENAI_API_KEY": "sk-test",
        }
        with patch.dict("os.environ", env, clear=True), patch.object(
            llm_mod, "AnthropicChatClient", return_value=sentinel
        ):
            self.assertIs(llm_mod.default_client(), sentinel)

    def test_anthropic_requested_but_key_missing_falls_back_to_openai(self) -> None:
        """Misconfiguration must not silently disable the agent — prefer
        OpenAI fallback over returning ``None``."""
        openai_sentinel = MagicMock()
        env = {
            "BRIARWOOD_AGENT_PROVIDER": "anthropic",
            "OPENAI_API_KEY": "sk-test",
        }
        with patch.dict("os.environ", env, clear=True), patch.object(
            llm_mod, "OpenAIChatClient", return_value=openai_sentinel
        ):
            self.assertIs(llm_mod.default_client(), openai_sentinel)

    def test_anthropic_import_failure_falls_back_to_openai(self) -> None:
        openai_sentinel = MagicMock()
        env = {
            "BRIARWOOD_AGENT_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "OPENAI_API_KEY": "sk-test",
        }
        with patch.dict("os.environ", env, clear=True), patch.object(
            llm_mod, "AnthropicChatClient", side_effect=RuntimeError("no anthropic pkg")
        ), patch.object(llm_mod, "OpenAIChatClient", return_value=openai_sentinel):
            self.assertIs(llm_mod.default_client(), openai_sentinel)

    def test_default_provider_is_openai(self) -> None:
        """No env → OpenAI path, unchanged from pre-1.3.4 behavior."""
        openai_sentinel = MagicMock()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=True), patch.object(
            llm_mod, "OpenAIChatClient", return_value=openai_sentinel
        ), patch.object(llm_mod, "AnthropicChatClient") as anth_ctor:
            self.assertIs(llm_mod.default_client(), openai_sentinel)
            anth_ctor.assert_not_called()


class OpenAIChatClientTests(unittest.TestCase):
    def _make_client(self) -> llm_mod.OpenAIChatClient:
        """Bypass __init__ so we don't need a real OpenAI package installed."""
        client = llm_mod.OpenAIChatClient.__new__(llm_mod.OpenAIChatClient)
        client._client = MagicMock()
        client._model = "gpt-test"
        return client

    def test_complete_returns_output_text(self) -> None:
        client = self._make_client()
        resp = MagicMock()
        resp.output_text = "hello world"
        resp.usage = MagicMock(input_tokens=10, output_tokens=5)
        client._client.responses.create.return_value = resp

        guard = MagicMock()
        with patch("briarwood.cost_guard.get_guard", return_value=guard):
            out = client.complete(system="s", user="u")

        self.assertEqual(out, "hello world")
        guard.check_openai.assert_called_once()
        guard.record_openai.assert_called_once()

    def test_complete_raises_on_budget_exceeded(self) -> None:
        """AUDIT 1.2.3: let BudgetExceeded propagate so the composer can
        distinguish a budget-exhausted fallback from a blank LLM response."""
        client = self._make_client()
        from briarwood.cost_guard import BudgetExceeded

        guard = MagicMock()
        guard.check_openai.side_effect = BudgetExceeded("cap")
        with patch("briarwood.cost_guard.get_guard", return_value=guard):
            with self.assertRaises(BudgetExceeded):
                client.complete(system="s", user="u")

        client._client.responses.create.assert_not_called()

    def test_complete_returns_empty_when_output_text_missing(self) -> None:
        client = self._make_client()
        resp = MagicMock(spec=[])  # no output_text attribute
        client._client.responses.create.return_value = resp

        guard = MagicMock()
        with patch("briarwood.cost_guard.get_guard", return_value=guard):
            out = client.complete(system="s", user="u")

        self.assertEqual(out, "")


class AnthropicChatClientTests(unittest.TestCase):
    """AUDIT 1.3.4: the Anthropic client fulfills the LLMClient protocol for
    prose (``complete``) and falls back deterministically for structured."""

    def _make_client(self) -> llm_mod.AnthropicChatClient:
        client = llm_mod.AnthropicChatClient.__new__(llm_mod.AnthropicChatClient)
        client._client = MagicMock()
        client._model = "claude-test"
        return client

    def test_complete_concatenates_text_blocks(self) -> None:
        client = self._make_client()
        block_a = MagicMock(text="hello ")
        block_b = MagicMock(text="world")
        resp = MagicMock()
        resp.content = [block_a, block_b]
        resp.usage = MagicMock(input_tokens=12, output_tokens=7)
        client._client.messages.create.return_value = resp

        guard = MagicMock()
        with patch("briarwood.cost_guard.get_guard", return_value=guard):
            out = client.complete(system="s", user="u")

        self.assertEqual(out, "hello world")
        guard.check_anthropic.assert_called_once()
        guard.record_anthropic.assert_called_once_with(
            model="claude-test", input_tokens=12, output_tokens=7
        )

    def test_complete_raises_on_budget_exceeded(self) -> None:
        client = self._make_client()
        from briarwood.cost_guard import BudgetExceeded

        guard = MagicMock()
        guard.check_anthropic.side_effect = BudgetExceeded("cap")
        with patch("briarwood.cost_guard.get_guard", return_value=guard):
            with self.assertRaises(BudgetExceeded):
                client.complete(system="s", user="u")

        client._client.messages.create.assert_not_called()

    def test_complete_returns_empty_on_transport_failure(self) -> None:
        client = self._make_client()
        client._client.messages.create.side_effect = RuntimeError("network")

        guard = MagicMock()
        with patch("briarwood.cost_guard.get_guard", return_value=guard):
            out = client.complete(system="s", user="u")

        self.assertEqual(out, "")

    def test_complete_structured_returns_none_unimplemented(self) -> None:
        """Deferred path returns ``None`` — same deterministic-fallback
        contract as the OpenAI path on failure. Callers must not assume
        the return is populated."""
        from pydantic import BaseModel

        class _S(BaseModel):
            x: int

        client = self._make_client()
        self.assertIsNone(client.complete_structured(system="s", user="u", schema=_S))


class CostGuardAnthropicTests(unittest.TestCase):
    """AUDIT 1.3.4: Anthropic budget is independent of OpenAI."""

    def test_record_anthropic_accumulates(self) -> None:
        from briarwood.cost_guard import CostGuard

        guard = CostGuard(anthropic_usd_cap=10.0)
        cost = guard.record_anthropic(
            model="claude-sonnet-4-6", input_tokens=1000, output_tokens=1000
        )
        # 0.003 + 0.015 = 0.018 per the pricing table
        self.assertAlmostEqual(cost, 0.018, places=4)
        self.assertAlmostEqual(guard.anthropic_usd, 0.018, places=4)

    def test_check_anthropic_raises_at_cap(self) -> None:
        from briarwood.cost_guard import BudgetExceeded, CostGuard

        guard = CostGuard(anthropic_usd=1.0, anthropic_usd_cap=1.0)
        with self.assertRaises(BudgetExceeded):
            guard.check_anthropic()

    def test_openai_and_anthropic_budgets_are_independent(self) -> None:
        from briarwood.cost_guard import CostGuard

        guard = CostGuard(openai_usd_cap=1.0, anthropic_usd_cap=1.0)
        guard.record_openai(model="gpt-4o-mini", input_tokens=1000, output_tokens=1000)
        self.assertGreater(guard.openai_usd, 0.0)
        self.assertEqual(guard.anthropic_usd, 0.0)


if __name__ == "__main__":
    unittest.main()
