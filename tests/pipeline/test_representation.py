"""Tests for the ClaimEvidenceValidator (decision-claims validation).

Covers both the deterministic fallback path (no LLM wired) and the
LLM-backed path with a stub client. After AUDIT 1.2.2 the LLM path goes
through `complete_structured` + Pydantic, so fakes return either a
validated `RepresentationResponse` or `None` to simulate strict-mode failure.

Renamed from ``RepresentationAgent`` in Handoff 2a Piece 5B (2026-04-24) to
disambiguate from the chart-selection ``RepresentationAgent`` at
``briarwood/representation/agent.py``.
"""

from __future__ import annotations

from typing import Any

from briarwood.pipeline.representation import (
    ClaimEvidenceValidator,
    RepresentationClaim,
    RepresentationResponse,
)
from briarwood.pipeline.session import PipelineSession


def _session_with_decision(
    *,
    rationale: str = "Expected cap rate 0.065 with monthly cash flow of 842.",
    scenarios: list[dict[str, Any]] | None = None,
    model_outputs: dict[str, dict[str, Any]] | None = None,
    decision_rationale: str = "",
) -> PipelineSession:
    session = PipelineSession(raw_intent="test")
    session.decision = {
        "primary_recommendation": {"strategy": "favorable", "rationale": rationale},
        "scenarios": scenarios
        or [
            {"label": "A", "tag": "base_case", "description": "Base path holds."},
        ],
    }
    session.decision_rationale = decision_rationale
    for name, data in (model_outputs or {}).items():
        session.record_model_output(name, data, confidence=0.7)
    return session


def test_deterministic_fallback_without_llm() -> None:
    session = _session_with_decision(
        rationale="Cap rate projected at 0.065; cash flow 842.",
        model_outputs={
            "income_model": {"cap_rate": 0.065, "monthly_cash_flow": 842},
            "risk_model": {"score": 80},
        },
    )

    agent = ClaimEvidenceValidator(llm_client=None)
    result = agent.validate(session)

    assert result is session.representation
    assert result["claims"], "should produce at least one claim entry"
    supported = [c for c in result["claims"] if c["supported"]]
    assert supported, "numeric-token match should flag at least one claim supported"
    assert any("income_model" in c["evidence_refs"] for c in supported)
    assert result["summary"].endswith("claims backed by specialist evidence.")


def test_no_claims_when_decision_empty() -> None:
    session = PipelineSession(raw_intent="test")
    session.decision = {"primary_recommendation": {"rationale": ""}, "scenarios": []}

    agent = ClaimEvidenceValidator(llm_client=None)
    result = agent.validate(session)

    assert result["claims"] == []
    assert "No decision claims" in result["summary"]


class _ScriptedLLM:
    """AUDIT 1.2.2: structured path. Returns a pre-baked `RepresentationResponse`
    (or `None` to simulate strict-mode / transport failure)."""

    def __init__(self, response: RepresentationResponse | None) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
        raise AssertionError("representation agent must go through complete_structured")

    def complete_structured(self, *, system, user, schema, model=None, max_tokens=600):
        self.calls.append({"system": system, "user": user, "schema": schema.__name__})
        return self._response


def test_llm_happy_path_returns_structured_claims() -> None:
    response = RepresentationResponse(
        claims=[
            RepresentationClaim(
                text="Cap rate projected at 0.065; cash flow 842.",
                supported=True,
                evidence_refs=["income_model"],
                confidence=0.91,
            ),
            RepresentationClaim(
                text="Base path holds.",
                supported=False,
                evidence_refs=[],
                confidence=0.4,
            ),
        ],
        summary="1/2 claims backed.",
    )
    llm = _ScriptedLLM(response)
    session = _session_with_decision(
        model_outputs={"income_model": {"cap_rate": 0.065}},
    )

    agent = ClaimEvidenceValidator(llm_client=llm)
    result = agent.validate(session)

    assert llm.calls, "LLM should have been called"
    assert len(result["claims"]) == 2
    assert result["claims"][0]["supported"] is True
    assert result["claims"][0]["evidence_refs"] == ["income_model"]
    assert result["summary"] == "1/2 claims backed."


def test_llm_failure_falls_back_to_deterministic() -> None:
    """Strict-mode failure (schema violation, transport error, empty output)
    surfaces as `None` from complete_structured. Agent must route to the
    deterministic fallback."""
    llm = _ScriptedLLM(response=None)
    session = _session_with_decision(
        rationale="Cap rate 0.065 on 500000 purchase.",
        model_outputs={"income_model": {"cap_rate": 0.065, "purchase_price": 500000}},
    )

    agent = ClaimEvidenceValidator(llm_client=llm)
    result = agent.validate(session)

    assert llm.calls, "LLM should have been attempted"
    # Deterministic fallback still produces a valid shape.
    assert isinstance(result["claims"], list)
    assert result["claims"]
    assert any(c["supported"] for c in result["claims"])


def test_confidence_is_clamped_to_unit_interval() -> None:
    """Pydantic allows `confidence` through as a float; downstream clamp
    guarantees [0, 1] even if the LLM reports an out-of-range value."""
    response = RepresentationResponse(
        claims=[
            RepresentationClaim(
                text="Cap rate 0.065.",
                supported=True,
                evidence_refs=["income_model"],
                confidence=1.7,
            )
        ],
        summary="",
    )
    llm = _ScriptedLLM(response)
    session = _session_with_decision(
        model_outputs={"income_model": {"cap_rate": 0.065}},
    )
    result = ClaimEvidenceValidator(llm_client=llm).validate(session)
    assert result["claims"][0]["confidence"] == 1.0


def test_empty_claims_synthesizes_unsupported_fallback() -> None:
    """If the LLM returns a well-formed but empty claim list, we backfill
    with the original rationale marked unsupported — upstream can then
    detect 'nothing usable' and escalate."""
    llm = _ScriptedLLM(RepresentationResponse(claims=[], summary=""))
    session = _session_with_decision()
    result = ClaimEvidenceValidator(llm_client=llm).validate(session)
    assert result["claims"], "fallback claims should be synthesized"
    assert all(c["supported"] is False for c in result["claims"])
