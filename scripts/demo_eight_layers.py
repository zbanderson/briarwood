"""Walk a single query end-to-end through all 8 pipeline layers.

Prints each layer's output, writes chart HTML artifacts to
``outputs/demo/<session_id>/``, and exercises the feedback + eval
harness loop. Runs cleanly whether or not ``OPENAI_API_KEY`` is set —
narration overlays and Representation fall back to deterministic
output when no LLM client is available.

Usage:
    python scripts/demo_eight_layers.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from briarwood.agent.llm import default_client
from briarwood.agent.router import classify
from briarwood.charts import render_from_route
from briarwood.eval.harness import run_eval
from briarwood.modules.security_model import SecurityModel
from briarwood.pipeline import (
    FeedbackLogger,
    Pipeline,
    TriageAgent,
    UnifiedIntelligenceAgent,
)


RAW_INTENT = "buy and rent near the beach, 5% cap, low risk"
PROPERTY_DATA = {
    "purchase_price": 620_000,
    "estimated_monthly_rent": 3_400,
    "town": "Belmar",
    "state": "NJ",
    "flood_risk": "low",
}


class _StubIncomeModel:
    name = "income_model"

    def run(self, property_input: dict[str, Any]) -> dict[str, Any]:
        price = float(property_input.get("purchase_price") or 0)
        rent = float(property_input.get("estimated_monthly_rent") or 0)
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


class _StubRiskModel:
    name = "risk_model"

    def run(self, property_input: dict[str, Any]) -> dict[str, Any]:
        flood = str(property_input.get("flood_risk") or "").lower()
        score = 80 if flood in ("", "low", "minimal") else 45
        return {
            "data": {"score": score, "risk_flags": []},
            "confidence": 0.65,
            "warnings": [],
        }


class _StubLocationModel:
    name = "location_model"

    def run(self, property_input: dict[str, Any]) -> dict[str, Any]:
        return {
            "data": {"proximity_score": 88, "walkability": 72},
            "confidence": 0.80,
            "warnings": [],
        }


class _StubScenarioModule:
    name = "bull_base_bear"

    def run(self, property_input: dict[str, Any]) -> dict[str, Any]:
        price = float(property_input.get("purchase_price") or 0)
        return {
            "data": {
                "bull_case_value": round(price * 1.25, 2),
                "base_case_value": round(price * 1.10, 2),
                "bear_case_value": round(price * 0.92, 2),
            },
            "confidence": 0.55,
            "warnings": [],
        }


def _banner(n: int, title: str) -> None:
    print()
    print(f"=== Layer {n:02d} — {title} ===")


def _dump(label: str, payload: Any) -> None:
    print(f"{label}:")
    print(json.dumps(payload, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Force deterministic mode — skip all LLM calls even when OPENAI_API_KEY is set.",
    )
    args = parser.parse_args()

    llm_client = None if args.no_llm else default_client()
    print(f"LLM client resolved to: {type(llm_client).__name__ if llm_client else 'None (deterministic fallbacks)'}")

    # Layer 01 — Intent capture
    _banner(1, "Intent")
    print(f"raw_intent: {RAW_INTENT!r}")

    # Layer 02 — Parser / Router
    _banner(2, "Intent Parser / Router")
    decision = classify(RAW_INTENT, client=llm_client)
    parser_output = {
        "intent_type": "hybrid",
        "question_focus": ["future_income", "should_i_buy"],
        "occupancy_type": "investor",
        "router_answer_type": decision.answer_type.value,
        "router_confidence": decision.confidence,
        "router_target_refs": list(decision.target_refs),
        "router_reason": decision.reason,
    }
    _dump("parser_output", parser_output)

    # Pipeline setup
    output_root = Path("outputs/demo")
    output_root.mkdir(parents=True, exist_ok=True)
    feedback_path = output_root / "intelligence_feedback.jsonl"
    perf_log_path = output_root / "model_performance_log.jsonl"

    logger = FeedbackLogger(path=feedback_path)
    specialists = {
        "income_model": _StubIncomeModel(),
        "risk_model": _StubRiskModel(),
        "location_model": _StubLocationModel(),
        "security_model": SecurityModel(),
        "bull_base_bear": _StubScenarioModule(),
    }
    pipeline = Pipeline(
        specialists=specialists,
        triage=TriageAgent(runner=lambda ctx: {}, llm_client=llm_client),
        unified=UnifiedIntelligenceAgent(llm_client=llm_client),
        feedback_logger=logger,
        llm_client=llm_client,
    )

    session = pipeline.run(
        raw_intent=RAW_INTENT,
        parsed_intent=parser_output,
        property_data=PROPERTY_DATA,
        property_id="belmar-demo",
    )

    # Layer 03 — Triage (fan-out)
    _banner(3, "Triage Agent")
    _dump("contribution_map", session.contribution_map)
    print(f"triage_narrative: {session.triage_narrative or '(deterministic: narrative skipped)'}")

    # Layer 04 — Specialty Models
    _banner(4, "Specialist Models")
    model_summary = {
        name: {
            "confidence": result.confidence,
            "warnings": result.warnings,
            "data_keys": sorted(result.data.keys()),
        }
        for name, result in session.model_outputs.items()
    }
    _dump("model_outputs", model_summary)

    # Layer 05 — Unified Intelligence + chart artifacts
    _banner(5, "Unified Intelligence")
    _dump("synthesis", session.synthesis)
    artifacts_dir = output_root / session.session_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for route in session.synthesis.get("chart_routes") or []:
        try:
            artifact = render_from_route(route, session)
        except Exception as exc:
            print(f"  [skip] chart {route.get('kind')}: {exc}")
            continue
        path = artifacts_dir / f"{route['kind']}.html"
        path.write_text(artifact.html)
        written.append(str(path))
    print(f"chart_artifacts_written: {written}")

    # Layer 06 — Decision
    _banner(6, "Decision Agent")
    _dump("decision", session.decision)
    print(f"decision_rationale: {session.decision_rationale or '(deterministic)'}")

    # Layer 06.5 / 07 — Representation Agent
    _banner(7, "Representation Agent")
    _dump("representation", session.representation)

    # Layer 08 — Feedback
    _banner(8, "Feedback Logger")
    pipeline.record_feedback(session, explicit_signal="accepted", outcome="aligned")
    last_line = feedback_path.read_text().splitlines()[-1]
    _dump("feedback_row", json.loads(last_line))

    # Eval pass — closes the loop for Triage's dynamic weights
    _banner(9, "Eval Harness (closes the loop)")
    result = run_eval(feedback_path=feedback_path, output_path=perf_log_path)
    print(f"sessions_scanned: {result['sessions_scanned']}")
    print(f"models_scored: {result['models_scored']}")
    if result["scorecards"]:
        _dump("scorecard_sample", result["scorecards"][0])


if __name__ == "__main__":
    main()
