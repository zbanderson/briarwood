from __future__ import annotations

import json
import unittest
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - environment-specific
    TestClient = None

from api import events
try:
    from api.main import app
except ModuleNotFoundError:  # pragma: no cover - environment-specific
    app = None
from briarwood.agent.router import AnswerType, RouterDecision


class _FakeStore:
    def __init__(self) -> None:
        self.conversation = {
            "id": "conv-test",
            "title": "Should I buy 123 Main?",
            "created_at": 1,
            "updated_at": 1,
            "messages": [],
        }
        self.added: list[tuple[str, str, str]] = []

    def create_conversation(self, title: str | None = None) -> dict[str, object]:
        if title:
            self.conversation["title"] = title
        return dict(self.conversation)

    def get_conversation(self, conversation_id: str) -> dict[str, object] | None:
        if conversation_id == self.conversation["id"]:
            return dict(self.conversation)
        return None

    def add_message(self, conversation_id: str, role: str, content: str, events=None) -> dict[str, object]:
        self.added.append((conversation_id, role, content))
        mid = f"{role}-{len(self.added)}"
        return {"id": mid, "role": role, "content": content, "events": events or []}


async def _fake_decision_stream(*args, **kwargs):
    del args, kwargs
    yield events.verdict({"stance": "buy_if_price_improves"})
    yield events.text_delta("First ")
    yield events.text_delta("reply.")


def _parse_sse_frames(body: str) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    for chunk in body.split("\n\n"):
        if not chunk.startswith("data:"):
            continue
        frames.append(json.loads(chunk[5:].strip()))
    return frames


class ChatApiTests(unittest.TestCase):
    @unittest.skipIf(TestClient is None or app is None, "fastapi is not installed in this environment")
    def test_new_chat_streams_conversation_then_assistant_message_then_done(self) -> None:
        store = _FakeStore()
        with (
            patch("api.main.get_store", return_value=store),
            patch(
                "api.main.classify_turn",
                return_value=RouterDecision(
                    answer_type=AnswerType.DECISION,
                    confidence=0.98,
                    reason="test",
                ),
            ),
            patch("api.main.decision_stream", side_effect=lambda *args, **kwargs: _fake_decision_stream()),
        ):
            client = TestClient(app)
            with client.stream(
                "POST",
                "/api/chat",
                json={"messages": [{"role": "user", "content": "Should I buy 123 Main?"}]},
            ) as response:
                body = "".join(response.iter_text())

        self.assertEqual(response.status_code, 200)
        payloads = _parse_sse_frames(body)
        event_types = [payload["type"] for payload in payloads]
        self.assertEqual(event_types[0], events.EVENT_CONVERSATION)
        self.assertIn(events.EVENT_TEXT_DELTA, event_types)
        self.assertEqual(event_types[-1], events.EVENT_DONE)
        assistant_message_index = next(
            idx
            for idx, payload in enumerate(payloads)
            if payload["type"] == events.EVENT_MESSAGE and payload.get("role") == "assistant"
        )
        self.assertLess(assistant_message_index, len(payloads) - 1)
        self.assertEqual(store.added[0][1], "user")
        self.assertEqual(store.added[-1][1], "assistant")
        self.assertEqual(store.added[-1][2], "First reply.")


class ClassifyTurnMissingLLMTests(unittest.TestCase):
    """NEW-V-010: when ``default_client()`` returns None (no provider
    configured), ``classify_turn`` must return None so the chat endpoint
    can emit an explicit LLM-unavailable error instead of silently running
    the LOOKUP default or the echo fallback."""

    def test_classify_turn_returns_none_when_get_llm_returns_none(self) -> None:
        from api import pipeline_adapter

        with patch("api.pipeline_adapter.get_llm", return_value=None):
            result = pipeline_adapter.classify_turn("Should I buy 123 Main?")
        self.assertIsNone(result)

    @unittest.skipIf(TestClient is None or app is None, "fastapi is not installed in this environment")
    def test_chat_endpoint_emits_error_and_done_when_classifier_returns_none(
        self,
    ) -> None:
        """No exception, no decision → explicit error event, no echo stream.
        Prior behavior routed to _echo_stream (mock listings); the new
        behavior surfaces configuration failure to the user."""
        store = _FakeStore()
        with (
            patch("api.main.get_store", return_value=store),
            patch("api.main.classify_turn", return_value=None),
            patch("api.main._echo_stream") as mocked_echo,
        ):
            client = TestClient(app)
            with client.stream(
                "POST",
                "/api/chat",
                json={"messages": [{"role": "user", "content": "Should I buy 123 Main?"}]},
            ) as response:
                body = "".join(response.iter_text())

        self.assertEqual(response.status_code, 200)
        mocked_echo.assert_not_called()
        payloads = _parse_sse_frames(body)
        event_types = [payload["type"] for payload in payloads]
        self.assertIn(events.EVENT_ERROR, event_types)
        self.assertEqual(event_types[-1], events.EVENT_DONE)


if __name__ == "__main__":
    unittest.main()
