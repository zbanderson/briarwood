"""End-to-end integration test for the pipeline reconciliation layer.

Exercises Intent → Parser → Triage → Specialist Models → Unified → Decision
→ Feedback → Eval using the new Pipeline coordinator, with a mix of real
and stub specialist models. Verifies the session is correctly populated at
each stage and that the eval harness runs cleanly over the resulting log.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from briarwood.eval.harness import run_eval
from briarwood.modules.security_model import SecurityModel
from briarwood.pipeline import (
    FeedbackLogger,
    Pipeline,
    PipelineSession,
    TriageAgent,
    UnifiedIntelligenceAgent,
)


class StubIncomeModel:
    name = "income_model"

    def run(self, property_input: dict[str, Any]) -> dict[str, Any]:
        price = float(property_input.get("purchase_price") or 500_000)
        rent = float(property_input.get("estimated_monthly_rent") or 3_000)
        cap = (rent * 12 * 0.65) / price if price else 0
        return {
            "data": {
                "cap_rate": round(cap, 4),
                "monthly_cash_flow": round(rent - 2400, 2),
                "gross_yield": round((rent * 12) / price, 4) if price else 0,
            },
            "confidence": 0.72,
            "warnings": [],
        }


class StubRiskModel:
    name = "risk_model"

    def run(self, property_input: dict[str, Any]) -> dict[str, Any]:
        flood = str(property_input.get("flood_risk") or "").lower()
        score = 80 if flood in ("", "low", "minimal") else 45
        return {
            "data": {"score": score, "risk_flags": []},
            "confidence": 0.65,
            "warnings": [],
        }


class StubLocationModel:
    name = "location_model"

    def run(self, property_input: dict[str, Any]) -> dict[str, Any]:
        return {
            "data": {"proximity_score": 88, "walkability": 72},
            "confidence": 0.8,
            "warnings": [],
        }


class StubScenarioModule:
    name = "bull_base_bear"

    def run(self, property_input: dict[str, Any]) -> dict[str, Any]:
        price = float(property_input.get("purchase_price") or 500_000)
        return {
            "data": {
                "bull_case_value": round(price * 1.25, 2),
                "base_case_value": round(price * 1.10, 2),
                "bear_case_value": round(price * 0.92, 2),
            },
            "confidence": 0.55,
            "warnings": [],
        }


@pytest.fixture
def sandbox_pipeline(tmp_path: Path) -> Pipeline:
    """Pipeline pointed at a tmp_path feedback file so tests don't pollute data/."""

    feedback_file = tmp_path / "intelligence_feedback.jsonl"
    logger = FeedbackLogger(path=feedback_file)
    specialists = {
        "income_model": StubIncomeModel(),
        "risk_model": StubRiskModel(),
        "location_model": StubLocationModel(),
        "security_model": SecurityModel(),
        "bull_base_bear": StubScenarioModule(),
    }
    return Pipeline(
        specialists=specialists,
        triage=TriageAgent(runner=lambda ctx: {}),
        unified=UnifiedIntelligenceAgent(),
        feedback_logger=logger,
    )


def test_pipeline_runs_all_layers(sandbox_pipeline: Pipeline) -> None:
    session = sandbox_pipeline.run(
        raw_intent="buy and rent near the beach with a 5% cap",
        parsed_intent={
            "intent_type": "hybrid",
            "question_focus": ["future_income", "should_i_buy"],
            "occupancy_type": "investor",
        },
        property_data={
            "purchase_price": 620_000,
            "estimated_monthly_rent": 3_400,
            "town": "Belmar",
            "state": "NJ",
            "flood_risk": "low",
        },
        property_id="belmar-demo",
    )

    assert isinstance(session, PipelineSession)
    assert session.session_id
    assert session.parser_output["intent_type"] == "hybrid"

    # Layer 04: each specialist produced an output
    for expected in ("income_model", "risk_model", "location_model", "security_model"):
        assert expected in session.model_outputs, f"missing {expected}"

    # Scenario Model adapter merged the bull_base_bear output
    assert "scenario_model" in session.model_outputs
    scen = session.model_outputs["scenario_model"].data
    assert scen["base_case_value"] is not None

    # Layer 05: synthesis populated with coherence + chart routes
    assert session.synthesis, "synthesis missing"
    assert session.synthesis["model_count"] >= 4
    assert session.synthesis["chart_routes"], "chart_routes should not be empty"
    kinds = {r["kind"] for r in session.synthesis["chart_routes"]}
    assert kinds & {"line_area", "bar_compare", "radar_score", "geo_map"}

    # Layer 06: decision populated with scenarios and risk flags
    assert session.decision["primary_recommendation"]
    assert len(session.decision["scenarios"]) >= 1
    assert isinstance(session.decision["risk_flags"], list)

    # Contribution map covers all contributing models
    assert set(session.contribution_map).issuperset(set(session.model_outputs))
    total = sum(session.contribution_map.values())
    assert 0.99 <= total <= 1.01, f"contribution_map should sum to ~1.0, got {total}"


def test_pipeline_writes_feedback(sandbox_pipeline: Pipeline, tmp_path: Path) -> None:
    session = sandbox_pipeline.run(
        raw_intent="is this a buy?",
        parsed_intent={"intent_type": "buy_decision"},
        property_data={"purchase_price": 450_000, "town": "Belmar", "state": "NJ"},
    )
    sandbox_pipeline.record_feedback(session, explicit_signal="accepted", outcome="aligned")

    feedback_path = sandbox_pipeline.feedback.path
    assert feedback_path.exists(), f"expected feedback file at {feedback_path}"

    rows = [json.loads(line) for line in feedback_path.read_text().splitlines() if line.strip()]
    assert len(rows) >= 1
    last = rows[-1]
    assert last["session_id"] == session.session_id
    assert last["explicit_signal"] == "accepted"
    assert last["outcome"] == "aligned"
    assert "contribution_map" in last
    assert last["contribution_map"]
    # Every contributing model appears in the map
    assert set(last["contribution_map"]).issuperset(set(session.model_outputs))


def test_eval_harness_runs(sandbox_pipeline: Pipeline, tmp_path: Path) -> None:
    # Produce two sessions with opposing signals so the harness has
    # something to score against.
    s1 = sandbox_pipeline.run(
        raw_intent="analyze this",
        parsed_intent={"intent_type": "buy_decision"},
        property_data={"purchase_price": 500_000, "town": "Belmar", "state": "NJ"},
    )
    sandbox_pipeline.record_feedback(s1, explicit_signal="accepted", outcome="aligned")

    s2 = sandbox_pipeline.run(
        raw_intent="should I pass on this?",
        parsed_intent={"intent_type": "buy_decision"},
        property_data={"purchase_price": 800_000, "town": "Belmar", "state": "NJ",
                       "flood_risk": "high"},
    )
    sandbox_pipeline.record_feedback(s2, explicit_signal="rejected", outcome="diverged")

    output_log = tmp_path / "model_performance_log.jsonl"
    result = run_eval(
        feedback_path=sandbox_pipeline.feedback.path,
        output_path=output_log,
    )

    assert result["sessions_scanned"] >= 2
    assert result["models_scored"] >= 4
    assert output_log.exists()
    assert output_log.stat().st_size > 0

    scorecards = result["scorecards"]
    models_scored = {sc["model"] for sc in scorecards}
    assert {"income_model", "risk_model", "location_model", "security_model"} & models_scored
