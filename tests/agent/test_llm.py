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

    def _structured_schema(self):
        from pydantic import BaseModel

        class _S(BaseModel):
            verdict: str
            count: int

        return _S

    def _tool_use_block(self, name: str, input_payload: dict) -> MagicMock:
        block = MagicMock()
        block.type = "tool_use"
        block.name = name
        block.input = input_payload
        return block

    def _text_block(self, text: str) -> MagicMock:
        block = MagicMock()
        block.type = "text"
        block.text = text
        # Explicitly make `name`/`input` absent so the structured-parser
        # doesn't accidentally treat a text block as tool_use.
        del block.name
        del block.input
        return block

    def test_complete_structured_happy_path_validates_payload(self) -> None:
        """AUDIT 1.3.3: tool_use block → Pydantic-validated model instance."""
        schema = self._structured_schema()
        client = self._make_client()
        resp = MagicMock()
        resp.content = [
            self._tool_use_block("emit__S", {"verdict": "keep", "count": 3})
        ]
        resp.usage = MagicMock(input_tokens=42, output_tokens=17)
        client._client.messages.create.return_value = resp

        guard = MagicMock()
        with patch("briarwood.cost_guard.get_guard", return_value=guard):
            out = client.complete_structured(system="s", user="u", schema=schema)

        self.assertIsNotNone(out)
        self.assertEqual(out.verdict, "keep")
        self.assertEqual(out.count, 3)
        guard.record_anthropic.assert_called_once()

    def test_complete_structured_returns_none_on_refusal_no_tool_use(self) -> None:
        """AUDIT 1.3.3: the model responded with prose only (no tool_use).
        Treat as refusal — do not raise, return ``None`` so caller falls back."""
        schema = self._structured_schema()
        client = self._make_client()
        resp = MagicMock()
        resp.content = [self._text_block("I can't answer that.")]
        resp.usage = MagicMock(input_tokens=10, output_tokens=4)
        client._client.messages.create.return_value = resp

        guard = MagicMock()
        with patch("briarwood.cost_guard.get_guard", return_value=guard):
            out = client.complete_structured(system="s", user="u", schema=schema)

        self.assertIsNone(out)

    def test_complete_structured_returns_none_on_empty_tool_input(self) -> None:
        """AUDIT 1.3.3: tool_use with empty input dict is Anthropic's
        in-schema refusal signal. Must be treated the same as no tool_use —
        validation failure, not an exception."""
        schema = self._structured_schema()
        client = self._make_client()
        resp = MagicMock()
        resp.content = [self._tool_use_block("emit__S", {})]
        resp.usage = MagicMock(input_tokens=10, output_tokens=2)
        client._client.messages.create.return_value = resp

        guard = MagicMock()
        with patch("briarwood.cost_guard.get_guard", return_value=guard):
            out = client.complete_structured(system="s", user="u", schema=schema)

        self.assertIsNone(out)

    def test_complete_structured_returns_none_on_schema_failure(self) -> None:
        """Missing required field → Pydantic ValidationError → ``None``."""
        schema = self._structured_schema()
        client = self._make_client()
        resp = MagicMock()
        resp.content = [self._tool_use_block("emit__S", {"verdict": "keep"})]
        resp.usage = MagicMock(input_tokens=10, output_tokens=4)
        client._client.messages.create.return_value = resp

        guard = MagicMock()
        with patch("briarwood.cost_guard.get_guard", return_value=guard):
            out = client.complete_structured(system="s", user="u", schema=schema)

        self.assertIsNone(out)

    def test_complete_structured_returns_none_on_transport_failure(self) -> None:
        schema = self._structured_schema()
        client = self._make_client()
        client._client.messages.create.side_effect = RuntimeError("network")

        guard = MagicMock()
        with patch("briarwood.cost_guard.get_guard", return_value=guard):
            out = client.complete_structured(system="s", user="u", schema=schema)

        self.assertIsNone(out)

    def test_complete_structured_raises_on_budget_exceeded(self) -> None:
        schema = self._structured_schema()
        client = self._make_client()
        from briarwood.cost_guard import BudgetExceeded

        guard = MagicMock()
        guard.check_anthropic.side_effect = BudgetExceeded("cap")
        with patch("briarwood.cost_guard.get_guard", return_value=guard):
            with self.assertRaises(BudgetExceeded):
                client.complete_structured(system="s", user="u", schema=schema)

        client._client.messages.create.assert_not_called()

    def test_complete_structured_honors_model_override(self) -> None:
        """The ``model`` kwarg overrides the client's default for this call."""
        schema = self._structured_schema()
        client = self._make_client()
        resp = MagicMock()
        resp.content = [self._tool_use_block("emit__S", {"verdict": "keep", "count": 1})]
        resp.usage = MagicMock(input_tokens=5, output_tokens=2)
        client._client.messages.create.return_value = resp

        guard = MagicMock()
        with patch("briarwood.cost_guard.get_guard", return_value=guard):
            client.complete_structured(
                system="s", user="u", schema=schema, model="claude-opus-4-7"
            )

        kwargs = client._client.messages.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "claude-opus-4-7")
        guard.record_anthropic.assert_called_once()
        self.assertEqual(
            guard.record_anthropic.call_args.kwargs["model"], "claude-opus-4-7"
        )


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
