from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_PATH = ROOT / "data" / "learning" / "intelligence_feedback.jsonl"


def append_intelligence_capture(record: dict[str, Any]) -> Path:
    """Append one lightweight intelligence interaction record to JSONL storage."""

    CAPTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        **dict(record),
    }
    with CAPTURE_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
    return CAPTURE_PATH


def build_routed_capture_record(
    *,
    question: str,
    context_type: str,
    routing_decision: dict[str, Any],
    execution_mode: str,
    unified_output: dict[str, Any],
    missing_context: bool = False,
    was_conditional_answer: bool = False,
) -> dict[str, Any]:
    """Build a reviewable routed interaction payload for product learning."""

    parser_output = dict(routing_decision.get("parser_output") or {})
    tags = _capture_tags(
        parser_output=parser_output,
        selected_modules=list(routing_decision.get("selected_modules") or []),
        execution_mode=execution_mode,
        confidence=float(unified_output.get("confidence") or 0.0),
        missing_context=missing_context,
        was_conditional_answer=was_conditional_answer,
    )
    return {
        "question": question,
        "context_type": context_type,
        "parser_output": parser_output,
        "routing_decision": routing_decision,
        "selected_modules": list(routing_decision.get("selected_modules") or []),
        "execution_mode": execution_mode,
        "unified_output_summary": {
            "recommendation": unified_output.get("recommendation"),
            "decision": unified_output.get("decision"),
            "confidence": unified_output.get("confidence"),
            "analysis_depth_used": unified_output.get("analysis_depth_used"),
            "recommended_next_run": unified_output.get("recommended_next_run"),
        },
        "missing_context": missing_context,
        "was_conditional_answer": was_conditional_answer,
        "tags": tags,
    }


def build_intake_agent_capture_record(
    *,
    question: str,
    triage_decision: dict[str, Any],
    execution_mode: str,
    prior_session: dict[str, Any] | None = None,
    final_answer_conditional: bool = False,
) -> dict[str, Any]:
    """Build one capture record for the intake triage agent."""

    resolved = dict(triage_decision.get("resolved_entity") or {})
    previous = dict(prior_session or {})
    previous_triage = dict(previous.get("latest_triage_decision") or {})
    tags: list[str] = []

    context_type = str(triage_decision.get("context_type") or "")
    triage_status = str(triage_decision.get("triage_status") or "")
    if triage_status == "needs_context":
        tags.append("needs-context")
    if context_type == "area":
        tags.append("area-question")
    if context_type == "property":
        tags.append("property-question")
    if previous_triage and previous_triage.get("context_type") != triage_decision.get("context_type"):
        tags.append("question-rerouted")
    if previous_triage and previous_triage.get("recommended_execution_mode") != triage_decision.get("recommended_execution_mode"):
        tags.append("question-rerouted")
    if final_answer_conditional and previous_triage:
        tags.append("answer-misaligned")

    return {
        "question": question,
        "context_type": context_type,
        "triage_decision": triage_decision,
        "resolved_entity": resolved,
        "execution_mode": execution_mode,
        "was_conditional_answer": final_answer_conditional,
        "tags": list(dict.fromkeys(tags)),
    }


def _capture_tags(
    *,
    parser_output: dict[str, Any],
    selected_modules: list[Any],
    execution_mode: str,
    confidence: float,
    missing_context: bool,
    was_conditional_answer: bool,
    follow_up_tags: list[str] | None = None,
) -> list[str]:
    tags: list[str] = []
    if missing_context:
        tags.append("low-confidence-due-to-missing-inputs")
    if was_conditional_answer:
        tags.append("unknown-question-pattern")
    if execution_mode == "legacy_fallback":
        tags.append("unsupported-module-path")
    if not selected_modules:
        tags.append("missing-scenario-type")
    if confidence < 0.55:
        tags.append("low-confidence-due-to-missing-inputs")
    if parser_output.get("missing_inputs"):
        tags.append("low-confidence-due-to-missing-inputs")
    if follow_up_tags:
        tags.extend(follow_up_tags)
    return list(dict.fromkeys(tags))


def build_followup_capture_record(
    *,
    question: str,
    context_type: str,
    routing_decision: dict[str, Any],
    execution_mode: str,
    unified_output: dict[str, Any],
    conversation_history: list[dict[str, Any]],
    trigger: str = "next_question",
) -> dict[str, Any]:
    """Build a capture record for a follow-up question in a conversation chain.

    *trigger* describes how the follow-up was initiated:
    - ``"next_question"`` — user clicked a suggested next question
    - ``"go_deeper"`` — user clicked the Go Deeper button
    - ``"manual"`` — user typed a new question manually

    The record includes the full conversation chain so product learning can
    see how users navigate through the decision engine.
    """

    turn_number = len(conversation_history) + 1
    follow_up_tags = [f"follow-up-turn-{turn_number}", f"trigger-{trigger}"]

    if turn_number >= 2:
        prev = conversation_history[-1] if conversation_history else {}
        prev_depth = str(prev.get("analysis_depth") or "")
        curr_depth = str(unified_output.get("analysis_depth_used") or "")
        if prev_depth and curr_depth and prev_depth != curr_depth:
            follow_up_tags.append("user-went-deeper")
            follow_up_tags.append("followup-depth-upgrade")

        prev_intent = str(prev.get("intent_type") or "")
        curr_intent = str((routing_decision.get("parser_output") or {}).get("intent_type") or "")
        if prev_intent and curr_intent and prev_intent != curr_intent:
            follow_up_tags.append("user-pivoted-intent")
            follow_up_tags.append("question-rerouted")

    if trigger == "manual" and conversation_history:
        follow_up_tags.append("answer-misaligned")

    parser_output = dict(routing_decision.get("parser_output") or {})
    tags = _capture_tags(
        parser_output=parser_output,
        selected_modules=list(routing_decision.get("selected_modules") or []),
        execution_mode=execution_mode,
        confidence=float(unified_output.get("confidence") or 0.0),
        missing_context=False,
        was_conditional_answer=False,
        follow_up_tags=follow_up_tags,
    )

    chain_summary = [
        {
            "turn": i + 1,
            "question": str(entry.get("question") or ""),
            "decision": str(entry.get("decision") or ""),
            "analysis_depth": str(entry.get("analysis_depth") or ""),
        }
        for i, entry in enumerate(conversation_history)
    ]
    chain_summary.append({
        "turn": turn_number,
        "question": question,
        "decision": str(unified_output.get("decision") or ""),
        "analysis_depth": str(unified_output.get("analysis_depth_used") or ""),
    })

    return {
        "question": question,
        "context_type": context_type,
        "parser_output": parser_output,
        "routing_decision": routing_decision,
        "selected_modules": list(routing_decision.get("selected_modules") or []),
        "execution_mode": execution_mode,
        "unified_output_summary": {
            "recommendation": unified_output.get("recommendation"),
            "decision": unified_output.get("decision"),
            "confidence": unified_output.get("confidence"),
            "analysis_depth_used": unified_output.get("analysis_depth_used"),
            "recommended_next_run": unified_output.get("recommended_next_run"),
        },
        "conversation_chain": chain_summary,
        "turn_number": turn_number,
        "trigger": trigger,
        "tags": tags,
    }


def build_user_feedback_record(
    *,
    rating: str,
    comment: str = "",
    analysis_id: str = "",
    analysis_confidence: float | None = None,
    analysis_decision: str = "",
    analysis_depth: str = "",
) -> dict[str, Any]:
    """Build a user-validation feedback record linked to a specific analysis.

    *rating* is one of: ``"yes"``, ``"partially"``, ``"no"``.
    """
    return {
        "feedback_type": "user_validation",
        "rating": rating,
        "comment": comment,
        "analysis_id": analysis_id,
        "analysis_confidence": analysis_confidence,
        "analysis_decision": analysis_decision,
        "analysis_depth": analysis_depth,
        "tags": [f"user-feedback-{rating}"],
    }


__all__ = [
    "append_intelligence_capture",
    "build_intake_agent_capture_record",
    "build_followup_capture_record",
    "build_routed_capture_record",
    "build_user_feedback_record",
]
