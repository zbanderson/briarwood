"""Agent tool handlers.

Each tool is a pure Python function with a narrow signature. Tools are
registered with the answer types that are allowed to invoke them — dispatch
enforces this, not the LLM.

Phase A scope:
- get_property_summary: cheap, reads saved_properties/{id}/summary.json
- analyze_property: wraps run_routed_report (full pipeline)
- research_town: stub returning cached signals only (real external research
  arrives in Phase C)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from briarwood.agent.router import AnswerType

SAVED_PROPERTIES_DIR = Path("data/saved_properties")


@dataclass(frozen=True)
class ToolError:
    tool: str
    message: str


class ToolUnavailable(Exception):
    """Raised when a tool cannot answer (e.g., unknown property_id)."""


# ---------- get_property_summary ----------


def get_property_summary(property_id: str) -> dict[str, Any]:
    path = SAVED_PROPERTIES_DIR / property_id / "summary.json"
    if not path.exists():
        raise ToolUnavailable(f"no saved property with id '{property_id}'")
    return json.loads(path.read_text())


# ---------- analyze_property ----------


def analyze_property(
    property_id: str,
    *,
    force_refresh: bool = False,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the full routed pipeline and return UnifiedIntelligenceOutput as dict.

    ``overrides`` supports what-if scenarios (e.g. ``{"ask_price": 1_300_000}``).
    When supplied, the inputs.json is mutated in a tempfile before the pipeline
    runs — the on-disk record is never touched.
    """
    from briarwood.agent.overrides import inputs_with_overrides
    from briarwood.runner_routed import run_routed_report

    inputs_path = SAVED_PROPERTIES_DIR / property_id / "inputs.json"
    if not inputs_path.exists():
        raise ToolUnavailable(f"no inputs.json for property '{property_id}'")

    with inputs_with_overrides(inputs_path, overrides or {}) as effective_path:
        result = run_routed_report(effective_path)
    return result.unified_output.model_dump()


# ---------- search_listings ----------


def search_listings(filters: dict[str, Any]) -> list[dict[str, Any]]:
    """Filter the listing index. Returns a list of summary dicts (not full facts)."""
    from briarwood.agent.index import search

    results = search(filters)
    return [
        {
            "property_id": p.property_id,
            "address": p.address,
            "town": p.town,
            "state": p.state,
            "beds": p.beds,
            "baths": p.baths,
            "ask_price": p.ask_price,
            "distance_to_beach_miles": p.distance_to_beach_miles,
            "blocks_to_beach": p.blocks_to_beach,
            "confidence": p.confidence,
        }
        for p in results
    ]


def underwrite_matches(property_ids: list[str]) -> list[dict[str, Any]]:
    """Batch wrapper — runs analyze_property on each id, returns slim stance records."""
    out: list[dict[str, Any]] = []
    for pid in property_ids:
        try:
            u = analyze_property(pid)
        except ToolUnavailable as exc:
            out.append({"property_id": pid, "error": str(exc)})
            continue
        stance = u.get("decision_stance")
        if hasattr(stance, "value"):
            stance = stance.value
        out.append(
            {
                "property_id": pid,
                "decision_stance": stance,
                "primary_value_source": u.get("primary_value_source"),
                "trust_flags": u.get("trust_flags") or [],
                "value_position": u.get("value_position") or {},
            }
        )
    return out


# ---------- research_town ----------


def research_town(
    town: str,
    state: str,
    focus: list[str] | None = None,
    *,
    service: Any | None = None,
    budget_seconds: float | None = None,
) -> dict[str, Any]:
    """Run the local_intelligence research pipeline with a wall-clock budget.

    Delegates to ``LocalIntelligenceService.research``. Adapters (static
    registry, web search, minutes feed) are wired at service construction.
    Returns a dict with fresh signals + what documents were retrieved so
    callers can diff against a prior state.
    """
    import os

    from briarwood.local_intelligence.service import LocalIntelligenceService

    svc = service or _default_research_service()
    if budget_seconds is None:
        raw = os.environ.get("BRIARWOOD_AGENT_RESEARCH_BUDGET_S")
        try:
            budget_seconds = float(raw) if raw else 30.0
        except ValueError:
            budget_seconds = 30.0

    run = svc.research(town=town, state=state, focus=focus or [], budget_seconds=budget_seconds)
    return {
        "town": town,
        "state": state,
        "focus": focus or [],
        "document_count": len(run.documents),
        "documents": [
            {"title": d.title, "url": d.url, "source_type": d.source_type.value if hasattr(d.source_type, "value") else d.source_type}
            for d in run.documents
        ],
        "signal_count": len(run.signals),
        "warnings": list(run.warnings or []),
    }


def _default_research_service():
    """Build a LocalIntelligenceService with default adapters wired.

    Kept in a helper so tests can inject a fake service via the
    ``research_town(service=...)`` kwarg.
    """
    from briarwood.local_intelligence.collector import MunicipalDocumentCollector
    from briarwood.local_intelligence.service import LocalIntelligenceService
    from briarwood.local_intelligence.sources import StaticRegistryAdapter
    from briarwood.local_intelligence.sources.minutes_feed_adapter import MinutesFeedAdapter
    from briarwood.local_intelligence.sources.web_search_adapter import WebSearchAdapter

    collector = MunicipalDocumentCollector()
    # Prepend web + minutes adapters; static seed adapter already in the default list.
    collector.adapters = [
        WebSearchAdapter(),
        MinutesFeedAdapter(),
        *collector.adapters,
    ]
    return LocalIntelligenceService(collector=collector)


# ---------- get_projection ----------


def get_projection(property_id: str, *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Force scenario-depth analysis and extract bull/base/bear projection.

    Returns a dict with ask_price, {bull,base,bear}_case_value, stress_case_value,
    {bull,base,bear}_total_adjustment_pct, spread. Values come from the
    resale_scenario module (which replaces bull_base_bear under scoped execution).
    """
    from briarwood.agent.overrides import inputs_with_overrides
    from briarwood.runner_routed import run_routed_report

    inputs_path = SAVED_PROPERTIES_DIR / property_id / "inputs.json"
    if not inputs_path.exists():
        raise ToolUnavailable(f"no inputs.json for property '{property_id}'")

    # The internal router keys on these words to select depth=SCENARIO.
    with inputs_with_overrides(inputs_path, overrides or {}) as effective_path:
        result = run_routed_report(
            effective_path,
            user_input="project forward 5 years bull base bear scenarios",
        )
    outputs = getattr(result.engine_output, "outputs", {}) or {}
    entry = outputs.get("resale_scenario") or outputs.get("bull_base_bear")
    if entry is None:
        raise ToolUnavailable("projection modules were not selected for this property")
    data = getattr(entry, "data", None) or (entry.get("data") if isinstance(entry, dict) else None) or {}
    m = data.get("metrics") or {}
    keys = (
        "ask_price", "bull_case_value", "base_case_value", "bear_case_value",
        "stress_case_value", "spread",
        "bull_total_adjustment_pct", "base_total_adjustment_pct", "bear_total_adjustment_pct",
        "bull_growth_rate", "base_growth_rate", "bear_growth_rate",
        "bcv_anchor",
    )
    return {"property_id": property_id, **{k: m.get(k) for k in keys}}


# ---------- get_rent_estimate ----------


def get_rent_estimate(property_id: str) -> dict[str, Any]:
    """Run the routed pipeline and surface rent-relevant metrics from carry_cost + rental_option modules."""
    from briarwood.runner_routed import run_routed_report

    inputs_path = SAVED_PROPERTIES_DIR / property_id / "inputs.json"
    if not inputs_path.exists():
        raise ToolUnavailable(f"no inputs.json for property '{property_id}'")

    result = run_routed_report(inputs_path)
    outputs = getattr(result.engine_output, "outputs", {}) or {}

    def _metrics(mod: str) -> dict[str, Any]:
        entry = outputs.get(mod)
        if entry is None:
            return {}
        data = getattr(entry, "data", None)
        if data is None and isinstance(entry, dict):
            data = entry.get("data")
        return (data or {}).get("metrics") or {}

    carry = _metrics("carry_cost")
    rental = _metrics("rental_option")
    return {
        "property_id": property_id,
        "monthly_rent": carry.get("monthly_rent"),
        "effective_monthly_rent": carry.get("effective_monthly_rent"),
        "rent_source_type": carry.get("rent_source_type"),
        "annual_noi": carry.get("annual_noi"),
        "monthly_cash_flow": carry.get("monthly_cash_flow"),
        "cash_on_cash_return": carry.get("cash_on_cash_return"),
        "rental_ease_score": rental.get("rental_ease_score"),
        "rental_ease_label": rental.get("rental_ease_label"),
        "rent_support_score": rental.get("rent_support_score"),
        "estimated_days_to_rent": rental.get("estimated_days_to_rent"),
    }


# ---------- get_risk_profile ----------


def get_risk_profile(property_id: str, *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Surface risk drivers from risk_model + unified.trust_flags + projection bear case."""
    from briarwood.agent.overrides import inputs_with_overrides
    from briarwood.runner_routed import run_routed_report

    inputs_path = SAVED_PROPERTIES_DIR / property_id / "inputs.json"
    if not inputs_path.exists():
        raise ToolUnavailable(f"no inputs.json for property '{property_id}'")

    with inputs_with_overrides(inputs_path, overrides or {}) as effective_path:
        result = run_routed_report(effective_path, user_input="deep dive stress test full analysis risk")
    outputs = getattr(result.engine_output, "outputs", {}) or {}
    unified = result.unified_output.model_dump()

    def _metrics(mod: str) -> dict[str, Any]:
        entry = outputs.get(mod)
        if entry is None:
            return {}
        data = getattr(entry, "data", None)
        if data is None and isinstance(entry, dict):
            data = entry.get("data")
        return (data or {}).get("metrics") or {}

    risk = _metrics("risk_model")
    scen = _metrics("resale_scenario") or _metrics("bull_base_bear")
    flags_raw = risk.get("risk_flags") or ""
    risk_flags = [f.strip() for f in flags_raw.split(",") if f.strip()] if isinstance(flags_raw, str) else []
    return {
        "property_id": property_id,
        "risk_flags": risk_flags,
        "risk_count": risk.get("risk_count"),
        "total_penalty": risk.get("total_penalty"),
        "total_credit": risk.get("total_credit"),
        "flood_risk": risk.get("flood_risk"),
        "trust_flags": unified.get("trust_flags") or [],
        "key_risks": unified.get("key_risks") or [],
        "ask_price": unified.get("value_position", {}).get("ask_price"),
        "bear_case_value": scen.get("bear_case_value"),
        "stress_case_value": scen.get("stress_case_value"),
        "decision_stance": (unified.get("decision_stance").value
                            if hasattr(unified.get("decision_stance"), "value")
                            else unified.get("decision_stance")),
    }


# ---------- get_value_thesis ----------


def get_value_thesis(property_id: str, *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Explain WHERE the value is: valuation anchors, discount/premium, drivers."""
    from briarwood.agent.overrides import inputs_with_overrides
    from briarwood.runner_routed import run_routed_report

    inputs_path = SAVED_PROPERTIES_DIR / property_id / "inputs.json"
    if not inputs_path.exists():
        raise ToolUnavailable(f"no inputs.json for property '{property_id}'")

    with inputs_with_overrides(inputs_path, overrides or {}) as effective_path:
        result = run_routed_report(effective_path)
    outputs = getattr(result.engine_output, "outputs", {}) or {}
    unified = result.unified_output.model_dump()

    def _metrics(mod: str) -> dict[str, Any]:
        entry = outputs.get(mod)
        if entry is None:
            return {}
        data = getattr(entry, "data", None)
        if data is None and isinstance(entry, dict):
            data = entry.get("data")
        return (data or {}).get("metrics") or {}

    val = _metrics("valuation")
    vp = unified.get("value_position") or {}
    return {
        "property_id": property_id,
        "ask_price": vp.get("ask_price"),
        "fair_value_base": vp.get("fair_value_base"),
        "value_low": vp.get("value_low"),
        "value_high": vp.get("value_high"),
        "premium_discount_pct": vp.get("premium_discount_pct"),
        "mispricing_amount": val.get("mispricing_amount"),
        "mispricing_pct": val.get("mispricing_pct"),
        "pricing_view": val.get("pricing_view"),
        "value_drivers": val.get("value_drivers"),
        "net_opportunity_delta_value": val.get("net_opportunity_delta_value"),
        "net_opportunity_delta_pct": val.get("net_opportunity_delta_pct"),
        "primary_value_source": unified.get("primary_value_source"),
        "key_value_drivers": unified.get("key_value_drivers") or [],
        "what_must_be_true": unified.get("what_must_be_true") or [],
    }


# ---------- get_strategy_fit ----------


def get_strategy_fit(property_id: str, *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Best-path read: rental profile + valuation stance + unified best_path."""
    from briarwood.agent.overrides import inputs_with_overrides
    from briarwood.runner_routed import run_routed_report

    inputs_path = SAVED_PROPERTIES_DIR / property_id / "inputs.json"
    if not inputs_path.exists():
        raise ToolUnavailable(f"no inputs.json for property '{property_id}'")

    with inputs_with_overrides(inputs_path, overrides or {}) as effective_path:
        result = run_routed_report(effective_path, user_input="best strategy flip rent hold primary")
    outputs = getattr(result.engine_output, "outputs", {}) or {}
    unified = result.unified_output.model_dump()

    def _metrics(mod: str) -> dict[str, Any]:
        entry = outputs.get(mod)
        if entry is None:
            return {}
        data = getattr(entry, "data", None)
        if data is None and isinstance(entry, dict):
            data = entry.get("data")
        return (data or {}).get("metrics") or {}

    rental = _metrics("rental_option")
    carry = _metrics("carry_cost")
    val = _metrics("valuation")
    return {
        "property_id": property_id,
        "best_path": unified.get("best_path"),
        "recommendation": unified.get("recommendation"),
        "primary_value_source": unified.get("primary_value_source"),
        "pricing_view": val.get("pricing_view"),
        "rental_ease_label": rental.get("rental_ease_label"),
        "rental_ease_score": rental.get("rental_ease_score"),
        "rent_support_score": rental.get("rent_support_score"),
        "liquidity_score": rental.get("liquidity_score"),
        "monthly_cash_flow": carry.get("monthly_cash_flow"),
        "cash_on_cash_return": carry.get("cash_on_cash_return"),
        "annual_noi": carry.get("annual_noi"),
    }


# ---------- registry ----------


def render_chart(
    kind: str,
    property_id: str,
    *,
    session_id: str = "default",
    fmt: str = "html",
) -> dict[str, Any]:
    """Run analyze_property, build the requested chart, write it to disk, return its path."""
    from briarwood.agent.rendering import ChartUnavailable, render_chart as _render

    try:
        if kind == "risk_bar":
            payload = get_risk_profile(property_id)
        elif kind == "scenario_fan":
            payload = get_projection(property_id)
        else:
            payload = analyze_property(property_id)
    except ToolUnavailable as exc:
        raise ChartUnavailable(str(exc)) from exc
    path = _render(kind, payload, session_id=session_id, fmt=fmt)
    return {"property_id": property_id, "kind": kind, "path": str(path.resolve()), "format": fmt}


TOOL_ALLOWED_FOR: dict[str, set[AnswerType]] = {
    "get_property_summary": {AnswerType.LOOKUP, AnswerType.SEARCH, AnswerType.CHITCHAT},
    "analyze_property": {AnswerType.DECISION, AnswerType.COMPARISON, AnswerType.VISUALIZE},
    "search_listings": {AnswerType.SEARCH},
    "underwrite_matches": {AnswerType.SEARCH, AnswerType.COMPARISON},
    "research_town": {AnswerType.RESEARCH, AnswerType.DECISION},
    "render_chart": {AnswerType.VISUALIZE},
    "get_rent_estimate": {AnswerType.RENT_LOOKUP},
    "get_projection": {AnswerType.PROJECTION},
    "get_risk_profile": {AnswerType.RISK, AnswerType.DECISION},
    "get_value_thesis": {AnswerType.EDGE, AnswerType.DECISION},
    "get_strategy_fit": {AnswerType.STRATEGY, AnswerType.DECISION},
}


def tool_allowed(tool_name: str, answer_type: AnswerType) -> bool:
    return answer_type in TOOL_ALLOWED_FOR.get(tool_name, set())
