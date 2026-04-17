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

    def test_complete_returns_empty_on_budget_exceeded(self) -> None:
        client = self._make_client()
        from briarwood.cost_guard import BudgetExceeded

        guard = MagicMock()
        guard.check_openai.side_effect = BudgetExceeded("cap")
        with patch("briarwood.cost_guard.get_guard", return_value=guard):
            out = client.complete(system="s", user="u")

        self.assertEqual(out, "")
        client._client.responses.create.assert_not_called()

    def test_complete_returns_empty_when_output_text_missing(self) -> None:
        client = self._make_client()
        resp = MagicMock(spec=[])  # no output_text attribute
        client._client.responses.create.return_value = resp

        guard = MagicMock()
        with patch("briarwood.cost_guard.get_guard", return_value=guard):
            out = client.complete(system="s", user="u")

        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
