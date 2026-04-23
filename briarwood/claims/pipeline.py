"""Build a ``VerdictWithComparisonClaim`` for a saved property.

Thin adapter between dispatch (which knows a ``property_id`` and a user
utterance) and the claim synthesizer (which needs the four artifacts
``build_verdict_with_comparison_claim`` consumes). Wraps
``run_briarwood_analysis_with_artifacts`` so the wedge reuses the existing
routed-execution stack — no parallel orchestrator.

Kept deliberately small: any complexity past "fetch artifacts and hand
them to the synthesizer" belongs in the synthesizer itself.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from briarwood.agent.overrides import inputs_with_overrides
from briarwood.agent.tools import SAVED_PROPERTIES_DIR, ToolUnavailable
from briarwood.claims.synthesis import build_verdict_with_comparison_claim
from briarwood.claims.verdict_with_comparison import VerdictWithComparisonClaim
from briarwood.inputs.property_loader import load_property_from_json
from briarwood.orchestrator import run_briarwood_analysis_with_artifacts
from briarwood.runner_routed import _scoped_synthesizer


def build_claim_for_property(
    property_id: str,
    *,
    user_text: str,
    overrides: Mapping[str, Any] | None = None,
) -> VerdictWithComparisonClaim:
    """Run the routed pipeline and synthesize a verdict_with_comparison claim."""
    inputs_path = SAVED_PROPERTIES_DIR / property_id / "inputs.json"
    if not inputs_path.exists():
        raise ToolUnavailable(f"no inputs.json for property '{property_id}'")

    with inputs_with_overrides(inputs_path, dict(overrides or {})) as effective_path:
        property_input = load_property_from_json(effective_path)
        property_data = property_input.to_dict()
        artifacts = run_briarwood_analysis_with_artifacts(
            property_data=property_data,
            user_input=user_text,
            synthesizer=_scoped_synthesizer,
        )

    property_summary = artifacts["property_summary"]
    module_results = artifacts.get("module_results") or {}
    parser_output = artifacts["routing_decision"].parser_output.model_dump()
    interaction_trace = _extract_interaction_trace(artifacts)

    return build_verdict_with_comparison_claim(
        property_summary=property_summary,
        parser_output=parser_output,
        module_results=module_results,
        interaction_trace=interaction_trace,
    )


def _extract_interaction_trace(artifacts: Mapping[str, Any]) -> dict[str, Any]:
    """Return the trace regardless of whether the cached or fresh branch ran.

    The orchestrator's synthesis cache hit skips emitting ``interaction_trace``
    at the top level; the trace is still reachable via the unified output.
    """
    trace = artifacts.get("interaction_trace")
    if isinstance(trace, Mapping):
        return dict(trace)
    unified = artifacts.get("unified_output")
    trace = getattr(unified, "interaction_trace", None)
    if hasattr(trace, "to_dict"):
        return dict(trace.to_dict())
    if isinstance(trace, Mapping):
        return dict(trace)
    return {}


__all__ = ["build_claim_for_property"]
