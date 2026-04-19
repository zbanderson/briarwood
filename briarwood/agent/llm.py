"""Thin LLM client abstraction for the agent layer.

Keeps provider details out of router/dispatch. Tests inject a fake client.

Two surfaces:
- `complete()` — free-text prose. Grounding verifier guards the prose.
- `complete_structured()` — strict JSON-schema call validated through a
  Pydantic model. Mirrors the `local_intelligence.adapters` template so
  every non-prose LLM output has a declared shape and a deterministic
  fallback on validation failure. See AUDIT 1.2.2.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

_logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str: ...

    def complete_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[BaseModel],
        model: str | None = None,
        max_tokens: int = 600,
    ) -> BaseModel | None: ...


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

    def complete_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        model: str | None = None,
        max_tokens: int = 600,
    ) -> T | None:
        """Strict JSON-schema LLM call validated by a Pydantic model.

        Mirrors `briarwood.local_intelligence.adapters.OpenAILocalIntelligenceExtractor`:
        the Responses API is called with `text.format.type="json_schema"`,
        the returned JSON is parsed, and the payload is passed through
        `schema.model_validate`. Any failure (transport, parse, schema)
        logs and returns `None` so callers can deterministically fall back.

        `BudgetExceeded` propagates (same convention as `complete`).
        """
        from briarwood.cost_guard import get_guard
        guard = get_guard()
        guard.check_openai()

        use_model = model or os.environ.get("BRIARWOOD_STRUCTURED_MODEL", "gpt-5")
        try:
            response = self._client.responses.create(
                model=use_model,
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema.__name__,
                        "strict": True,
                        "schema": schema.model_json_schema(),
                    }
                },
                max_output_tokens=max_tokens,
            )
        except Exception as exc:
            _logger.warning("structured LLM call transport failed (%s): %s", schema.__name__, exc)
            return None

        usage = getattr(response, "usage", None)
        if usage is not None:
            guard.record_openai(
                model=use_model,
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            )

        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text.strip():
            _logger.warning("structured LLM call returned empty text (%s)", schema.__name__)
            return None

        try:
            payload = json.loads(output_text)
        except json.JSONDecodeError as exc:
            _logger.warning("structured LLM call returned invalid JSON (%s): %s", schema.__name__, exc)
            return None
        try:
            return schema.model_validate(payload)
        except ValidationError as exc:
            _logger.warning("structured LLM call failed schema (%s): %s", schema.__name__, exc)
            return None


def default_client() -> LLMClient | None:
    """Return a real client if OpenAI is available and key is set, else None."""
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    try:
        return OpenAIChatClient()
    except Exception:
        return None
