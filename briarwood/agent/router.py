"""Answer Type Router.

Every user turn is classified into exactly one AnswerType before any tool
fires. This keeps behavior predictable and bounds tool usage.

Design: LLM-first with a tiny regex cache.

- 4 high-precision cache rules catch the ~50% of traffic that's unambiguous:
  greetings, explicit comparisons, explicit buy/pass phrasing, explicit search
  imperatives. Cache hits are sub-ms and don't consult the LLM.
- Everything else is classified by the LLM — the single source of truth for
  semantic routing. Drifting language and new intents are handled by updating
  the prompt, not by growing a regex list.
- The untracked log (`data/agent_feedback/untracked.jsonl`) captures low-
  confidence / fallback turns so patterns that appear in volume can be
  promoted to cache rules deliberately.

Rationale: maintaining a second-source-of-truth regex ontology alongside the
LLM prompt caused drift — every new intent required updating both, and the
rules couldn't express semantic nuance (browse vs. decision on identical
surface tokens). Cache rules are restricted to cases where regex is genuinely
decisive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, ConfigDict

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
    BROWSE = "browse"
    CHITCHAT = "chitchat"


@dataclass(frozen=True)
class RouterDecision:
    answer_type: AnswerType
    confidence: float
    target_refs: list[str] = field(default_factory=list)
    reason: str = ""
    llm_suggestion: AnswerType | None = None  # set when LLM participated


# ─── Cache rules ──────────────────────────────────────────────────────────────
# Only patterns where regex is decisive. Scanned in order; first match wins.
# Anything semantically subtle is the LLM's job, not the cache's.

_CACHE_RULES: tuple[tuple[AnswerType, re.Pattern[str], str], ...] = (
    # Stand-alone greeting/thanks — must be the whole message.
    (
        AnswerType.CHITCHAT,
        re.compile(
            r"^\s*(hi|hello|hey|yo|sup|thanks|thank you|ok|okay|cool|nice)\b[\s\.!?]*$",
            re.IGNORECASE,
        ),
        "greeting",
    ),
    # Explicit multi-property comparison.
    (
        AnswerType.COMPARISON,
        re.compile(
            r"\bcompare\b|"
            r"(?:[a-z0-9]+(?:-[a-z0-9]+){2,})\s+(?:vs\.?|versus)\s+(?:[a-z0-9]+(?:-[a-z0-9]+){2,})|"
            r"\bwhich (?:one )?is (?:better|worse)\b",
            re.IGNORECASE,
        ),
        "compare/vs keyword",
    ),
    # Explicit decisive verbs — buy/pass/underwrite call, not opinion-solicit.
    (
        AnswerType.DECISION,
        re.compile(
            r"\b(should i (?:buy|pass|offer)"
            r"|underwrite"
            r"|worth (?:it|buying)"
            r"|go/no-?go"
            r"|is this a (?:buy|deal|good deal|bad deal|good|bad))\b",
            re.IGNORECASE,
        ),
        "decision verb",
    ),
    # Explicit renovation / resale / capex scenario questions.
    (
        AnswerType.PROJECTION,
        re.compile(
            r"\b("
            r"what if (?:we|i) invest(?:ed|ing)?\s+\$?\d[\d,]*(?:\.\d+)?\s*(?:k|m|mm|mil|million|thousand)?"
            r"|invest(?:ed|ing)?\s+\$?\d[\d,]*(?:\.\d+)?\s*(?:k|m|mm|mil|million|thousand)?\s+(?:into|in)\s+(?:it|this)"
            r"|if (?:we|i) renovat(?:e|ed)"
            r"|renovat(?:e|ed|ion).*(?:sell|resale|arv|after repair value)"
            r"|what could (?:we|i) sell (?:it|this) for"
            r"|turn around and sell"
            r"|\barv\b"
            r"|after repair value"
            r"|resale value"
            r"|flip (?:it|this)"
            r")\b",
            re.IGNORECASE,
        ),
        "renovation/resale scenario",
    ),
    # Explicit search imperative — "find me X", "show me listings/properties".
    (
        AnswerType.SEARCH,
        re.compile(
            r"\b(find me|search for|look for|"
            r"show me (?:properties|listings|homes|houses|options|similar|other|nearby|more)|"
            r"what(?:'s| is| are)? (?:the )?(?:homes|houses|properties|listings)\s+(?:are\s+)?(?:listed\s+)?for sale|"
            r"(?:homes|houses|properties|listings)\s+(?:are\s+)?(?:listed\s+)?for sale\s+in)\b",
            re.IGNORECASE,
        ),
        "search imperative",
    ),
    # Explicit chart/plot command — render instruction, unambiguous.
    (
        AnswerType.VISUALIZE,
        re.compile(
            r"\b(chart|plot|visuali[sz]e|graph|gauge"
            r"|show (?:me )?(?:the )?(?:value picture|verdict|gauge))\b",
            re.IGNORECASE,
        ),
        "visualize keyword",
    ),
)


_PROPERTY_ID_RE = re.compile(r"\b([a-z0-9]+(?:-[a-z0-9]+){2,})\b", re.IGNORECASE)
_ADDRESS_LIKE_RE = re.compile(
    r"\b\d+\s+[A-Za-z0-9 .'-]+?\b(?:ave|avenue|st|street|rd|road|dr|drive|ln|lane|blvd|boulevard|"
    r"pkwy|parkway|ct|court|pl|place|ter|terrace|hwy|highway|cir|circle|way)\b",
    re.IGNORECASE,
)
_EXPLICIT_BROWSE_RE = re.compile(
    r"\b(?:what do you think of|your take on|thoughts on|tell me about)\b",
    re.IGNORECASE,
)


def _cache_classify(text: str) -> tuple[AnswerType, str] | None:
    """Return (answer_type, reason) for the first matching cache rule, or None."""
    for answer_type, pattern, reason in _CACHE_RULES:
        if pattern.search(text):
            return answer_type, reason
    if _EXPLICIT_BROWSE_RE.search(text) and (
        _PROPERTY_ID_RE.search(text) or _ADDRESS_LIKE_RE.search(text)
    ):
        return AnswerType.BROWSE, "browse phrasing"
    return None


def _extract_refs(text: str) -> list[str]:
    return [m.group(1).lower() for m in _PROPERTY_ID_RE.finditer(text)]


_LLM_SYSTEM = (
    "You are a triage classifier for a real-estate decision assistant. "
    "Classify the user turn into EXACTLY ONE answer_type. "
    "Respond with strict JSON: {\"answer_type\": <one>, \"reason\": <short>}. "
    "Types: "
    "lookup = factual retrieval about a known property (address, beds, price, year built). "
    "browse = browse-style first read on ONE specific property. Opinion-solicit phrasing with "
    "no decisive verb: 'what do you think of X', 'your take on X', 'thoughts on X', 'tell me about X'. "
    "Returns an underwrite-lite purchase brief. This is the DEFAULT "
    "for any open-ended question about a single property that doesn't explicitly ask for a decision. "
    "decision = EXPLICIT buy/pass phrasing on a specific property: 'should I buy', 'is this a good deal', "
    "'underwrite this', 'worth it at $X', 'go/no-go'. Requires decisive verb, not just opinion. "
    "comparison = compare two or more specific properties. "
    "search = find other properties matching criteria (beds/price/distance/similar). "
    "research = town-level news, zoning, permits, development context. "
    "visualize = user asks for a chart, plot, gauge, or says 'show me the X picture'. "
    "rent_lookup = how much could it rent, rental income, rental profile, NOI. "
    "micro_location = how close/far to beach/train/downtown, walkability, commute distance. "
    "projection = forward-looking or scenario analysis: 5-year outlook, bull/base/bear cases, break-even, rent ramp, "
    "what this becomes over time, scenarios, renovation budget questions, ARV, resale-after-renovation, "
    "'what if we invested 100k', 'if we renovated it', 'what could we sell it for'. "
    "risk = 'what could go wrong', 'downside', 'worst case', 'risks', 'red flags', 'what am i missing'. "
    "edge = 'where's the value', 'what's the edge', 'why is this a deal', 'value thesis', 'angle', 'catch'. "
    "strategy = 'best way to play', 'flip vs rent vs hold', 'primary or rental', 'what strategy'. "
    "chitchat = ONLY greetings, thanks, small-talk like 'hi' or 'ok'. "
    "Never classify a substantive real-estate question as chitchat. "
    "Tie-break rule: if the question is layered ('for a family', 'as an investment', "
    "'best way to play'), pick the intent that ANSWERS the user's underlying need, not the "
    "surface keyword. "
    "IMPORTANT MAPPINGS: "
    "'what do you think of X' / 'your take on X' / 'thoughts on X' -> browse (NOT decision). "
    "'what could go wrong' / 'downside' / 'worst case' / 'risks' -> risk. "
    "'where is the value' / 'what is the edge' / 'why does this deal exist' -> edge. "
    "'best way to play' / 'what strategy' / 'flip vs rent vs hold' -> strategy. "
    "'what if we invested 100k' / 'if we renovated it' / 'what could we sell it for' / 'ARV' -> projection. "
    "'should I buy X' / 'is X a good deal' / 'underwrite X' -> decision. "
    "'does X make sense for a family/investor/...' -> decision (has decisive framing). "
    "Example: 'what do you think of 526 W End Ave?' is BROWSE, not DECISION — the user is asking "
    "for a first read, not a buy/pass call. Decision requires explicit buy/pass/underwrite verb."
)


_CHITCHAT_ONLY_RE = re.compile(
    r"^\s*(hi|hello|hey|yo|sup|thanks|thank you|ok|okay|cool|nice)\b[\s\.!?]*$",
    re.IGNORECASE,
)

_RENT_LOOKUP_HINT_RE = re.compile(
    r"\b(how much could .* rent for|what would .* rent for|rent for|monthly rent|rental income|lease for)\b",
    re.IGNORECASE,
)

_PROJECTION_OVERRIDE_HINT_RE = re.compile(
    r"\b(arv|after repair value|sell it for|resale|turn around and sell|flip)\b",
    re.IGNORECASE,
)


class RouterClassification(BaseModel):
    """Strict JSON schema for the router's intent classification.

    AUDIT 1.2.2: replaces a `json.loads` + manual enum coercion with a
    declared Pydantic shape. OpenAI's `strict: true` JSON-schema mode
    enforces the contract at the API level; model_validate catches any
    residual drift (e.g., older model rolled back to permissive mode)."""

    model_config = ConfigDict(extra="forbid")

    answer_type: AnswerType
    reason: str = ""


def _llm_classify(text: str, client: LLMClient) -> AnswerType | None:
    try:
        result = client.complete_structured(
            system=_LLM_SYSTEM,
            user=text,
            schema=RouterClassification,
            max_tokens=80,
        )
    except Exception:
        return None
    if result is None:
        return None
    guess = result.answer_type
    # Sanity guard: LLMs sometimes return CHITCHAT for real questions they
    # don't have a better bucket for. Default to BROWSE (quick read) unless
    # the text really is a greeting — safer than DECISION (full cascade).
    if guess is AnswerType.CHITCHAT and not _CHITCHAT_ONLY_RE.match(text):
        return AnswerType.BROWSE
    return guess


def classify(text: str, *, client: LLMClient | None = None) -> RouterDecision:
    """Classify a user turn into an AnswerType.

    Policy:
    - Empty input → CHITCHAT.
    - What-if price override ("if I bought at 1.3M") → DECISION short-circuit.
    - Cache rule hit (greetings / compare / explicit buy / explicit search) →
      rule wins immediately, no LLM call.
    - Everything else → LLM classifies. LLM unavailable → LOOKUP default.
    """
    text = text.strip()
    if not text:
        return RouterDecision(AnswerType.CHITCHAT, confidence=1.0, reason="empty input")

    refs = _extract_refs(text)

    # Cache rules run first — explicit commands (chart, compare, find me, should
    # I buy) shouldn't be short-circuited by incidental number parsing downstream.
    cache_hit = _cache_classify(text)
    if cache_hit is not None:
        answer_type, reason = cache_hit
        return RouterDecision(
            answer_type=answer_type,
            confidence=0.9,
            target_refs=refs,
            reason=reason,
        )

    # What-if price overrides are inherently decisions. Only consulted when
    # no cache rule fired — avoids the override parser's false positives on
    # street numbers ("for 526") or bed counts ("4-bed") hijacking the turn.
    try:
        from briarwood.agent.overrides import parse_overrides

        has_override = bool(parse_overrides(text))
    except Exception:
        has_override = False
    if has_override:
        if _RENT_LOOKUP_HINT_RE.search(text):
            return RouterDecision(
                answer_type=AnswerType.RENT_LOOKUP,
                confidence=0.75,
                target_refs=refs,
                reason="override with rent question",
            )
        if _PROJECTION_OVERRIDE_HINT_RE.search(text):
            return RouterDecision(
                answer_type=AnswerType.PROJECTION,
                confidence=0.75,
                target_refs=refs,
                reason="override with projection question",
            )
        return RouterDecision(
            answer_type=AnswerType.DECISION,
            confidence=0.7,
            target_refs=refs,
            reason="what-if price override",
        )

    if client is not None:
        llm_guess = _llm_classify(text, client)
        if llm_guess is not None:
            return RouterDecision(
                answer_type=llm_guess,
                confidence=0.6,
                target_refs=refs,
                reason="llm classify",
                llm_suggestion=llm_guess,
            )

    return RouterDecision(
        answer_type=AnswerType.LOOKUP,
        confidence=0.3,
        target_refs=refs,
        reason="default fallback",
    )
