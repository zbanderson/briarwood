"""ModelSpec definitions for each specialist model.

Each spec declares:
- how to invoke the model (PropertyInput → {data, confidence, warnings})
- numeric bounds for accuracy checks
- sensitivities (expected directional responses)
- explainability + decision-question field maps
- which input fields should drop confidence when removed

The adapter `_wrap(module)` normalizes the ModuleResult pydantic objects real
modules emit into the flat {data, confidence, warnings} dict the criteria
functions expect.
"""

from __future__ import annotations

from typing import Any, Callable

from briarwood.eval.model_quality.types import (
    DecisionQuestionMap,
    ModelSpec,
    Sensitivity,
)
from briarwood.modules.bull_base_bear import BullBaseBearModule
from briarwood.modules.income_support import IncomeSupportModule
from briarwood.modules.location_intelligence import LocationIntelligenceModule
from briarwood.modules.renovation_scenario import RenovationScenarioModule
from briarwood.modules.risk_constraints import RiskConstraintsModule
from briarwood.modules.security_model import SecurityModel
from briarwood.modules.teardown_scenario import TeardownScenarioModule
from briarwood.modules.town_county_outlook import TownCountyOutlookModule


def _payload_to_dict(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    for attr in ("model_dump", "dict"):
        fn = getattr(payload, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                continue
    return {}


def _wrap_module_result(module: Any, property_input: Any) -> dict[str, Any]:
    """Call module.run() and normalize ModuleResult → {data, confidence, warnings}."""

    result = module.run(property_input)

    if isinstance(result, dict) and "data" in result:
        return result  # SecurityModel already emits the right shape

    metrics = getattr(result, "metrics", None) or {}
    payload = _payload_to_dict(getattr(result, "payload", None))
    score = getattr(result, "score", None)
    top_conf = getattr(result, "confidence", None)
    summary = getattr(result, "summary", None)
    section_evidence = getattr(result, "section_evidence", None)

    data: dict[str, Any] = {}
    if isinstance(metrics, dict):
        data.update(metrics)
    data.update(payload)
    if score is not None and "score" not in data:
        data["score"] = score
    if summary and "summary" not in data:
        data["summary"] = summary
    if section_evidence and "section_evidence" not in data:
        try:
            data["section_evidence"] = [
                _payload_to_dict(e) for e in section_evidence
            ]
        except Exception:
            pass

    confidence = payload.get("confidence") if isinstance(payload, dict) else None
    if not isinstance(confidence, (int, float)):
        confidence = top_conf
    if not isinstance(confidence, (int, float)):
        confidence = 0.0

    warnings = payload.get("warnings") if isinstance(payload, dict) else None
    if not isinstance(warnings, list):
        warnings = []

    return {
        "data": data,
        "confidence": float(confidence),
        "warnings": list(warnings),
    }


def _securitymodel_invoke(p: Any) -> dict[str, Any]:
    m = SecurityModel()
    payload = {
        "town": getattr(p, "town", None),
        "state": getattr(p, "state", None),
    }
    return m.run(payload)


def _scenario_invoke(p: Any) -> dict[str, Any]:
    """Merge the scenario modules the way the pipeline does."""
    pieces = {
        "bull_base_bear": _wrap_module_result(BullBaseBearModule(), p),
        "renovation_scenario": _wrap_module_result(RenovationScenarioModule(), p),
        "teardown_scenario": _wrap_module_result(TeardownScenarioModule(), p),
    }
    bbb = pieces["bull_base_bear"]["data"]
    confidences = [
        piece["confidence"] for piece in pieces.values()
        if isinstance(piece.get("confidence"), (int, float))
    ]
    warnings: list[str] = []
    for name, piece in pieces.items():
        for w in piece.get("warnings") or []:
            warnings.append(f"{name}:{w}")
    merged = {
        "scenarios": {k: v["data"] for k, v in pieces.items()},
        "scenario_count": len(pieces),
        "bull_case_value": bbb.get("bull_case_value"),
        "base_case_value": bbb.get("base_case_value"),
        "bear_case_value": bbb.get("bear_case_value"),
        "spread": bbb.get("spread"),
        "summary": f"{len(pieces)} scenarios fanned",
    }
    return {
        "data": merged,
        "confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0.0,
        "warnings": warnings,
    }


def _income_invoke(p: Any) -> dict[str, Any]:
    return _wrap_module_result(IncomeSupportModule(), p)


def _risk_invoke(p: Any) -> dict[str, Any]:
    return _wrap_module_result(RiskConstraintsModule(), p)


def _location_invoke(p: Any) -> dict[str, Any]:
    return _wrap_module_result(LocationIntelligenceModule(), p)


def _town_invoke(p: Any) -> dict[str, Any]:
    return _wrap_module_result(TownCountyOutlookModule(), p)


# ---------- Specs ----------

INCOME_SPEC = ModelSpec(
    name="income",
    invoke=_income_invoke,
    required_inputs=["purchase_price", "estimated_monthly_rent", "taxes"],
    expected_output_fields=[
        "price_to_rent",
        "operating_monthly_cash_flow",
        "effective_monthly_rent",
    ],
    numeric_bounds={
        "price_to_rent": (5.0, 60.0),
        "effective_monthly_rent": (500.0, 25000.0),
        "operating_monthly_cash_flow": (-15000.0, 15000.0),
    },
    sensitivities=[
        Sensitivity(
            input_field="estimated_monthly_rent",
            delta=0.2,
            output_field="effective_monthly_rent",
            expected_direction="up",
            min_move_pct=0.05,
            label="rent+20%",
        ),
        Sensitivity(
            input_field="purchase_price",
            delta=0.2,
            output_field="price_to_rent",
            expected_direction="up",
            min_move_pct=0.05,
            label="price+20%",
        ),
        Sensitivity(
            input_field="taxes",
            delta=0.5,
            output_field="operating_monthly_cash_flow",
            expected_direction="down",
            min_move_pct=0.01,
            label="taxes+50%",
        ),
    ],
    explainability_fields=["explanation", "summary", "warnings"],
    decision_questions=DecisionQuestionMap(
        should_i_buy=["operating_monthly_cash_flow", "price_to_rent"],
        what_could_go_wrong=["warnings", "missing_inputs"],
        where_is_value=["effective_monthly_rent", "rent_support_classification"],
        what_path=["rent_source_type", "rent_support_classification"],
    ),
    trust_drop_fields=["estimated_monthly_rent"],
)


SCENARIO_SPEC = ModelSpec(
    name="scenario",
    invoke=_scenario_invoke,
    required_inputs=["purchase_price", "town_price_trend"],
    expected_output_fields=["bull_case_value", "base_case_value", "bear_case_value"],
    numeric_bounds={
        "bull_case_value": (50_000.0, 10_000_000.0),
        "base_case_value": (50_000.0, 10_000_000.0),
        "bear_case_value": (25_000.0, 10_000_000.0),
        "scenario_count": (1, 10),
    },
    sensitivities=[
        Sensitivity(
            input_field="town_price_trend",
            delta=0.05,
            output_field="bull_case_value",
            expected_direction="up",
            min_move_pct=0.01,
            label="price_trend+5pp",
        ),
        Sensitivity(
            input_field="purchase_price",
            delta=0.2,
            output_field="base_case_value",
            expected_direction="any",
            min_move_pct=0.0,
            label="price+20%",
        ),
    ],
    explainability_fields=["scenarios", "summary"],
    decision_questions=DecisionQuestionMap(
        should_i_buy=["base_case_value", "bull_case_value"],
        what_could_go_wrong=["bear_case_value", "spread"],
        where_is_value=["bull_case_value", "base_case_value"],
        what_path=["scenarios"],
    ),
    trust_drop_fields=["town_price_trend", "school_rating"],
)


RISK_SPEC = ModelSpec(
    name="risk",
    invoke=_risk_invoke,
    required_inputs=["flood_risk", "condition_profile"],
    expected_output_fields=["risk_flags", "risk_count", "score"],
    numeric_bounds={
        "score": (0.0, 100.0),
        "risk_count": (0, 30),
        "total_penalty": (0.0, 200.0),
    },
    sensitivities=[
        Sensitivity(
            input_field="flood_risk",
            delta="high",
            output_field="score",
            expected_direction="down",
            min_move_pct=0.01,
            label="flood_risk=high",
        ),
    ],
    explainability_fields=["risk_flags", "summary", "warnings"],
    decision_questions=DecisionQuestionMap(
        should_i_buy=["score"],
        what_could_go_wrong=["risk_flags", "total_penalty"],
        where_is_value=["risk_flags"],
        what_path=["risk_flags"],
    ),
    trust_drop_fields=["flood_risk", "condition_profile"],
)


LOCATION_SPEC = ModelSpec(
    name="location",
    invoke=_location_invoke,
    required_inputs=["town", "state", "school_rating"],
    expected_output_fields=["location_score", "scarcity_score"],
    numeric_bounds={
        "location_score": (0.0, 100.0),
        "scarcity_score": (0.0, 100.0),
        "location_premium_pct": (-50.0, 50.0),
    },
    sensitivities=[
        Sensitivity(
            input_field="school_rating",
            delta=3.0,
            output_field="location_score",
            expected_direction="any",
            min_move_pct=0.0,
            label="school+3",
        ),
    ],
    explainability_fields=["narratives", "confidence_notes", "summary"],
    decision_questions=DecisionQuestionMap(
        should_i_buy=["location_score"],
        what_could_go_wrong=["confidence_notes", "missing_inputs"],
        where_is_value=["location_premium_pct", "scarcity_score"],
        what_path=["narratives"],
    ),
    trust_drop_fields=["school_rating", "town_population_trend"],
)


SECURITY_SPEC = ModelSpec(
    name="security",
    invoke=_securitymodel_invoke,
    required_inputs=["town", "state"],
    expected_output_fields=["score", "trend"],
    numeric_bounds={
        "score": (0.0, 100.0),
    },
    sensitivities=[],
    explainability_fields=["notes", "trend"],
    decision_questions=DecisionQuestionMap(
        should_i_buy=["score"],
        what_could_go_wrong=["notes", "negative_count"],
        where_is_value=["trend", "positive_count"],
        what_path=["trend"],
    ),
    trust_drop_fields=[],  # only town/state drive it; dropping breaks lookup
)


TOWN_SPEC = ModelSpec(
    name="town_intel",
    invoke=_town_invoke,
    required_inputs=["town", "state", "town_price_trend"],
    expected_output_fields=["town_county_score", "location_thesis_label"],
    numeric_bounds={
        "town_county_score": (0.0, 100.0),
    },
    sensitivities=[
        Sensitivity(
            input_field="town_price_trend",
            delta=0.05,
            output_field="town_county_score",
            expected_direction="up",
            min_move_pct=0.0,
            label="price_trend+5pp",
        ),
    ],
    explainability_fields=["demand_drivers", "demand_risks", "assumptions_used"],
    decision_questions=DecisionQuestionMap(
        should_i_buy=["town_county_score", "location_thesis_label"],
        what_could_go_wrong=["demand_risks"],
        where_is_value=["demand_drivers", "appreciation_support_view"],
        what_path=["liquidity_view", "appreciation_support_view"],
    ),
    trust_drop_fields=["town_price_trend", "town_population_trend"],
)


ALL_MODEL_SPECS: dict[str, ModelSpec] = {
    "income": INCOME_SPEC,
    "scenario": SCENARIO_SPEC,
    "risk": RISK_SPEC,
    "location": LOCATION_SPEC,
    "security": SECURITY_SPEC,
    "town_intel": TOWN_SPEC,
}


__all__ = [
    "ALL_MODEL_SPECS",
    "INCOME_SPEC",
    "SCENARIO_SPEC",
    "RISK_SPEC",
    "LOCATION_SPEC",
    "SECURITY_SPEC",
    "TOWN_SPEC",
]
