from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def detect_context_type(
    question: str | None,
    *,
    resolution_route: str | None = None,
    selected_town: str | None = None,
) -> str:
    """Classify landing intake into property, area, or generic context."""

    normalized_question = " ".join(str(question or "").strip().lower().split())
    if resolution_route in {"saved_property", "new_property"}:
        return "property"
    if resolution_route == "town" or str(selected_town or "").strip():
        return "area"
    if any(
        token in normalized_question
        for token in (
            "market",
            "area",
            "town",
            "zip code",
            "neighborhood",
            "around here",
            "in belmar",
            "in asbury park",
        )
    ):
        return "area"
    return "generic"


def build_intelligence_session(
    *,
    question: str | None,
    context_type: str,
    title: str,
    recommendation: str,
    decision: str = "mixed",
    best_path: str = "",
    key_risks: list[str] | None = None,
    confidence: float = 0.0,
    next_questions: list[str] | None = None,
    recommended_next_run: str | None = None,
    selected_town: str | None = None,
    missing_context: bool = False,
    supporting_facts: dict[str, Any] | None = None,
    lower_section: str | None = None,
) -> dict[str, Any]:
    """Build a UI-safe conditional intelligence result payload."""

    return {
        "page": "result",
        "question": str(question or "").strip(),
        "context_type": context_type,
        "title": title,
        "recommendation": recommendation,
        "decision": decision,
        "best_path": best_path,
        "key_risks": list(key_risks or []),
        "confidence": float(confidence),
        "next_questions": list(next_questions or []),
        "recommended_next_run": recommended_next_run,
        "selected_town": selected_town,
        "missing_context": bool(missing_context),
        "was_conditional_answer": True,
        "supporting_facts": dict(supporting_facts or {}),
        "lower_section": lower_section or "",
    }


def build_area_or_generic_result(
    *,
    question: str | None,
    context_type: str,
    selected_town: str | None = None,
    analysis_lenses: list[str] | None = None,
) -> dict[str, Any]:
    """Return a conditional result page payload for area or generic questions."""

    clean_question = str(question or "").strip()
    lenses = {str(item).strip().lower() for item in (analysis_lenses or [])}
    if context_type == "area" and selected_town:
        recommendation = (
            f"Briarwood can frame the market question for {selected_town}, "
            "but a specific buy/pass answer still needs a property."
        )
        best_path = (
            f"Use {selected_town} as a search zone, then open one candidate property "
            "for a routed, property-specific decision run."
        )
        key_risks = [
            "Area-level context is directional, not property-specific underwriting.",
            "A true buy/pass decision still depends on one address, basis, and assumptions.",
        ]
        next_questions = [
            f"Which property in {selected_town} deserves the first decision run?",
            "What question matters most for that property: buy, risk, value, or future rent?",
        ]
        title = f"{selected_town} intelligence"

        if "market_upside" in lenses:
            recommendation = (
                f"{selected_town} can be framed as a premium search zone with potential upside, "
                "but Briarwood still needs one address to test entry basis and trapped value."
            )
            best_path = (
                f"Use {selected_town} as a premium-market filter, then open one candidate property "
                "to test whether the entry basis is truly attractive relative to comps and scarcity."
            )
            key_risks = [
                "Town-level upside does not prove that one listing is mispriced.",
                "Scarcity and premium-market narratives still need a property-specific entry basis check.",
            ]
            next_questions = [
                f"Which {selected_town} property looks discounted relative to recent comps?",
                "Is the opportunity really entry basis, or is the market rejecting this listing for a property-specific reason?",
            ]
            title = f"{selected_town} upside intelligence"
        elif "valuation" in lenses:
            recommendation = (
                f"Briarwood can use {selected_town} to frame premium-market pricing context, "
                "but the actual value call still depends on one address and one basis."
            )
            best_path = (
                "Anchor the next run to one property so Briarwood can compare entry basis, local comp support, and the quality of the value gap."
            )
        elif "risk" in lenses:
            recommendation = (
                f"Briarwood can frame the main risk themes in {selected_town}, "
                "but the true downside still depends on the property and basis."
            )
            best_path = (
                "Use the area read to understand liquidity and market tone, then open one property to pressure-test downside directly."
            )

        return build_intelligence_session(
            question=clean_question,
            context_type="area",
            title=title,
            recommendation=recommendation,
            decision="mixed",
            best_path=best_path,
            key_risks=key_risks,
            confidence=0.42,
            next_questions=next_questions,
            selected_town=selected_town,
            supporting_facts={"selected_town": selected_town, "analysis_lenses": sorted(lenses)},
            lower_section="town_results",
        )

    return build_intelligence_session(
        question=clean_question,
        context_type="generic",
        title="More context needed",
        recommendation=(
            "Briarwood needs either a property or an area to give a useful decision answer."
        ),
        decision="mixed",
        best_path=(
            "Add a property address, listing URL, or town so the routing system can pick the right analysis depth and module path."
        ),
        key_risks=[
            "The current question is too general for property-specific underwriting.",
            "Without context, any answer would pretend precision Briarwood does not have.",
        ],
        confidence=0.18,
        next_questions=[
            "Which property are you evaluating?",
            "If not one property, which town or area are you thinking about?",
        ],
        missing_context=True,
        supporting_facts={"reason": "missing_property_or_area_context"},
    )


def run_routed_property_question(
    *,
    question: str,
    property_id: str,
) -> dict[str, Any] | None:
    """Route a property question through the V2 router and return a session dict.

    Returns an intelligence-session dict built from the real
    UnifiedIntelligenceOutput, or None if the routed path fails (in which
    case the caller should fall back to the legacy rendering).
    """
    from briarwood.dash_app.data import load_routed_result_for_preset

    try:
        routed = load_routed_result_for_preset(property_id)
    except Exception:
        logger.debug(
            "load_routed_result_for_preset failed for %s, skipping routed question",
            property_id,
            exc_info=True,
        )
        routed = None

    if routed is None:
        return None

    # Re-route with the user's actual question if it differs from the
    # default "Should I buy this property?" that the loader used.
    clean_question = str(question or "").strip()
    if clean_question:
        from briarwood.router import route_user_input

        try:
            routing_decision = route_user_input(clean_question)
        except Exception:
            logger.debug(
                "route_user_input failed for question %r, using existing routed result",
                clean_question,
                exc_info=True,
            )
            routing_decision = routed.routing_decision
    else:
        routing_decision = routed.routing_decision

    unified = routed.unified_output
    return build_intelligence_session(
        question=clean_question or question,
        context_type="property",
        title=f"Routed analysis for {routed.report.address}",
        recommendation=unified.recommendation,
        decision=unified.decision.value,
        best_path=unified.best_path,
        key_risks=unified.key_risks,
        confidence=unified.confidence,
        next_questions=unified.next_questions,
        recommended_next_run=unified.recommended_next_run,
        missing_context=False,
        supporting_facts={
            **(unified.supporting_facts or {}),
            "execution_mode": routed.execution_mode,
            "analysis_depth_used": unified.analysis_depth_used.value,
            "intent_type": routing_decision.intent_type.value,
            "selected_modules": [m.value for m in routing_decision.selected_modules],
        },
    )


def capture_tags_for_session(session: dict[str, Any]) -> list[str]:
    """Tag conditional sessions for lightweight product-learning review."""

    tags: list[str] = []
    if bool(session.get("missing_context")):
        tags.append("low-confidence-due-to-missing-inputs")
    if str(session.get("context_type") or "") == "generic":
        tags.append("unknown-question-pattern")
    if str(session.get("context_type") or "") == "area":
        tags.append("missing-scenario-type")
    return tags


__all__ = [
    "build_area_or_generic_result",
    "build_intelligence_session",
    "capture_tags_for_session",
    "detect_context_type",
    "run_routed_property_question",
]
