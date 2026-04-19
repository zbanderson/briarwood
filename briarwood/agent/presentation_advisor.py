from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from api.prompts import load_prompt
from briarwood.agent.composer import compose_contract_response
from briarwood.agent.llm import LLMClient


class SectionAdvice(BaseModel):
    """Bounded presentation guidance for one visual section.

    All fields are optional — advisor may skip sections it has nothing to add
    for. `preferred_surface` is a closed enum; the strict JSON-schema call
    rejects anything outside the choices at the API level."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    summary: str | None = None
    companion: str | None = None
    preferred_surface: Literal["chart_first", "table_first", "card_first"] | None = None


class VisualAdvice(BaseModel):
    """Strict schema for `advise_visual_surfaces`.

    AUDIT 1.2.2: replaces hand-rolled `_parse_visual_advice` (strip fences,
    whitelist keys, whitelist enum values). The schema bakes those invariants
    into the JSON contract itself."""

    model_config = ConfigDict(extra="forbid")

    value: SectionAdvice | None = None
    cma: SectionAdvice | None = None
    rent: SectionAdvice | None = None
    scenario: SectionAdvice | None = None
    risk: SectionAdvice | None = None
    trust: SectionAdvice | None = None


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
        advice = llm.complete_structured(
            system=load_prompt("visual_advisor"),
            user=f"payload_json: {payload!r}",
            schema=VisualAdvice,
            max_tokens=600,
        )
    except Exception:
        return None
    if advice is None:
        return None
    return _flatten_advice(advice)


def _flatten_advice(advice: VisualAdvice) -> dict[str, dict[str, str]] | None:
    """Convert the Pydantic instance into the `{section: {field: str}}` shape
    callers expect. Sections with no populated fields are dropped."""
    out: dict[str, dict[str, str]] = {}
    for section_name, section in advice.model_dump(exclude_none=True).items():
        if not isinstance(section, dict):
            continue
        cleaned = {
            key: value.strip()
            for key, value in section.items()
            if isinstance(value, str) and value.strip()
        }
        if cleaned:
            out[section_name] = cleaned
    return out or None


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


__all__ = [
    "SectionAdvice",
    "VisualAdvice",
    "advise_visual_surfaces",
    "compose_browse_surface",
    "compose_section_followup",
]
