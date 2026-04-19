"""Deterministic unified-output builder for Phase 5.

Given module results + the Phase 4 interaction trace, this module produces a
fully-populated ``UnifiedIntelligenceOutput`` whose decision is derivable
without an LLM. Every field can be traced back to either a module metric or
a bridge record.

Trust gate (Spec §6): if trust is too low, the stance collapses to
``CONDITIONAL`` and the recommendation explicitly says *why no stronger
stance is possible*. Stronger stances are only issued when the trust floor is met.
"""

from __future__ import annotations

from typing import Any

from briarwood.routing_schema import (
    AnalysisDepth,
    DecisionStance,
    DecisionType,
    ParserOutput,
    UnifiedIntelligenceOutput,
)

# Confidence thresholds for the trust gate. Below TRUST_FLOOR_STRONG, no
# "strong_buy"; below TRUST_FLOOR_ANY, stance collapses to conditional.
TRUST_FLOOR_STRONG = 0.70
TRUST_FLOOR_ANY = 0.40


# ─── Public entry point ───────────────────────────────────────────────────────


def build_unified_output(
    *,
    property_summary: dict[str, Any],
    parser_output: dict[str, Any],
    module_results: dict[str, Any],
    interaction_trace: dict[str, Any],
) -> dict[str, Any]:
    """Build a UnifiedIntelligenceOutput dict from module + interaction state.

    Returns a dict (not a model) so the orchestrator's normalization path
    continues to work. The output is immediately validatable against
    ``UnifiedIntelligenceOutput``.
    """

    parser = ParserOutput.model_validate(parser_output)
    outputs = _unwrap_outputs(module_results)
    bridges = _index_bridges(interaction_trace)

    value_position = compute_value_position(outputs, bridges)
    primary_value_source = _primary_value_source(bridges)
    trust_flags = collect_trust_flags(outputs, bridges)
    what_must_be_true = _what_must_be_true(bridges)
    next_checks = _next_checks(parser, outputs, bridges)

    aggregate_confidence = _aggregate_confidence(outputs, bridges)
    contradiction_count = _contradiction_count(bridges)
    blocked_thesis_warnings = _blocked_thesis_warnings(bridges)
    trust_summary = _trust_summary(outputs, bridges, aggregate_confidence)

    stance, decision, recommendation, best_path = classify_decision_stance(
        value_position=value_position,
        trust_flags=trust_flags,
        bridges=bridges,
        aggregate_confidence=aggregate_confidence,
    )

    key_value_drivers = _key_value_drivers(outputs, bridges, primary_value_source)
    key_risks = _key_risks(outputs, bridges)
    why_this_stance = _why_this_stance(
        value_position=value_position,
        key_value_drivers=key_value_drivers,
        key_risks=key_risks,
        trust_flags=trust_flags,
        bridges=bridges,
        stance=stance,
        aggregate_confidence=aggregate_confidence,
    )
    what_changes_my_view = _what_changes_my_view(
        value_position=value_position,
        trust_flags=trust_flags,
        next_checks=next_checks,
        bridges=bridges,
    )

    return {
        "recommendation": recommendation,
        "decision": decision.value,
        "best_path": best_path,
        "key_value_drivers": key_value_drivers,
        "key_risks": key_risks,
        "confidence": round(aggregate_confidence, 2),
        "analysis_depth_used": parser.analysis_depth.value,
        "next_questions": next_checks[:3],
        "recommended_next_run": _recommended_next_run(parser),
        "supporting_facts": {
            "property_id": property_summary.get("property_id"),
            "selected_modules": sorted(outputs.keys()),
            "primary_value_source": primary_value_source,
        },
        "decision_stance": stance.value,
        "primary_value_source": primary_value_source,
        "value_position": value_position,
        "what_must_be_true": what_must_be_true,
        "next_checks": next_checks,
        "trust_flags": trust_flags,
        "trust_summary": trust_summary,
        "contradiction_count": contradiction_count,
        "blocked_thesis_warnings": blocked_thesis_warnings,
        "why_this_stance": why_this_stance,
        "what_changes_my_view": what_changes_my_view,
        "interaction_trace": interaction_trace,
    }


# ─── Decision stance classifier (the trust gate lives here) ───────────────────


def classify_decision_stance(
    *,
    value_position: dict[str, Any],
    trust_flags: list[str],
    bridges: dict[str, dict[str, Any]],
    aggregate_confidence: float,
) -> tuple[DecisionStance, DecisionType, str, str]:
    """Pick a decision stance, a coarse DecisionType, a recommendation line,
    and a best-path line.

    Rule order:
    1. Trust floor: below ``TRUST_FLOOR_ANY`` → CONDITIONAL. No strong stance.
    2. Strong buy: comp-supported, no major conflicts, no heavy fragility.
    3. Pass / pass-unless-changes: price is materially above comp-supported value.
    4. Interesting-but-fragile: solid value but risk/fragility makes it thin.
    5. Execution-dependent: thesis requires material reno / appreciation.
    6. Buy-if-price-improves: fair to slightly overpriced but good fundamentals.
    7. Fallback: MIXED + PASS_UNLESS_CHANGES.
    """

    premium_pct = value_position.get("premium_discount_pct")
    discount_demanded = _float(
        (bridges.get("valuation_x_risk") or {}).get("adjustments", {}).get("extra_discount_demanded_pct")
    ) or 0.0
    band_upper = _float(
        (bridges.get("valuation_x_town") or {}).get("adjustments", {}).get("premium_band_upper_pct")
    ) or 0.07
    fragility = _float(
        (bridges.get("scenario_x_risk") or {}).get("adjustments", {}).get("fragility_score")
    ) or 0.0
    conflicts = (bridges.get("conflict_detector") or {}).get("adjustments", {}).get("conflicts") or []

    # --- 1. Trust gate ----------------------------------------------------------
    if aggregate_confidence < TRUST_FLOOR_ANY:
        return (
            DecisionStance.CONDITIONAL,
            DecisionType.MIXED,
            "Conditional — trust is too low to issue a directional recommendation. "
            "Resolve the flagged trust gaps before leaning in or out.",
            "Close the data gaps listed under trust_flags before making this a decision question.",
        )

    # Determine whether price is favorable vs comps.
    if isinstance(premium_pct, (int, float)):
        # premium_pct > 0 means ask is ABOVE comp-supported value.
        adjusted_acceptable_premium = band_upper - discount_demanded
        price_gap = premium_pct - adjusted_acceptable_premium
    else:
        price_gap = None

    # --- 2. Strong buy ---------------------------------------------------------
    if (
        price_gap is not None
        and price_gap <= -0.05
        and aggregate_confidence >= TRUST_FLOOR_STRONG
        and fragility < 0.5
        and not conflicts
    ):
        return (
            DecisionStance.STRONG_BUY,
            DecisionType.BUY,
            "Strong buy — price sits meaningfully below the risk-adjusted value band with no major conflicts.",
            "Move to offer; the evidence supports leaning in at current pricing.",
        )

    # --- 3. Price-too-high path ------------------------------------------------
    if price_gap is not None and price_gap > 0.05:
        return (
            DecisionStance.PASS_UNLESS_CHANGES,
            DecisionType.PASS,
            "Pass unless the basis improves — price is above the risk-adjusted comp band.",
            "Do not chase at ask. Re-engage only if the entry price moves into the acceptable band.",
        )

    # --- 4. Fragile / execution-dependent --------------------------------------
    if fragility >= 0.6:
        return (
            DecisionStance.EXECUTION_DEPENDENT,
            DecisionType.MIXED,
            "Execution-dependent — the thesis works only if the listed what-must-be-true items hold.",
            "Underwrite this only if you can credibly own the execution risks enumerated in what_must_be_true.",
        )

    if conflicts or fragility >= 0.4:
        return (
            DecisionStance.INTERESTING_BUT_FRAGILE,
            DecisionType.MIXED,
            "Interesting but fragile — value is there, but risk and conflict flags make it thinner than it first appears.",
            "Treat this as conditional interest: verify the named conflicts before committing.",
        )

    # --- 5. Buy-if-price-improves ---------------------------------------------
    if price_gap is not None and price_gap > -0.02:
        return (
            DecisionStance.BUY_IF_PRICE_IMPROVES,
            DecisionType.MIXED,
            "Buy if price improves — fundamentals support engagement, but current pricing leaves little margin.",
            "Make an offer inside the risk-adjusted band rather than at ask.",
        )

    # --- 6. Fallback -----------------------------------------------------------
    return (
        DecisionStance.PASS_UNLESS_CHANGES,
        DecisionType.MIXED,
        "Mixed — no single factor dominates. Pass unless the data improves in a specific, testable way.",
        "Identify which trust_flags or conflicts most change the picture and resolve those first.",
    )


# ─── Field builders ────────────────────────────────────────────────────────────


def compute_value_position(
    outputs: dict[str, dict[str, Any]],
    bridges: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build the value_position dict.

    Invariant: ``ask_price`` is always the listing ask (a listing fact). The
    old contract silently aliased ``ask_price = all_in_basis`` which made the
    same nominal field mean different things in different handlers. The two
    are now distinct:

    - ``ask_price``         = listing ask (from valuation.listing_ask_price)
    - ``all_in_basis``      = purchase_price + capex
    - ``ask_premium_pct``   = (all-in basis, actually) vs fair; legacy alias for ``premium_discount_pct``
    - ``basis_premium_pct`` = all_in_basis vs fair value
    """

    val_metrics = _metrics(outputs.get("valuation"))
    fair_value = _float(val_metrics.get("briarwood_current_value"))
    ask_price = _float(val_metrics.get("listing_ask_price"))
    all_in_basis = _float(val_metrics.get("all_in_basis"))
    mispricing_pct = _float(val_metrics.get("mispricing_pct"))
    basis_mispricing_pct = _float(val_metrics.get("basis_mispricing_pct"))

    ask_premium_pct = -mispricing_pct if mispricing_pct is not None else None
    basis_premium_pct = -basis_mispricing_pct if basis_mispricing_pct is not None else None

    return {
        "fair_value_base": fair_value,
        "ask_price": ask_price,
        "all_in_basis": all_in_basis,
        "ask_premium_pct": round(ask_premium_pct, 4) if ask_premium_pct is not None else None,
        "basis_premium_pct": round(basis_premium_pct, 4) if basis_premium_pct is not None else None,
        "premium_discount_pct": (
            round(basis_premium_pct, 4) if basis_premium_pct is not None else None
        ),
        "value_low": _float(val_metrics.get("value_low")),
        "value_high": _float(val_metrics.get("value_high")),
    }


def collect_trust_flags(
    outputs: dict[str, dict[str, Any]],
    bridges: dict[str, dict[str, Any]],
) -> list[str]:
    """Collect module + bridge signals that reduce trust in the recommendation."""

    flags: list[str] = []

    # Valuation trust
    val_payload = outputs.get("valuation") or {}
    val_metrics = _metrics(val_payload)
    comp_conf = _float(val_metrics.get("comp_confidence_score"))
    if comp_conf is not None and comp_conf < 0.5:
        flags.append("thin_comp_set")

    # Valuation anchors disagree materially — the valuation agent flags this by
    # emitting a "ZHVI-based" divergence warning on the wrapped CurrentValueOutput.
    # Surface it so the stance logic and the user both see the anchor conflict
    # instead of silently blending.
    legacy_payload = (val_payload.get("data") or {}).get("legacy_payload") or {}
    val_warnings = list(val_payload.get("warnings") or []) + list(legacy_payload.get("warnings") or [])
    if any(isinstance(w, str) and "ZHVI-based" in w and "diverges" in w for w in val_warnings):
        flags.append("valuation_anchor_divergence")

    # Legal confidence
    legal_conf = _confidence(outputs.get("legal_confidence"))
    if legal_conf is not None and legal_conf < 0.5:
        flags.append("zoning_unverified")

    confidence_payload = outputs.get("confidence") or {}
    confidence_data = (confidence_payload.get("data") or {})
    contradiction_count = int(confidence_data.get("contradiction_count") or 0)
    if contradiction_count > 0:
        flags.append("contradictory_inputs")
    estimated_reliance = _float(confidence_data.get("estimated_reliance"))
    if estimated_reliance is not None and estimated_reliance >= 0.5:
        flags.append("estimated_inputs_heavy")
    field_completeness = _float(confidence_data.get("field_completeness"))
    if field_completeness is not None and field_completeness < 0.55:
        flags.append("sparse_property_inputs")

    # Fragility / execution
    fragility = _float(
        (bridges.get("scenario_x_risk") or {}).get("adjustments", {}).get("fragility_score")
    )
    if fragility is not None and fragility >= 0.6:
        flags.append("execution_heavy")

    # Rent downgrade from interaction layer
    rent_bridge = bridges.get("rent_x_risk") or {}
    adj = rent_bridge.get("adjustments") or {}
    downgrade = _float(adj.get("downgrade_amount"))
    if downgrade is not None and downgrade > 0.2:
        flags.append("rent_assumption_fragile")

    # Town context. Fires off RAW data quality (market aggregates +
    # local-intelligence coverage), not the downweighted prior — otherwise
    # towns with rich seeded context flag as weak whenever direct comps exist.
    town_conf = _float(val_metrics.get("town_context_confidence_raw"))
    if town_conf is None:
        town_conf = _float(val_metrics.get("town_context_confidence"))
    if town_conf is not None and town_conf < 0.4:
        flags.append("weak_town_context")

    # Carry cost completeness
    carry_metrics = _metrics(outputs.get("carry_cost"))
    if carry_metrics.get("carrying_cost_complete") is False:
        flags.append("incomplete_carry_inputs")

    return list(dict.fromkeys(flags))


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _primary_value_source(bridges: dict[str, dict[str, Any]]) -> str:
    rec = bridges.get("primary_value_source") or {}
    adj = rec.get("adjustments") or {}
    return str(adj.get("primary_value_source") or "unknown")


def _what_must_be_true(bridges: dict[str, dict[str, Any]]) -> list[str]:
    items: list[str] = []
    scenario = bridges.get("scenario_x_risk") or {}
    for line in (scenario.get("adjustments") or {}).get("what_must_be_true") or []:
        if line and line not in items:
            items.append(str(line))

    # Rent-dependent conditions.
    rent_cost = bridges.get("rent_x_cost") or {}
    required_occ = _float((rent_cost.get("adjustments") or {}).get("required_occupancy"))
    if required_occ is not None and required_occ >= 0.85:
        items.append(f"Property sustains ~{required_occ*100:.0f}% occupancy or better.")

    return items


def _next_checks(
    parser: ParserOutput,
    outputs: dict[str, dict[str, Any]],
    bridges: dict[str, dict[str, Any]],
) -> list[str]:
    checks: list[str] = []

    for flag in collect_trust_flags(outputs, bridges):
        checks.append(_flag_to_check(flag))

    for item in parser.missing_inputs:
        if item == "rent_estimate":
            checks.append("Confirm a defensible market rent from comps or a broker letter.")
        elif item == "purchase_price":
            checks.append("Lock the all-in basis including closing costs and any negotiated credits.")

    # De-duplicate preserving order.
    seen: set[str] = set()
    unique = []
    for c in checks:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def _flag_to_check(flag: str) -> str:
    mapping = {
        "thin_comp_set": "Gather additional comparable sales to tighten the valuation band.",
        "zoning_unverified": "Verify zoning / legal unit status with a source-backed document.",
        "execution_heavy": "Stress-test the renovation/scenario budget and timeline assumptions.",
        "rent_assumption_fragile": "Independently corroborate the rent assumption (broker, comp rentals).",
        "weak_town_context": "Pull town-level scarcity/absorption data before anchoring on town priors.",
        "valuation_anchor_divergence": "Reconcile comps vs. ZHVI — the two anchors disagree by more than the acceptable band.",
        "incomplete_carry_inputs": "Complete the carry-cost inputs (taxes, insurance, financing).",
        "contradictory_inputs": "Resolve the contradictory property facts before trusting the recommendation.",
        "estimated_inputs_heavy": "Replace estimated/defaulted inputs with source-backed property facts.",
        "sparse_property_inputs": "Fill in the missing core property details so the models have a stable baseline.",
    }
    return mapping.get(flag, f"Resolve the {flag} trust gap before deciding.")


def _key_value_drivers(
    outputs: dict[str, dict[str, Any]],
    bridges: dict[str, dict[str, Any]],
    primary_value_source: str,
) -> list[str]:
    drivers: list[str] = []

    rec = bridges.get("valuation_x_town") or {}
    if rec.get("fired"):
        for reason in rec.get("reasoning") or []:
            drivers.append(reason)

    rec = bridges.get("primary_value_source") or {}
    if rec.get("fired"):
        for reason in rec.get("reasoning") or []:
            drivers.append(reason)

    rent_cost = bridges.get("rent_x_cost") or {}
    if rent_cost.get("fired"):
        ratio = _float((rent_cost.get("adjustments") or {}).get("carry_offset_ratio"))
        if ratio is not None and ratio >= 1.0:
            drivers.append(f"Rent covers carry (ratio {ratio:.2f}).")

    opp = bridges.get("opportunity_x_value") or {}
    if opp.get("fired") and (opp.get("adjustments") or {}).get("signal") == "value_driver":
        for reason in opp.get("reasoning") or []:
            drivers.append(reason)

    return list(dict.fromkeys(drivers))[:3]


def _key_risks(
    outputs: dict[str, dict[str, Any]],
    bridges: dict[str, dict[str, Any]],
) -> list[str]:
    risks: list[str] = []

    val_risk = bridges.get("valuation_x_risk") or {}
    if val_risk.get("fired"):
        for r in val_risk.get("reasoning") or []:
            risks.append(r)

    conflicts = (bridges.get("conflict_detector") or {}).get("adjustments", {}).get("conflicts") or []
    for c in conflicts:
        if isinstance(c, dict) and c.get("message"):
            risks.append(c["message"])

    fragility = bridges.get("scenario_x_risk") or {}
    if fragility.get("fired"):
        frag_score = _float((fragility.get("adjustments") or {}).get("fragility_score"))
        if frag_score is not None and frag_score >= 0.5:
            risks.append(f"Execution fragility {frag_score:.2f} — thesis depends on assumptions holding.")

    opp = bridges.get("opportunity_x_value") or {}
    if opp.get("fired") and (opp.get("adjustments") or {}).get("signal") == "risk":
        for reason in opp.get("reasoning") or []:
            risks.append(reason)

    return list(dict.fromkeys(risks))[:3]


def _aggregate_confidence(
    outputs: dict[str, dict[str, Any]],
    bridges: dict[str, dict[str, Any]],
) -> float:
    confidences = [
        _confidence(payload)
        for payload in outputs.values()
        if _confidence(payload) is not None
    ]
    if not confidences:
        return 0.0
    module_avg = sum(confidences) / len(confidences)

    # Apply bridge-level downgrades: rent_x_risk explicitly reports an adjusted
    # rent confidence we can fold in.
    rent_risk = bridges.get("rent_x_risk") or {}
    adj = rent_risk.get("adjustments") or {}
    adjusted_rent_conf = _float(adj.get("adjusted_rent_confidence"))
    raw_rent_conf = _float(adj.get("raw_rent_confidence"))
    if adjusted_rent_conf is not None and raw_rent_conf is not None and raw_rent_conf > 0:
        # Scale the module average by how much rent confidence got cut.
        ratio = max(0.0, min(adjusted_rent_conf / raw_rent_conf, 1.0))
        # Only apply a partial shrink so a single fragile signal doesn't crater everything.
        module_avg *= 0.85 + 0.15 * ratio

    contradiction_penalty = min(_contradiction_count(bridges) * 0.06, 0.18)
    blocked_penalty = min(len(_blocked_thesis_warnings(bridges)) * 0.04, 0.12)
    module_avg -= contradiction_penalty + blocked_penalty

    return max(0.0, min(module_avg, 1.0))


def _contradiction_count(bridges: dict[str, dict[str, Any]]) -> int:
    conflicts = (bridges.get("conflict_detector") or {}).get("adjustments", {}).get("conflicts") or []
    return len([conflict for conflict in conflicts if isinstance(conflict, dict)])


def _blocked_thesis_warnings(bridges: dict[str, dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    conflicts = (bridges.get("conflict_detector") or {}).get("adjustments", {}).get("conflicts") or []
    for conflict in conflicts:
        if isinstance(conflict, dict) and conflict.get("message"):
            warnings.append(str(conflict["message"]))
    scenario = bridges.get("scenario_x_risk") or {}
    fragility = _float((scenario.get("adjustments") or {}).get("fragility_score"))
    if fragility is not None and fragility >= 0.65:
        warnings.append("The thesis is blocked until the execution burden is reduced or better supported.")
    return list(dict.fromkeys(warnings))


def _trust_summary(
    outputs: dict[str, dict[str, Any]],
    bridges: dict[str, dict[str, Any]],
    aggregate_confidence: float,
) -> dict[str, Any]:
    confidence_payload = outputs.get("confidence") or {}
    data = dict((confidence_payload.get("data") or {}))
    return {
        "confidence": round(aggregate_confidence, 4),
        "band": _confidence_band(aggregate_confidence),
        "field_completeness": _float(data.get("field_completeness")),
        "estimated_reliance": _float(data.get("estimated_reliance")),
        "contradiction_count": int(data.get("contradiction_count") or _contradiction_count(bridges)),
        "blocked_thesis_warnings": _blocked_thesis_warnings(bridges),
        "trust_flags": collect_trust_flags(outputs, bridges),
    }


def _why_this_stance(
    *,
    value_position: dict[str, Any],
    key_value_drivers: list[str],
    key_risks: list[str],
    trust_flags: list[str],
    bridges: dict[str, dict[str, Any]],
    stance: DecisionStance | None = None,
    aggregate_confidence: float | None = None,
) -> list[str]:
    lines: list[str] = []
    # AUDIT O.5: when the trust gate fires, the CONDITIONAL stance is an
    # informational limit (Briarwood can't issue a directional call), not a
    # "wait and see" market judgment. Lead with that so downstream consumers
    # and the user can tell the collapse apart from an ordinary PASS/HOLD.
    if stance is DecisionStance.CONDITIONAL:
        if aggregate_confidence is not None:
            lines.append(
                f"Trust floor fired (confidence {aggregate_confidence:.2f} below "
                f"{TRUST_FLOOR_ANY:.2f}) — no directional call until the flagged "
                "gaps close."
            )
        else:
            lines.append(
                "Trust floor fired — no directional call until the flagged gaps close."
            )
    premium = _float(value_position.get("premium_discount_pct"))
    if premium is not None:
        if premium > 0:
            lines.append(f"Current basis sits about {premium*100:.1f}% above Briarwood's fair-value anchor.")
        else:
            lines.append(f"Current basis sits about {abs(premium)*100:.1f}% below Briarwood's fair-value anchor.")
    lines.extend(key_value_drivers[:2])
    lines.extend(key_risks[:2])
    if trust_flags:
        lines.append("Trust is limited by " + ", ".join(trust_flags[:3]) + ".")
    return list(dict.fromkeys(lines))[:4]


def _what_changes_my_view(
    *,
    value_position: dict[str, Any],
    trust_flags: list[str],
    next_checks: list[str],
    bridges: dict[str, dict[str, Any]],
) -> list[str]:
    items: list[str] = []
    premium = _float(value_position.get("premium_discount_pct"))
    extra_discount = _float(
        (bridges.get("valuation_x_risk") or {}).get("adjustments", {}).get("extra_discount_demanded_pct")
    )
    if premium is not None and premium > 0:
        required = premium + (extra_discount or 0.0)
        items.append(f"A price improvement of about {required*100:.1f}% would materially improve the setup.")
    if "incomplete_carry_inputs" in trust_flags:
        items.append("Confirmed taxes, insurance, and financing could tighten the carry picture.")
    if "zoning_unverified" in trust_flags:
        items.append("A clean legal/zoning confirmation would improve rent confidence and reduce risk.")
    items.extend(next_checks[:3])
    return list(dict.fromkeys(items))[:4]


def _confidence_band(value: float) -> str:
    if value >= 0.75:
        return "High confidence"
    if value >= 0.55:
        return "Moderate confidence"
    if value >= 0.3:
        return "Low confidence"
    return "Speculative"


def _recommended_next_run(parser: ParserOutput) -> str | None:
    if parser.analysis_depth == AnalysisDepth.SNAPSHOT:
        return "decision"
    if parser.analysis_depth == AnalysisDepth.DECISION:
        return "scenario"
    if parser.analysis_depth == AnalysisDepth.SCENARIO and parser.renovation_plan:
        return "deep_dive"
    return None


def _unwrap_outputs(module_results: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Module results may be wrapped as {'outputs': {...}} or flat."""
    if "outputs" in module_results and isinstance(module_results["outputs"], dict):
        inner = module_results["outputs"]
        if inner and all(isinstance(v, dict) for v in inner.values()):
            return inner
    return {k: v for k, v in module_results.items() if isinstance(v, dict)}


def _index_bridges(trace: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = trace.get("records") or []
    return {r.get("name"): r for r in records if isinstance(r, dict) and r.get("name")}


def _metrics(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data") or {}
    return dict(data.get("metrics") or {})


def _confidence(payload: dict[str, Any] | None) -> float | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("confidence")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


__all__ = [
    "build_unified_output",
    "classify_decision_stance",
    "collect_trust_flags",
    "compute_value_position",
]
