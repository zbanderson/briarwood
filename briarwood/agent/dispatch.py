"""Per-answer-type handlers.

Each handler takes (user_text, router_decision, session, llm_client) and
returns a short response string. Handlers call at most TWO tools. This is
enforced by convention and by test coverage — no generic tool-use loop.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import logging
import math
import re

from api.prompts import load_prompt
from briarwood.agent.composer import (
    complete_and_verify,
    compose_contract_response,
    compose_structured_response,
)
from briarwood.agent.llm import LLMClient
from briarwood.agent.router import AnswerType, RouterDecision
from briarwood.agent.session import Session
from briarwood.agent.fuzzy_terms import translate
from briarwood.agent.feedback import log_turn as _log_untracked
from briarwood.agent.overrides import parse_overrides, summarize as _override_summary
from briarwood.agent.property_view import PropertyView
from briarwood.agent.tools import (
    CMAResult,
    InvestmentScreenResult,
    LiveListingDecision,
    LiveListingCandidate,
    PromotedPropertyRecord,
    PropertyBrief,
    RentOutlook,
    RenovationResaleOutlook,
    TownMarketRead,
    ToolUnavailable,
    analyze_live_listing,
    analyze_property,
    build_property_brief,
    get_cma,
    get_investment_screen,
    get_projection,
    get_property_brief,
    get_property_presentation,
    get_property_enrichment,
    get_rent_outlook,
    get_property_summary,
    get_rent_estimate,
    promote_unsaved_address,
    saved_property_has_valid_location,
    screen_saved_listings_by_cap_rate,
    get_renovation_resale_outlook,
    get_risk_profile,
    get_strategy_fit,
    get_town_market_read,
    get_value_thesis,
    promote_discovered_listing,
    render_chart,
    research_town,
    search_live_listings,
    search_listings,
    underwrite_matches,
)

logger = logging.getLogger(__name__)

MAX_TOOLS_PER_TURN = 2

# Trust flags that trigger auto-research in decision mode. Plan §Phase C:
# only these two — zoning_unverified and weak_town_context. Other flags
# (incomplete_carry_inputs, thin_comp_set) reflect user-input gaps, not
# external data gaps.
_AUTO_RESEARCH_FLAGS = {"weak_town_context", "zoning_unverified"}


@dataclass(frozen=True)
class PropertyResolution:
    property_id: str | None
    candidates: list[str]
    explicit_reference: bool


def _set_workflow_state(
    session: Session,
    *,
    contract_type: str | None = None,
    analysis_mode: str | None = None,
    search_context: dict[str, object] | None = None,
) -> None:
    if contract_type is not None:
        session.last_answer_contract = contract_type
    if analysis_mode is not None:
        session.last_analysis_mode = analysis_mode
    if search_context is not None:
        session.current_search_context = search_context
        session.search_context = search_context


def _flag_to_focus(flag: str) -> list[str]:
    return {
        "weak_town_context": ["weak_town_context", "development"],
        "zoning_unverified": ["zoning", "zoning_unverified"],
    }.get(flag, [flag])


def _summary_town_state(pid: str) -> tuple[str | None, str | None]:
    # Prefer inputs.json facts (authoritative); summary.json often omits town/state.
    import json

    from briarwood.agent.tools import SAVED_PROPERTIES_DIR

    inputs_path = SAVED_PROPERTIES_DIR / pid / "inputs.json"
    if inputs_path.exists():
        try:
            facts = (json.loads(inputs_path.read_text()).get("facts") or {})
            town = facts.get("town")
            state = facts.get("state")
            if town and state:
                return town, state
        except (OSError, json.JSONDecodeError):
            pass
    try:
        s = get_property_summary(pid)
    except ToolUnavailable:
        return None, None
    return s.get("town"), s.get("state")


def _load_property_facts(pid: str) -> dict[str, object]:
    from briarwood.agent.tools import SAVED_PROPERTIES_DIR

    inputs_path = SAVED_PROPERTIES_DIR / pid / "inputs.json"
    if not inputs_path.exists():
        return {}
    try:
        payload = json.loads(inputs_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload.get("facts") or {})


def _is_value_question(text: str) -> bool:
    lowered = text.lower()
    return bool(
        re.search(r"\b(?:worth|value|valued at)\b", lowered)
        or "how much do you think" in lowered
    )


def _is_listing_history_question(text: str) -> bool:
    lowered = text.lower()
    return bool(
        "last time" in lowered and "listed" in lowered
        or "when was it listed" in lowered
        or "when was the property listed" in lowered
        or "listing date" in lowered
    )


def _listing_history_lookup_response(pid: str) -> str | None:
    summary = get_property_summary(pid)
    facts = _load_property_facts(pid)
    address = summary.get("address") or pid
    listing_date = facts.get("listing_date")
    if isinstance(listing_date, str) and listing_date.strip():
        return f"The latest recorded listing date for {address} is {listing_date.strip()}."
    price_history = facts.get("price_history")
    if isinstance(price_history, list):
        dated_list_events = []
        for entry in price_history:
            if not isinstance(entry, dict):
                continue
            event = str(entry.get("event") or "").lower()
            date = entry.get("date")
            if "list" in event and isinstance(date, str) and date.strip():
                dated_list_events.append(date.strip())
        if dated_list_events:
            return f"The latest recorded listing date for {address} is {max(dated_list_events)}."
    return (
        f"I don't have a recorded listing-date event for {address} yet. "
        "I can still use ATTOM sale history and other property facts, but not a confirmed prior listing timestamp."
    )


def _session_town_state(session: Session) -> tuple[str | None, str | None]:
    if session.current_property_id:
        return _summary_town_state(session.current_property_id)
    if session.current_live_listing:
        town = session.current_live_listing.get("town")
        state = session.current_live_listing.get("state")
        return (
            str(town).strip() if isinstance(town, str) and town.strip() else None,
            str(state).strip() if isinstance(state, str) and state.strip() else None,
        )
    return None, None


def _diff_unified(before: dict, after: dict) -> list[str]:
    """Compare two UnifiedIntelligenceOutput dicts. Return human-readable deltas."""
    lines: list[str] = []

    def _stance(u):
        s = u.get("decision_stance")
        return s.value if hasattr(s, "value") else s

    before_flags = set(before.get("trust_flags") or [])
    after_flags = set(after.get("trust_flags") or [])
    cleared = before_flags - after_flags
    added = after_flags - before_flags
    if cleared:
        lines.append(f"cleared trust flags: {', '.join(sorted(cleared))}")
    if added:
        lines.append(f"new trust flags: {', '.join(sorted(added))}")

    if _stance(before) != _stance(after):
        lines.append(f"stance shifted: {_stance(before)} → {_stance(after)}")

    if before.get("primary_value_source") != after.get("primary_value_source"):
        lines.append(
            f"primary value source shifted: {before.get('primary_value_source')} → {after.get('primary_value_source')}"
        )

    fv_before = (before.get("value_position") or {}).get("fair_value_base")
    fv_after = (after.get("value_position") or {}).get("fair_value_base")
    if isinstance(fv_before, (int, float)) and isinstance(fv_after, (int, float)) and fv_before > 0:
        delta = (fv_after - fv_before) / fv_before
        if abs(delta) >= 0.03:
            lines.append(f"fair value moved {delta:+.1%} (${fv_before:,.0f} → ${fv_after:,.0f})")

    return lines


def _resolve_property_match(
    decision: RouterDecision, session: Session, text: str | None = None
) -> PropertyResolution:
    """Resolve a property id and preserve candidate context for prompts."""
    for ref in decision.target_refs:
        if _SAVED_DIR_EXISTS(ref) and saved_property_has_valid_location(ref):
            return PropertyResolution(ref, [ref], True)

    if text:
        from briarwood.agent.resolver import resolve_property_id

        pid, ranked = resolve_property_id(text)
        if pid and saved_property_has_valid_location(pid):
            return PropertyResolution(pid, ranked, True)
        if pid and not saved_property_has_valid_location(pid):
            return PropertyResolution(None, [candidate for candidate in ranked if saved_property_has_valid_location(candidate)], True)
        if ranked:
            usable = [candidate for candidate in ranked if saved_property_has_valid_location(candidate)]
            return PropertyResolution(None, usable, True)

    if _text_references_unknown_property(decision, text):
        return PropertyResolution(None, [], True)

    if session.current_property_id and saved_property_has_valid_location(session.current_property_id):
        return PropertyResolution(session.current_property_id, [], False)
    return PropertyResolution(None, [], False)


def _resolve_property_id(
    decision: RouterDecision, session: Session, text: str | None = None
) -> str | None:
    return _resolve_property_match(decision, session, text).property_id


def _text_references_unknown_property(
    decision: RouterDecision, text: str | None
) -> bool:
    """True when the user named a property we couldn't resolve.

    Suppresses the session fallback so stale pids don't hijack mismatched
    references. Matches: an unresolved hyphenated slug in target_refs, or
    a street-number + street-word pattern in the free text.
    """
    if any(not _SAVED_DIR_EXISTS(r) for r in decision.target_refs):
        return True
    if text:
        from briarwood.agent.resolver import _extract_street_number

        if _extract_street_number(text) is not None:
            return True
    return False


def _SAVED_DIR_EXISTS(property_id: str) -> bool:
    from briarwood.agent.tools import SAVED_PROPERTIES_DIR

    return (SAVED_PROPERTIES_DIR / property_id).is_dir()


def _candidate_prompt(candidates: list[str]) -> str:
    labels: list[str] = []
    for candidate in candidates[:3]:
        try:
            summary = get_property_summary(candidate)
        except ToolUnavailable:
            labels.append(candidate)
            continue
        address = summary.get("address") or candidate
        town = summary.get("town")
        if town:
            labels.append(f"{candidate} — {address}, {town}")
        else:
            labels.append(f"{candidate} — {address}")
    if not labels:
        return "I couldn't match that property to the saved corpus yet."
    return "I found a few close matches:\n" + "\n".join(f"- {label}" for label in labels)


def _lookup_missing_property_message(match: PropertyResolution) -> str:
    if match.candidates:
        return _candidate_prompt(match.candidates)
    if match.explicit_reference:
        return "I couldn't match that property to a saved record yet."
    return "Which property? I don't have one loaded yet."


def _browse_missing_property_message(match: PropertyResolution) -> str:
    if match.candidates:
        return _candidate_prompt(match.candidates)
    if match.explicit_reference:
        return "I couldn't match that property to the saved corpus yet."
    return "Which property would you like a first purchase read on?"


def _money(value: float | int | None) -> str:
    return f"${value:,.0f}" if isinstance(value, (int, float)) else "n/a"


def _decision_view_to_dict(view: "PropertyView") -> dict[str, object]:
    """Snapshot the decision-tier fields a UI verdict card needs. Kept as a
    dict (not the PropertyView object itself) so it serializes cleanly into
    Session.save() and round-trips through the persisted session JSON."""
    return {
        "pid": view.pid,
        "address": view.address,
        "town": view.town,
        "state": view.state,
        "decision_stance": view.decision_stance,
        "primary_value_source": view.primary_value_source,
        "ask_price": view.ask_price,
        "all_in_basis": view.all_in_basis,
        "fair_value_base": view.fair_value_base,
        "value_low": view.value_low,
        "value_high": view.value_high,
        "ask_premium_pct": view.ask_premium_pct,
        "basis_premium_pct": view.basis_premium_pct,
        "trust_flags": list(view.trust_flags or []),
        "what_must_be_true": list(view.what_must_be_true or []),
        "key_risks": list(view.key_risks or []),
        "overrides_applied": dict(view.overrides_applied or {}),
    }


def _build_town_summary(town: str | None, state: str | None) -> dict[str, object] | None:
    """Build a lightweight town summary from market aggregates + seeded intel.

    No LLM, no web research — reads from the same town-context + signals files
    the valuation already consumed. Emitted inline on first DECISION response
    so the user gets town trust signals without asking a follow-up question.
    """
    if not town:
        return None
    from briarwood.modules.town_aggregation_diagnostics import get_town_context
    from briarwood.local_intelligence.storage import JsonLocalSignalStore, _slugify

    ctx = get_town_context(town)
    if ctx is None:
        return None

    # Raw confidence: we mirror the raw-with-intel-bonus calculation so the
    # UI sees the same number that flag logic uses (structured.py reads the
    # raw field). Keep in sync with _town_prior_raw_confidence in
    # briarwood/agents/current_value/agent.py.
    raw_conf = float(ctx.context_confidence or 0.0)
    doc_count = 0
    bullish: list[str] = []
    bearish: list[str] = []
    if state:
        try:
            signals = JsonLocalSignalStore().load_town_signals(town=town, state=state)
        except Exception:
            signals = []
        # Rank by confidence * impact_magnitude descending, filter out rejected.
        ranked = sorted(
            (s for s in signals if getattr(s, "status", None) != "rejected"),
            key=lambda s: -(float(getattr(s, "confidence", 0) or 0)),
        )
        for s in ranked:
            title = getattr(s, "title", None)
            if not title:
                continue
            direction = getattr(s, "impact_direction", None)
            if direction == "positive" and len(bullish) < 3:
                bullish.append(str(title))
            elif direction == "negative" and len(bearish) < 3:
                bearish.append(str(title))
        # Doc count from the documents folder (signals root is sibling).
        try:
            slug = _slugify(f"{town}-{state}")
            from pathlib import Path
            doc_dir = Path(__file__).resolve().parents[2] / "data" / "local_intelligence" / "documents"
            doc_path = doc_dir / f"{slug}.json"
            if doc_path.exists():
                import json as _json
                payload = _json.loads(doc_path.read_text())
                docs = payload.get("documents") if isinstance(payload, dict) else payload
                doc_count = len(docs) if isinstance(docs, list) else 0
        except Exception:
            doc_count = 0

    intel_bonus = min(doc_count / 3.0, 1.0) * 0.15
    raw_with_intel = round(min(raw_conf + intel_bonus, 0.92), 2)
    if raw_with_intel >= 0.70:
        tier = "strong"
    elif raw_with_intel >= 0.40:
        tier = "moderate"
    else:
        tier = "thin"

    return {
        "town": town,
        "state": state,
        "median_price": ctx.median_price,
        "median_ppsf": ctx.median_ppsf,
        "sold_count": ctx.sold_count,
        "confidence_raw": raw_with_intel,
        "confidence_tier": tier,
        "doc_count": doc_count,
        "bullish_signals": bullish,
        "bearish_signals": bearish,
    }


def _build_comps_preview(pid: str, view: "PropertyView") -> dict[str, object] | None:
    """Top 3-5 saved comps used in the valuation, shaped for a preview card.

    Uses the existing comp-matching helper rather than re-running CMA. Each
    row carries address, beds/baths/sqft, price, and premium vs subject so
    the UI can render a compact stack without another round-trip.
    """
    subject_ask = view.ask_price
    thesis = {"ask_price": subject_ask}
    try:
        comps = _cma_comps_for_property(pid, thesis)
    except Exception:
        return None
    if not comps:
        return None
    rows: list[dict[str, object]] = []
    prices: list[float] = []
    for c in comps[:5]:
        price = c.get("ask_price") or c.get("price")
        premium_pct = None
        if isinstance(price, (int, float)) and isinstance(subject_ask, (int, float)) and subject_ask:
            premium_pct = round((float(price) - float(subject_ask)) / float(subject_ask), 4)
        rows.append({
            "property_id": c.get("property_id"),
            "address": c.get("address"),
            "beds": c.get("beds"),
            "baths": c.get("baths"),
            "sqft": c.get("sqft"),
            "price": price,
            "premium_pct": premium_pct,
        })
        if isinstance(price, (int, float)):
            prices.append(float(price))
    median_price = None
    if prices:
        prices.sort()
        mid = len(prices) // 2
        median_price = prices[mid] if len(prices) % 2 else (prices[mid - 1] + prices[mid]) / 2
    return {
        "subject_pid": pid,
        "subject_ask": subject_ask,
        "count": len(rows),
        "median_price": median_price,
        "comps": rows,
    }


def _format_browse_setup(brief: PropertyBrief) -> str:
    recommendation = brief.recommendation or "No recommendation yet."
    stance = brief.decision_stance or "conditional"
    premium = brief.ask_premium_pct
    if isinstance(premium, (int, float)):
        pricing = "below" if premium < 0 else "above" if premium > 0 else "at"
        return (
            f"Briarwood sees the immediate setup as {stance.replace('_', ' ')}: "
            f"{recommendation} Ask is {pricing} the fair value anchor by {abs(premium):.1%}."
        )
    return f"Briarwood sees the immediate setup as {stance.replace('_', ' ')}: {recommendation}"


def _format_browse_support(brief: PropertyBrief) -> str:
    drivers = list(brief.key_value_drivers or [])
    if drivers:
        return "What supports that view: " + "; ".join(drivers[:2]) + "."
    if brief.primary_value_source and str(brief.primary_value_source).strip().lower() != "unknown":
        return f"What supports that view: primary value source is {brief.primary_value_source}."
    if brief.best_path:
        return f"What supports that view: best path currently reads as {brief.best_path}."
    return "What supports that view: the current snapshot read is still light on explicit supporting drivers."


def _format_browse_caution(brief: PropertyBrief) -> str:
    cautions = list(brief.trust_flags or [])
    if cautions:
        return "What could weaken confidence: " + ", ".join(cautions[:3]) + "."
    risks = list(brief.key_risks or [])
    if risks:
        return "What could weaken confidence: " + "; ".join(risks[:2]) + "."
    return "What could weaken confidence: no major trust flags are surfaced in the snapshot read."


def _format_next_step(brief: PropertyBrief) -> str:
    if brief.next_questions:
        return f"Next best question: {brief.next_questions[0]}"
    mapping = {
        "decision": "should I buy this at the current ask?",
        "scenario": "what does the forward scenario path do to value?",
        "deep_dive": "what is the deepest unresolved risk or assumption here?",
    }
    if brief.recommended_next_run:
        return f"Next best question: {mapping.get(brief.recommended_next_run, brief.recommended_next_run)}"
    return "Next best question: should I buy this at the current ask?"


def _format_browse_brief(brief: PropertyBrief, neighbors: list[dict[str, object]]) -> str:
    parts: list[str] = [brief.address or brief.property_id]
    if brief.beds is not None and brief.baths is not None:
        parts.append(f"{brief.beds}bd/{brief.baths}ba")
    if brief.ask_price is not None:
        parts.append(f"ask {_money(brief.ask_price)}")
    lines = [
        " — ".join(parts),
        _format_browse_setup(brief),
        _format_browse_support(brief),
        _format_browse_caution(brief),
        _format_next_step(brief),
    ]
    if neighbors:
        similar_lines = [f"Nearby support in {brief.town or 'the area'}:"]
        for n in neighbors[:3]:
            bits: list[str] = []
            if n.get("address"):
                bits.append(str(n["address"]))
            if n.get("beds") is not None and n.get("baths") is not None:
                bits.append(f"{n['beds']}bd/{n['baths']}ba")
            if n.get("ask_price") is not None:
                bits.append(_money(n.get("ask_price")))
            if isinstance(n.get("blocks_to_beach"), (int, float)):
                bits.append(f"{n['blocks_to_beach']:.1f} blocks to beach")
            tail = ", ".join(bits)
            similar_lines.append(f"- {n['property_id']}" + (f" — {tail}" if tail else ""))
        lines.append("\n".join(similar_lines))
    return "\n".join(lines)


def _extract_search_place(text: str) -> tuple[str | None, str | None]:
    normalized = re.sub(r"\s+", " ", text.strip())
    patterns = (
        r"\bfor sale in\s+([A-Za-z][A-Za-z .'-]+?)(?:,\s*([A-Z]{2})|\s+([A-Z]{2}))?(?:\b|$)",
        r"\b(?:in|for|around|near)\s+([A-Za-z][A-Za-z .'-]+?)(?:,\s*([A-Z]{2})|\s+([A-Z]{2}))?(?:\b|$)",
        r"\b([A-Za-z][A-Za-z .'-]+?)\s+(?:homes|houses|properties|listings)\s+for sale\b(?:,\s*([A-Z]{2})|\s+([A-Z]{2}))?",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if not match:
            continue
        town = (match.group(1) or "").strip(" ,.")
        if not town:
            continue
        state = (match.group(2) or match.group(3) or "").strip() or None
        if state:
            state = state.upper()
            if state not in _US_STATE_CODES:
                state = None
        town = re.sub(r"\b(?:listed?|sale|homes?|houses?|properties|listings?)\b", "", town, flags=re.IGNORECASE).strip(" ,.")
        if town:
            return town.title(), state
    return None, None


def _extract_place_reply(text: str) -> tuple[str | None, str | None]:
    normalized = re.sub(r"\s+", " ", text.strip().strip("?.!"))
    normalized = re.sub(r"^(?:yes|yeah|yep|ok|okay|sure)\s+", "", normalized, flags=re.IGNORECASE)
    match = re.fullmatch(r"([A-Za-z][A-Za-z .'-]+?)(?:,\s*|\s+)([A-Za-z]{2})", normalized)
    if not match:
        return None, None
    town = match.group(1).strip(" ,.")
    state = match.group(2).strip().upper()
    if state not in _US_STATE_CODES:
        return None, None
    return (town.title(), state) if town else (None, None)


def _live_listing_query(
    text: str,
    town: str | None,
    state: str | None,
    filters: dict[str, object] | None = None,
) -> str | None:
    filters = filters or {}
    if town:
        suffix = f", {state}" if state else ""
        return f"{town}{suffix}"
    stripped = re.sub(r"[?.!]+$", "", text.strip())
    return stripped or None


def _looks_like_specific_town(town: str | None) -> bool:
    if not town:
        return False
    normalized = town.strip().casefold()
    return normalized not in {
        "the",
        "beach",
        "shore",
        "water",
        "ocean",
        "downtown",
        "town",
        "city",
        "area",
        "neighborhood",
    }


def _format_live_listing_candidate(candidate: LiveListingCandidate) -> str:
    bits: list[str] = []
    if candidate.address:
        bits.append(candidate.address)
    if candidate.beds is not None and candidate.baths is not None:
        bits.append(f"{candidate.beds}bd/{candidate.baths}ba")
    if isinstance(candidate.ask_price, (int, float)):
        bits.append(_money(candidate.ask_price))
    if candidate.sqft is not None:
        bits.append(f"{candidate.sqft:,} sqft")
    if candidate.property_type:
        bits.append(candidate.property_type)
    if candidate.listing_status:
        bits.append(candidate.listing_status)
    line = " — ".join(bits[:2])
    tail = ", ".join(bits[2:])
    if tail:
        line = f"{line}, {tail}" if line else tail
    if candidate.listing_url:
        line = f"{line}\n  {candidate.listing_url}"
    return f"- {line}" if line else "- listing candidate"


_ORDINAL_WORDS = {
    "first": 0,
    "1st": 0,
    "second": 1,
    "2nd": 1,
    "third": 2,
    "3rd": 2,
}
_DEICTIC_LIVE_RE = re.compile(r"\b(this house|that house|this one|that one|the house|the listing)\b", re.IGNORECASE)
_CAP_RATE_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*%?\s*cap(?:\s+rate)?\b", re.IGNORECASE)
_US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}


def _serialize_live_listing(candidate: LiveListingCandidate) -> dict[str, object]:
    return {
        "address": candidate.address,
        "town": candidate.town,
        "state": candidate.state,
        "zip_code": candidate.zip_code,
        "ask_price": candidate.ask_price,
        "beds": candidate.beds,
        "baths": candidate.baths,
        "sqft": candidate.sqft,
        "property_type": candidate.property_type,
        "listing_status": candidate.listing_status,
        "listing_url": candidate.listing_url,
        "external_id": candidate.external_id,
        "source": candidate.source,
    }


def _remember_selected_listing(session: Session, listing: dict[str, object] | None) -> None:
    session.selected_search_result = listing
    session.current_live_listing = listing


def _select_live_listing_from_session(text: str, session: Session) -> dict[str, object] | None:
    results = list(session.last_live_listing_results or [])
    if not results:
        return session.current_live_listing
    lowered = text.lower()
    text_tokens = set(re.findall(r"[a-z0-9]+", lowered))
    for result in results:
        address = str(result.get("address") or "").lower()
        address_tokens = [token for token in re.findall(r"[a-z0-9]+", address) if token not in {"nj", "unit", "apt"}]
        if not address_tokens:
            continue
        if address in lowered:
            return result
        street_num = next((token for token in address_tokens if token.isdigit()), None)
        overlap = sum(1 for token in address_tokens if token in text_tokens)
        if street_num and street_num in text_tokens and overlap >= min(3, len(address_tokens)):
            return result
    for word, idx in _ORDINAL_WORDS.items():
        if re.search(rf"\b(?:the\s+)?{re.escape(word)}(?:\s+one|\s+house|\s+listing)?\b", lowered):
            if idx < len(results):
                return results[idx]
    if _DEICTIC_LIVE_RE.search(text):
        if session.current_live_listing:
            return session.current_live_listing
        if len(results) == 1:
            return results[0]
    if session.current_live_listing:
        return session.current_live_listing
    if len(results) == 1:
        return results[0]
    return None


def _promotion_intake_lines(record: PromotedPropertyRecord) -> list[str]:
    lines: list[str] = []
    if record.sourced_fields:
        lines.append("Source coverage: Zillow/SearchAPI sourced " + ", ".join(record.sourced_fields[:4]) + ".")
    if record.inferred_fields:
        lines.append("Briarwood inferred or normalized " + ", ".join(record.inferred_fields[:3]) + ".")
    if record.missing_fields:
        lines.append("Still missing for higher-confidence reads: " + ", ".join(record.missing_fields[:4]) + ".")
    return lines


def _promotion_enrichment_lines(enrichment: dict[str, object] | None) -> list[str]:
    if not isinstance(enrichment, dict):
        return []
    lines: list[str] = []
    attom = enrichment.get("attom")
    if isinstance(attom, dict) and attom:
        attom_bits: list[str] = []
        if isinstance(attom.get("sale_history_snapshot"), dict):
            attom_bits.append("sale history")
        if isinstance(attom.get("assessment_detail"), dict):
            attom_bits.append("tax/assessment")
        if isinstance(attom.get("rental_avm"), dict):
            attom_bits.append("rent support")
        if attom_bits:
            lines.append("Structured enrichment pulled from ATTOM: " + ", ".join(attom_bits[:3]) + ".")
    google = enrichment.get("google")
    if isinstance(google, dict) and google:
        geo_bits: list[str] = []
        if isinstance(google.get("geocode"), dict) and google.get("geocode"):
            geo_bits.append("geocode")
        nearby = google.get("nearby_places")
        if isinstance(nearby, dict) and nearby.get("type_counts"):
            geo_bits.append("nearby places")
        if google.get("street_view_image_url"):
            geo_bits.append("street view")
        if geo_bits:
            lines.append("Location enrichment pulled from Google Maps: " + ", ".join(geo_bits[:3]) + ".")
    return lines


def _presentation_card_map(payload: dict[str, object] | None) -> dict[str, dict[str, object]]:
    if not isinstance(payload, dict):
        return {}
    cards = payload.get("cards")
    if not isinstance(cards, list):
        return {}
    mapped: dict[str, dict[str, object]] = {}
    for card in cards:
        if not isinstance(card, dict):
            continue
        key = card.get("key")
        if isinstance(key, str):
            mapped[key] = card
    return mapped


def _card_body_lines(card: dict[str, object] | None) -> list[str]:
    if not isinstance(card, dict):
        return []
    body = card.get("body")
    if not isinstance(body, list):
        return []
    return [str(line) for line in body if isinstance(line, str) and line.strip()]


def _format_browse_from_presentation(
    payload: dict[str, object] | None,
    brief: PropertyBrief,
    neighbors: list[dict[str, object]],
) -> str | None:
    card_map = _presentation_card_map(payload)
    header = _card_body_lines(card_map.get("property_header"))
    purchase = _card_body_lines(card_map.get("purchase_brief"))
    coverage = _card_body_lines(card_map.get("data_coverage"))
    location = _card_body_lines(card_map.get("location_pulse"))
    if not header or len(purchase) < 4:
        return None
    lines = [
        header[0],
        "Briarwood sees the immediate setup as " + purchase[0].removeprefix("Immediate setup: ").strip(),
        "What supports that view: " + purchase[1].removeprefix("What supports it: ").strip(),
        "What could weaken confidence: " + purchase[2].removeprefix("What could weaken confidence: ").strip(),
        purchase[3],
    ]
    if coverage:
        lines.append("Source coverage: " + " ".join(coverage[:2]))
    if location:
        lines.append("Location pulse: " + " ".join(location[:2]))
    if neighbors:
        similar_lines = [f"Nearby support in {brief.town or 'the area'}:"]
        for n in neighbors[:3]:
            bits: list[str] = []
            if n.get("address"):
                bits.append(str(n["address"]))
            if n.get("beds") is not None and n.get("baths") is not None:
                bits.append(f"{n['beds']}bd/{n['baths']}ba")
            if n.get("ask_price") is not None:
                bits.append(_money(n.get("ask_price")))
            if isinstance(n.get("blocks_to_beach"), (int, float)):
                bits.append(f"{n['blocks_to_beach']:.1f} blocks to beach")
            tail = ", ".join(bits)
            similar_lines.append(f"- {n['property_id']}" + (f" — {tail}" if tail else ""))
        lines.append("\n".join(similar_lines))
    return "\n".join(lines)


def _format_decision_from_presentation(
    payload: dict[str, object] | None,
    *,
    stance: str,
    view: PropertyView,
    research_lines: list[str],
) -> str | None:
    card_map = _presentation_card_map(payload)
    header = _card_body_lines(card_map.get("property_header"))
    purchase = _card_body_lines(card_map.get("purchase_brief"))
    coverage = _card_body_lines(card_map.get("data_coverage"))
    if not header:
        return None
    money = lambda v: f"${v:,.0f}" if isinstance(v, (int, float)) else "n/a"
    lines = [
        header[0],
        f"Stance: {stance}. " + (purchase[0].removeprefix("Immediate setup: ") if purchase else ""),
        (
            f"Fair value anchor: {money(view.fair_value_base)} against all-in basis "
            f"{money(view.all_in_basis if view.all_in_basis is not None else view.ask_price)}."
        ),
        f"Primary value source: {view.primary_value_source or 'unknown'}.",
        "Trust flags: " + (", ".join(view.trust_flags) if view.trust_flags else "none") + ".",
    ]
    if purchase and len(purchase) > 1:
        lines.append("What supports that view: " + purchase[1].removeprefix("What supports it: ").strip())
    if coverage:
        lines.append("Source coverage: " + " ".join(coverage[:2]))
    if research_lines:
        lines.extend(research_lines)
    return "\n".join(lines)


def _promote_selected_listing(
    text: str,
    session: Session,
) -> tuple[str | None, PromotedPropertyRecord | None, str | None]:
    listing = _select_live_listing_from_session(text, session)
    if listing is None:
        return None, None, None
    try:
        record = promote_discovered_listing(listing_context=listing)
    except ToolUnavailable as exc:
        session.promotion_error = str(exc)
        _remember_selected_listing(session, listing)
        return None, None, f"I couldn't promote that discovered listing into Briarwood yet ({exc})."
    session.current_property_id = record.property_id
    session.promoted_property_id = record.property_id
    session.promotion_error = None
    _remember_selected_listing(session, listing)
    return record.property_id, record, None


def _promote_unsaved_address_from_text(
    text: str,
    session: Session,
) -> tuple[str | None, PromotedPropertyRecord | None, str | None]:
    street_number = re.search(r"\b\d+\b", text)
    street_word = re.search(
        r"\b(?:ave|avenue|st|street|rd|road|dr|drive|ln|lane|blvd|boulevard|ct|court|pl|place|way)\b",
        text,
        re.IGNORECASE,
    )
    if not street_number or not street_word:
        return None, None, None
    try:
        record = promote_unsaved_address(text)
    except ToolUnavailable as exc:
        session.promotion_error = str(exc)
        return None, None, None
    except Exception as exc:
        logger.warning("unsaved-address promotion failed for %r: %s", text, exc)
        return None, None, None
    session.current_property_id = record.property_id
    session.promoted_property_id = record.property_id
    session.promotion_error = None
    return record.property_id, record, None


def _format_live_listing_brief(candidate: dict[str, object]) -> str:
    money = lambda v: f"${v:,.0f}" if isinstance(v, (int, float)) else "n/a"
    address = str(candidate.get("address") or "This listing")
    town = str(candidate.get("town") or "")
    state = str(candidate.get("state") or "")
    bits = [address]
    beds = candidate.get("beds")
    baths = candidate.get("baths")
    if isinstance(beds, int) and isinstance(baths, (int, float)):
        bits.append(f"{beds}bd/{baths}ba")
    if isinstance(candidate.get("ask_price"), (int, float)):
        bits.append(f"ask {money(candidate.get('ask_price'))}")
    lines = [" — ".join(bits)]
    place = ", ".join(part for part in (town, state) if part)
    property_type = candidate.get("property_type")
    if property_type or place:
        lines.append(
            "This is a live Zillow listing"
            + (f" in {place}" if place else "")
            + (f" for a {str(property_type).replace('_', ' ').lower()}" if property_type else "")
            + "."
        )
    support: list[str] = []
    if candidate.get("sqft") is not None:
        support.append(f"{int(candidate['sqft']):,} sqft")
    if candidate.get("listing_status"):
        support.append(str(candidate["listing_status"]).replace("_", " ").lower())
    if support:
        lines.append("What stands out: " + ", ".join(support) + ".")
    lines.append(
        "What is still missing: Briarwood has not run the full saved-property underwrite path on this live listing yet, "
        "so value posture, trust flags, and strategy fit are still provisional."
    )
    if candidate.get("listing_url"):
        lines.append("Next best move: use this Zillow URL for a deeper purchase read.\n" + str(candidate["listing_url"]))
    else:
        lines.append("Next best move: paste the Zillow URL and I can go deeper on the purchase read.")
    return "\n".join(lines)


def _format_live_listing_decision(decision: LiveListingDecision) -> str:
    money = lambda v: f"${v:,.0f}" if isinstance(v, (int, float)) else "n/a"
    flags = ", ".join(decision.trust_flags) if decision.trust_flags else "none"
    lines = [
        f"{decision.address or 'Live listing'} — ask {money(decision.ask_price)}",
        (
            f"Decision stance: {(decision.decision_stance or 'unknown').replace('_', ' ')}. "
            f"{decision.recommendation or 'No recommendation yet.'}"
        ),
        (
            f"Fair value anchor: {money(decision.fair_value_base)}"
            + (
                f" against all-in basis {money(decision.all_in_basis)}."
                if isinstance(decision.all_in_basis, (int, float))
                else "."
            )
        ),
        f"Primary value source: {decision.primary_value_source or 'n/a'}.",
        f"Trust flags: {flags}.",
    ]
    if decision.best_path:
        lines.append(f"Best path: {decision.best_path}.")
    return "\n".join(lines)


# ---------- LOOKUP ----------


def handle_lookup(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    match = _resolve_property_match(decision, session, text)
    pid = match.property_id
    if pid is None:
        pid, _, promotion_error = _promote_selected_listing(text, session)
        if promotion_error:
            return promotion_error
        if pid is None:
            pid, _, _ = _promote_unsaved_address_from_text(text, session)
        if pid is None:
            return _lookup_missing_property_message(match)
    try:
        summary = get_property_summary(pid)
    except ToolUnavailable as exc:
        return f"I couldn't find summary data ({exc})."
    session.current_property_id = pid
    _set_workflow_state(session, contract_type="lookup", analysis_mode="lookup")
    _set_workflow_state(session, contract_type="full_underwrite", analysis_mode="decision")

    if _is_listing_history_question(text):
        return _listing_history_lookup_response(pid)

    if llm is None:
        addr = summary.get("address", pid)
        price = summary.get("ask_price")
        price_s = _money(price)
        return f"{addr} — ask {price_s}, {summary.get('pricing_view', '')}.".strip()

    system = load_prompt("lookup")
    user = f"Question: {text}\n\nSummary JSON:\n{summary}"
    cleaned, report = complete_and_verify(
        llm=llm,
        system=system,
        user=user,
        structured_inputs=dict(summary),
        tier="lookup",
        max_tokens=120,
    )
    session.last_verifier_report = report
    return cleaned


# ---------- DECISION ----------


def handle_decision(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    pid = _resolve_property_id(decision, session, text)
    if pid is None:
        pid, _, promotion_error = _promote_selected_listing(text, session)
        if promotion_error:
            return promotion_error
        if pid is None:
            pid, _, _ = _promote_unsaved_address_from_text(text, session)
        if pid is None:
            live_listing = _select_live_listing_from_session(text, session)
            if live_listing and live_listing.get("listing_url"):
                try:
                    result = analyze_live_listing(
                        listing_url=str(live_listing["listing_url"]),
                        listing_context=live_listing,
                        user_input=text or "should I buy this property?",
                    )
                except ToolUnavailable as exc:
                    return f"I couldn't analyze that live listing ({exc})."
                _remember_selected_listing(session, live_listing)
                session.current_property_id = None
                return _format_live_listing_decision(result)
            return "Which property should I underwrite?"
    overrides = parse_overrides(text)
    try:
        view = PropertyView.load(pid, overrides=overrides, depth="decision")
    except ToolUnavailable as exc:
        return f"I couldn't analyze that ({exc})."
    session.current_property_id = pid
    session.last_decision_view = _decision_view_to_dict(view)

    # Spoon-feed the first DECISION response with town context + comp preview
    # so the user doesn't need two follow-ups to get the full picture. Both
    # calls are file-backed and fast; failures degrade silently.
    try:
        session.last_town_summary = _build_town_summary(view.town, view.state)
    except Exception as exc:
        logger.warning("town summary build failed: %s", exc)
        session.last_town_summary = None
    try:
        session.last_comps_preview = _build_comps_preview(pid, view)
    except Exception as exc:
        logger.warning("comps preview build failed: %s", exc)
        session.last_comps_preview = None

    # Populate the scenario view so the first DECISION response can emit a
    # bull/base/bear table + fan chart inline. Failures here must not block
    # the decision narrative — scenarios are enrichment, not the core answer.
    projection_chart_line = ""
    try:
        proj = get_projection(pid, overrides=overrides)
        session.last_projection_view = {
            **proj,
            "address": view.address,
            "town": view.town,
            "state": view.state,
        }
        from briarwood.agent.rendering import ChartUnavailable, render_chart as _render
        try:
            path = _render("scenario_fan", proj, session_id=session.session_id or "default")
            projection_chart_line = f"\n\nChart: file://{path.resolve()}"
        except ChartUnavailable:
            pass
    except Exception as exc:
        logger.warning("decision projection failed for %s: %s", pid, exc)

    def _finalize(response: str) -> str:
        return response + projection_chart_line

    # Auto-research hook: exactly one loop, only in decision mode, only when a
    # research-fixable trust flag is present. Visible "researching..." is
    # mandatory so the user never wonders where latency came from.
    # Skip research when overrides are present — what-if turns aren't about
    # new town context, they're about re-underwriting at a user-supplied basis.
    research_targets = set(view.trust_flags) & _AUTO_RESEARCH_FLAGS
    research_lines: list[str] = []
    if research_targets and not overrides:
        town, state = _summary_town_state(pid)
        if town and state:
            first_flag = next(iter(research_targets))
            focus = _flag_to_focus(first_flag)
            print(f"[researching {town}, {state} ({first_flag})…]", flush=True)
            try:
                research_result = research_town(town, state, focus)
            except Exception as exc:  # pragma: no cover - defensive
                research_result = {"warnings": [f"research error: {exc}"]}
            before = view
            try:
                view = PropertyView.load(pid, overrides=overrides, depth="decision")
            except ToolUnavailable:
                view = before
            diff = _diff_unified(before.unified or {}, view.unified or {})
            if diff:
                research_lines.append("Research update: " + "; ".join(diff) + ".")
            else:
                research_lines.append(
                    f"Research update: no material change after fetching {research_result.get('document_count', 0)} "
                    f"document(s) for {first_flag}."
                )

    stance = view.decision_stance or "unknown"
    pvs = view.primary_value_source or "unknown"
    flags = list(view.trust_flags)
    # Decision narration shows the all-in basis — what the buyer actually
    # commits — not just the listing ask. Ask vs basis diverge whenever
    # capex is applied (renovation override, capex lane, etc.).
    basis = view.all_in_basis if view.all_in_basis is not None else view.ask_price
    premium = view.basis_premium_pct
    presentation_payload: dict[str, object] | None = None
    if not overrides:
        try:
            summary = get_property_summary(pid)
            derived_brief = build_property_brief(pid, summary, dict(view.unified or {}))
            presentation_payload = get_property_presentation(
                pid,
                include_town_research=False,
                brief=derived_brief,
                contract_type="decision_summary",
                analysis_mode="decision",
            )
        except Exception as exc:
            logger.warning("decision presentation failed for %s: %s", pid, exc)
            presentation_payload = None

    if llm is None:
        if _is_value_question(text) and isinstance(view.fair_value_base, (int, float)):
            range_bits: list[str] = []
            if isinstance(view.value_low, (int, float)) and isinstance(view.value_high, (int, float)):
                range_bits.append(
                    f"with a working range of {_money(view.value_low)} to {_money(view.value_high)}"
                )
            support = (
                f" based on the current {view.primary_value_source.replace('_', ' ')} anchor"
                if isinstance(view.primary_value_source, str) and view.primary_value_source
                else ""
            )
            caveat = (
                f" Confidence drag: {', '.join(flags)}."
                if flags
                else ""
            )
            return _finalize(
                f"{view.address or 'This property'} looks worth about {_money(view.fair_value_base)}"
                + (f" {range_bits[0]}" if range_bits else "")
                + f"{support}.{caveat}"
            )
        rendered = _format_decision_from_presentation(
            presentation_payload,
            stance=stance,
            view=view,
            research_lines=research_lines,
        )
        if rendered:
            return _finalize(rendered)
        money = lambda v: f"${v:,.0f}" if isinstance(v, (int, float)) else "n/a"
        pct = f"{premium:+.1%}" if isinstance(premium, (int, float)) else "n/a"
        flags_s = ", ".join(flags) if flags else "none"
        base = (
            f"Stance: {stance}. Primary value source: {pvs}. "
            f"Fair value {money(view.fair_value_base)} vs all-in {money(basis)} "
            f"(ask {money(view.ask_price)}, {pct}). "
            f"Trust flags: {flags_s}."
        )
        if research_lines:
            base += "\n" + "\n".join(research_lines)
        return _finalize(base)

    if _is_value_question(text) and isinstance(view.fair_value_base, (int, float)):
        range_s = (
            f"{_money(view.value_low)} to {_money(view.value_high)}"
            if isinstance(view.value_low, (int, float)) and isinstance(view.value_high, (int, float))
            else "n/a"
        )
        support = view.primary_value_source or "current analysis"
        caveat = ", ".join(flags) if flags else "none"
        value_inputs = {
            "address": view.address,
            "fair_value_base": view.fair_value_base,
            "value_low": view.value_low,
            "value_high": view.value_high,
            "primary_value_source": support,
            "trust_flags": list(flags),
            "ask_price": view.ask_price,
            "all_in_basis": view.all_in_basis,
        }
        cleaned, report = complete_and_verify(
            llm=llm,
            system=load_prompt("decision_value"),
            user=(
                f"user_question: {text}\n"
                f"address: {view.address}\n"
                f"fair_value_base: {view.fair_value_base}\n"
                f"value_range: {range_s}\n"
                f"primary_value_source: {support}\n"
                f"trust_flags: {caveat}\n"
                f"ask_price: {view.ask_price}\n"
                f"all_in_basis: {view.all_in_basis}\n"
            ),
            structured_inputs=value_inputs,
            tier="decision_value",
            max_tokens=180,
        )
        session.last_verifier_report = report
        return _finalize(cleaned)

    system = load_prompt("decision_summary")
    summary_inputs = {
        "overrides_applied": dict(view.overrides_applied) or {},
        "decision_stance": stance,
        "primary_value_source": pvs,
        "ask_price": view.ask_price,
        "all_in_basis": view.all_in_basis,
        "fair_value_base": view.fair_value_base,
        "basis_premium_pct": view.basis_premium_pct,
        "ask_premium_pct": view.ask_premium_pct,
        "trust_flags": list(flags),
        "what_must_be_true": list(view.what_must_be_true),
        "research_update": research_lines,
    }
    user = (
        f"User question: {text}\n\n"
        f"overrides_applied: {dict(view.overrides_applied) or 'none'}\n"
        f"decision_stance: {stance}\n"
        f"primary_value_source: {pvs}\n"
        f"ask_price: {view.ask_price}\n"
        f"all_in_basis: {view.all_in_basis}\n"
        f"fair_value_base: {view.fair_value_base}\n"
        f"basis_premium_pct: {view.basis_premium_pct}\n"
        f"ask_premium_pct: {view.ask_premium_pct}\n"
        f"trust_flags: {flags}\n"
        f"what_must_be_true: {list(view.what_must_be_true)}\n"
        f"research_update: {' | '.join(research_lines) or 'none'}"
    )
    cleaned, report = complete_and_verify(
        llm=llm,
        system=system,
        user=user,
        structured_inputs=summary_inputs,
        tier="decision_summary",
        max_tokens=260,
    )
    session.last_verifier_report = report
    return _finalize(cleaned)


# ---------- SEARCH (Phase B placeholder) ----------


def handle_search(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    translation = translate(text)
    town, state = _extract_search_place(text)
    if not town or not state:
        reply_town, reply_state = _extract_place_reply(text)
        if reply_town and reply_state:
            town = town or reply_town
            state = state or reply_state
    if session.current_search_context or session.search_context:
        context = dict(session.current_search_context or session.search_context or {})
        if not town and context.get("town"):
            town = str(context.get("town"))
        if not state and context.get("state"):
            state = str(context.get("state"))
        context_filters = context.get("filters")
        if isinstance(context_filters, dict) and translation.filters:
            translation.filters = {**context_filters, **translation.filters}
        elif isinstance(context_filters, dict) and not translation.filters:
            translation.filters = context_filters
    if town and not state and _looks_like_specific_town(town):
        _set_workflow_state(
            session,
            search_context={"town": town, "state": None, "filters": dict(translation.filters)},
        )
        return (
            f"I can run live listing discovery for {town}, but I need the state too. "
            "Please provide the town and state, like 'Belmar, NJ'."
        )
    target_cap_rate = _extract_target_cap_rate(text)
    if target_cap_rate is not None:
        screening_filters = dict(translation.filters)
        if town:
            screening_filters["town"] = town
        if state:
            screening_filters["state"] = state
        results = screen_saved_listings_by_cap_rate(
            filters=screening_filters,
            target_cap_rate=target_cap_rate,
            tolerance=0.0025,
        )
        if results:
            place = ", ".join(part for part in (town, state) if part) or "the saved corpus"
            _set_workflow_state(session, contract_type="investment_screen", analysis_mode="search")
            lines = [f"Saved-corpus cap-rate screen at {target_cap_rate:.1%} in {place}:"]
            for row in results:
                lines.append(
                    f"- {row.property_id} — {row.address or 'Unknown address'}, "
                    f"ask {_money(row.ask_price)}, NOI {_money(row.annual_noi)}, "
                    f"cap {row.cap_rate:.1%}, rent {_money(row.monthly_rent)}"
                    + (f" ({row.rent_source_type})" if row.rent_source_type else "")
                )
            lines.append("Next best move: pick one and I can underwrite whether that cap rate is actually durable.")
            return "\n".join(lines)
        if town and state:
            return (
                f"I screened the saved Briarwood corpus for roughly {target_cap_rate:.1%} cap-rate deals in {town}, {state}, "
                "and nothing qualified yet. I can still show raw live listings there, but I can only screen cap rate deterministically on saved properties today."
            )
    live_query = _live_listing_query(text, town, state, translation.filters)
    live_failure: str | None = None

    if town and live_query:
        try:
            live_matches = search_live_listings(
                query=live_query,
                town=town,
                state=state,
                beds=translation.filters.get("beds") if isinstance(translation.filters.get("beds"), int) else None,
                beds_min=translation.filters.get("beds_min") if isinstance(translation.filters.get("beds_min"), int) else None,
            )
        except ToolUnavailable as exc:
            live_matches = []
            live_failure = str(exc)
        if live_matches:
            serialized = [_serialize_live_listing(match) for match in live_matches]
            session.last_live_listing_results = serialized
            _remember_selected_listing(session, serialized[0] if len(serialized) == 1 else None)
            session.current_property_id = None
            session.promoted_property_id = None
            session.promotion_error = None
            _set_workflow_state(
                session,
                contract_type="search_results",
                analysis_mode="search",
                search_context={
                    "town": town,
                    "state": state,
                    "filters": dict(translation.filters),
                },
            )
            heading_place = ", ".join(part for part in (town, state) if part)
            lines = [
                f"Found {len(live_matches)} live Zillow listing(s) for sale in {heading_place or town}:"
            ]
            for match in live_matches[:6]:
                lines.append(_format_live_listing_candidate(match))
            lines.append("Next best move: paste one Zillow URL or name one address and I can give you a first purchase read.")
            return "\n".join(lines)

    if not translation.filters:
        return (
            "I couldn't translate that into concrete saved-corpus filters, and I didn't get a clean town-level live listing pull. "
            "Try wording like 'show me houses for sale in Belmar' or '3 beds near the beach under $1.5M'."
        )

    matches = search_listings(translation.filters)
    if not matches:
        live_note = f" Live Zillow discovery was unavailable ({live_failure})." if live_failure else ""
        return (
            f"No matches for {translation.filters}. "
            f"(matched phrases: {translation.matched_phrases or 'none'}).{live_note}"
        )

    lines = []
    if live_failure:
        lines.append(f"Live Zillow discovery was unavailable ({live_failure}), so I fell back to the saved corpus.")
    lines.append(f"Matched {len(matches)} of the saved corpus on filters {translation.filters}:")
    for m in matches[:5]:
        price = f"${m['ask_price']:,.0f}" if isinstance(m.get("ask_price"), (int, float)) else "n/a"
        dist = (
            f"{m['blocks_to_beach']} blocks to beach"
            if m.get("blocks_to_beach") is not None
            else ""
        )
        lines.append(
            f"- {m['property_id']} — {m.get('address') or ''}, "
            f"{m.get('beds') or '?'}bd/{m.get('baths') or '?'}ba, {price} {dist}".rstrip()
        )
    if len(matches) > 5:
        lines.append(f"(+{len(matches) - 5} more)")

    # Remember the last search so a follow-up "underwrite the first two" works.
    session.last_live_listing_results = []
    _remember_selected_listing(session, None)
    session.current_property_id = matches[0]["property_id"]
    session.promoted_property_id = session.current_property_id
    session.promotion_error = None
    _set_workflow_state(
        session,
        contract_type="search_results",
        analysis_mode="search",
        search_context={
            "town": town,
            "state": state,
            "filters": dict(translation.filters),
        },
    )
    return "\n".join(lines)


# ---------- COMPARISON (Phase A: defers to decision) ----------


def handle_comparison(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    refs = [ref for ref in decision.target_refs if _SAVED_DIR_EXISTS(ref)]
    if len(refs) < 2:
        return "Comparison needs two valid property ids I've seen before."
    results = underwrite_matches(refs[:2])
    enriched: list[dict[str, object]] = []
    lines = ["Comparison:"]
    for r in results:
        if "error" in r:
            lines.append(f"- {r['property_id']}: {r['error']}")
            enriched.append(dict(r))
            continue
        vp = r.get("value_position") or {}
        premium = vp.get("premium_discount_pct")
        premium_s = f"{premium:+.1%}" if isinstance(premium, (int, float)) else "n/a"
        flags = ", ".join(r.get("trust_flags") or []) or "none"
        lines.append(
            f"- {r['property_id']}: {r.get('decision_stance')} ({premium_s}), flags: {flags}"
        )
        facts = _load_property_facts(r["property_id"])
        enriched.append(
            {
                **r,
                "address": facts.get("address"),
                "town": facts.get("town"),
                "state": facts.get("state"),
                "ask_price": facts.get("purchase_price"),
                "beds": facts.get("beds"),
                "baths": facts.get("baths"),
                "sqft": facts.get("sqft"),
            }
        )
    session.last_comparison_view = enriched
    return "\n".join(lines)


# ---------- RESEARCH ----------


def handle_research(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    pid = _resolve_property_id(decision, session, text)
    if pid:
        session.current_property_id = pid
    town, state = _session_town_state(session)
    if (not town or not state) and (session.selected_search_result or session.current_live_listing):
        promoted_pid, _, _ = _promote_selected_listing(text, session)
        if promoted_pid:
            session.current_property_id = promoted_pid
            town, state = _session_town_state(session)
    if (not town or not state) and not session.current_property_id:
        promoted_pid, _, _ = _promote_unsaved_address_from_text(text, session)
        if promoted_pid:
            session.current_property_id = promoted_pid
            town, state = _session_town_state(session)
    if not town or not state:
        town, state = _extract_research_place(text)
    if not town or not state:
        return "Which property or town should I research? I need a loaded property or a saved town context."
    try:
        result = research_town(town, state, _research_focus(text))
    except Exception as exc:
        return f"I couldn't research {town}, {state} ({exc})."
    summary = dict(result.get("summary") or {})
    market_read = TownMarketRead(
        town=town,
        state=state,
        confidence_label=summary.get("confidence_label"),
        narrative_summary=summary.get("narrative_summary"),
        bullish_signals=list(summary.get("bullish_signals") or []),
        bearish_signals=list(summary.get("bearish_signals") or []),
        watch_items=list(summary.get("watch_items") or []),
        document_count=result.get("document_count") if isinstance(result.get("document_count"), int) else None,
        warnings=list(result.get("warnings") or []),
    )
    _set_workflow_state(session, contract_type="town_market_read", analysis_mode="research")
    bullish = list(market_read.bullish_signals or [])
    bearish = list(market_read.bearish_signals or [])
    watch_items = list(market_read.watch_items or [])
    confidence = market_read.confidence_label or "Low"
    narrative = market_read.narrative_summary or f"No clear town pulse yet for {town}, {state}."
    session.last_research_view = {
        "town": town,
        "state": state,
        "confidence_label": market_read.confidence_label,
        "narrative_summary": market_read.narrative_summary,
        "bullish_signals": bullish,
        "bearish_signals": bearish,
        "watch_items": watch_items,
        "document_count": market_read.document_count,
        "warnings": list(market_read.warnings or []),
    }
    lines = [f"{town}, {state} market read ({confidence} confidence): {narrative}"]
    if bullish:
        lines.append("What looks constructive: " + "; ".join(bullish[:2]) + ".")
    if bearish:
        lines.append("What could weigh on the market: " + "; ".join(bearish[:2]) + ".")
    elif watch_items:
        lines.append("What still needs watching: " + "; ".join(watch_items[:2]) + ".")
    if isinstance(market_read.document_count, int):
        lines.append(f"Research pull: {market_read.document_count} document(s) reviewed.")
    warnings = list(market_read.warnings or [])
    if warnings:
        lines.append("Caution: " + "; ".join(warnings[:2]))
    return "\n".join(lines)


# ---------- VISUALIZE ----------


_CHART_KIND_KEYWORDS = (
    ("verdict_gauge", re.compile(r"\b(verdict|gauge|stance chart)\b", re.IGNORECASE)),
    ("value_opportunity", re.compile(r"\b(value (picture|chart|opportunity)|ask vs (fair|value))\b", re.IGNORECASE)),
    ("rent_burn", re.compile(r"\b(rent burn|burn chart|rent chart|break[- ]?even rent)\b", re.IGNORECASE)),
)

_CMA_RE = re.compile(
    r"\b(?:cma|comparative market analysis|comparative market assessment|market analysis)\b",
    re.IGNORECASE,
)


def _infer_chart_kind(text: str) -> str:
    for kind, pattern in _CHART_KIND_KEYWORDS:
        if pattern.search(text):
            return kind
    return "value_opportunity"  # default: the chart that answers "what's the picture?"


def _cma_comps_for_property(pid: str, thesis: dict[str, object]) -> list[dict[str, object]]:
    try:
        summary = get_property_summary(pid)
    except ToolUnavailable:
        return []
    filters: dict[str, object] = {}
    if summary.get("town"):
        filters["town"] = summary.get("town")
    if summary.get("state"):
        filters["state"] = summary.get("state")
    if isinstance(summary.get("beds"), int):
        filters["beds"] = summary.get("beds")
    if not filters:
        return []
    comps = [row for row in search_listings(filters) if row.get("property_id") != pid]
    subject_ask = thesis.get("ask_price")

    def _rank_key(row: dict[str, object]) -> tuple[int, float]:
        ask = row.get("ask_price")
        same_baths = 0
        if summary.get("baths") is not None and row.get("baths") == summary.get("baths"):
            same_baths = -1
        if isinstance(subject_ask, (int, float)) and isinstance(ask, (int, float)):
            return (same_baths, abs(float(ask) - float(subject_ask)))
        return (same_baths, float("inf"))

    comps.sort(key=_rank_key)
    return comps[:4]


def _format_cma_comp_lines(comps: list[dict[str, object]]) -> list[str]:
    if not comps:
        return []
    lines = ["CMA support comps:"]
    for comp in comps:
        bits: list[str] = []
        if comp.get("address"):
            bits.append(str(comp["address"]))
        if comp.get("beds") is not None and comp.get("baths") is not None:
            bits.append(f"{comp['beds']}bd/{comp['baths']}ba")
        if comp.get("ask_price") is not None:
            bits.append(_money(comp.get("ask_price")))
        if isinstance(comp.get("blocks_to_beach"), (int, float)):
            bits.append(f"{comp['blocks_to_beach']:.1f} blocks to beach")
        tail = ", ".join(bits)
        lines.append(f"- {comp.get('property_id')}" + (f" — {tail}" if tail else ""))
    return lines


def handle_visualize(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    pid = _resolve_property_id(decision, session, text)
    if pid is None:
        pid, _, promotion_error = _promote_selected_listing(text, session)
        if promotion_error:
            return promotion_error
        if pid is None:
            pid, _, _ = _promote_unsaved_address_from_text(text, session)
    if pid is None:
        return "Which property should I chart? Give me a saved property id."
    from briarwood.agent.rendering import ChartUnavailable

    kind = _infer_chart_kind(text)
    try:
        result = render_chart(kind, pid, session_id=session.session_id or "default")
    except ChartUnavailable as exc:
        return f"I couldn't render that chart ({exc})."
    session.current_property_id = pid
    return f"Rendered {kind} for {pid}: file://{result['path']}"


# ---------- RENT_LOOKUP ----------


def handle_rent_lookup(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    pid = _resolve_property_id(decision, session, text)
    if pid is None:
        pid, _, promotion_error = _promote_selected_listing(text, session)
        if promotion_error:
            return promotion_error
        if pid is None:
            pid, _, _ = _promote_unsaved_address_from_text(text, session)
    if pid is None:
        return "Which property? Give me a saved property id to estimate rent on."
    overrides = parse_overrides(text)
    horizon_years = _future_rent_horizon_years(text)
    try:
        rent = get_rent_estimate(pid, overrides=overrides)
        summary = get_property_summary(pid)
        rent_outlook = get_rent_outlook(
            pid,
            years=horizon_years,
            overrides=overrides,
            owner_occupy_then_rent=_mentions_owner_occupy_then_rent(text),
            rent_payload=rent,
            property_summary=summary,
        )
    except ToolUnavailable as exc:
        return f"I couldn't estimate rent ({exc})."
    session.current_property_id = pid
    _set_workflow_state(session, contract_type="rent_outlook", analysis_mode="rent_lookup")

    money = lambda v: f"${v:,.0f}" if isinstance(v, (int, float)) else "n/a"
    monthly = rent.get("monthly_rent")
    effective = rent.get("effective_monthly_rent")
    source = rent.get("rent_source_type") or "estimated"
    label = rent.get("rental_ease_label")
    ease = rent.get("rental_ease_score")
    noi = rent.get("annual_noi")
    session.last_rent_outlook_view = {
        "address": summary.get("address"),
        "town": summary.get("town"),
        "state": summary.get("state"),
        "monthly_rent": monthly,
        "effective_monthly_rent": effective,
        "rent_source_type": source,
        "rental_ease_label": label,
        "rental_ease_score": ease,
        "annual_noi": noi,
        "horizon_years": horizon_years,
        "future_rent_low": rent_outlook.future_rent_low,
        "future_rent_mid": rent_outlook.future_rent_mid,
        "future_rent_high": rent_outlook.future_rent_high,
        "zillow_market_rent": rent_outlook.zillow_market_rent,
        "zillow_rental_comp_count": rent_outlook.zillow_rental_comp_count,
        "basis_to_rent_framing": rent_outlook.basis_to_rent_framing,
        "owner_occupy_then_rent": rent_outlook.owner_occupy_then_rent,
    }
    lines = [
        f"Estimated monthly rent: {money(monthly)} (source: {source}).",
        f"Effective rent after vacancy/management: {money(effective)}.",
    ]
    if label or isinstance(ease, (int, float)):
        ease_s = f"{ease:.0f}/100" if isinstance(ease, (int, float)) else "n/a"
        lines.append(f"Rental profile: {label or 'n/a'} (ease {ease_s}).")
    if isinstance(noi, (int, float)):
        lines.append(f"Annual NOI: {money(noi)}.")
    if horizon_years:
        if isinstance(rent_outlook.future_rent_low, (int, float)):
            lines.append(
                f"Working {horizon_years}-year rent range: {money(rent_outlook.future_rent_low)} to {money(rent_outlook.future_rent_high)}/mo, "
                f"with a midpoint near {money(rent_outlook.future_rent_mid)}/mo if rent grows about 3% annually."
            )
        lines.extend(rent_outlook.confidence_notes[:1])
    if rent_outlook.basis_to_rent_framing:
        lines.append(rent_outlook.basis_to_rent_framing)
    if rent_outlook.owner_occupy_then_rent:
        lines.append(rent_outlook.owner_occupy_then_rent)
    if isinstance(rent_outlook.zillow_market_rent, (int, float)):
        lines.append(
            f"SearchAPI Zillow rental read: nearby rentals point to about {money(rent_outlook.zillow_market_rent)}/mo"
            + (
                f" across {rent_outlook.zillow_rental_comp_count} live rental listing(s)."
                if rent_outlook.zillow_rental_comp_count
                else "."
            )
        )
    if _mentions_owner_occupy_then_rent(text):
        try:
            fit = get_strategy_fit(pid, overrides=overrides)
        except ToolUnavailable:
            fit = {}
        best_path = fit.get("best_path")
        recommendation = fit.get("recommendation")
        if best_path:
            lines.append(f"Likely path: {best_path}")
        elif recommendation:
            lines.append(f"Likely path: {recommendation}")
    chart_line = ""
    if horizon_years is not None or "chart" in text.lower() or "burn" in text.lower():
        try:
            from briarwood.agent.rendering import ChartUnavailable, render_chart as _render

            path = _render("rent_burn", rent_outlook.burn_chart_payload, session_id=session.session_id or "default")
            chart_line = f"\nChart: file://{path.resolve()}"
        except (ChartUnavailable, ToolUnavailable) as exc:
            chart_line = f"\n(chart unavailable: {exc})"
    fallback = lambda: " ".join(lines)
    system = load_prompt("rent_lookup")
    user = (
        f"User question: {text}\n"
        f"monthly_rent: {monthly}\n"
        f"effective_monthly_rent: {effective}\n"
        f"rent_source_type: {source}\n"
        f"rental_ease_label: {label}\n"
        f"rental_ease_score: {ease}\n"
        f"annual_noi: {noi}\n"
        f"horizon_years: {horizon_years}\n"
        f"rendered_fallback: {' '.join(lines)}"
    )
    rent_payload = asdict(rent_outlook)
    narrative, report = compose_contract_response(
        llm=llm,
        contract_type="rent_outlook",
        payload=rent_payload,
        system=system,
        fallback=fallback,
        max_tokens=220,
        structured_inputs=rent_payload,
        tier="rent_lookup",
    )
    session.last_verifier_report = report
    return narrative + chart_line if chart_line and not narrative.endswith(chart_line) else narrative


# ---------- PROJECTION ----------


def handle_projection(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    pid = _resolve_property_id(decision, session, text)
    if pid is None:
        pid, _, promotion_error = _promote_selected_listing(text, session)
        if promotion_error:
            return promotion_error
        if pid is None:
            pid, _, _ = _promote_unsaved_address_from_text(text, session)
    if pid is None:
        return "Which property should I project forward?"
    overrides = parse_overrides(text)
    if _is_renovation_resale_question(text):
        try:
            outlook = get_renovation_resale_outlook(pid, overrides=overrides)
        except ToolUnavailable as exc:
            return f"I couldn't build a renovation resale outlook ({exc})."
        session.current_property_id = pid
        _set_workflow_state(session, contract_type="renovation_resale", analysis_mode="projection")
        return _format_renovation_resale_outlook(outlook)
    try:
        proj = get_projection(pid, overrides=overrides)
    except ToolUnavailable as exc:
        return f"I couldn't build a projection ({exc})."
    session.current_property_id = pid
    _set_workflow_state(session, contract_type="projection", analysis_mode="projection")
    facts = _load_property_facts(pid)
    session.last_projection_view = {
        **proj,
        "address": facts.get("address"),
        "town": facts.get("town"),
        "state": facts.get("state"),
    }

    from briarwood.agent.rendering import ChartUnavailable, render_chart as _render

    ask = proj.get("ask_price")
    bull = proj.get("bull_case_value")
    base = proj.get("base_case_value")
    bear = proj.get("bear_case_value")
    stress = proj.get("stress_case_value")

    money = lambda v: f"${v:,.0f}" if isinstance(v, (int, float)) else "n/a"
    def _delta(v):
        if isinstance(v, (int, float)) and isinstance(ask, (int, float)) and ask:
            return f"{(v - ask) / ask:+.1%}"
        return "n/a"

    chart_line = ""
    try:
        path = _render("scenario_fan", proj, session_id=session.session_id or "default")
        chart_line = f"\nChart: file://{path.resolve()}"
    except ChartUnavailable as exc:
        chart_line = f"\n(chart unavailable: {exc})"

    if llm is None:
        lines = [
            f"5-year projection vs ask {money(ask)}:",
            f"- Bull {money(bull)} ({_delta(bull)})",
            f"- Base {money(base)} ({_delta(base)})",
            f"- Bear {money(bear)} ({_delta(bear)})",
        ]
        if isinstance(stress, (int, float)):
            lines.append(f"- Stress {money(stress)} ({_delta(stress)}) — historical peak-to-trough overlay")
        spread = proj.get("spread")
        if isinstance(spread, (int, float)):
            lines.append(f"Spread (bull-bear): {money(spread)}.")
        return "\n".join(lines) + chart_line

    system = load_prompt("projection")
    user = (
        f"User question: {text}\n\n"
        f"overrides_applied: {overrides or 'none'}\n"
        f"ask_price: {ask}\n"
        f"bull_case_value: {bull} ({_delta(bull)})\n"
        f"base_case_value: {base} ({_delta(base)})\n"
        f"bear_case_value: {bear} ({_delta(bear)})\n"
        f"stress_case_value: {stress}\n"
        f"base_growth_rate: {proj.get('base_growth_rate')}\n"
        f"bull_growth_rate: {proj.get('bull_growth_rate')}\n"
        f"bear_growth_rate: {proj.get('bear_growth_rate')}\n"
    )
    fallback = lambda: f"Base {money(base)} ({_delta(base)})."
    projection_inputs = {
        "overrides_applied": overrides or {},
        "ask_price": ask,
        "bull_case_value": bull,
        "base_case_value": base,
        "bear_case_value": bear,
        "stress_case_value": stress,
        "base_growth_rate": proj.get("base_growth_rate"),
        "bull_growth_rate": proj.get("bull_growth_rate"),
        "bear_growth_rate": proj.get("bear_growth_rate"),
    }
    narrative, report = compose_structured_response(
        llm=llm,
        system=system,
        user=user,
        fallback=fallback,
        max_tokens=300,
        structured_inputs=projection_inputs,
        tier="projection",
    )
    session.last_verifier_report = report
    return narrative + chart_line if chart_line and not narrative.endswith(chart_line) else narrative


_RESEARCH_FOCUS_KEYWORDS: tuple[tuple[str, list[str]], ...] = (
    ("up and coming", ["development", "demand", "migration"]),
    ("improvement", ["development", "pricing", "permits"]),
    ("market", ["pricing", "supply", "demand"]),
    ("zoning", ["zoning"]),
    ("permit", ["permits", "development"]),
)

_TOWN_STATE_RE = re.compile(
    r"\b([A-Za-z][A-Za-z .'-]+?)(?:,\s*|\s+)([A-Za-z]{2})(?=\b|[?.,!])",
    re.IGNORECASE,
)

_RENOVATION_RESALE_RE = re.compile(
    r"\b("
    r"renovat(?:e|ed|ion)"
    r"|what if (?:we|i) invest(?:ed|ing)?\s+\$?\d"
    r"|sell (?:it|this) for"
    r"|turn around and sell"
    r"|\barv\b"
    r"|after repair value"
    r"|resale"
    r"|flip"
    r")\b",
    re.IGNORECASE,
)


def _research_focus(text: str) -> list[str]:
    normalized = text.lower()
    focus: list[str] = []
    for keyword, tags in _RESEARCH_FOCUS_KEYWORDS:
        if keyword in normalized:
            focus.extend(tags)
    if not focus:
        focus.extend(["development", "pricing"])
    # Preserve order while de-duping.
    return list(dict.fromkeys(focus))


def _extract_research_place(text: str) -> tuple[str | None, str | None]:
    match = _TOWN_STATE_RE.search(text)
    if not match:
        return None, None
    town = match.group(1).strip(" ,.?")
    state = match.group(2).strip().upper()
    if state not in _US_STATE_CODES:
        return None, None
    for prefix in ("is ", "how is ", "what about ", "tell me about ", "research ", "check "):
        if town.lower().startswith(prefix):
            town = town[len(prefix):].strip(" ,.?")
            break
    if not town:
        return None, None
    return town.title(), state


def _is_renovation_resale_question(text: str) -> bool:
    return bool(_RENOVATION_RESALE_RE.search(text))


def _mentions_owner_occupy_then_rent(text: str) -> bool:
    normalized = text.lower()
    return (
        ("live there" in normalized or "live here" in normalized or "owner occupy" in normalized)
        and "rent" in normalized
    )


def _future_rent_horizon_years(text: str) -> int | None:
    normalized = text.lower()
    if "rent" not in normalized:
        return None
    match = re.search(r"\bin\s+(\d+)\s+years?\b", normalized)
    if match:
        return int(match.group(1))
    if "couple years" in normalized or "a couple years" in normalized:
        return 2
    if "few years" in normalized or "a few years" in normalized:
        return 3
    return None


def _extract_target_cap_rate(text: str) -> float | None:
    match = _CAP_RATE_RE.search(text)
    if not match:
        return None
    try:
        raw = float(match.group(1))
    except ValueError:
        return None
    return raw / 100.0 if raw > 1 else raw


def _format_renovation_resale_outlook(outlook: RenovationResaleOutlook) -> str:
    money = lambda v: f"${v:,.0f}" if isinstance(v, (int, float)) else "n/a"

    def _pct(value: object) -> str:
        return f"{value:+.1f}%" if isinstance(value, (int, float)) else "n/a"

    address = outlook.address or outlook.property_id
    lines = [
        (
            f"{address} renovation resale read: buy around {money(outlook.entry_basis)} and "
            f"all-in basis lands around {money(outlook.all_in_basis)}."
        ),
        (
            f"Expected resale anchor: {money(outlook.renovated_bcv)} "
            f"vs current value anchor {money(outlook.current_bcv)}."
        ),
    ]
    if isinstance(outlook.renovated_bcv, (int, float)) and isinstance(outlook.all_in_basis, (int, float)):
        spread = outlook.renovated_bcv - outlook.all_in_basis
        lines.append(
            f"Rough spread after renovation before selling friction: {money(spread)}."
        )
    if isinstance(outlook.renovation_budget, (int, float)) or isinstance(outlook.roi_pct, (int, float)):
        lines.append(
            f"Renovation budget: {money(outlook.renovation_budget)}; modeled ROI on the value-add path: {_pct(outlook.roi_pct)}."
        )
    if isinstance(outlook.total_hold_cost, (int, float)) or isinstance(outlook.budget_overrun_margin_pct, (int, float)):
        lines.append(
            f"What has to go right: hold/selling drag stays near {money(outlook.total_hold_cost)} and budget cushion remains {_pct(outlook.budget_overrun_margin_pct)} before breakeven."
        )
    scenario = next(
        (
            item
            for item in outlook.margin_scenarios
            if str(item.get("label", "")).lower() in {"budget +20%, value -10%", "value -10%", "budget +20%"}
        ),
        None,
    )
    if scenario:
        lines.append(
            "Stress check: "
            f"{scenario.get('label')} leaves net profit around {money(scenario.get('net_profit'))}."
        )
    elif outlook.key_risks:
        lines.append("Stress check: " + "; ".join(outlook.key_risks[:2]) + ".")
    if outlook.trust_flags:
        lines.append("Confidence drag: " + ", ".join(outlook.trust_flags[:3]) + ".")
    elif outlook.recommendation:
        lines.append("Briarwood read: " + outlook.recommendation)
    return "\n".join(lines)


# ---------- MICRO_LOCATION ----------


def handle_micro_location(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    pid = _resolve_property_id(decision, session, text)
    if pid is None:
        pid, _, promotion_error = _promote_selected_listing(text, session)
        if promotion_error:
            return promotion_error
        if pid is None:
            pid, _, _ = _promote_unsaved_address_from_text(text, session)
    if pid is None:
        live_listing = _select_live_listing_from_session(text, session)
        if live_listing:
            session.current_live_listing = live_listing
            address = str(live_listing.get("address") or "this live listing")
            return (
                f"I don't have cached micro-location metrics for {address} yet. "
                "If you want beach distance or walkability on a live Zillow result, I need that listing promoted into intake first."
            )
        return "Which property? Give me a saved property id."
    from briarwood.agent.index import load_index

    index = load_index()
    entry = next((p for p in index.properties if p.property_id == pid), None)
    if entry is None:
        return f"I don't have a micro-location row for {pid} yet — rebuild the index."
    session.current_property_id = pid

    def _fmt_dist(blocks, miles, label):
        if isinstance(blocks, (int, float)):
            return f"{blocks:.1f} blocks to {label} ({miles:.2f} mi)" if isinstance(miles, (int, float)) else f"{blocks:.1f} blocks to {label}"
        if isinstance(miles, (int, float)):
            return f"{miles:.2f} mi to {label}"
        return None

    t = text.lower()
    parts: list[str] = []
    if "beach" in t or "ocean" in t:
        p = _fmt_dist(entry.blocks_to_beach, entry.distance_to_beach_miles, "beach")
        if p: parts.append(p)
    if "train" in t or "station" in t or "commute" in t:
        p = _fmt_dist(None, getattr(entry, "distance_to_train_miles", None), "train")
        if p: parts.append(p)
    if "downtown" in t or "shop" in t or "walk" in t:
        p = _fmt_dist(None, entry.distance_to_downtown_miles, "downtown")
        if p: parts.append(p)
    if not parts:
        for p in (
            _fmt_dist(entry.blocks_to_beach, entry.distance_to_beach_miles, "beach"),
            _fmt_dist(None, entry.distance_to_downtown_miles, "downtown"),
            _fmt_dist(None, getattr(entry, "distance_to_train_miles", None), "train"),
        ):
            if p: parts.append(p)
    if not parts:
        return f"No micro-location data cached for {pid}."
    return f"{pid}: " + "; ".join(parts) + "."


# ---------- RISK ----------


def handle_risk(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    pid = _resolve_property_id(decision, session, text)
    if pid is None:
        pid, _, promotion_error = _promote_selected_listing(text, session)
        if promotion_error:
            return promotion_error
        if pid is None:
            pid, _, _ = _promote_unsaved_address_from_text(text, session)
    if pid is None:
        return "Which property? Give me a saved property id."
    overrides = parse_overrides(text)
    try:
        profile = get_risk_profile(pid, overrides=overrides)
    except ToolUnavailable as exc:
        return f"I couldn't pull a risk profile ({exc})."
    session.current_property_id = pid

    from briarwood.agent.rendering import ChartUnavailable, render_chart as _render

    ask = profile.get("ask_price")
    bear = profile.get("bear_case_value")
    stress = profile.get("stress_case_value")
    risk_flags = profile.get("risk_flags") or []
    trust_flags = profile.get("trust_flags") or []

    facts = _load_property_facts(pid)
    total_penalty = profile.get("total_penalty")
    if isinstance(total_penalty, (int, float)):
        tier = "thin" if total_penalty >= 0.5 else "moderate" if total_penalty >= 0.25 else "strong"
    else:
        tier = None
    session.last_risk_view = {
        "address": facts.get("address"),
        "town": facts.get("town"),
        "state": facts.get("state"),
        "ask_price": ask,
        "bear_value": bear,
        "stress_value": stress,
        "risk_flags": list(risk_flags),
        "trust_flags": list(trust_flags),
        "key_risks": list(profile.get("key_risks") or []),
        "total_penalty": total_penalty,
        "confidence_tier": tier,
    }

    chart_line = ""
    try:
        path = _render("risk_bar", profile, session_id=session.session_id or "default")
        chart_line = f"\nChart: file://{path.resolve()}"
    except ChartUnavailable as exc:
        chart_line = f"\n(chart unavailable: {exc})"

    money = lambda v: f"${v:,.0f}" if isinstance(v, (int, float)) else "n/a"

    if llm is None:
        lines = [f"Risk read for {pid}:"]
        if risk_flags:
            lines.append(f"- Drivers: {', '.join(risk_flags)}")
        if trust_flags:
            lines.append(f"- Trust flags: {', '.join(trust_flags)}")
        if isinstance(bear, (int, float)) and isinstance(ask, (int, float)):
            lines.append(f"- Bear case {money(bear)} vs ask {money(ask)}.")
        if isinstance(stress, (int, float)):
            lines.append(f"- Stress (historical peak-to-trough overlay): {money(stress)}.")
        if len(lines) == 1:
            lines.append("- No material risk drivers cached.")
        return "\n".join(lines) + chart_line

    system = load_prompt("risk")
    risk_inputs = {
        "risk_flags": list(risk_flags),
        "trust_flags": list(trust_flags),
        "ask_price": ask,
        "bear_case_value": bear,
        "stress_case_value": stress,
        "total_penalty": profile.get("total_penalty"),
        "key_risks": list(profile.get("key_risks") or []),
    }
    user = (
        f"User question: {text}\n\n"
        f"risk_flags: {risk_flags}\n"
        f"trust_flags: {trust_flags}\n"
        f"ask_price: {ask}\n"
        f"bear_case_value: {bear}\n"
        f"stress_case_value: {stress}\n"
        f"total_penalty: {profile.get('total_penalty')}\n"
        f"key_risks: {profile.get('key_risks')}\n"
    )
    narrative, report = complete_and_verify(
        llm=llm,
        system=system,
        user=user,
        structured_inputs=risk_inputs,
        tier="risk",
        max_tokens=300,
    )
    session.last_verifier_report = report
    return (narrative or "No material risk drivers surfaced.") + chart_line


# ---------- EDGE ----------


def handle_edge(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    pid = _resolve_property_id(decision, session, text)
    if pid is None:
        pid, _, promotion_error = _promote_selected_listing(text, session)
        if promotion_error:
            return promotion_error
        if pid is None:
            pid, _, _ = _promote_unsaved_address_from_text(text, session)
    if pid is None:
        return "Which property? Give me a saved property id."
    overrides = parse_overrides(text)
    cma_mode = bool(_CMA_RE.search(text))
    try:
        thesis = get_value_thesis(pid, overrides=overrides)
        cma_result = get_cma(pid, overrides=overrides) if cma_mode else None
    except ToolUnavailable as exc:
        return f"I couldn't build a value thesis ({exc})."
    session.current_property_id = pid
    _set_workflow_state(
        session,
        contract_type="cma" if cma_mode else "value_thesis",
        analysis_mode="edge",
    )

    from briarwood.agent.rendering import ChartUnavailable, render_chart as _render

    chart_line = ""
    try:
        unified = analyze_property(pid, overrides=overrides)
        path = _render("value_opportunity", unified, session_id=session.session_id or "default")
        chart_line = f"\nChart: file://{path.resolve()}"
    except (ChartUnavailable, ToolUnavailable) as exc:
        chart_line = f"\n(chart unavailable: {exc})"

    money = lambda v: f"${v:,.0f}" if isinstance(v, (int, float)) else "n/a"
    ask = thesis.get("ask_price")
    fair = thesis.get("fair_value_base")
    prem = thesis.get("premium_discount_pct")
    comps = [
        {
            "property_id": comp.property_id,
            "address": comp.address,
            "beds": comp.beds,
            "baths": comp.baths,
            "ask_price": comp.ask_price,
            "blocks_to_beach": comp.blocks_to_beach,
        }
        for comp in (cma_result.comps if cma_result else [])
    ]

    edge_facts = _load_property_facts(pid)
    session.last_value_thesis_view = {
        "address": edge_facts.get("address"),
        "town": edge_facts.get("town"),
        "state": edge_facts.get("state"),
        "ask_price": ask,
        "fair_value_base": fair,
        "premium_discount_pct": prem,
        "pricing_view": thesis.get("pricing_view"),
        "primary_value_source": thesis.get("primary_value_source"),
        "net_opportunity_delta_pct": thesis.get("net_opportunity_delta_pct"),
        "value_drivers": list(thesis.get("value_drivers") or []),
        "key_value_drivers": list(thesis.get("key_value_drivers") or []),
        "what_must_be_true": list(thesis.get("what_must_be_true") or []),
        "comp_selection_summary": cma_result.comp_selection_summary if cma_result else None,
        "comps": list(comps),
    }

    if llm is None:
        lines = [f"{'CMA' if cma_mode else 'Value thesis'} for {pid}:"]
        lines.append(f"- Ask {money(ask)} vs fair {money(fair)} " +
                     (f"({prem:+.1%})." if isinstance(prem, (int, float)) else "."))
        if thesis.get("pricing_view"):
            lines.append(f"- Pricing view: {thesis['pricing_view']}.")
        if thesis.get("value_drivers"):
            lines.append(f"- Anchors: {thesis['value_drivers']}")
        if thesis.get("key_value_drivers"):
            lines.append(f"- Drivers: {'; '.join(thesis['key_value_drivers'])}")
        if thesis.get("what_must_be_true"):
            lines.append(f"- What must be true: {'; '.join(thesis['what_must_be_true'])}")
        if cma_result and cma_result.comp_selection_summary:
            lines.append(f"- Comp selection: {cma_result.comp_selection_summary}")
        lines.extend(_format_cma_comp_lines(comps))
        return "\n".join(lines) + chart_line

    system = load_prompt("edge")
    edge_inputs = {
        "ask_price": ask,
        "fair_value_base": fair,
        "premium_discount_pct": prem,
        "pricing_view": thesis.get("pricing_view"),
        "value_drivers": list(thesis.get("value_drivers") or []),
        "primary_value_source": thesis.get("primary_value_source"),
        "net_opportunity_delta_pct": thesis.get("net_opportunity_delta_pct"),
        "key_value_drivers": list(thesis.get("key_value_drivers") or []),
        "what_must_be_true": list(thesis.get("what_must_be_true") or []),
        "comp_selection_summary": cma_result.comp_selection_summary if cma_result else None,
        "comps": list(comps),
    }
    user = (
        f"User question: {text}\n\n"
        f"ask_price: {ask}\n"
        f"fair_value_base: {fair}\n"
        f"premium_discount_pct: {prem}\n"
        f"pricing_view: {thesis.get('pricing_view')}\n"
        f"value_drivers: {thesis.get('value_drivers')}\n"
        f"primary_value_source: {thesis.get('primary_value_source')}\n"
        f"net_opportunity_delta_pct: {thesis.get('net_opportunity_delta_pct')}\n"
        f"key_value_drivers: {thesis.get('key_value_drivers')}\n"
        f"what_must_be_true: {thesis.get('what_must_be_true')}\n"
        f"comp_selection_summary: {cma_result.comp_selection_summary if cma_result else 'none'}\n"
        f"comp_lines: {_format_cma_comp_lines(comps) if comps else 'none'}\n"
    )
    narrative, report = complete_and_verify(
        llm=llm,
        system=system,
        user=user,
        structured_inputs=edge_inputs,
        tier="edge",
        max_tokens=300,
    )
    session.last_verifier_report = report
    fallback = f"Ask {money(ask)} vs fair {money(fair)}."
    if comps:
        fallback += "\n" + "\n".join(_format_cma_comp_lines(comps))
    return (narrative or fallback) + chart_line


# ---------- STRATEGY ----------


def handle_strategy(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    pid = _resolve_property_id(decision, session, text)
    if pid is None:
        pid, _, promotion_error = _promote_selected_listing(text, session)
        if promotion_error:
            return promotion_error
        if pid is None:
            pid, _, _ = _promote_unsaved_address_from_text(text, session)
    if pid is None:
        return "Which property? Give me a saved property id."
    overrides = parse_overrides(text)
    try:
        fit = get_strategy_fit(pid, overrides=overrides)
    except ToolUnavailable as exc:
        return f"I couldn't score strategy fit ({exc})."
    session.current_property_id = pid

    strategy_facts = _load_property_facts(pid)
    session.last_strategy_view = {
        "address": strategy_facts.get("address"),
        "town": strategy_facts.get("town"),
        "state": strategy_facts.get("state"),
        "best_path": fit.get("best_path"),
        "recommendation": fit.get("recommendation"),
        "pricing_view": fit.get("pricing_view"),
        "primary_value_source": fit.get("primary_value_source"),
        "rental_ease_label": fit.get("rental_ease_label"),
        "rental_ease_score": fit.get("rental_ease_score"),
        "rent_support_score": fit.get("rent_support_score"),
        "liquidity_score": fit.get("liquidity_score"),
        "monthly_cash_flow": fit.get("monthly_cash_flow"),
        "cash_on_cash_return": fit.get("cash_on_cash_return"),
        "annual_noi": fit.get("annual_noi"),
    }

    money = lambda v: f"${v:,.0f}" if isinstance(v, (int, float)) else "n/a"

    if llm is None:
        lines = [f"Best play for {pid}:"]
        if fit.get("best_path"):
            lines.append(f"- Path: {fit['best_path']}")
        if fit.get("rental_ease_label"):
            lines.append(
                f"- Rental: {fit['rental_ease_label']} (ease {fit.get('rental_ease_score')}, "
                f"cash flow {money(fit.get('monthly_cash_flow'))}/mo, "
                f"CoC {fit.get('cash_on_cash_return')})"
            )
        if fit.get("pricing_view"):
            lines.append(f"- Valuation: {fit['pricing_view']}.")
        if fit.get("recommendation"):
            lines.append(f"- Overall: {fit['recommendation']}")
        return "\n".join(lines)

    system = load_prompt("strategy")
    strategy_inputs = {
        "best_path": fit.get("best_path"),
        "recommendation": fit.get("recommendation"),
        "pricing_view": fit.get("pricing_view"),
        "rental_ease_label": fit.get("rental_ease_label"),
        "rental_ease_score": fit.get("rental_ease_score"),
        "rent_support_score": fit.get("rent_support_score"),
        "liquidity_score": fit.get("liquidity_score"),
        "monthly_cash_flow": fit.get("monthly_cash_flow"),
        "cash_on_cash_return": fit.get("cash_on_cash_return"),
        "annual_noi": fit.get("annual_noi"),
        "primary_value_source": fit.get("primary_value_source"),
    }
    user = (
        f"User question: {text}\n\n"
        f"best_path: {fit.get('best_path')}\n"
        f"recommendation: {fit.get('recommendation')}\n"
        f"pricing_view: {fit.get('pricing_view')}\n"
        f"rental_ease_label: {fit.get('rental_ease_label')}\n"
        f"rental_ease_score: {fit.get('rental_ease_score')}\n"
        f"rent_support_score: {fit.get('rent_support_score')}\n"
        f"liquidity_score: {fit.get('liquidity_score')}\n"
        f"monthly_cash_flow: {fit.get('monthly_cash_flow')}\n"
        f"cash_on_cash_return: {fit.get('cash_on_cash_return')}\n"
        f"annual_noi: {fit.get('annual_noi')}\n"
        f"primary_value_source: {fit.get('primary_value_source')}\n"
    )
    narrative, report = complete_and_verify(
        llm=llm,
        system=system,
        user=user,
        structured_inputs=strategy_inputs,
        tier="strategy",
        max_tokens=300,
    )
    session.last_verifier_report = report
    return narrative or (fit.get("best_path") or "No strategy fit cached.")


# ---------- BROWSE ----------


def handle_browse(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    """Underwrite-lite first purchase read on a property."""
    match = _resolve_property_match(decision, session, text)
    pid = match.property_id
    promotion: PromotedPropertyRecord | None = None
    if pid is None:
        pid, promotion, promotion_error = _promote_selected_listing(text, session)
        if promotion_error:
            return promotion_error
        if pid is not None:
            session.current_property_id = pid
            session.promoted_property_id = pid
        else:
            pid, promotion, _ = _promote_unsaved_address_from_text(text, session)
            if pid is not None:
                session.current_property_id = pid
                session.promoted_property_id = pid
            else:
                live_listing = _select_live_listing_from_session(text, session)
                if live_listing is not None:
                    _remember_selected_listing(session, live_listing)
                    session.current_property_id = None
                    return _format_live_listing_brief(live_listing)
                return _browse_missing_property_message(match)
    overrides = parse_overrides(text)
    try:
        brief = get_property_brief(pid, overrides=overrides)
    except ToolUnavailable as exc:
        return f"I couldn't build a property brief ({exc})."
    session.current_property_id = pid
    presentation_payload: dict[str, object] | None = None
    enrichment: dict[str, object] | None = None
    if promotion and promotion.property_id == pid:
        try:
            enrichment = get_property_enrichment(
                pid,
                include_town_research=False,
                save_artifact=True,
            )
        except Exception as exc:
            logger.warning("browse enrichment failed for %s: %s", pid, exc)
            enrichment = None
    try:
        presentation_payload = get_property_presentation(
            pid,
            include_town_research=False,
            include_risk=False,
            brief=brief,
            enrichment=enrichment,
            contract_type="property_brief",
            analysis_mode="browse",
        )
    except Exception as exc:
        logger.warning("browse presentation failed for %s: %s", pid, exc)
        presentation_payload = None

    filters: dict = {}
    if brief.town:
        filters["town"] = brief.town
    if brief.state:
        filters["state"] = brief.state
    if isinstance(brief.beds, int):
        filters["beds_min"] = max(1, brief.beds - 1)
        filters["beds_max"] = brief.beds + 1
    if isinstance(brief.ask_price, (int, float)) and brief.ask_price > 0:
        filters["min_price"] = brief.ask_price * 0.75
        filters["max_price"] = brief.ask_price * 1.25

    try:
        neighbors = search_listings(filters) if filters else []
    except Exception:
        neighbors = []
    neighbors = [n for n in neighbors if n.get("property_id") != pid][:5]
    _set_workflow_state(session, contract_type="property_brief", analysis_mode="browse")
    response = _format_browse_from_presentation(
        presentation_payload,
        brief,
        neighbors,
    ) or _format_browse_brief(brief, neighbors)
    if promotion and promotion.property_id == pid:
        intro = (
            f"Briarwood {'saved' if promotion.created_new else 'reused'} {brief.address or pid} "
            f"as {pid} from live Zillow discovery."
        )
        response = "\n".join([intro, *_promotion_intake_lines(promotion), *_promotion_enrichment_lines(enrichment), response])
    return response


# ---------- CHITCHAT ----------


def handle_chitchat(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    return "Hi. Ask me about a saved property (e.g. '526-west-end-ave') — lookup, decision, or search."


DISPATCH_TABLE = {
    AnswerType.LOOKUP: handle_lookup,
    AnswerType.DECISION: handle_decision,
    AnswerType.COMPARISON: handle_comparison,
    AnswerType.SEARCH: handle_search,
    AnswerType.RESEARCH: handle_research,
    AnswerType.VISUALIZE: handle_visualize,
    AnswerType.RENT_LOOKUP: handle_rent_lookup,
    AnswerType.PROJECTION: handle_projection,
    AnswerType.MICRO_LOCATION: handle_micro_location,
    AnswerType.RISK: handle_risk,
    AnswerType.EDGE: handle_edge,
    AnswerType.STRATEGY: handle_strategy,
    AnswerType.BROWSE: handle_browse,
    AnswerType.CHITCHAT: handle_chitchat,
}


_OVERRIDE_AWARE_TYPES = {
    AnswerType.DECISION,
    AnswerType.PROJECTION,
    AnswerType.RISK,
    AnswerType.EDGE,
    AnswerType.STRATEGY,
}


_AFFIRMATIVE_FIRST_WORDS = frozenset(
    {"yes", "yeah", "yep", "yup", "ok", "okay", "sure", "proceed", "underwrite"}
)
_BROWSE_DEEPEN_PHRASES = frozenset(
    {"and", "and?", "go on", "tell me more", "more", "keep going"}
)
_TERM_EXPLAINERS: dict[str, str] = {
    "absorption": (
        "Absorption data is a market-speed read: it measures how quickly available homes or rentals are getting taken out of inventory "
        "relative to new supply. For a buy decision in Belmar, strong absorption means demand is clearing listings quickly and can support "
        "pricing; weak absorption means homes are sitting longer, so town-level price support is less trustworthy."
    ),
    "scarcity": (
        "Scarcity is Briarwood's read on how constrained the local supply is. In practice, it asks whether there are enough comparable homes "
        "coming to market to give buyers alternatives, or whether limited inventory is helping protect values and liquidity."
    ),
}
_TERM_EXPLAIN_RE = re.compile(r"\bwhat (?:is|does)\b", re.IGNORECASE)
_TOWN_RESEARCH_RE = re.compile(
    r"^(how is|how's|what is|what's|tell me about|is)\s+([a-z][a-z .'-]+?)(?:\s+up and coming)?\??$",
    re.IGNORECASE,
)


def _is_browse_affirmative(text: str) -> bool:
    t = text.strip().lower()
    if not t or "?" in t or len(t) > 60:
        return False
    first = re.split(r"[\s,.!]+", t, maxsplit=1)[0]
    return first in _AFFIRMATIVE_FIRST_WORDS


def _escalate_browse_affirmative(
    text: str, decision: RouterDecision, session: Session
) -> RouterDecision:
    """'yes/ok' after a BROWSE turn promotes to DECISION on the pinned property.

    Why: handle_browse ends with 'Want a full underwrite?' but nothing caught
    the affirmative follow-up, so users got the same browse summary on repeat.
    """
    if not session.turns or session.turns[-1].answer_type != AnswerType.BROWSE.value:
        return decision
    if not session.current_property_id and not session.current_live_listing:
        return decision
    if not _is_browse_affirmative(text):
        return decision
    target_refs = [session.current_property_id] if session.current_property_id else []
    return RouterDecision(
        answer_type=AnswerType.DECISION,
        confidence=max(decision.confidence, 0.7),
        target_refs=target_refs,
        reason="browse-followup escalate",
        llm_suggestion=decision.llm_suggestion,
    )


def _deepen_browse_followup(
    text: str, decision: RouterDecision, session: Session
) -> RouterDecision:
    if not session.turns or session.turns[-1].answer_type != AnswerType.BROWSE.value:
        return decision
    if not session.current_property_id and not session.current_live_listing:
        return decision
    normalized = text.strip().lower()
    if normalized not in _BROWSE_DEEPEN_PHRASES:
        return decision
    target_refs = [session.current_property_id] if session.current_property_id else []
    return RouterDecision(
        answer_type=AnswerType.DECISION,
        confidence=max(decision.confidence, 0.65),
        target_refs=target_refs,
        reason="browse-followup deepen",
        llm_suggestion=decision.llm_suggestion,
    )


def _contextualize_followup_turn(
    text: str, decision: RouterDecision, session: Session
) -> RouterDecision:
    """Rewrite low-context browse repeats into the follow-up mode the user actually meant."""
    if (
        decision.answer_type in {AnswerType.SEARCH, AnswerType.BROWSE, AnswerType.LOOKUP}
        and session.current_property_id
        and _CMA_RE.search(text)
    ):
        return RouterDecision(
            answer_type=AnswerType.EDGE,
            confidence=max(decision.confidence, 0.74),
            target_refs=[session.current_property_id],
            reason="cma rewrite",
            llm_suggestion=decision.llm_suggestion,
        )
    if (
        decision.answer_type in {AnswerType.BROWSE, AnswerType.DECISION}
        and session.current_property_id
        and _mentions_owner_occupy_then_rent(text)
    ):
        return RouterDecision(
            answer_type=AnswerType.STRATEGY,
            confidence=max(decision.confidence, 0.72),
            target_refs=[session.current_property_id],
            reason="owner-occupy then rent rewrite",
            llm_suggestion=decision.llm_suggestion,
        )
    if (
        decision.answer_type in {AnswerType.BROWSE, AnswerType.DECISION, AnswerType.PROJECTION}
        and session.current_property_id
        and _future_rent_horizon_years(text) is not None
    ):
        return RouterDecision(
            answer_type=AnswerType.RENT_LOOKUP,
            confidence=max(decision.confidence, 0.72),
            target_refs=[session.current_property_id],
            reason="future rent rewrite",
            llm_suggestion=decision.llm_suggestion,
        )
    if (
        decision.answer_type is AnswerType.BROWSE
        and (session.current_search_context or session.search_context)
        and (session.current_search_context or session.search_context or {}).get("state") is None
    ):
        town, state = _extract_place_reply(text)
        if town and state:
            return RouterDecision(
                answer_type=AnswerType.SEARCH,
                confidence=max(decision.confidence, 0.72),
                target_refs=[],
                reason="search-followup place completion",
                llm_suggestion=decision.llm_suggestion,
            )
    if not session.turns or decision.answer_type is not AnswerType.BROWSE:
        return decision
    town, state = _session_town_state(session)
    if not session.current_property_id and not session.current_live_listing:
        return decision
    normalized = text.strip().lower()

    if _TERM_EXPLAIN_RE.search(normalized):
        for term in _TERM_EXPLAINERS:
            target_refs = [session.current_property_id] if session.current_property_id else []
            if term in normalized:
                return RouterDecision(
                    answer_type=AnswerType.BROWSE,
                    confidence=max(decision.confidence, 0.72),
                    target_refs=target_refs,
                    reason="browse-followup explain",
                    llm_suggestion=decision.llm_suggestion,
                )

    town_match = _TOWN_RESEARCH_RE.match(normalized)
    if town_match:
        asked_town = town_match.group(2).strip(" ?")
        if town and asked_town == town.lower():
            target_refs = [session.current_property_id] if session.current_property_id else []
            return RouterDecision(
                answer_type=AnswerType.RESEARCH,
                confidence=max(decision.confidence, 0.72),
                target_refs=target_refs,
                reason="browse-followup town research",
                llm_suggestion=decision.llm_suggestion,
            )

    return decision


def _contextualize_property_specific_analysis(
    text: str, decision: RouterDecision, session: Session
) -> RouterDecision:
    if not _CMA_RE.search(text):
        return decision
    target_refs = [session.current_property_id] if session.current_property_id else []
    if not target_refs:
        match = _resolve_property_match(decision, session, text)
        if match.property_id:
            target_refs = [match.property_id]
    if not target_refs:
        return decision
    return RouterDecision(
        answer_type=AnswerType.EDGE,
        confidence=max(decision.confidence, 0.74),
        target_refs=target_refs,
        reason="cma rewrite",
        llm_suggestion=decision.llm_suggestion,
    )


def _browse_followup_explainer(text: str) -> str | None:
    normalized = text.strip().lower()
    if not _TERM_EXPLAIN_RE.search(normalized):
        return None
    for term, explanation in _TERM_EXPLAINERS.items():
        if term in normalized:
            return explanation
    return None


def contextualize_decision(
    text: str, decision: RouterDecision, session: Session
) -> RouterDecision:
    """Apply session-aware route rewrites before the turn is shown or dispatched."""
    decision = _contextualize_property_specific_analysis(text, decision, session)
    decision = _contextualize_followup_turn(text, decision, session)
    decision = _escalate_browse_affirmative(text, decision, session)
    decision = _deepen_browse_followup(text, decision, session)
    return decision


def dispatch(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    decision = contextualize_decision(text, decision, session)
    explainer = _browse_followup_explainer(text)
    if decision.reason == "browse-followup explain" and explainer:
        response = explainer
        try:
            _log_untracked(
                text=text,
                decision=decision,
                response=response,
                extra={"llm_used": llm is not None},
            )
        except Exception:
            pass
        return response
    handler = DISPATCH_TABLE[decision.answer_type]
    response = handler(text, decision, session, llm)
    # Echo what-if overrides at the top so the user sees the underwrite
    # reflects their scenario, not the canonical listing.
    if decision.answer_type in _OVERRIDE_AWARE_TYPES:
        overrides = parse_overrides(text)
        if overrides:
            response = _override_summary(overrides) + "\n" + response
    try:
        _log_untracked(
            text=text,
            decision=decision,
            response=response,
            extra={"llm_used": llm is not None},
        )
    except Exception:
        pass  # never let telemetry break a turn
    return response
