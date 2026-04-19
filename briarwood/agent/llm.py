"""Thin LLM client abstraction for the agent layer.

Keeps provider details out of router/dispatch. Tests inject a fake client.
"""

from __future__ import annotations

import os
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str: ...


class OpenAIChatClient:
    """OpenAI client using the Responses API (matches local_intelligence usage)."""

    def __init__(self, model: str | None = None, timeout: float = 30.0) -> None:
        from openai import OpenAI

        self._client = OpenAI(timeout=timeout)
        self._model = model or os.environ.get("BRIARWOOD_AGENT_MODEL", "gpt-4o-mini")

    def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
        from briarwood.cost_guard import get_guard
        guard = get_guard()
        # Propagate BudgetExceeded to callers so they can distinguish
        # "budget cap hit → fall back" from "LLM returned empty text".
        # See AUDIT 1.2.3. The composer catches this explicitly and flags
        # the verifier report; other call sites treat it as a generic
        # failure via their existing broad except.
        guard.check_openai()

        response = self._client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_output_tokens=max_tokens,
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            guard.record_openai(
                model=self._model,
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            )
        text = getattr(response, "output_text", None)
        return text if isinstance(text, str) else ""


def default_client() -> LLMClient | None:
    """Return a real client if OpenAI is available and key is set, else None."""
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    try:
        return OpenAIChatClient()
    except Exception:
        return None
