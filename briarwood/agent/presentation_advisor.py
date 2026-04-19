from __future__ import annotations

import json
from typing import Any

from api.prompts import load_prompt
from briarwood.agent.composer import compose_contract_response
from briarwood.agent.llm import LLMClient

_VISUAL_SECTIONS = {"value", "cma", "rent", "scenario", "risk", "trust"}
_SURFACE_CHOICES = {"chart_first", "table_first", "card_first"}


def compose_browse_surface(
    *,
    llm: LLMClient | None,
    payload: dict[str, Any],
    fallback: str,
) -> tuple[str, dict[str, Any] | None]:
    """Use the LLM to turn a browse payload into a sharper first-impression summary.

    The payload is still Briarwood-native truth. OpenAI only improves the
    framing and readability.
    """

    return compose_contract_response(
        llm=llm,
        contract_type="browse_surface",
        payload=payload,
        system=load_prompt("browse_surface"),
        fallback=lambda: fallback,
        max_tokens=320,
        structured_inputs=payload,
        tier="browse_surface",
    )


def advise_visual_surfaces(
    *,
    llm: LLMClient | None,
    payload: dict[str, Any],
) -> dict[str, dict[str, str]] | None:
    """Ask OpenAI for bounded presentation guidance per visible section.

    The advisor may recommend titles, summaries, and companion explanations
    from a fixed menu of sections and surface preferences. It never chooses
    numbers or creates new analytical conclusions.
    """

    if llm is None or not payload:
        return None
    try:
        raw = llm.complete(
            system=load_prompt("visual_advisor"),
            user=f"payload_json: {json.dumps(payload, sort_keys=True, default=str)}",
            max_tokens=600,
        ).strip()
    except Exception:
        return None
    return _parse_visual_advice(raw)


def compose_section_followup(
    *,
    llm: LLMClient | None,
    section: str,
    question: str,
    payload: dict[str, Any],
    fallback: str,
) -> tuple[str, dict[str, Any] | None]:
    """Render a targeted drill-down answer for one surfaced section.

    Briarwood still determines the underlying facts and metrics. OpenAI is used
    only to explain that bounded payload in a sharper, more human way.
    """

    followup_payload = {
        "section": section,
        "question": question,
        "section_payload": payload,
    }
    return compose_contract_response(
        llm=llm,
        contract_type=f"{section}_followup",
        payload=followup_payload,
        system=load_prompt("section_followup"),
        fallback=lambda: fallback,
        max_tokens=260,
        structured_inputs=followup_payload,
        tier=f"{section}_followup",
    )


def _parse_visual_advice(raw: str) -> dict[str, dict[str, str]] | None:
    if not raw:
        return None
    candidate = raw.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:]
        candidate = candidate.strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    out: dict[str, dict[str, str]] = {}
    for key, value in parsed.items():
        if key not in _VISUAL_SECTIONS or not isinstance(value, dict):
            continue
        normalized: dict[str, str] = {}
        for field in ("title", "summary", "companion", "preferred_surface"):
            field_value = value.get(field)
            if not isinstance(field_value, str) or not field_value.strip():
                continue
            cleaned = field_value.strip()
            if field == "preferred_surface" and cleaned not in _SURFACE_CHOICES:
                continue
            normalized[field] = cleaned
        if normalized:
            out[key] = normalized
    return out or None


__all__ = [
    "advise_visual_surfaces",
    "compose_browse_surface",
    "compose_section_followup",
]
