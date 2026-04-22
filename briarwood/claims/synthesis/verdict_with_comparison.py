"""Deterministic producer that turns module/bridge state into a
VerdictWithComparisonClaim.

Consumes the same raw inputs as `briarwood.synthesis.structured.build_unified_output`
(property_summary, parser_output, module_results, interaction_trace) but
produces a narrowly-shaped claim object for the wedge's
verdict_with_comparison archetype. No LLM calls; no prose.
"""
from __future__ import annotations

from statistics import median
from typing import Any, Iterable, Mapping

from briarwood.claims.archetypes import Archetype  # noqa: F401  (re-exported via __init__)
from briarwood.claims.base import (
    Caveat,
    Confidence,
    NextQuestion,
    Provenance,
    SurfacedInsight,  # noqa: F401  (placeholder for scout fill-in)
)
from briarwood.claims.synthesis.templates import (
    BRIDGE_SENTENCE,
    DEFAULT_NEXT_QUESTIONS,
    VERDICT_HEADLINE,
)
from briarwood.claims.verdict_with_comparison import (
    Comparison,
    ComparisonScenario,
    Subject,
    Verdict,
    VerdictWithComparisonClaim,
)

METHOD_NAME = "comparable_sales_v1"
MIN_SCENARIO_SAMPLE = 1  # Editor's "sample_size < 5" caveat is a separate check.

# Delta thresholds (in percent) for verdict label.
VALUE_FIND_THRESHOLD = -5.0
OVERPRICED_THRESHOLD = 5.0


def build_verdict_with_comparison_claim(
    *,
    property_summary: Mapping[str, Any],
    parser_output: Mapping[str, Any],  # noqa: ARG001  (kept for signature parity)
    module_results: Mapping[str, Any],
    interaction_trace: Mapping[str, Any],
) -> VerdictWithComparisonClaim:
    outputs = _unwrap_outputs(module_results)

    subject = _build_subject(property_summary, outputs)
    verdict = _build_verdict(subject, outputs)
    scenarios, scenario_caveats = _build_scenarios(subject, outputs)
    comparison = Comparison(
        metric="price_per_sqft",
        unit="$/sqft",
        scenarios=scenarios,
        chart_rule="horizontal_bar_with_ranges",
        emphasis_scenario_id=None,  # Value Scout sets this if it fires.
    )

    caveats = list(scenario_caveats) + _caveats_from_bridges(interaction_trace)
    provenance = _build_provenance(outputs, interaction_trace)
    next_questions = [NextQuestion(**q) for q in DEFAULT_NEXT_QUESTIONS]

    return VerdictWithComparisonClaim(
        subject=subject,
        verdict=verdict,
        bridge_sentence=BRIDGE_SENTENCE,
        comparison=comparison,
        caveats=caveats,
        next_questions=next_questions,
        provenance=provenance,
        surfaced_insight=None,
    )


# ─── Subject / Verdict ─────────────────────────────────────────────────


def _build_subject(
    property_summary: Mapping[str, Any],
    outputs: Mapping[str, Mapping[str, Any]],
) -> Subject:
    val_metrics = _metrics(outputs.get("valuation"))
    ask = _float(val_metrics.get("listing_ask_price")) or _float(
        property_summary.get("purchase_price")
    ) or 0.0
    return Subject(
        property_id=str(property_summary.get("property_id") or ""),
        address=str(property_summary.get("address") or ""),
        beds=int(property_summary.get("beds") or 0),
        baths=float(property_summary.get("baths") or 0.0),
        sqft=int(property_summary.get("sqft") or 0),
        ask_price=float(ask),
        status=_resolve_status(property_summary),
    )


def _resolve_status(property_summary: Mapping[str, Any]) -> str:
    raw = str(property_summary.get("status") or "").strip().lower()
    if raw in {"active", "pending", "sold"}:
        return raw
    return "unknown"


def _build_verdict(
    subject: Subject,
    outputs: Mapping[str, Mapping[str, Any]],
) -> Verdict:
    val_metrics = _metrics(outputs.get("valuation"))
    fmv = _float(val_metrics.get("briarwood_current_value"))
    confidence_score = _overall_confidence(outputs)

    comp_count, comp_radius_mi, comp_window_months = _comp_window_stats(outputs)

    if fmv is None or fmv <= 0 or subject.ask_price <= 0:
        return Verdict(
            label="insufficient_data",
            headline=VERDICT_HEADLINE["insufficient_data"],
            basis_fmv=float(fmv or 0.0),
            ask_vs_fmv_delta_pct=0.0,
            method=METHOD_NAME,
            comp_count=comp_count,
            comp_radius_mi=comp_radius_mi,
            comp_window_months=comp_window_months,
            confidence=Confidence.from_score(confidence_score),
        )

    delta_pct = ((subject.ask_price - fmv) / fmv) * 100.0
    label = _verdict_label(delta_pct)
    headline = _format_headline(label, ask=subject.ask_price, fmv=fmv, delta_pct=delta_pct)

    return Verdict(
        label=label,
        headline=headline,
        basis_fmv=fmv,
        ask_vs_fmv_delta_pct=delta_pct,
        method=METHOD_NAME,
        comp_count=comp_count,
        comp_radius_mi=comp_radius_mi,
        comp_window_months=comp_window_months,
        confidence=Confidence.from_score(confidence_score),
    )


def _verdict_label(delta_pct: float) -> str:
    if delta_pct <= VALUE_FIND_THRESHOLD:
        return "value_find"
    if delta_pct >= OVERPRICED_THRESHOLD:
        return "overpriced"
    return "fair"


def _format_headline(label: str, *, ask: float, fmv: float, delta_pct: float) -> str:
    template = VERDICT_HEADLINE[label]
    if label in {"value_find", "overpriced"}:
        return template.format(
            delta_abs=abs(ask - fmv),
            delta_pct=abs(delta_pct),
        )
    return template


def _overall_confidence(outputs: Mapping[str, Mapping[str, Any]]) -> float:
    conf_module = outputs.get("confidence") or {}
    score = _float(conf_module.get("confidence"))
    if score is None:
        data = conf_module.get("data") if isinstance(conf_module, Mapping) else None
        extra = data.get("extra_data") if isinstance(data, Mapping) else None
        if isinstance(extra, Mapping):
            score = _float(extra.get("combined_confidence"))
    if score is None:
        # Fallback: lean on valuation's comp confidence when the confidence
        # module didn't participate.
        val_metrics = _metrics(outputs.get("valuation"))
        score = _float(val_metrics.get("comp_confidence_score"))
    if score is None:
        return 0.0
    return max(0.0, min(1.0, float(score)))


def _comp_window_stats(
    outputs: Mapping[str, Mapping[str, Any]],
) -> tuple[int, float, int]:
    """Returns (comp_count, radius_mi, window_months) from the comp set.

    Radius and window are computed from the adjusted comps actually used;
    valuation does not emit them directly today.
    """
    comps = _iter_comps(outputs)
    distances = [_float(_attr(c, "distance_to_subject_miles")) for c in comps]
    ages_days = [_float(_attr(c, "sale_age_days")) for c in comps]
    valid_distances = [d for d in distances if d is not None]
    valid_ages = [a for a in ages_days if a is not None]

    val_metrics = _metrics(outputs.get("valuation"))
    comp_count = int(val_metrics.get("comp_count") or len(list(_iter_comps(outputs))) or 0)

    radius = max(valid_distances) if valid_distances else 0.0
    window_months = int(round(max(valid_ages) / 30.0)) if valid_ages else 0
    return comp_count, float(radius), window_months


# ─── Scenarios ─────────────────────────────────────────────────────────


def _build_scenarios(
    subject: Subject,
    outputs: Mapping[str, Mapping[str, Any]],
) -> tuple[list[ComparisonScenario], list[Caveat]]:
    """Assemble three tiers from comparable_sales.comps_used.

    Tiers:
        - subject_config: same beds+baths as subject, any condition
        - renovated_same: same beds+baths, condition_profile in {renovated, updated}
        - renovated_plus_bath: baths roughly one higher, renovated/updated

    If a tier has zero qualifying comps we drop it and add a caveat.
    """
    comps = list(_iter_comps(outputs))

    def select(predicate) -> list[Any]:
        return [c for c in comps if predicate(c) and _price_per_sqft(c) is not None]

    same_config = select(
        lambda c: _bed_match(c, subject) and _bath_match(c, subject, offset=0.0)
    )
    renovated_same = select(
        lambda c: _bed_match(c, subject)
        and _bath_match(c, subject, offset=0.0)
        and _is_upgraded(c)
    )
    renovated_plus_bath = select(
        lambda c: _bed_match(c, subject)
        and _bath_match(c, subject, offset=1.0)
        and _is_upgraded(c)
    )

    scenarios: list[ComparisonScenario] = []
    caveats: list[Caveat] = []

    tiers = [
        ("subject", "Subject config", same_config, True),
        ("renovated_same", "Renovated, same config", renovated_same, False),
        ("renovated_plus_bath", "Renovated +bath", renovated_plus_bath, False),
    ]

    for tier_id, label, tier_comps, is_subject in tiers:
        if len(tier_comps) < MIN_SCENARIO_SAMPLE:
            caveats.append(
                Caveat(
                    text=f"No qualifying comps for the '{label}' scenario.",
                    severity="info",
                    source="synthesis.verdict_with_comparison",
                )
            )
            continue
        scenarios.append(_scenario_from_comps(tier_id, label, tier_comps, is_subject))

    if not scenarios:
        caveats.append(
            Caveat(
                text="No comparable scenarios could be assembled from the current comp set.",
                severity="warning",
                source="synthesis.verdict_with_comparison",
            )
        )

    return scenarios, caveats


def _scenario_from_comps(
    tier_id: str,
    label: str,
    comps: list[Any],
    is_subject: bool,
) -> ComparisonScenario:
    values = [v for v in (_price_per_sqft(c) for c in comps) if v is not None]
    low = min(values)
    high = max(values)
    med = float(median(values))
    return ComparisonScenario(
        id=tier_id,
        label=label,
        metric_range=(float(low), float(high)),
        metric_median=med,
        is_subject=is_subject,
        sample_size=len(comps),
        flag="none",
        flag_reason=None,
    )


def _bed_match(comp: Any, subject: Subject) -> bool:
    beds = _int(_attr(comp, "bedrooms"))
    return beds is not None and beds == subject.beds


def _bath_match(comp: Any, subject: Subject, *, offset: float) -> bool:
    baths = _float(_attr(comp, "bathrooms"))
    if baths is None:
        return False
    target = subject.baths + offset
    return abs(baths - target) <= 0.5


def _is_upgraded(comp: Any) -> bool:
    profile = _attr(comp, "condition_profile")
    if not isinstance(profile, str):
        return False
    return profile.strip().lower() in {"renovated", "updated"}


def _price_per_sqft(comp: Any) -> float | None:
    price = _float(_attr(comp, "adjusted_price"))
    sqft = _int(_attr(comp, "sqft"))
    if price is None or sqft is None or sqft <= 0:
        return None
    return price / sqft


# ─── Caveats / Provenance ──────────────────────────────────────────────


def _caveats_from_bridges(interaction_trace: Mapping[str, Any]) -> list[Caveat]:
    caveats: list[Caveat] = []
    records = interaction_trace.get("records") if isinstance(interaction_trace, Mapping) else None
    if not isinstance(records, list):
        return caveats
    for record in records:
        if not isinstance(record, Mapping) or not record.get("fired"):
            continue
        name = str(record.get("name") or "bridge")
        adjustments = record.get("adjustments") or {}
        if isinstance(adjustments, Mapping):
            conflicts = adjustments.get("conflicts") or []
            if isinstance(conflicts, list):
                for conflict in conflicts:
                    if isinstance(conflict, str) and conflict.strip():
                        caveats.append(
                            Caveat(text=conflict, severity="warning", source=name)
                        )
        reasoning = record.get("reasoning") or []
        if isinstance(reasoning, list):
            for reason in reasoning:
                if not isinstance(reason, str) or not reason.strip():
                    continue
                caveats.append(Caveat(text=reason, severity="info", source=name))
    return caveats


def _build_provenance(
    outputs: Mapping[str, Mapping[str, Any]],
    interaction_trace: Mapping[str, Any],
) -> Provenance:
    consulted = sorted(k for k, v in outputs.items() if isinstance(v, Mapping) and v)
    bridges_fired: list[str] = []
    records = interaction_trace.get("records") if isinstance(interaction_trace, Mapping) else None
    if isinstance(records, list):
        for record in records:
            if isinstance(record, Mapping) and record.get("fired"):
                name = record.get("name")
                if isinstance(name, str):
                    bridges_fired.append(name)
    return Provenance(
        models_consulted=consulted,
        models_skipped=[],
        skip_reason=None,
        bridges_fired=bridges_fired,
    )


# ─── Helpers ───────────────────────────────────────────────────────────


def _unwrap_outputs(module_results: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Same contract as `briarwood.synthesis.structured._unwrap_outputs`."""
    if not isinstance(module_results, Mapping):
        return {}
    if "outputs" in module_results and isinstance(module_results["outputs"], Mapping):
        inner = module_results["outputs"]
        if inner and all(isinstance(v, Mapping) for v in inner.values()):
            return dict(inner)
    return {k: v for k, v in module_results.items() if isinstance(v, Mapping)}


def _metrics(payload: Any) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    data = payload.get("data") or {}
    if not isinstance(data, Mapping):
        return {}
    metrics = data.get("metrics") or {}
    return metrics if isinstance(metrics, Mapping) else {}


def _iter_comps(outputs: Mapping[str, Mapping[str, Any]]) -> Iterable[Any]:
    comp_module = outputs.get("comparable_sales")
    if not isinstance(comp_module, Mapping):
        return []
    payload = comp_module.get("payload")
    # Payload can be either a pydantic model (ComparableSalesOutput) or its
    # dumped dict form; we duck-type through both.
    comps = _attr(payload, "comps_used")
    if comps is None and isinstance(payload, Mapping):
        comps = payload.get("comps_used")
    if comps is None:
        return []
    return [c for c in comps if c is not None]


def _attr(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:  # NaN check
        return None
    return result


def _int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
