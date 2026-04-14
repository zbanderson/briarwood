from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IntakeContextType(str, Enum):
    """Top-level context class for intake triage."""

    PROPERTY = "property"
    AREA = "area"
    GENERIC = "generic"


class IntakeTriageStatus(str, Enum):
    """High-level triage status used by the UI and dispatcher."""

    READY = "ready"
    NEEDS_CONTEXT = "needs_context"
    NEEDS_PROPERTY_DETAILS = "needs_property_details"
    AREA_ONLY = "area_only"
    PROPERTY_ONLY = "property_only"


class IntakeExecutionMode(str, Enum):
    """Execution mode selected by intake triage."""

    PROPERTY_ROUTED_ANALYSIS = "property_routed_analysis"
    AREA_CONDITIONAL_ANSWER = "area_conditional_answer"
    GENERIC_CLARIFICATION = "generic_clarification"
    PROPERTY_INTAKE_REQUIRED = "property_intake_required"


class AnalysisLens(str, Enum):
    """Question lens used to emphasize the right downstream evidence."""

    MARKET_UPSIDE = "market_upside"
    VALUATION = "valuation"
    RISK = "risk"
    FUTURE_INCOME = "future_income"
    RENOVATION = "renovation"
    BEST_PATH = "best_path"
    DECISION = "decision"


class ResolvedEntity(BaseModel):
    """Resolved property or area context from intake inputs."""

    model_config = ConfigDict(extra="forbid")

    property_id: str | None = None
    address: str | None = None
    town: str | None = None
    state: str | None = None
    resolution_route: str | None = None
    source_url: str | None = None
    source_label: str | None = None
    is_saved_property: bool = False


class IntakeRequest(BaseModel):
    """Normalized user intake request for the triage agent."""

    model_config = ConfigDict(extra="forbid")

    user_question: str = ""
    address_or_area: str = ""
    listing_url: str = ""
    session_id: str | None = None
    prior_turns: list[dict[str, Any]] = Field(default_factory=list)
    resolved_context: dict[str, Any] = Field(default_factory=dict)


class IntakeTriageDecision(BaseModel):
    """Decision-complete output from the intake triage agent."""

    model_config = ConfigDict(extra="forbid")

    context_type: IntakeContextType
    triage_status: IntakeTriageStatus
    resolved_entity: ResolvedEntity = Field(default_factory=ResolvedEntity)
    user_question: str = ""
    normalized_question: str = ""
    recommended_execution_mode: IntakeExecutionMode
    clarification_prompt: str | None = None
    missing_context: list[str] = Field(default_factory=list)
    should_run_analysis: bool = False
    should_persist_session: bool = True
    analysis_lenses: list[AnalysisLens] = Field(default_factory=list)


class IntakeMessage(BaseModel):
    """One visible turn in the chat-style intake thread."""

    model_config = ConfigDict(extra="forbid")

    role: str
    content: str
    kind: str = "message"
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntakeSessionState(BaseModel):
    """Primary UI state for intake, triage, and follow-up behavior."""

    model_config = ConfigDict(extra="forbid")

    session_id: str | None = None
    current_question: str = ""
    resolved_entity: ResolvedEntity = Field(default_factory=ResolvedEntity)
    clarification_history: list[str] = Field(default_factory=list)
    latest_triage_decision: dict[str, Any] | None = None
    routed_result_metadata: dict[str, Any] = Field(default_factory=dict)
    latest_execution_mode: str | None = None
    was_conditional_answer: bool = False
    context_type: IntakeContextType = IntakeContextType.GENERIC
    analysis_lenses: list[AnalysisLens] = Field(default_factory=list)
    messages: list[IntakeMessage] = Field(default_factory=list)
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)


_AREA_TOKENS = (
    "market",
    "scarcity",
    "premium market",
    "upside",
    "liquidity",
    "inventory",
    "dom",
    "days on market",
    "neighborhood",
    "town",
    "area",
)


def normalize_intake_text(value: str | None) -> str:
    """Normalize intake text without throwing on empty strings."""

    return " ".join(str(value or "").strip().lower().split())


def classify_analysis_lenses(question: str | None) -> list[AnalysisLens]:
    """Classify the main analytical lenses implied by the user's question."""

    normalized = normalize_intake_text(question)
    lenses: list[AnalysisLens] = []

    def _has(*tokens: str) -> bool:
        return any(token in normalized for token in tokens)

    if _has("upside", "premium market", "scarcity", "market", "avon", "neighborhood", "town"):
        lenses.append(AnalysisLens.MARKET_UPSIDE)
    if _has("below ask", "entry", "basis", "price", "ask", "comps", "comp", "mispriced", "discount"):
        lenses.append(AnalysisLens.VALUATION)
    if _has("risk", "downside", "go wrong", "watch out", "worst case"):
        lenses.append(AnalysisLens.RISK)
    if _has("rent", "income", "cash flow", "rental", "future income", "hold"):
        lenses.append(AnalysisLens.FUTURE_INCOME)
    if _has("renovate", "renovation", "value add", "arv", "rehab"):
        lenses.append(AnalysisLens.RENOVATION)
    if _has("best path", "best move", "strategy", "path forward"):
        lenses.append(AnalysisLens.BEST_PATH)
    if _has("should i buy", "buy", "buy at"):
        lenses.append(AnalysisLens.DECISION)

    if not lenses:
        lenses.append(AnalysisLens.DECISION)

    return list(dict.fromkeys(lenses))


def triage_intake_request(
    request: IntakeRequest,
    prior_session: IntakeSessionState | dict[str, Any] | None = None,
) -> IntakeTriageDecision:
    """Interpret one intake request and choose the appropriate next step."""

    normalized_question = normalize_intake_text(request.user_question)
    resolution = dict(request.resolved_context or {})
    route = str(resolution.get("route") or "")
    address_or_area = str(request.address_or_area or "").strip()
    listing_url = str(request.listing_url or "").strip()
    prior = (
        prior_session
        if isinstance(prior_session, IntakeSessionState)
        else IntakeSessionState.model_validate(prior_session)
        if isinstance(prior_session, dict) and prior_session
        else None
    )

    resolved = ResolvedEntity(
        property_id=str(resolution.get("property_id") or "") or None,
        address=str(resolution.get("address") or "") or None,
        town=str(resolution.get("town") or "") or None,
        state=str(resolution.get("state") or "") or None,
        resolution_route=route or None,
        source_url=str(resolution.get("source_url") or listing_url or "") or None,
        source_label=str(resolution.get("source_label") or "") or None,
        is_saved_property=route == "saved_property",
    )

    if not normalized_question and not address_or_area and not listing_url and prior is None:
        return IntakeTriageDecision(
            context_type=IntakeContextType.GENERIC,
            triage_status=IntakeTriageStatus.NEEDS_CONTEXT,
            resolved_entity=resolved,
            user_question=str(request.user_question or ""),
            normalized_question=normalized_question,
            recommended_execution_mode=IntakeExecutionMode.GENERIC_CLARIFICATION,
            clarification_prompt="What property or area are you interested in, and what do you want to know about it?",
            missing_context=["property_or_area", "question"],
            should_run_analysis=False,
        )

    if not normalized_question and (resolved.address or resolved.property_id or resolved.town):
        context_type = IntakeContextType.PROPERTY if (resolved.address or resolved.property_id) else IntakeContextType.AREA
        return IntakeTriageDecision(
            context_type=context_type,
            triage_status=IntakeTriageStatus.PROPERTY_ONLY if context_type == IntakeContextType.PROPERTY else IntakeTriageStatus.AREA_ONLY,
            resolved_entity=resolved,
            user_question=str(request.user_question or ""),
            normalized_question=normalized_question,
            recommended_execution_mode=(
                IntakeExecutionMode.PROPERTY_INTAKE_REQUIRED
                if context_type == IntakeContextType.PROPERTY
                else IntakeExecutionMode.AREA_CONDITIONAL_ANSWER
            ),
            clarification_prompt=(
                "What do you want Briarwood to answer about this property?"
                if context_type == IntakeContextType.PROPERTY
                else "What do you want to understand about this area?"
            ),
            missing_context=["question"],
            should_run_analysis=False,
        )

    analysis_lenses = classify_analysis_lenses(normalized_question)
    looks_area = route == "town" or any(token in normalized_question for token in _AREA_TOKENS)

    if route in {"saved_property", "new_property"}:
        if resolved.address or resolved.property_id:
            return IntakeTriageDecision(
                context_type=IntakeContextType.PROPERTY,
                triage_status=IntakeTriageStatus.READY,
                resolved_entity=resolved,
                user_question=str(request.user_question or ""),
                normalized_question=normalized_question,
                recommended_execution_mode=IntakeExecutionMode.PROPERTY_ROUTED_ANALYSIS,
                should_run_analysis=True,
                analysis_lenses=analysis_lenses,
            )
        return IntakeTriageDecision(
            context_type=IntakeContextType.PROPERTY,
            triage_status=IntakeTriageStatus.NEEDS_PROPERTY_DETAILS,
            resolved_entity=resolved,
            user_question=str(request.user_question or ""),
            normalized_question=normalized_question,
            recommended_execution_mode=IntakeExecutionMode.PROPERTY_INTAKE_REQUIRED,
            clarification_prompt="I found a property lead, but I still need enough property detail to run analysis safely.",
            missing_context=["property_details"],
            should_run_analysis=False,
            analysis_lenses=analysis_lenses,
        )

    if route == "town" or (looks_area and resolved.town):
        return IntakeTriageDecision(
            context_type=IntakeContextType.AREA,
            triage_status=IntakeTriageStatus.AREA_ONLY,
            resolved_entity=resolved,
            user_question=str(request.user_question or ""),
            normalized_question=normalized_question,
            recommended_execution_mode=IntakeExecutionMode.AREA_CONDITIONAL_ANSWER,
            should_run_analysis=False,
            analysis_lenses=analysis_lenses,
        )

    if not address_or_area and not listing_url and prior is not None and prior.resolved_entity.property_id:
        return IntakeTriageDecision(
            context_type=IntakeContextType.PROPERTY,
            triage_status=IntakeTriageStatus.READY,
            resolved_entity=prior.resolved_entity,
            user_question=str(request.user_question or ""),
            normalized_question=normalized_question,
            recommended_execution_mode=IntakeExecutionMode.PROPERTY_ROUTED_ANALYSIS,
            should_run_analysis=True,
            analysis_lenses=analysis_lenses,
        )

    if looks_area and not resolved.town:
        return IntakeTriageDecision(
            context_type=IntakeContextType.AREA,
            triage_status=IntakeTriageStatus.NEEDS_CONTEXT,
            resolved_entity=resolved,
            user_question=str(request.user_question or ""),
            normalized_question=normalized_question,
            recommended_execution_mode=IntakeExecutionMode.GENERIC_CLARIFICATION,
            clarification_prompt="Is this about a specific property or about a town or market such as Avon?",
            missing_context=["area_or_property_anchor"],
            should_run_analysis=False,
            analysis_lenses=analysis_lenses,
        )

    return IntakeTriageDecision(
        context_type=IntakeContextType.GENERIC,
        triage_status=IntakeTriageStatus.NEEDS_CONTEXT,
        resolved_entity=resolved,
        user_question=str(request.user_question or ""),
        normalized_question=normalized_question,
        recommended_execution_mode=IntakeExecutionMode.GENERIC_CLARIFICATION,
        clarification_prompt="Which property or area are you asking about?",
        missing_context=["property_or_area"],
        should_run_analysis=False,
        analysis_lenses=analysis_lenses,
    )


def dispatch_triage_decision(
    decision: IntakeTriageDecision,
    prior_session: IntakeSessionState | dict[str, Any] | None = None,
) -> IntakeSessionState:
    """Build the next UI-facing intake session state from a triage decision."""

    session = (
        prior_session
        if isinstance(prior_session, IntakeSessionState)
        else IntakeSessionState.model_validate(prior_session)
        if isinstance(prior_session, dict) and prior_session
        else IntakeSessionState()
    )

    messages = list(session.messages)
    if decision.user_question.strip():
        messages.append(
            IntakeMessage(
                role="user",
                content=decision.user_question.strip(),
                kind="question",
                metadata={"context_type": decision.context_type.value},
            )
        )

    assistant_text = _assistant_message_for_decision(decision)
    if assistant_text:
        messages.append(
            IntakeMessage(
                role="assistant",
                content=assistant_text,
                kind="triage",
                metadata={
                    "triage_status": decision.triage_status.value,
                    "execution_mode": decision.recommended_execution_mode.value,
                },
            )
        )

    clarification_history = list(session.clarification_history)
    if decision.clarification_prompt:
        clarification_history.append(decision.clarification_prompt)

    return IntakeSessionState(
        session_id=session.session_id,
        current_question=decision.user_question,
        resolved_entity=decision.resolved_entity,
        clarification_history=clarification_history,
        latest_triage_decision=decision.model_dump(mode="json"),
        routed_result_metadata=dict(session.routed_result_metadata),
        latest_execution_mode=decision.recommended_execution_mode.value,
        was_conditional_answer=decision.recommended_execution_mode != IntakeExecutionMode.PROPERTY_ROUTED_ANALYSIS,
        context_type=decision.context_type,
        analysis_lenses=decision.analysis_lenses,
        messages=messages,
        conversation_history=list(session.conversation_history),
    )


def attach_result_to_session(
    session: IntakeSessionState | dict[str, Any] | None,
    *,
    routed_result: dict[str, Any] | None = None,
    intelligence_session: dict[str, Any] | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
    execution_mode: str | None = None,
) -> IntakeSessionState:
    """Attach analysis output back onto the intake session for rendering."""

    base = (
        session
        if isinstance(session, IntakeSessionState)
        else IntakeSessionState.model_validate(session)
        if isinstance(session, dict) and session
        else IntakeSessionState()
    )
    messages = list(base.messages)
    result_meta: dict[str, Any] = {}
    was_conditional = base.was_conditional_answer

    if routed_result:
        unified = dict(routed_result.get("unified_output") or {})
        recommendation = str(unified.get("recommendation") or "")
        best_path = str(unified.get("best_path") or "")
        summary = recommendation if recommendation == best_path or not best_path else f"{recommendation} {best_path}"
        messages.append(
            IntakeMessage(
                role="assistant",
                content=summary.strip(),
                kind="analysis_result",
                metadata={
                    "decision": unified.get("decision"),
                    "confidence": unified.get("confidence"),
                    "analysis_depth_used": unified.get("analysis_depth_used"),
                },
            )
        )
        result_meta = {
            "unified_output": unified,
            "routing_decision": dict(routed_result.get("routing_decision") or {}),
            "property_summary": dict(routed_result.get("property_summary") or {}),
        }
        was_conditional = False
    elif intelligence_session:
        messages.append(
            IntakeMessage(
                role="assistant",
                content=str(intelligence_session.get("recommendation") or ""),
                kind="conditional_result",
                metadata={
                    "decision": intelligence_session.get("decision"),
                    "confidence": intelligence_session.get("confidence"),
                },
            )
        )
        result_meta = {"intelligence_session": intelligence_session}
        was_conditional = bool(intelligence_session.get("was_conditional_answer"))

    return IntakeSessionState(
        session_id=base.session_id,
        current_question=base.current_question,
        resolved_entity=base.resolved_entity,
        clarification_history=list(base.clarification_history),
        latest_triage_decision=base.latest_triage_decision,
        routed_result_metadata=result_meta,
        latest_execution_mode=execution_mode or base.latest_execution_mode,
        was_conditional_answer=was_conditional,
        context_type=base.context_type,
        analysis_lenses=list(base.analysis_lenses),
        messages=messages,
        conversation_history=list(conversation_history or base.conversation_history),
    )


def _assistant_message_for_decision(decision: IntakeTriageDecision) -> str:
    """Generate the assistant's visible triage message for the chat thread."""

    if decision.triage_status == IntakeTriageStatus.READY:
        if decision.context_type == IntakeContextType.PROPERTY and decision.resolved_entity.address:
            return f"I found the property and I’m routing the question through the right analysis path for {decision.resolved_entity.address}."
        return "I have enough context to run the right analysis."
    if decision.triage_status == IntakeTriageStatus.AREA_ONLY:
        town = decision.resolved_entity.town or "this area"
        return f"I can frame the question as an area-intelligence read for {town}, but I’ll keep it conditional until we anchor to one property."
    if decision.triage_status == IntakeTriageStatus.PROPERTY_ONLY:
        return decision.clarification_prompt or "I found the property. What do you want Briarwood to answer about it?"
    if decision.triage_status == IntakeTriageStatus.NEEDS_PROPERTY_DETAILS:
        return decision.clarification_prompt or "I need a bit more property detail before I can run the analysis."
    return decision.clarification_prompt or "I need a little more context before I can answer that well."


__all__ = [
    "AnalysisLens",
    "IntakeContextType",
    "IntakeExecutionMode",
    "IntakeMessage",
    "IntakeRequest",
    "IntakeSessionState",
    "IntakeTriageDecision",
    "IntakeTriageStatus",
    "ResolvedEntity",
    "attach_result_to_session",
    "classify_analysis_lenses",
    "dispatch_triage_decision",
    "normalize_intake_text",
    "triage_intake_request",
]
