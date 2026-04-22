"""IntentContract — shared intent model between chat-tier and analysis routers.

F9 context: `briarwood/agent/router.py::classify()` answers "what kind of
answer does the user want?" (chat tier, ``AnswerType``).
`briarwood/router.py::route_user_input()` answers "which modules should run?"
(analysis tier, ``CoreQuestion`` + module selection). Historically the two
systems had no shared contract — intent drift between "answer type" and
"selected modules" was a structural risk flagged in the audit (P1, F9).

This module is the alignment layer, not a merge. Both routers still own
their internals. Three pieces close the contract loop:

1. :class:`IntentContract` — a small Pydantic model either router can emit.
2. :data:`ANSWER_TYPE_TO_CORE_QUESTIONS` — canonical mapping from chat-tier
   ``AnswerType`` values to the analysis-tier ``CoreQuestion`` set they imply.
3. :func:`align_question_focus_with_contract` — when the analysis router
   receives a contract from the chat router, it threads the contract's
   questions into ``question_focus`` so the two tiers produce a matching
   ``core_questions`` set on the final ``RoutingDecision``.

Design intent: contract-level reconciliation. Either router can be
rewritten later without breaking the other; the test pins the invariant
that the chat-tier contract's questions always appear in the analysis
router's final ``core_questions`` when threaded through.

Import discipline: this module must not import from
``briarwood.agent.router`` (``AnswerType`` is keyed by string here), so the
chat router can safely depend on it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from briarwood.routing_schema import CoreQuestion


class IntentContract(BaseModel):
    """Shared intent shape emitted by both the chat-tier and analysis routers.

    ``answer_type`` is carried as a plain string (the ``AnswerType`` enum
    value) to avoid a cross-module import. ``core_questions`` is the
    analysis-tier vocabulary — the canonical translation of whatever the
    emitter's native intent read was.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    answer_type: str
    core_questions: list[CoreQuestion] = Field(default_factory=list)
    question_focus: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


ANSWER_TYPE_TO_CORE_QUESTIONS: dict[str, tuple[CoreQuestion, ...]] = {
    # Explicit buy/pass framing — the full decision triad.
    "decision": (
        CoreQuestion.SHOULD_I_BUY,
        CoreQuestion.WHAT_COULD_GO_WRONG,
        CoreQuestion.WHERE_IS_VALUE,
    ),
    # Opinion-solicit on one property; short read, not a decision cascade.
    "browse": (CoreQuestion.SHOULD_I_BUY,),
    "risk": (CoreQuestion.WHAT_COULD_GO_WRONG,),
    # "Where's the value / what's the angle" includes hidden upside by F5.
    "edge": (CoreQuestion.WHERE_IS_VALUE, CoreQuestion.HIDDEN_UPSIDE),
    "strategy": (CoreQuestion.BEST_PATH,),
    "rent_lookup": (CoreQuestion.FUTURE_INCOME,),
    "projection": (CoreQuestion.WHERE_IS_VALUE, CoreQuestion.BEST_PATH),
    "comparison": (CoreQuestion.SHOULD_I_BUY, CoreQuestion.BEST_PATH),
    # AnswerTypes that don't imply a CoreQuestion (factual retrieval, search
    # over the listing set, town-level research, pure rendering) keep an
    # empty tuple so the contract stays honest instead of inventing intent.
    "lookup": (),
    "search": (),
    "research": (),
    "visualize": (),
    "micro_location": (),
    "chitchat": (),
}


def core_questions_for_answer_type(answer_type: str) -> list[CoreQuestion]:
    """Return the ``CoreQuestion`` list implied by a chat-tier answer type."""

    return list(ANSWER_TYPE_TO_CORE_QUESTIONS.get(answer_type, ()))


def build_contract_from_answer_type(
    answer_type: str,
    confidence: float,
) -> IntentContract:
    """Build an ``IntentContract`` from a chat-tier answer type + confidence.

    The ``question_focus`` field mirrors ``core_questions`` as string values
    — that's the shape ``ParserOutput.question_focus`` uses, so downstream
    alignment can merge them without a conversion step.
    """

    questions = core_questions_for_answer_type(answer_type)
    return IntentContract(
        answer_type=answer_type,
        core_questions=questions,
        question_focus=[q.value for q in questions],
        confidence=max(0.0, min(1.0, float(confidence))),
    )


def align_question_focus_with_contract(
    question_focus: list[str],
    contract: IntentContract,
) -> list[str]:
    """Merge the contract's questions into ``question_focus`` in order.

    The contract's questions come first (the chat tier's intent read is the
    user-facing source of truth for "what answer the user wants"); any
    rules-inferred focus items the analysis router already had are appended
    after, preserving their relative order. Duplicates are removed.
    """

    merged: list[str] = []
    seen: set[str] = set()
    for question in contract.core_questions:
        value = question.value
        if value not in seen:
            merged.append(value)
            seen.add(value)
    for item in question_focus:
        if item not in seen:
            merged.append(item)
            seen.add(item)
    return merged


__all__ = [
    "ANSWER_TYPE_TO_CORE_QUESTIONS",
    "IntentContract",
    "align_question_focus_with_contract",
    "build_contract_from_answer_type",
    "core_questions_for_answer_type",
]
