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


def _force_all_required(schema: Any) -> Any:
    """Rewrite a Pydantic-generated JSON schema for OpenAI strict mode.

    OpenAI's ``strict: true`` rejects schemas whose ``required`` array does
    not contain every key in ``properties``. Pydantic omits any field with a
    default from ``required``, so fields typed ``X | None = None`` (already
    nullable via ``anyOf``) slip through. This walker forces every object's
    ``required`` to mirror ``properties`` — safe because those fields are
    still nullable, so the model can emit ``null`` to mean "skipped".
    """
    if isinstance(schema, dict):
        if schema.get("type") == "object" and isinstance(schema.get("properties"), dict):
            schema["required"] = list(schema["properties"].keys())
        for value in schema.values():
            _force_all_required(value)
    elif isinstance(schema, list):
        for item in schema:
            _force_all_required(item)
    return schema


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
                        "schema": _force_all_required(schema.model_json_schema()),
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


class AnthropicChatClient:
    """Anthropic Claude client implementing the ``LLMClient`` protocol.

    AUDIT 1.3.4: a parallel provider so narrative/critique prompts can be
    routed to Claude without touching call sites.

    AUDIT 1.3.3: ``complete_structured()`` is now wired via Anthropic's
    tool-use JSON mode — the model is forced to emit the schema through a
    single synthetic tool. Refusals (no tool_use block, or a tool_use block
    with an empty ``input``) are treated as validation failures and return
    ``None`` so callers fall back deterministically. Same contract as the
    OpenAI path — transport, parse, and schema failures all return ``None``.
    """

    def __init__(self, model: str | None = None, timeout: float = 30.0) -> None:
        from anthropic import Anthropic

        self._client = Anthropic(timeout=timeout)
        self._model = model or os.environ.get(
            "BRIARWOOD_ANTHROPIC_MODEL", "claude-sonnet-4-6"
        )

    def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
        from briarwood.cost_guard import get_guard
        guard = get_guard()
        guard.check_anthropic()

        try:
            response = self._client.messages.create(
                model=self._model,
                system=system,
                messages=[{"role": "user", "content": user}],
                max_tokens=max_tokens,
            )
        except Exception as exc:
            _logger.warning("Anthropic complete() transport failed: %s", exc)
            return ""

        usage = getattr(response, "usage", None)
        if usage is not None:
            guard.record_anthropic(
                model=self._model,
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            )

        blocks = getattr(response, "content", None) or []
        parts: list[str] = []
        for block in blocks:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)

    def complete_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        model: str | None = None,
        max_tokens: int = 600,
    ) -> T | None:
        """Strict-schema call via Anthropic tool-use JSON mode.

        AUDIT 1.3.3: the model is forced to emit ``schema`` through a
        synthetic ``emit_<SchemaName>`` tool. We parse the single tool_use
        block's ``input`` dict and pass it through ``schema.model_validate``.

        Failure modes that return ``None`` (deterministic fallback):
        - Transport failure (SDK raised)
        - No ``tool_use`` block in response (model returned prose instead
          of calling the tool — treat as refusal)
        - ``tool_use.input`` is empty or non-dict (model called the tool
          but declined to fill it — also a refusal)
        - Pydantic validation failure
        - Budget-exceeded propagates (same convention as ``complete``)
        """
        from briarwood.cost_guard import get_guard
        guard = get_guard()
        guard.check_anthropic()

        use_model = model or self._model
        tool_name = f"emit_{schema.__name__}"
        try:
            response = self._client.messages.create(
                model=use_model,
                system=system,
                messages=[{"role": "user", "content": user}],
                max_tokens=max_tokens,
                tools=[
                    {
                        "name": tool_name,
                        "description": (
                            f"Emit a {schema.__name__} payload. Call this tool "
                            "exactly once with all required fields populated."
                        ),
                        "input_schema": schema.model_json_schema(),
                    }
                ],
                tool_choice={"type": "tool", "name": tool_name},
            )
        except Exception as exc:
            _logger.warning(
                "Anthropic structured call transport failed (%s): %s",
                schema.__name__,
                exc,
            )
            return None

        usage = getattr(response, "usage", None)
        if usage is not None:
            guard.record_anthropic(
                model=use_model,
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            )

        # Find the tool_use block. Anthropic returns a list of content blocks;
        # for tool_choice={"type":"tool",...} the model is supposed to emit
        # exactly one tool_use. Walk the list defensively — the SDK may also
        # return text blocks alongside (explanations) that we ignore.
        blocks = getattr(response, "content", None) or []
        payload: dict[str, Any] | None = None
        for block in blocks:
            if getattr(block, "type", None) != "tool_use":
                continue
            if getattr(block, "name", None) != tool_name:
                continue
            candidate = getattr(block, "input", None)
            if isinstance(candidate, dict) and candidate:
                payload = candidate
                break

        if payload is None:
            # No tool_use block, or the model called the tool with an empty
            # input dict. Anthropic surfaces schema refusals this way — the
            # model is declining mid-generation. Treat as validation failure.
            _logger.warning(
                "Anthropic structured call refused schema (%s)",
                schema.__name__,
            )
            return None

        try:
            return schema.model_validate(payload)
        except ValidationError as exc:
            _logger.warning(
                "Anthropic structured call failed schema (%s): %s",
                schema.__name__,
                exc,
            )
            return None


def default_client() -> LLMClient | None:
    """Return a real client based on ``BRIARWOOD_AGENT_PROVIDER``.

    AUDIT 1.3.4: defaults to OpenAI so existing behavior is preserved.
    Setting the env to ``anthropic`` switches to Claude iff ``ANTHROPIC_API_KEY``
    is set; if the Anthropic SDK isn't installed or the key is missing we
    fall through to OpenAI rather than returning ``None`` so one-off
    mis-configuration doesn't silently disable the agent.
    """
    provider = os.environ.get("BRIARWOOD_AGENT_PROVIDER", "openai").strip().lower()
    if provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return AnthropicChatClient()
        except Exception as exc:
            _logger.warning("Anthropic client init failed, falling back to OpenAI: %s", exc)
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    try:
        return OpenAIChatClient()
    except Exception:
        return None
