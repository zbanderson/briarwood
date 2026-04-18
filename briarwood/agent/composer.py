from __future__ import annotations

import json
from typing import Callable

from briarwood.agent.llm import LLMClient


def compose_structured_response(
    *,
    llm: LLMClient | None,
    system: str,
    user: str,
    fallback: Callable[[], str],
    max_tokens: int = 280,
) -> str:
    """Use the LLM as a renderer over structured facts, with a deterministic fallback."""
    if llm is None:
        return fallback()
    try:
        rendered = llm.complete(system=system, user=user, max_tokens=max_tokens).strip()
    except Exception:
        rendered = ""
    return rendered or fallback()


def compose_contract_response(
    *,
    llm: LLMClient | None,
    contract_type: str,
    payload: dict[str, object],
    system: str,
    fallback: Callable[[], str],
    max_tokens: int = 320,
) -> str:
    """Render a contract payload through the LLM without letting it invent data."""
    return compose_structured_response(
        llm=llm,
        system=system,
        user=f"contract_type: {contract_type}\npayload_json: {json.dumps(payload, default=str, sort_keys=True)}",
        fallback=fallback,
        max_tokens=max_tokens,
    )


__all__ = ["compose_structured_response", "compose_contract_response"]
