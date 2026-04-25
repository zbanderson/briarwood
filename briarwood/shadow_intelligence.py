"""Shadow LLM planning and intent-satisfaction checks.

These helpers observe the routed analysis pipeline without controlling it.
They are deliberately telemetry-only: deterministic module routing and
execution remain the production authority.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from briarwood.agent.llm import LLMClient
from briarwood.agent.llm_observability import complete_structured_observed
from briarwood.execution.registry import ModuleSpec, build_module_registry

_logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
_TOOL_REGISTRY = _ROOT / "TOOL_REGISTRY.md"


class ShadowToolPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposed_modules: list[str] = Field(default_factory=list)
    proposed_tools: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""


class IntentSatisfactionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_satisfied: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_capabilities: list[str] = Field(default_factory=list)
    suggested_modules: list[str] = Field(default_factory=list)
    suggested_follow_up: str | None = None
    reason: str = ""


class ShadowIntelligenceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planner: ShadowToolPlan | None = None
    evaluator: IntentSatisfactionReport | None = None
    module_diff: dict[str, list[str]] = Field(default_factory=dict)


def _read_tool_registry_excerpt(limit: int = 12_000) -> str:
    try:
        text = _TOOL_REGISTRY.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    return text[:limit]


def _module_registry_digest(
    registry: Mapping[str, ModuleSpec] | None = None,
) -> list[dict[str, Any]]:
    source = registry or build_module_registry()
    return [
        {
            "name": name,
            "depends_on": list(spec.depends_on),
            "required_context_keys": list(spec.required_context_keys),
            "optional_context_keys": list(spec.optional_context_keys),
            "description": spec.description or "",
        }
        for name, spec in sorted(source.items())
    ]


_PLANNER_SYSTEM = (
    "You are a shadow planner for Briarwood's real-estate intelligence stack. "
    "Read the module registry and TOOL_REGISTRY notes, then propose modules or "
    "tools that would answer the user's intent. This is telemetry only. Do not "
    "invent valuation math, legal conclusions, comp selection, rent math, or "
    "risk scoring. Return only the declared ShadowToolPlan JSON."
)

_EVALUATOR_SYSTEM = (
    "You are a shadow intent-satisfaction evaluator for Briarwood. Judge "
    "whether the deterministic modules and unified output answered the user's "
    "intent. This is telemetry only. Do not redo math or make a buy/pass "
    "decision. Return only the declared IntentSatisfactionReport JSON."
)


def run_shadow_tool_planner(
    *,
    user_input: str,
    selected_modules: list[str],
    parser_output: Mapping[str, Any],
    llm: LLMClient | None,
    registry: Mapping[str, ModuleSpec] | None = None,
) -> ShadowToolPlan | None:
    if llm is None:
        return None
    payload = {
        "user_input": user_input,
        "deterministic_selected_modules": selected_modules,
        "parser_output": dict(parser_output),
        "module_registry": _module_registry_digest(registry),
        "tool_registry_markdown": _read_tool_registry_excerpt(),
    }
    user = json.dumps(payload, sort_keys=True, default=str)
    try:
        return complete_structured_observed(
            surface="shadow_intelligence.tool_planner",
            schema=ShadowToolPlan,
            system=_PLANNER_SYSTEM,
            user=user,
            provider=llm.__class__.__name__,
            model=None,
            max_attempts=2,
            call=lambda: llm.complete_structured(
                system=_PLANNER_SYSTEM,
                user=user,
                schema=ShadowToolPlan,
                max_tokens=800,
            ),
        )
    except Exception as exc:
        _logger.warning("shadow planner failed: %s", exc)
        return None


def run_intent_satisfaction_evaluator(
    *,
    user_input: str,
    selected_modules: list[str],
    parser_output: Mapping[str, Any],
    module_results: Mapping[str, Any],
    unified_output: Any,
    llm: LLMClient | None,
) -> IntentSatisfactionReport | None:
    if llm is None:
        return None
    if hasattr(unified_output, "model_dump"):
        unified_payload = unified_output.model_dump(mode="json")
    elif isinstance(unified_output, Mapping):
        unified_payload = dict(unified_output)
    else:
        unified_payload = {"repr": repr(unified_output)}
    payload = {
        "user_input": user_input,
        "selected_modules": selected_modules,
        "parser_output": dict(parser_output),
        "module_result_keys": sorted(str(k) for k in module_results.keys()),
        "unified_output": unified_payload,
    }
    user = json.dumps(payload, sort_keys=True, default=str)
    try:
        return complete_structured_observed(
            surface="shadow_intelligence.intent_satisfaction",
            schema=IntentSatisfactionReport,
            system=_EVALUATOR_SYSTEM,
            user=user,
            provider=llm.__class__.__name__,
            model=None,
            max_attempts=2,
            call=lambda: llm.complete_structured(
                system=_EVALUATOR_SYSTEM,
                user=user,
                schema=IntentSatisfactionReport,
                max_tokens=700,
            ),
        )
    except Exception as exc:
        _logger.warning("shadow evaluator failed: %s", exc)
        return None


def module_diff(
    *,
    selected_modules: list[str],
    proposed_modules: list[str],
) -> dict[str, list[str]]:
    selected = set(selected_modules)
    proposed = set(proposed_modules)
    return {
        "missing_from_deterministic": sorted(proposed - selected),
        "extra_deterministic": sorted(selected - proposed),
    }


def run_shadow_intelligence(
    *,
    user_input: str,
    selected_modules: list[str],
    parser_output: Mapping[str, Any],
    module_results: Mapping[str, Any],
    unified_output: Any,
    llm: LLMClient | None,
    registry: Mapping[str, ModuleSpec] | None = None,
) -> ShadowIntelligenceReport | None:
    if llm is None:
        return None
    planner = run_shadow_tool_planner(
        user_input=user_input,
        selected_modules=selected_modules,
        parser_output=parser_output,
        llm=llm,
        registry=registry,
    )
    evaluator = run_intent_satisfaction_evaluator(
        user_input=user_input,
        selected_modules=selected_modules,
        parser_output=parser_output,
        module_results=module_results,
        unified_output=unified_output,
        llm=llm,
    )
    diff = (
        module_diff(
            selected_modules=selected_modules,
            proposed_modules=planner.proposed_modules,
        )
        if planner is not None
        else {}
    )
    return ShadowIntelligenceReport(planner=planner, evaluator=evaluator, module_diff=diff)


__all__ = [
    "IntentSatisfactionReport",
    "ShadowIntelligenceReport",
    "ShadowToolPlan",
    "module_diff",
    "run_intent_satisfaction_evaluator",
    "run_shadow_intelligence",
    "run_shadow_tool_planner",
]
