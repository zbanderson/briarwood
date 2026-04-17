"""Tests for the Representation Agent (claims validation).

Covers both the deterministic fallback path (no LLM wired) and the
LLM-backed path with a stub client, including malformed-JSON handling.
"""

from __future__ import annotations

import json
from typing import Any

from briarwood.pipeline.representation import RepresentationAgent
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

    agent = RepresentationAgent(llm_client=None)
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

    agent = RepresentationAgent(llm_client=None)
    result = agent.validate(session)

    assert result["claims"] == []
    assert "No decision claims" in result["summary"]


class _ScriptedLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict[str, str]] = []

    def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
        self.calls.append({"system": system, "user": user})
        return self.response


def test_llm_happy_path_returns_structured_claims() -> None:
    payload = {
        "claims": [
            {
                "text": "Cap rate projected at 0.065; cash flow 842.",
                "supported": True,
                "evidence_refs": ["income_model"],
                "confidence": 0.91,
            },
            {
                "text": "Base path holds.",
                "supported": False,
                "evidence_refs": [],
                "confidence": 0.4,
            },
        ],
        "summary": "1/2 claims backed.",
    }
    llm = _ScriptedLLM(json.dumps(payload))
    session = _session_with_decision(
        model_outputs={"income_model": {"cap_rate": 0.065}},
    )

    agent = RepresentationAgent(llm_client=llm)
    result = agent.validate(session)

    assert llm.calls, "LLM should have been called"
    assert len(result["claims"]) == 2
    assert result["claims"][0]["supported"] is True
    assert result["claims"][0]["evidence_refs"] == ["income_model"]
    assert result["summary"] == "1/2 claims backed."


def test_llm_malformed_json_falls_back_to_deterministic() -> None:
    llm = _ScriptedLLM("not json at all {{")
    session = _session_with_decision(
        rationale="Cap rate 0.065 on 500000 purchase.",
        model_outputs={"income_model": {"cap_rate": 0.065, "purchase_price": 500000}},
    )

    agent = RepresentationAgent(llm_client=llm)
    result = agent.validate(session)

    assert llm.calls, "LLM should have been attempted"
    # Deterministic fallback still produces a valid shape.
    assert isinstance(result["claims"], list)
    assert result["claims"]
    assert any(c["supported"] for c in result["claims"])


def test_llm_fenced_json_is_unwrapped() -> None:
    payload = {
        "claims": [
            {
                "text": "Base path holds.",
                "supported": False,
                "evidence_refs": [],
                "confidence": 0.3,
            }
        ],
        "summary": "0/1",
    }
    llm = _ScriptedLLM("```json\n" + json.dumps(payload) + "\n```")
    session = _session_with_decision()

    agent = RepresentationAgent(llm_client=llm)
    result = agent.validate(session)

    assert len(result["claims"]) == 1
    assert result["claims"][0]["supported"] is False
