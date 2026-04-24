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

import logging
import re
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, ConfigDict

from briarwood.agent.llm import LLMClient
from briarwood.agent.llm_observability import complete_structured_observed
from briarwood.intent_contract import IntentContract, build_contract_from_answer_type

logger = logging.getLogger(__name__)


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


class PersonaType(str, Enum):
    FIRST_TIME_BUYER = "first_time_buyer"
    INVESTOR = "investor"
    DEVELOPER = "developer"
    AGENT_OR_ADVISOR = "agent_or_advisor"
    UNKNOWN = "unknown"


class UseCaseType(str, Enum):
    OWNER_OCCUPANT = "owner_occupant"
    RENTAL = "rental"
    FLIP = "flip"
    HOUSE_HACK = "house_hack"
    DEVELOPMENT = "development"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class UserType:
    persona_type: PersonaType = PersonaType.UNKNOWN
    use_case_type: UseCaseType = UseCaseType.UNKNOWN

    def as_dict(self) -> dict[str, str]:
        return {
            "persona_type": self.persona_type.value,
            "use_case_type": self.use_case_type.value,
        }


@dataclass(frozen=True)
class RouterDecision:
    answer_type: AnswerType
    confidence: float
    target_refs: list[str] = field(default_factory=list)
    reason: str = ""
    llm_suggestion: AnswerType | None = None  # set when LLM participated
    user_type: UserType = field(default_factory=UserType)
    # F9: shared shape with the analysis router. Auto-populated from
    # ``answer_type`` + ``confidence`` in ``__post_init__`` unless the caller
    # supplies one (e.g. when rehydrating from a persisted decision).
    intent_contract: IntentContract | None = None

    def __post_init__(self) -> None:
        if self.intent_contract is None:
            contract = build_contract_from_answer_type(
                self.answer_type.value, self.confidence
            )
            # Frozen dataclass: bypass __setattr__ via object.__setattr__,
            # same pattern as stdlib's post-init immutable defaults.
            object.__setattr__(self, "intent_contract", contract)


# ─── Cache rules ──────────────────────────────────────────────────────────────
# Only patterns where regex is decisive. Scanned in order; first match wins.
# Anything semantically subtle is the LLM's job, not the cache's.

_CACHE_RULES: tuple[tuple[AnswerType, re.Pattern[str], str], ...] = (
    # Stand-alone greeting/thanks — must be the whole message. Only CHITCHAT
    # and explicit COMPARISON shortcut the LLM — every other intent routes
    # through the LLM so it generates training signal and adapts to phrasing
    # drift. Removed rules (decision verb, renovation scenario, search
    # imperative, visualize keyword) are all handled by the LLM prompt.
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
)


_PROPERTY_ID_RE = re.compile(r"\b([a-z0-9]+(?:-[a-z0-9]+){2,})\b", re.IGNORECASE)
_ADDRESS_LIKE_RE = re.compile(
    r"\b\d+\s+[A-Za-z0-9 .'-]+?\b(?:ave|avenue|st|street|rd|road|dr|drive|ln|lane|blvd|boulevard|"
    r"pkwy|parkway|ct|court|pl|place|ter|terrace|hwy|highway|cir|circle|way)\b",
    re.IGNORECASE,
)


def _cache_classify(text: str) -> tuple[AnswerType, str] | None:
    """Return (answer_type, reason) for the first matching cache rule, or None.

    The cache is deliberately narrow — only greetings and explicit compare
    strings short-circuit. Every other intent (decision, search, projection,
    visualize, browse, risk, edge, strategy, rent_lookup, micro_location,
    research) goes to the LLM so the classifier generates training signal
    and adapts to phrasing drift.
    """
    for answer_type, pattern, reason in _CACHE_RULES:
        if pattern.search(text):
            return answer_type, reason
    return None


def _extract_refs(text: str) -> list[str]:
    return [m.group(1).lower() for m in _PROPERTY_ID_RE.finditer(text)]


_LLM_SYSTEM = (
    "You are a triage classifier for a real-estate decision assistant. "
    "Classify the user turn into EXACTLY ONE answer_type and also infer "
    "telemetry-only user_type metadata. user_type must not change answer_type. "
    "Respond with strict JSON: {\"answer_type\": <one>, "
    "\"persona_type\": <one>, \"use_case_type\": <one>, \"reason\": <short>}. "
    "persona_type values: first_time_buyer, investor, developer, agent_or_advisor, unknown. "
    "use_case_type values: owner_occupant, rental, flip, house_hack, development, unknown. "
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
    persona_type: PersonaType
    use_case_type: UseCaseType
    reason: str = ""


_FIRST_TIME_RE = re.compile(r"\b(first[- ]time|starter home|my first)\b", re.IGNORECASE)
_INVESTOR_RE = re.compile(r"\b(investor|investment|cap rate|noi|cash flow|rental)\b", re.IGNORECASE)
_DEVELOPER_RE = re.compile(r"\b(developer|develop|redevelop|subdivide|zoning|entitle)\b", re.IGNORECASE)
_ADVISOR_RE = re.compile(r"\b(my client|client asks|buyer client|listing client|agent|broker)\b", re.IGNORECASE)
_OWNER_RE = re.compile(r"\b(live there|live in|for my family|primary home|owner[- ]occup|move in)\b", re.IGNORECASE)
_HOUSE_HACK_RE = re.compile(r"\b(house hack|live.*rent|rent.*unit|back house|additional unit|adu)\b", re.IGNORECASE)
_FLIP_RE = re.compile(r"\b(flip|renovate.*sell|fix.*sell|arv|after repair)\b", re.IGNORECASE)


def _infer_user_type_rules(text: str) -> UserType:
    persona = PersonaType.UNKNOWN
    use_case = UseCaseType.UNKNOWN
    if _ADVISOR_RE.search(text):
        persona = PersonaType.AGENT_OR_ADVISOR
    elif _DEVELOPER_RE.search(text):
        persona = PersonaType.DEVELOPER
    elif _INVESTOR_RE.search(text):
        persona = PersonaType.INVESTOR
    elif _FIRST_TIME_RE.search(text):
        persona = PersonaType.FIRST_TIME_BUYER

    if _HOUSE_HACK_RE.search(text):
        use_case = UseCaseType.HOUSE_HACK
    elif _DEVELOPER_RE.search(text):
        use_case = UseCaseType.DEVELOPMENT
    elif _FLIP_RE.search(text):
        use_case = UseCaseType.FLIP
    elif _INVESTOR_RE.search(text):
        use_case = UseCaseType.RENTAL
    elif _OWNER_RE.search(text) or persona is PersonaType.FIRST_TIME_BUYER:
        use_case = UseCaseType.OWNER_OCCUPANT
    return UserType(persona_type=persona, use_case_type=use_case)


def _classification_user_type(result: RouterClassification, text: str) -> UserType:
    inferred = _infer_user_type_rules(text)
    persona = result.persona_type or PersonaType.UNKNOWN
    use_case = result.use_case_type or UseCaseType.UNKNOWN
    if persona is PersonaType.UNKNOWN:
        persona = inferred.persona_type
    if use_case is UseCaseType.UNKNOWN:
        use_case = inferred.use_case_type
    return UserType(persona_type=persona, use_case_type=use_case)


def _llm_classify(text: str, client: LLMClient) -> RouterClassification | None:
    """Classify via LLM with one retry. `complete_structured` already returns
    `None` on any failure (transport, empty, invalid JSON, schema), so the
    retry covers all of those uniformly; the second attempt usually succeeds
    when the first was a transient transport/timeout blip. Persistent schema
    mismatches fail twice and fall through to the caller's default."""
    result = complete_structured_observed(
        surface="agent_router.classify",
        schema=RouterClassification,
        system=_LLM_SYSTEM,
        user=text,
        provider=client.__class__.__name__,
        model=None,
        max_attempts=2,
        call=lambda: client.complete_structured(
            system=_LLM_SYSTEM,
            user=text,
            schema=RouterClassification,
            max_tokens=120,
        ),
    )
    if result is None:
        return None
    guess = result.answer_type
    # Sanity guard: LLMs sometimes return CHITCHAT for real questions they
    # don't have a better bucket for. Default to BROWSE (quick read) unless
    # the text really is a greeting — safer than DECISION (full cascade).
    if guess is AnswerType.CHITCHAT and not _CHITCHAT_ONLY_RE.match(text):
        return result.model_copy(update={"answer_type": AnswerType.BROWSE})
    return result


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
    inferred_user_type = _infer_user_type_rules(text)

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
            user_type=inferred_user_type,
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
                user_type=inferred_user_type,
            )
        if _PROJECTION_OVERRIDE_HINT_RE.search(text):
            return RouterDecision(
                answer_type=AnswerType.PROJECTION,
                confidence=0.75,
                target_refs=refs,
                reason="override with projection question",
                user_type=inferred_user_type,
            )
        return RouterDecision(
            answer_type=AnswerType.DECISION,
            confidence=0.7,
            target_refs=refs,
            reason="what-if price override",
            user_type=inferred_user_type,
        )

    if client is not None:
        llm_result = _llm_classify(text, client)
        if llm_result is not None:
            return RouterDecision(
                answer_type=llm_result.answer_type,
                confidence=0.6,
                target_refs=refs,
                reason="llm classify",
                llm_suggestion=llm_result.answer_type,
                user_type=_classification_user_type(llm_result, text),
            )

    logger.warning(
        "router fallthrough to LOOKUP default (client=%s, text=%r)",
        "present" if client is not None else "missing",
        text[:120],
    )
    return RouterDecision(
        answer_type=AnswerType.LOOKUP,
        confidence=0.3,
        target_refs=refs,
        reason="default fallback",
        user_type=inferred_user_type,
    )
