"""Claim evidence validator — validates decision claims against per-model evidence.

Renamed from ``RepresentationAgent`` in Handoff 2a Piece 5B (2026-04-24).
Distinct from the chart-selection ``RepresentationAgent`` at
``briarwood/representation/agent.py`` (the Layer-4 concept in
``GAP_ANALYSIS.md``); this module does not plan charts.

Consumes the Decision output + per-model evidence on the session and
produces a claim-by-claim validation report:

    {
      "claims": [
        {"text": str, "supported": bool,
         "evidence_refs": list[str], "confidence": float},
        ...
      ],
      "summary": str,
    }

Operates in one of two modes:

  - **LLM mode** (when an LLMClient is provided): a single call asks the
    model to inspect each candidate claim against the evidence pool and
    return structured JSON.
  - **Deterministic fallback** (when no client is available, or when the
    LLM returns malformed JSON): numeric-token match — any number in a
    claim that also appears in the evidence pool marks the claim as
    supported, with the owning model_names as evidence_refs.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from briarwood.agent.llm import LLMClient
from briarwood.pipeline.session import PipelineSession


_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")


class RepresentationClaim(BaseModel):
    """One validated claim. `confidence` is clamped to [0, 1] downstream."""

    model_config = ConfigDict(extra="forbid")

    text: str
    supported: bool
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = 0.5


class RepresentationResponse(BaseModel):
    """Strict schema for claim validation against evidence.

    AUDIT 1.2.2: replaces hand-rolled JSON parsing + normalization with a
    declared Pydantic shape. Fence-wrapped JSON no longer needs string
    surgery — the strict API mode returns a clean object."""

    model_config = ConfigDict(extra="forbid")

    claims: list[RepresentationClaim] = Field(default_factory=list)
    summary: str = ""


class ClaimEvidenceValidator:
    name = "claim_evidence_validator"

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client

    def validate(self, session: PipelineSession) -> dict[str, Any]:
        claims = _extract_claims(session)
        evidence = _build_evidence_pool(session)

        if self._llm is not None:
            llm_result = self._validate_with_llm(claims, evidence)
            if llm_result is not None:
                session.representation = llm_result
                return llm_result

        fallback = _deterministic_fallback(claims, evidence)
        session.representation = fallback
        return fallback

    def _validate_with_llm(
        self,
        claims: list[str],
        evidence: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not claims:
            return {"claims": [], "summary": "No decision claims to validate."}

        payload = {"claims": claims, "evidence": evidence}
        try:
            result = self._llm.complete_structured(
                system=(
                    "You validate factual claims against specialist model "
                    "evidence. For each claim, decide whether any evidence "
                    "entry supports it and list the owning model names as "
                    "evidence_refs. confidence is a float in [0, 1]."
                ),
                user=json.dumps(payload, default=str),
                schema=RepresentationResponse,
                max_tokens=500,
            )
        except Exception:
            return None

        if result is None:
            return None
        return _normalize_representation(result, claims)


def _extract_claims(session: PipelineSession) -> list[str]:
    decision = session.decision or {}
    claims: list[str] = []

    primary = decision.get("primary_recommendation") or {}
    rationale = primary.get("rationale")
    if isinstance(rationale, str) and rationale.strip():
        claims.append(rationale.strip())

    for scenario in decision.get("scenarios") or []:
        if not isinstance(scenario, dict):
            continue
        description = scenario.get("description")
        if isinstance(description, str) and description.strip():
            claims.append(description.strip())

    decision_rationale = session.decision_rationale
    if isinstance(decision_rationale, str) and decision_rationale.strip():
        claims.append(decision_rationale.strip())

    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for claim in claims:
        if claim in seen:
            continue
        seen.add(claim)
        unique.append(claim)
    return unique


def _build_evidence_pool(session: PipelineSession) -> dict[str, dict[str, Any]]:
    return {
        name: dict(result.data)
        for name, result in session.model_outputs.items()
    }


def _deterministic_fallback(
    claims: list[str],
    evidence: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    evidence_numbers = _index_evidence_numbers(evidence)

    validated: list[dict[str, Any]] = []
    supported_count = 0
    for claim in claims:
        numbers = _NUMBER_PATTERN.findall(claim)
        refs: list[str] = []
        for token in numbers:
            owners = evidence_numbers.get(token) or []
            for owner in owners:
                if owner not in refs:
                    refs.append(owner)
        supported = bool(refs)
        if supported:
            supported_count += 1
        validated.append(
            {
                "text": claim,
                "supported": supported,
                "evidence_refs": refs,
                "confidence": 0.6 if supported else 0.3,
            }
        )

    total = len(validated)
    summary = (
        f"{supported_count}/{total} claims backed by specialist evidence."
        if total
        else "No decision claims to validate."
    )
    return {"claims": validated, "summary": summary}


def _index_evidence_numbers(
    evidence: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for model_name, data in evidence.items():
        for token in _iter_numeric_tokens(data):
            owners = index.setdefault(token, [])
            if model_name not in owners:
                owners.append(model_name)
    return index


def _iter_numeric_tokens(value: Any) -> list[str]:
    tokens: list[str] = []
    if isinstance(value, bool):
        return tokens
    if isinstance(value, (int, float)):
        tokens.append(_format_number(value))
        return tokens
    if isinstance(value, str):
        tokens.extend(_NUMBER_PATTERN.findall(value))
        return tokens
    if isinstance(value, dict):
        for v in value.values():
            tokens.extend(_iter_numeric_tokens(v))
        return tokens
    if isinstance(value, (list, tuple, set)):
        for v in value:
            tokens.extend(_iter_numeric_tokens(v))
    return tokens


def _format_number(value: int | float) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _normalize_representation(
    result: RepresentationResponse,
    fallback_claims: list[str],
) -> dict[str, Any]:
    """Apply post-validation invariants the schema alone can't express:
    trim text, clamp confidence, drop empty-text entries, backfill summary
    from counts, and synthesize an unsupported-claims payload when the LLM
    returned an empty list (so callers can detect 'nothing usable' and
    route to the deterministic fallback upstream)."""

    normalized: list[dict[str, Any]] = []
    for claim in result.claims:
        text = claim.text.strip()
        if not text:
            continue
        normalized.append(
            {
                "text": text,
                "supported": claim.supported,
                "evidence_refs": list(claim.evidence_refs),
                "confidence": max(0.0, min(1.0, float(claim.confidence))),
            }
        )

    summary = result.summary.strip()
    if not summary:
        supported = sum(1 for c in normalized if c["supported"])
        summary = (
            f"{supported}/{len(normalized)} claims backed by specialist evidence."
            if normalized
            else "No decision claims to validate."
        )

    if not normalized and fallback_claims:
        # LLM returned no usable claims — treat as failure for fallback upstream.
        return {
            "claims": [
                {
                    "text": claim,
                    "supported": False,
                    "evidence_refs": [],
                    "confidence": 0.3,
                }
                for claim in fallback_claims
            ],
            "summary": summary,
        }

    return {"claims": normalized, "summary": summary}


__all__ = ["ClaimEvidenceValidator"]
