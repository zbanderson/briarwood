"""Answer Type Router.

Every user turn is classified into exactly one AnswerType before any tool
fires. This keeps behavior predictable and bounds tool usage.

Hybrid classifier:
1. Rule-based pass (deterministic keyword/regex match)
2. Qualifier detection ("for a family", "as an investment", lifestyle fit
   language) — flags the question as semantically complex even when a rule
   fires with high confidence.
3. LLM consulted when:
   - no rule matched, OR
   - rule match is ambiguous (multiple rules fire), OR
   - qualifier phrase is present (rule might be right but worth a second look)
4. LLM can OVERRIDE the rule when the rule was ambiguous OR a qualifier is
   present; otherwise rule wins and LLM guess is advisory (llm_suggestion).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum

from briarwood.agent.llm import LLMClient


class AnswerType(str, Enum):
    LOOKUP = "lookup"
    DECISION = "decision"
    COMPARISON = "comparison"
    SEARCH = "search"
    RESEARCH = "research"
    VISUALIZE = "visualize"
    RENT_LOOKUP = "rent_lookup"
    MICRO_LOCATION = "micro_location"
    PROJECTION = "projection"
    RISK = "risk"
    EDGE = "edge"
    STRATEGY = "strategy"
    CHITCHAT = "chitchat"


@dataclass(frozen=True)
class RouterDecision:
    answer_type: AnswerType
    confidence: float
    target_refs: list[str] = field(default_factory=list)
    reason: str = ""
    llm_suggestion: AnswerType | None = None


_RULES: tuple[tuple[AnswerType, re.Pattern[str], str], ...] = (
    (
        AnswerType.COMPARISON,
        re.compile(
            r"\bcompare\b|\bwhich\b[^?]*\b(?:better|worse)\b"
            r"|(?:[a-z0-9]+(?:-[a-z0-9]+){2,})\s+(?:vs\.?|versus)\s+(?:[a-z0-9]+(?:-[a-z0-9]+){2,})",
            re.IGNORECASE,
        ),
        "compare/vs keyword",
    ),
    (
        AnswerType.SEARCH,
        re.compile(
            r"\b("
            r"find|search for|look for|"
            r"show me (properties|listings|homes|options)|"
            r"(another|other|different|similar|nearby|close ?by|better)\s+(property|properties|listing|listings|home|homes|option|options|deal|deals)|"
            r"tell me (about )?(more |other |similar )?(property|properties|listings?|homes?|options?|deals?)|"
            r"(any|are there|is there|any other).*(property|properties|listings?|homes?|options?|deals?)|"
            r"properties (that are |similar|like|nearby|close)"
            r")\b",
            re.IGNORECASE,
        ),
        "search keyword",
    ),
    (
        AnswerType.MICRO_LOCATION,
        re.compile(
            r"\b(how (close|far)|distance|blocks|miles|minutes|walk(able|ing)?|commute)\b.*\b(beach|train|downtown|ocean|station|shops?)\b"
            r"|\b(beach|train|downtown|ocean|station)\b.*\b(how (close|far)|distance|blocks|miles|walk)\b",
            re.IGNORECASE,
        ),
        "micro-location keyword",
    ),
    (
        AnswerType.VISUALIZE,
        re.compile(r"\b(chart|plot|visuali[sz]e|graph|gauge|show (me )?(the )?(value picture|verdict|gauge))\b", re.IGNORECASE),
        "visualize keyword",
    ),
    (
        AnswerType.PROJECTION,
        re.compile(
            r"\b(project(ion)?|forecast|forward[- ]looking|bull[/ -]?b(ear|ase)|bear case|base case|bull case|"
            r"(what|how) (does|will|would) (this|it) (become|look|be worth|trade|sell) (in|over|after|at|for)|"
            r"(what|how) would (this|it) trade at|"
            r"what does (this|it) trade at|"
            r"(\d+)[- ]?year (outlook|projection|forecast|picture)|"
            r"break[- ]?even|rent ramp|stabiliz(e|ed|ation)|over time|scenarios?)\b",
            re.IGNORECASE,
        ),
        "projection keyword",
    ),
    (
        AnswerType.RENT_LOOKUP,
        re.compile(r"\b(rent|rental|lease|how much (could|can|would) (i|it|this) (rent|lease))\b", re.IGNORECASE),
        "rent keyword",
    ),
    (
        AnswerType.RISK,
        re.compile(
            r"\b(what could go wrong|worst[- ]?case|downside|risks?|red flags?|what am i missing|blow ?up|break)\b",
            re.IGNORECASE,
        ),
        "risk keyword",
    ),
    (
        AnswerType.EDGE,
        re.compile(
            r"\b(where'?s? the value|where is the value|what'?s? the edge|what is the edge|"
            r"why is this a deal|why does this deal exist|what'?s? the angle|what'?s? the catch|"
            r"value thesis|mispriced?|underpriced?)\b",
            re.IGNORECASE,
        ),
        "edge keyword",
    ),
    (
        AnswerType.STRATEGY,
        re.compile(
            r"\b(best way to play|best play|what strategy|which strategy|"
            r"flip (vs|or) rent|rent (vs|or) hold|flip or hold|primary (vs|or) rental|"
            r"how should i play|what'?s? the play)\b",
            re.IGNORECASE,
        ),
        "strategy keyword",
    ),
    (
        AnswerType.DECISION,
        re.compile(r"\b(should i (buy|pass|offer)|is this a (buy|deal|good|bad)|worth( buying| it)?|underwrite|go/no-?go)\b", re.IGNORECASE),
        "decision keyword",
    ),
    (
        AnswerType.RESEARCH,
        re.compile(r"\b(what'?s happening in|research|town news|permits|zoning|developments?)\b", re.IGNORECASE),
        "research keyword",
    ),
    (
        AnswerType.LOOKUP,
        re.compile(r"\b(what'?s the|what is the|how many|address|price|beds?|baths?|sqft|square feet|year built|list(ed)? price)\b", re.IGNORECASE),
        "lookup keyword",
    ),
    (
        AnswerType.CHITCHAT,
        re.compile(r"^\s*(hi|hello|hey|thanks|thank you|ok|okay|cool)\b", re.IGNORECASE),
        "greeting",
    ),
)


_PROPERTY_ID_RE = re.compile(r"\b([a-z0-9]+(?:-[a-z0-9]+){2,})\b", re.IGNORECASE)


_PRIORITY = [
    AnswerType.COMPARISON,
    AnswerType.VISUALIZE,
    AnswerType.RISK,
    AnswerType.EDGE,
    AnswerType.STRATEGY,
    AnswerType.DECISION,
    AnswerType.PROJECTION,
    AnswerType.RENT_LOOKUP,
    AnswerType.MICRO_LOCATION,
    AnswerType.SEARCH,
    AnswerType.RESEARCH,
    AnswerType.LOOKUP,
    AnswerType.CHITCHAT,
]


def _rule_classify(text: str) -> tuple[AnswerType, float, str, int] | None:
    """Return (answer_type, confidence, reason, match_count). None if no match."""
    matches: list[tuple[AnswerType, str]] = []
    for answer_type, pattern, reason in _RULES:
        if pattern.search(text):
            matches.append((answer_type, reason))
    if not matches:
        return None
    for candidate in _PRIORITY:
        for answer_type, reason in matches:
            if answer_type is candidate:
                confidence = 0.9 if len(matches) == 1 else 0.65
                return answer_type, confidence, reason, len(matches)
    return None  # pragma: no cover


# Phrases that signal the question has layered intent beyond surface keywords.
# When any of these fire, we force an LLM consult even if a rule matched cleanly.
_QUALIFIER_RE = re.compile(
    r"\b(for (a |my |our |the )?(family|investor|investment|rental|retiree|couple|flipper|kid|kids)"
    r"|as (a |an )?(investment|rental|flip|primary|second home|airbnb|str|ltr)"
    r"|if (i|we|you) (plan|want|were|are going|can|could|can't)"
    r"|make sense (for|as|to)"
    r"|best (way|strategy|play)"
    r"|worst case|downside|what could go wrong"
    r"|how (should|would) i|what'?s the (edge|play|angle|catch))\b",
    re.IGNORECASE,
)


def _has_qualifier(text: str) -> bool:
    return bool(_QUALIFIER_RE.search(text))


def _extract_refs(text: str) -> list[str]:
    return [m.group(1).lower() for m in _PROPERTY_ID_RE.finditer(text)]


_LLM_SYSTEM = (
    "You are a triage classifier for a real-estate decision assistant. "
    "Classify the user turn into EXACTLY ONE answer_type. "
    "Respond with strict JSON: {\"answer_type\": <one>, \"reason\": <short>}. "
    "Types: "
    "lookup = factual retrieval about a known property (address, beds, price, year built). "
    "decision = should-I-buy / underwrite / go-no-go / 'is this a good deal' for a specific property. "
    "comparison = compare two or more specific properties. "
    "search = find other properties matching criteria (beds/price/distance/similar). "
    "research = town-level news, zoning, permits, development context. "
    "visualize = user asks for a chart, plot, gauge, or says 'show me the X picture'. "
    "rent_lookup = how much could it rent, rental income, rental profile, NOI. "
    "micro_location = how close/far to beach/train/downtown, walkability, commute distance. "
    "projection = forward-looking: 5-year outlook, bull/base/bear cases, break-even, rent ramp, "
    "what this becomes over time, scenarios. "
    "risk = 'what could go wrong', 'downside', 'worst case', 'risks', 'red flags', 'what am i missing'. "
    "edge = 'where's the value', 'what's the edge', 'why is this a deal', 'value thesis', 'angle', 'catch'. "
    "strategy = 'best way to play', 'flip vs rent vs hold', 'primary or rental', 'what strategy'. "
    "chitchat = ONLY greetings, thanks, small-talk like 'hi' or 'ok'. "
    "Never classify a substantive real-estate question as chitchat. "
    "Tie-break rule: if the question is layered ('for a family', 'as an investment', "
    "'best way to play'), pick the intent that ANSWERS the user's underlying need, not the "
    "surface keyword. "
    "IMPORTANT MAPPINGS: "
    "'what could go wrong' / 'downside' / 'worst case' / 'risks' -> risk. "
    "'where is the value' / 'what is the edge' / 'why does this deal exist' -> edge. "
    "'best way to play' / 'what strategy' / 'flip vs rent vs hold' -> strategy. "
    "'does X make sense for a family/investor/...' -> decision. "
    "Example: 'does 526 make sense for a family that wants to walk to ocean?' is DECISION, "
    "not MICRO_LOCATION."
)


_CHITCHAT_ONLY_RE = re.compile(r"^\s*(hi|hello|hey|yo|sup|thanks|thank you|ok|okay|cool|nice)\b[\s\.!?]*$", re.IGNORECASE)


def _llm_classify(text: str, client: LLMClient) -> AnswerType | None:
    try:
        raw = client.complete(system=_LLM_SYSTEM, user=text, max_tokens=80)
    except Exception:
        return None
    try:
        payload = json.loads(raw.strip())
        guess = AnswerType(payload["answer_type"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
    # Sanity guard: LLMs sometimes return CHITCHAT for real questions it doesn't
    # have a better bucket for. Force DECISION unless the text really is a greeting.
    if guess is AnswerType.CHITCHAT and not _CHITCHAT_ONLY_RE.match(text):
        return AnswerType.DECISION
    return guess


def classify(text: str, *, client: LLMClient | None = None) -> RouterDecision:
    """Classify a user turn into an AnswerType.

    Policy:
    - Rule alone: strong single match (confidence 0.9) and no qualifier -> rule wins outright.
    - Rule + ambiguity: multi-match OR qualifier present -> consult LLM; LLM overrides when it
      disagrees (signals layered intent the rule missed).
    - No rule: LLM decides; defaults to LOOKUP if LLM unavailable.
    """
    text = text.strip()
    if not text:
        return RouterDecision(AnswerType.CHITCHAT, confidence=1.0, reason="empty input")

    refs = _extract_refs(text)
    rule = _rule_classify(text)
    qualifier = _has_qualifier(text)

    # What-if price overrides ("if i bought at 1.3M") are inherently decisions.
    # Bias toward DECISION when no rule fires or only a weak factual rule matches.
    try:
        from briarwood.agent.overrides import parse_overrides

        has_override = bool(parse_overrides(text))
    except Exception:
        has_override = False
    if has_override:
        weak_rule = rule is None or rule[0] in (AnswerType.LOOKUP, AnswerType.CHITCHAT)
        if weak_rule:
            return RouterDecision(
                answer_type=AnswerType.DECISION,
                confidence=0.7,
                target_refs=refs,
                reason="what-if price override",
            )
    llm_guess: AnswerType | None = None

    if rule is not None:
        rule_type, rule_confidence, rule_reason, match_count = rule
        ambiguous = match_count > 1 or qualifier
        if client is not None and (ambiguous or rule_confidence < 0.8):
            llm_guess = _llm_classify(text, client)
        # Override rule when LLM disagrees on an ambiguous question.
        if llm_guess is not None and llm_guess is not rule_type and ambiguous:
            return RouterDecision(
                answer_type=llm_guess,
                confidence=0.75,
                target_refs=refs,
                reason=f"llm override ({rule_reason} -> {llm_guess.value}; qualifier={qualifier})",
                llm_suggestion=llm_guess,
            )
        return RouterDecision(
            answer_type=rule_type,
            confidence=rule_confidence,
            target_refs=refs,
            reason=rule_reason + (" + qualifier" if qualifier else ""),
            llm_suggestion=llm_guess,
        )

    if client is not None:
        llm_guess = _llm_classify(text, client)
        if llm_guess is not None:
            return RouterDecision(
                answer_type=llm_guess,
                confidence=0.6,
                target_refs=refs,
                reason="llm fallback",
                llm_suggestion=llm_guess,
            )

    return RouterDecision(
        answer_type=AnswerType.LOOKUP,
        confidence=0.3,
        target_refs=refs,
        reason="default fallback",
    )
