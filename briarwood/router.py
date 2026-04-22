from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from pathlib import Path

from briarwood.intent_contract import (
    IntentContract,
    align_question_focus_with_contract,
)
from briarwood.routing_schema import (
    CORE_QUESTIONS,
    DEPTH_BASELINE_MODULES,
    INTENT_TO_MODULES,
    INTENT_TO_QUESTIONS,
    QUESTION_FOCUS_TO_MODULE_HINTS,
    AnalysisDepth,
    CoreQuestion,
    ExitOption,
    IntentType,
    ModuleName,
    OccupancyType,
    ParserOutput,
    RoutingDecision,
)


class RoutingError(RuntimeError):
    """Raised when Briarwood cannot safely build a routing decision."""


INTENT_KEYWORDS: dict[IntentType, list[str]] = {
    IntentType.BUY_DECISION: [
        "should i buy",
        "buy this",
        "worth buying",
        "good buy",
        "decision",
        "worth it",
    ],
    IntentType.OWNER_OCCUPANT_SHORT_HOLD: [
        "live in",
        "owner occupy",
        "owner-occupy",
        "short hold",
        "sell in",
        "move in",
        "primary residence",
    ],
    IntentType.OWNER_OCCUPANT_THEN_RENT: [
        "then rent",
        "rent later",
        "keep it as a rental",
        "hold to rent",
        "live there first",
        "owner occupant then rent",
    ],
    IntentType.RENOVATE_THEN_SELL: [
        "renovate and sell",
        "flip",
        "arv",
        "after repair value",
        "renovation",
        "value add",
        "margin",
    ],
    IntentType.HOUSE_HACK_MULTI_UNIT: [
        "house hack",
        "multi unit",
        "multi-unit",
        "duplex",
        "triplex",
        "fourplex",
        "back house",
        "adu",
        "additional unit",
        "offset the payment",
        "offset the mortgage",
    ],
}

_LEARNED_KEYWORDS_PATH = Path(__file__).resolve().parents[1] / "data" / "learning" / "learned_keywords.json"
_logger = logging.getLogger(__name__)


def _merge_learned_keywords() -> None:
    """Load learned keyword → intent mappings from disk and merge into INTENT_KEYWORDS."""
    if not _LEARNED_KEYWORDS_PATH.exists():
        return
    try:
        data = json.loads(_LEARNED_KEYWORDS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _logger.debug("Could not load learned keywords: %s", exc)
        return
    if not isinstance(data, dict):
        return
    for intent_str, keywords in data.items():
        try:
            intent = IntentType(intent_str)
        except ValueError:
            continue
        if not isinstance(keywords, list):
            continue
        existing = set(INTENT_KEYWORDS.get(intent, []))
        for kw in keywords:
            if isinstance(kw, str) and kw not in existing:
                INTENT_KEYWORDS[intent].append(kw)
                existing.add(kw)


_merge_learned_keywords()


DEPTH_KEYWORDS: dict[AnalysisDepth, list[str]] = {
    AnalysisDepth.SNAPSHOT: [
        "quick",
        "snapshot",
        "high level",
        "headline",
        "at a glance",
        "should i buy",
    ],
    AnalysisDepth.DECISION: [
        "should i buy",
        "decision",
        "worth it",
        "recommendation",
        "go or no go",
        "buy or pass",
    ],
    AnalysisDepth.SCENARIO: [
        "scenario",
        "what if",
        "if we",
        "if i",
        "forward rent",
        "best path",
        "after 3 years",
        "after three years",
        "hold period",
    ],
    AnalysisDepth.DEEP_DIVE: [
        "deep dive",
        "full analysis",
        "underwrite",
        "underwriting",
        "detailed",
        "comprehensive",
        "dig deep",
        "stress test",
    ],
}

QUESTION_KEYWORDS: dict[CoreQuestion, list[str]] = {
    CoreQuestion.SHOULD_I_BUY: [
        "should i buy",
        "buy this",
        "worth buying",
        "buy or pass",
        "good deal",
    ],
    CoreQuestion.WHAT_COULD_GO_WRONG: [
        "risk",
        "go wrong",
        "downside",
        "watch out",
        "what could go wrong",
        "worst case",
    ],
    CoreQuestion.WHERE_IS_VALUE: [
        "where is value",
        "upside",
        "margin",
        "mispriced",
        "value add",
        "renovate",
        "renovation",
        "renovation impact",
    ],
    CoreQuestion.BEST_PATH: [
        "best path",
        "best option",
        "best move",
        "should we do",
        "sell or rent",
        "path forward",
    ],
    CoreQuestion.FUTURE_INCOME: [
        "rent",
        "income",
        "cash flow",
        "future income",
        "forward rent",
        "rental",
    ],
}

OCCUPANCY_KEYWORDS: dict[OccupancyType, list[str]] = {
    OccupancyType.OWNER_OCCUPANT: [
        "live in",
        "move in",
        "owner occupy",
        "owner-occupy",
        "primary residence",
        "we buy this to live",
    ],
    OccupancyType.INVESTOR: [
        "investment",
        "investor",
        "rental",
        "cash flow",
        "tenant",
        "hold as a rental",
    ],
}

EXIT_KEYWORDS: dict[ExitOption, list[str]] = {
    ExitOption.SELL: ["sell", "resale", "flip", "exit sale"],
    ExitOption.RENT: ["rent", "rental", "lease", "tenant"],
    ExitOption.HOLD: ["hold", "keep", "long term", "long-term"],
    ExitOption.REDEVELOP: ["redevelop", "expand", "add units", "rebuild", "subdivide"],
}

MISSING_INPUT_HINTS: dict[str, list[str]] = {
    "purchase_price": ["price", "ask", "purchase price", "buy for", "listed at"],
    "rent_estimate": ["rent", "rental", "lease", "income", "cash flow"],
    "hold_period_years": ["year", "years", "month", "months", "hold"],
    "renovation_scope": ["renovate", "renovation", "rehab", "repair", "update"],
    "occupancy_plan": ["live in", "owner occupy", "owner-occupy", "rent", "tenant", "investor"],
}


def normalize_text(text: str) -> str:
    """Normalize free-form user text into a lowercase routing-friendly string."""

    if not isinstance(text, str):
        raise RoutingError("User input must be a string.")
    normalized = " ".join(text.strip().lower().split())
    if not normalized:
        raise RoutingError("User input is empty after normalization.")
    return normalized


def keyword_match_score(text: str, keywords: list[str]) -> int:
    """Return a simple additive score for keyword matches in normalized text."""

    normalized = normalize_text(text)
    score = 0
    for keyword in keywords:
        token = normalize_text(keyword)
        if token in normalized:
            score += max(1, len(token.split()))
    return score


def infer_analysis_depth_rules(text: str) -> AnalysisDepth:
    """Infer analysis depth from the explicit depth implied by the question."""

    normalized = normalize_text(text)
    scores = {
        depth: keyword_match_score(normalized, keywords)
        for depth, keywords in DEPTH_KEYWORDS.items()
    }

    if re.search(r"\b(what if|scenario|forward|after \d+ (?:year|years|month|months))\b", normalized):
        scores[AnalysisDepth.SCENARIO] += 3
    if re.search(r"\b(deep dive|full analysis|underwrite|stress test|detailed)\b", normalized):
        scores[AnalysisDepth.DEEP_DIVE] += 4

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_depth, best_score = ranked[0]
    if best_score <= 0:
        return AnalysisDepth.SNAPSHOT
    if best_depth == AnalysisDepth.DECISION and "should i buy" in normalized and len(normalized.split()) <= 6:
        return AnalysisDepth.SNAPSHOT
    return best_depth


def infer_question_focus_rules(text: str) -> list[str]:
    """Infer the emphasized question areas from free-form user language."""

    normalized = normalize_text(text)
    scored_questions: list[tuple[CoreQuestion, int]] = []
    for question, keywords in QUESTION_KEYWORDS.items():
        score = keyword_match_score(normalized, keywords)
        if score > 0:
            scored_questions.append((question, score))

    scored_questions.sort(key=lambda item: item[1], reverse=True)
    if not scored_questions:
        return [CoreQuestion.SHOULD_I_BUY.value]

    return [question.value for question, _score in scored_questions[:3]]


def infer_occupancy_type_rules(text: str) -> OccupancyType:
    """Infer whether the user sounds like an owner-occupant or investor."""

    normalized = normalize_text(text)
    owner_score = keyword_match_score(normalized, OCCUPANCY_KEYWORDS[OccupancyType.OWNER_OCCUPANT])
    investor_score = keyword_match_score(normalized, OCCUPANCY_KEYWORDS[OccupancyType.INVESTOR])

    if owner_score > investor_score and owner_score > 0:
        return OccupancyType.OWNER_OCCUPANT
    if investor_score > owner_score and investor_score > 0:
        return OccupancyType.INVESTOR
    return OccupancyType.UNKNOWN


def infer_exit_options_rules(text: str) -> list[ExitOption]:
    """Infer candidate exit options directly from the user's wording."""

    normalized = normalize_text(text)
    options: list[ExitOption] = []
    for exit_option, keywords in EXIT_KEYWORDS.items():
        if keyword_match_score(normalized, keywords) > 0:
            options.append(exit_option)

    if not options:
        return [ExitOption.UNKNOWN]
    return options


def infer_hold_period_years(text: str) -> float | None:
    """Extract an explicit hold period in years when the user states one."""

    normalized = normalize_text(text)

    years_match = re.search(r"\b(?:after|in|for|within)?\s*(\d+(?:\.\d+)?)\s+years?\b", normalized)
    if years_match:
        return float(years_match.group(1))

    months_match = re.search(r"\b(?:after|in|for|within)?\s*(\d+(?:\.\d+)?)\s+months?\b", normalized)
    if months_match:
        return round(float(months_match.group(1)) / 12.0, 2)

    word_year_match = re.search(r"\bafter three years\b", normalized)
    if word_year_match:
        return 3.0

    return None


def infer_missing_inputs(
    *,
    intent_type: IntentType,
    occupancy_type: OccupancyType,
    exit_options: list[ExitOption],
    hold_period_years: float | None,
    question_focus: list[str],
    text: str,
) -> list[str]:
    """Infer which important routing inputs are still unspecified by the user."""

    normalized = normalize_text(text)
    missing: list[str] = []

    if keyword_match_score(normalized, MISSING_INPUT_HINTS["purchase_price"]) == 0:
        missing.append("purchase_price")

    future_income_focus = CoreQuestion.FUTURE_INCOME.value in question_focus or ExitOption.RENT in exit_options
    if future_income_focus and keyword_match_score(normalized, MISSING_INPUT_HINTS["rent_estimate"]) == 0:
        missing.append("rent_estimate")

    if hold_period_years is None and intent_type in {
        IntentType.OWNER_OCCUPANT_SHORT_HOLD,
        IntentType.OWNER_OCCUPANT_THEN_RENT,
        IntentType.RENOVATE_THEN_SELL,
    }:
        missing.append("hold_period_years")

    if intent_type == IntentType.RENOVATE_THEN_SELL and keyword_match_score(
        normalized,
        MISSING_INPUT_HINTS["renovation_scope"],
    ) == 0:
        missing.append("renovation_scope")

    if occupancy_type == OccupancyType.UNKNOWN and intent_type in {
        IntentType.OWNER_OCCUPANT_SHORT_HOLD,
        IntentType.OWNER_OCCUPANT_THEN_RENT,
        IntentType.HOUSE_HACK_MULTI_UNIT,
    }:
        missing.append("occupancy_plan")

    seen: set[str] = set()
    deduped: list[str] = []
    for item in missing:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def infer_intent_rules(user_input: str) -> ParserOutput:
    """Infer Briarwood routing intent with a deterministic rules-first parser."""

    normalized = normalize_text(user_input)
    analysis_depth = infer_analysis_depth_rules(normalized)
    question_focus = infer_question_focus_rules(normalized)
    occupancy_type = infer_occupancy_type_rules(normalized)
    exit_options = infer_exit_options_rules(normalized)
    hold_period_years = infer_hold_period_years(normalized)

    scores = {
        intent: keyword_match_score(normalized, keywords)
        for intent, keywords in INTENT_KEYWORDS.items()
    }

    if occupancy_type == OccupancyType.OWNER_OCCUPANT:
        scores[IntentType.OWNER_OCCUPANT_SHORT_HOLD] += 1
        scores[IntentType.OWNER_OCCUPANT_THEN_RENT] += 1
    if occupancy_type == OccupancyType.INVESTOR:
        scores[IntentType.BUY_DECISION] += 1
    if ExitOption.RENT in exit_options:
        scores[IntentType.OWNER_OCCUPANT_THEN_RENT] += 2
        scores[IntentType.HOUSE_HACK_MULTI_UNIT] += 1
    if ExitOption.SELL in exit_options:
        scores[IntentType.RENOVATE_THEN_SELL] += 2
        scores[IntentType.OWNER_OCCUPANT_SHORT_HOLD] += 1
    if hold_period_years is not None:
        scores[IntentType.OWNER_OCCUPANT_SHORT_HOLD] += 1
        scores[IntentType.OWNER_OCCUPANT_THEN_RENT] += 1
    if CoreQuestion.FUTURE_INCOME.value in question_focus:
        scores[IntentType.OWNER_OCCUPANT_THEN_RENT] += 1
        scores[IntentType.HOUSE_HACK_MULTI_UNIT] += 1
    if CoreQuestion.WHERE_IS_VALUE.value in question_focus:
        scores[IntentType.RENOVATE_THEN_SELL] += 1

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_intent, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    total_score = sum(scores.values())

    if best_score <= 0:
        best_intent = IntentType.BUY_DECISION
        confidence = 0.55
    else:
        margin = max(best_score - second_score, 0)
        confidence = min(0.95, 0.45 + (best_score / max(total_score, 1)) * 0.3 + margin * 0.08)

    renovation_plan = best_intent == IntentType.RENOVATE_THEN_SELL or "renovat" in normalized or "rehab" in normalized
    has_additional_units = bool(
        re.search(r"\b(adu|back house|additional unit|multi[- ]unit|duplex|triplex|fourplex)\b", normalized)
    )

    missing_inputs = infer_missing_inputs(
        intent_type=best_intent,
        occupancy_type=occupancy_type,
        exit_options=exit_options,
        hold_period_years=hold_period_years,
        question_focus=question_focus,
        text=normalized,
    )

    return ParserOutput(
        intent_type=best_intent,
        analysis_depth=analysis_depth,
        question_focus=question_focus,
        hold_period_years=hold_period_years,
        occupancy_type=occupancy_type,
        renovation_plan=renovation_plan or None,
        exit_options=exit_options,
        has_additional_units=has_additional_units or None,
        confidence=round(confidence, 2),
        missing_inputs=missing_inputs,
    )


def parse_intent_and_depth(
    user_input: str,
    llm_parser: Callable[[str], ParserOutput] | None = None,
    confidence_threshold: float = 0.70,
) -> ParserOutput:
    """Run rules-first parsing and optionally fall back to an injected LLM parser."""

    if not 0.0 <= confidence_threshold <= 1.0:
        raise RoutingError("confidence_threshold must be between 0 and 1.")

    rules_result = infer_intent_rules(user_input)
    if rules_result.confidence >= confidence_threshold:
        return rules_result

    if llm_parser is None:
        return rules_result

    try:
        llm_result = llm_parser(user_input)
    except Exception as exc:
        raise RoutingError(f"LLM parser failed: {exc}") from exc

    if not isinstance(llm_result, ParserOutput):
        raise RoutingError("LLM parser must return a ParserOutput instance.")
    return llm_result


def filter_modules_by_depth_and_focus(
    intent_type: IntentType,
    analysis_depth: AnalysisDepth,
    question_focus: list[str],
) -> list[ModuleName]:
    """Select modules from intent, depth, and question focus without running analysis."""

    try:
        intent_modules = list(INTENT_TO_MODULES[intent_type])
        depth_modules = set(DEPTH_BASELINE_MODULES[analysis_depth])
    except KeyError as exc:
        raise RoutingError(f"Unsupported routing configuration: {exc}") from exc

    selected = [module for module in intent_modules if module in depth_modules]
    intent_universe = set(intent_modules)

    for focus_item in question_focus:
        try:
            core_question = CoreQuestion(focus_item)
        except ValueError:
            continue
        for hinted_module in QUESTION_FOCUS_TO_MODULE_HINTS.get(core_question, ()):
            if hinted_module in intent_universe and hinted_module not in selected:
                selected.append(hinted_module)

    if ModuleName.CONFIDENCE in intent_universe and ModuleName.CONFIDENCE not in selected:
        selected.append(ModuleName.CONFIDENCE)

    return selected


def build_routing_decision(parser_output: ParserOutput) -> RoutingDecision:
    """Build the final routing decision from parsed conversational intent."""

    if not isinstance(parser_output, ParserOutput):
        raise RoutingError("parser_output must be a ParserOutput instance.")

    default_questions = INTENT_TO_QUESTIONS.get(parser_output.intent_type, ())
    selected_questions: list[CoreQuestion] = []

    for focus_item in parser_output.question_focus:
        try:
            question = CoreQuestion(focus_item)
        except ValueError:
            continue
        if question not in selected_questions:
            selected_questions.append(question)

    if not selected_questions:
        selected_questions = list(default_questions)
    else:
        for question in default_questions:
            if question not in selected_questions:
                selected_questions.append(question)

    selected_modules = filter_modules_by_depth_and_focus(
        intent_type=parser_output.intent_type,
        analysis_depth=parser_output.analysis_depth,
        question_focus=[question.value for question in selected_questions],
    )

    return RoutingDecision(
        intent_type=parser_output.intent_type,
        analysis_depth=parser_output.analysis_depth,
        core_questions=selected_questions,
        selected_modules=selected_modules,
        parser_output=parser_output,
    )


def route_user_input(
    user_input: str,
    llm_parser: Callable[[str], ParserOutput] | None = None,
    confidence_threshold: float = 0.70,
    prior_context: list[dict[str, object]] | None = None,
    intent_contract: IntentContract | None = None,
) -> RoutingDecision:
    """Route one user question into parsed intent, depth, and selected modules.

    When *prior_context* is supplied (a list of ``{"question", "decision",
    "analysis_depth", "intent_type"}`` dicts from earlier turns), the router
    uses it to upgrade depth and refine focus.  For example, after a SNAPSHOT
    BUY_DECISION the user asks "tell me more about the risk" — the router
    promotes depth to DECISION and adds WHAT_COULD_GO_WRONG focus.

    When *intent_contract* is supplied (produced by the chat-tier router in
    ``briarwood.agent.router.classify``), the contract's ``core_questions``
    are merged into the parsed ``question_focus`` before the routing
    decision is built. This is the F9 alignment layer — it ensures the
    analysis tier's ``RoutingDecision.core_questions`` covers every question
    the chat tier declared the user wanted answered.
    """

    parser_output = parse_intent_and_depth(
        user_input=user_input,
        llm_parser=llm_parser,
        confidence_threshold=confidence_threshold,
    )
    if prior_context:
        parser_output = _apply_prior_context(parser_output, prior_context)
    if intent_contract is not None:
        parser_output = _align_parser_with_intent_contract(parser_output, intent_contract)
    return build_routing_decision(parser_output)


def _align_parser_with_intent_contract(
    parser_output: ParserOutput,
    contract: IntentContract,
) -> ParserOutput:
    """F9: thread the chat-tier contract's questions into parser_output.

    Replaces ``question_focus`` with the contract's core questions followed
    by any rules-inferred focus items the analysis tier already had. The
    rest of ``parser_output`` is untouched — the analysis router still owns
    intent, depth, occupancy, exit options, and missing-inputs.
    """

    aligned_focus = align_question_focus_with_contract(
        list(parser_output.question_focus), contract,
    )
    if aligned_focus == list(parser_output.question_focus):
        return parser_output
    return parser_output.model_copy(update={"question_focus": aligned_focus})


def _apply_prior_context(
    parser_output: ParserOutput,
    prior_context: list[dict[str, object]],
) -> ParserOutput:
    """Upgrade routing based on conversation history.

    Rules:
    - If the prior run was at a shallower depth, promote to at least the next level.
    - If the prior intent is the same, inherit prior focus areas to avoid regressing.
    - Boost confidence when the follow-up is a natural continuation.
    """

    if not prior_context:
        return parser_output

    last = prior_context[-1]
    prior_depth_str = str(last.get("analysis_depth") or "").lower()
    prior_intent_str = str(last.get("intent_type") or "").lower()

    _DEPTH_RANK = {"snapshot": 0, "decision": 1, "scenario": 2, "deep_dive": 3}
    prior_rank = _DEPTH_RANK.get(prior_depth_str, -1)
    current_rank = _DEPTH_RANK.get(parser_output.analysis_depth.value, 0)

    new_depth = parser_output.analysis_depth
    if prior_rank >= 0 and current_rank <= prior_rank:
        next_rank = min(prior_rank + 1, 3)
        for depth_key, rank in _DEPTH_RANK.items():
            if rank == next_rank:
                new_depth = AnalysisDepth(depth_key)
                break

    new_confidence = parser_output.confidence
    if prior_intent_str == parser_output.intent_type.value:
        new_confidence = min(0.95, parser_output.confidence + 0.08)

    return ParserOutput(
        intent_type=parser_output.intent_type,
        analysis_depth=new_depth,
        question_focus=parser_output.question_focus,
        hold_period_years=parser_output.hold_period_years,
        occupancy_type=parser_output.occupancy_type,
        renovation_plan=parser_output.renovation_plan,
        exit_options=parser_output.exit_options,
        has_additional_units=parser_output.has_additional_units,
        confidence=round(new_confidence, 2),
        missing_inputs=parser_output.missing_inputs,
    )


__all__ = [
    "RoutingError",
    "build_routing_decision",
    "filter_modules_by_depth_and_focus",
    "infer_analysis_depth_rules",
    "infer_exit_options_rules",
    "infer_hold_period_years",
    "infer_intent_rules",
    "infer_missing_inputs",
    "infer_occupancy_type_rules",
    "infer_question_focus_rules",
    "keyword_match_score",
    "normalize_text",
    "parse_intent_and_depth",
    "route_user_input",
]
