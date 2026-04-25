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
from briarwood.agent.presentation_advisor import (
    compose_browse_surface,
    compose_section_followup,
)
from briarwood.agent.router import AnswerType, RouterDecision
from briarwood.agent.session import Session
from briarwood.agent.fuzzy_terms import translate
from briarwood.agent.feedback import log_turn as _log_untracked
from briarwood.agent.overrides import parse_overrides, summarize as _override_summary
from briarwood.agent.property_view import PropertyView
from briarwood.local_intelligence.presentation import build_town_signal_items
from briarwood.agent.tools import (
    CMAResult,
    ComparableProperty,
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


def _remember_surface_output(
    session: Session,
    *,
    narrative: str | None = None,
    presentation_payload: dict[str, object] | None = None,
) -> None:
    """Persist the shared turn contract plus the rendered first-read."""
    if presentation_payload is not None:
        session.last_presentation_payload = presentation_payload
    if narrative is not None:
        session.last_surface_narrative = narrative


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


_DECISION_SURFACE_HOOKS: dict[str, str] = {
    "price_position": "Open the value chart next to see how the ask sits against Briarwood's fair-value anchor.",
    "comp_evidence": "Open the comp view next to see which comps are actually supporting the price read.",
    "risk_composition": "Open the risk chart next to see what is actually driving the caution.",
    "scenario_range": "Open the scenario range next to see how much room exists between the base case and the downside.",
    "rent_coverage": "Open the rent view next to see whether rent can realistically cover the monthly carry.",
}


def _clean_sentence(text: str | None) -> str | None:
    if not isinstance(text, str):
        return None
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return None
    return cleaned if cleaned[-1] in ".!?" else f"{cleaned}."


def _humanize_flag(flag: str | None) -> str | None:
    if not isinstance(flag, str):
        return None
    cleaned = " ".join(flag.strip().split("_"))
    return cleaned or None


def _dedupe_lines(lines: list[str], *, limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        cleaned = _clean_sentence(line)
        if cleaned is None:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
        if len(out) >= limit:
            break
    return out


def _price_reason(view: "PropertyView") -> str | None:
    premium = (
        view.basis_premium_pct
        if isinstance(view.basis_premium_pct, (int, float))
        else view.ask_premium_pct
    )
    basis_label = "all-in basis" if view.all_in_basis is not None else "ask"
    if isinstance(premium, (int, float)):
        if premium > 0.01:
            return (
                f"The {basis_label} is running about {abs(premium):.1%} above "
                "Briarwood's fair-value read."
            )
        if premium < -0.01:
            return (
                f"The {basis_label} is landing about {abs(premium):.1%} below "
                "Briarwood's fair-value read."
            )
        return f"The {basis_label} is broadly in line with Briarwood's fair-value read."
    if isinstance(view.fair_value_base, (int, float)) and isinstance(view.ask_price, (int, float)):
        return (
            f"Briarwood's fair value is {_money(view.fair_value_base)} against an ask of "
            f"{_money(view.ask_price)}."
        )
    return None


def _supporting_facts(
    view: "PropertyView",
    *,
    value_thesis_view: dict[str, object] | None,
    strategy_view: dict[str, object] | None,
    rent_view: dict[str, object] | None,
) -> list[str]:
    lines: list[str] = []
    if isinstance(view.fair_value_base, (int, float)):
        basis = view.all_in_basis if isinstance(view.all_in_basis, (int, float)) else view.ask_price
        if isinstance(basis, (int, float)):
            lines.append(
                f"Fair value is {_money(view.fair_value_base)} against a working basis of {_money(basis)}."
            )
    lines.extend(list(view.why_this_stance or [])[:2])
    if isinstance(value_thesis_view, dict):
        lines.extend(list(value_thesis_view.get("key_value_drivers") or value_thesis_view.get("value_drivers") or [])[:2])
    if isinstance(strategy_view, dict) and strategy_view.get("best_path"):
        lines.append(f"Best current path: {strategy_view.get('best_path')}.")
    if isinstance(rent_view, dict) and isinstance(rent_view.get("basis_to_rent_framing"), str):
        lines.append(str(rent_view.get("basis_to_rent_framing")))
    return _dedupe_lines(lines, limit=3)


def _top_risk_or_trust_caveat(
    view: "PropertyView",
    *,
    risk_view: dict[str, object] | None,
) -> str | None:
    risk_lines = list(view.key_risks or [])
    if isinstance(risk_view, dict):
        risk_lines.extend(list(risk_view.get("key_risks") or []))
    first_risk = _dedupe_lines(risk_lines, limit=1)
    if first_risk:
        return first_risk[0]
    trust_flag = next(iter(view.trust_flags or ()), None)
    if trust_flag:
        label = _humanize_flag(trust_flag)
        if label:
            return f"Confidence is still limited by {label}."
    if isinstance(risk_view, dict):
        risk_flags = list(risk_view.get("risk_flags") or [])
        if risk_flags:
            label = _humanize_flag(str(risk_flags[0]))
            if label:
                return f"The biggest visible caution is {label}."
    return None


def _decision_claim_hint(
    view: "PropertyView",
    *,
    value_thesis_view: dict[str, object] | None,
    risk_view: dict[str, object] | None,
    rent_view: dict[str, object] | None,
    projection_view: dict[str, object] | None,
) -> str:
    pvs = str(view.primary_value_source or "").lower()
    stance = str(view.decision_stance or "").lower()
    if ("rent" in pvs or "income" in pvs or "unit" in pvs) and isinstance(rent_view, dict):
        return "rent_coverage"
    if stance == "execution_dependent" and isinstance(projection_view, dict):
        return "scenario_range"
    if stance in {"conditional", "pass", "pass_unless_changes", "interesting_but_fragile"} and isinstance(risk_view, dict):
        if list(risk_view.get("risk_flags") or []) or list(risk_view.get("trust_flags") or []):
            return "risk_composition"
    if isinstance(value_thesis_view, dict) and list(value_thesis_view.get("comps") or []):
        return "price_position"
    return "price_position"


def _decision_underwrite_digest(
    view: "PropertyView",
    *,
    value_thesis_view: dict[str, object] | None,
    risk_view: dict[str, object] | None,
    strategy_view: dict[str, object] | None,
    rent_view: dict[str, object] | None,
    projection_view: dict[str, object] | None,
) -> dict[str, object]:
    primary_thesis = _dedupe_lines(
        list(view.why_this_stance or [])
        + (
            list(value_thesis_view.get("key_value_drivers") or value_thesis_view.get("value_drivers") or [])
            if isinstance(value_thesis_view, dict)
            else []
        ),
        limit=1,
    )
    claim_hint = _decision_claim_hint(
        view,
        value_thesis_view=value_thesis_view,
        risk_view=risk_view,
        rent_view=rent_view,
        projection_view=projection_view,
    )
    lead_reason = _price_reason(view)
    return {
        "lead_reason": lead_reason,
        "primary_thesis": primary_thesis[0] if primary_thesis else _price_reason(view),
        "top_supporting_facts": _supporting_facts(
            view,
            value_thesis_view=value_thesis_view,
            strategy_view=strategy_view,
            rent_view=rent_view,
        ),
        "top_risk_or_trust_caveat": _top_risk_or_trust_caveat(view, risk_view=risk_view),
        "flip_condition": _dedupe_lines(list(view.what_changes_my_view or []), limit=1)[0]
        if list(view.what_changes_my_view or [])
        else None,
        "next_surface_hook": _DECISION_SURFACE_HOOKS.get(claim_hint),
        "primary_chart_claim": claim_hint,
    }


def _compose_compact_underwrite(
    view: "PropertyView",
    *,
    underwrite_digest: dict[str, object],
    research_lines: list[str],
) -> str:
    stance = (view.decision_stance or "conditional").replace("_", " ")
    verdict_line = f"Verdict: {stance}."
    lead_reason = _clean_sentence(underwrite_digest.get("lead_reason")) if isinstance(underwrite_digest.get("lead_reason"), str) else None
    caveat = _clean_sentence(underwrite_digest.get("top_risk_or_trust_caveat")) if isinstance(underwrite_digest.get("top_risk_or_trust_caveat"), str) else None
    flip = _clean_sentence(underwrite_digest.get("flip_condition")) if isinstance(underwrite_digest.get("flip_condition"), str) else None
    teaser = _clean_sentence(underwrite_digest.get("next_surface_hook")) if isinstance(underwrite_digest.get("next_surface_hook"), str) else None
    lines = [verdict_line]
    if lead_reason:
        lines.append(lead_reason)
    if caveat:
        lines.append(caveat)
    if flip:
        lines.append(flip)
    if teaser:
        lines.append(teaser)
    lines.extend(_dedupe_lines(research_lines, limit=1))
    return " ".join(lines)


def _decision_view_to_dict(
    view: "PropertyView",
    *,
    underwrite_digest: dict[str, object] | None = None,
) -> dict[str, object]:
    """Snapshot the decision-tier fields a UI verdict card needs. Kept as a
    dict (not the PropertyView object itself) so it serializes cleanly into
    Session.save() and round-trips through the persisted session JSON."""
    payload: dict[str, object] = {
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
        "trust_summary": dict(view.trust_summary or {}),
        "what_must_be_true": list(view.what_must_be_true or []),
        "key_risks": list(view.key_risks or []),
        "why_this_stance": list(view.why_this_stance or []),
        "what_changes_my_view": list(view.what_changes_my_view or []),
        "contradiction_count": view.contradiction_count,
        "blocked_thesis_warnings": list(view.blocked_thesis_warnings or []),
        "overrides_applied": dict(view.overrides_applied or {}),
    }
    if underwrite_digest:
        payload.update(
            {
                "lead_reason": underwrite_digest.get("lead_reason"),
                "evidence_items": list(underwrite_digest.get("top_supporting_facts") or []),
                "next_step_teaser": underwrite_digest.get("next_surface_hook"),
                "primary_chart_claim": underwrite_digest.get("primary_chart_claim"),
            }
        )
    return payload


# Per-process cache of (town, state) tuples that have already auto-fetched
# town research this run. Prevents refetching on every DECISION turn for a
# cached town. Reset on process restart — the signal store itself persists.
_AUTO_TOWN_FETCH_SEEN: set[tuple[str, str]] = set()


def _maybe_auto_fetch_town_research(
    *,
    town: str | None,
    state: str | None,
    session: Session,
    record_partial,
) -> None:
    """Synchronously trigger town research when the store has no signals.

    Gated on ``BRIARWOOD_ENABLE_AUTO_TOWN_RESEARCH`` and a per-process seen
    cache. Bounded to a short wall-clock budget so the collector cannot
    stall the DECISION turn. Timeouts/failures are recorded as partial-data
    warnings rather than bubbled.
    """
    import os

    if not town or not state:
        return
    flag = os.environ.get("BRIARWOOD_ENABLE_AUTO_TOWN_RESEARCH", "").strip().lower()
    if flag not in {"1", "true", "yes"}:
        return
    key = (town.strip().lower(), state.strip().lower())
    if key in _AUTO_TOWN_FETCH_SEEN:
        return

    try:
        from briarwood.local_intelligence.storage import JsonLocalSignalStore
        store = JsonLocalSignalStore()
        existing = store.load_town_signals(town=town, state=state)
    except Exception as exc:
        record_partial("town_research_auto_fetch", exc)
        _AUTO_TOWN_FETCH_SEEN.add(key)
        return

    if existing:
        _AUTO_TOWN_FETCH_SEEN.add(key)
        return

    _AUTO_TOWN_FETCH_SEEN.add(key)
    try:
        from briarwood.agent.tools import research_town
        research_town(town=town, state=state, budget_seconds=2.0)
    except Exception as exc:
        session.last_partial_data_warnings.append(
            {
                "section": "town_research_auto_fetch",
                "reason": f"{type(exc).__name__}: {exc}".strip(": "),
                "verdict_reliable": True,
            }
        )
        return

    try:
        session.last_town_summary = _build_town_summary(town, state)
    except Exception as exc:
        record_partial("town_summary", exc)


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

    signal_items = build_town_signal_items(town, state, geocode=_geocode_town_signal_query)

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
        "signal_items": signal_items,
    }


def _geocode_town_signal_query(query: str) -> tuple[float | None, float | None]:
    """Best-effort geocode for town-signal drill-ins."""

    from briarwood.data_sources.google_maps_client import GoogleMapsClient

    client = GoogleMapsClient()
    if not client.is_configured or not query.strip():
        return None, None
    try:
        response = client.geocode(query)
    except Exception:
        return None, None
    payload = response.normalized_payload or {}
    lat = payload.get("latitude")
    lng = payload.get("longitude")
    return (
        float(lat) if isinstance(lat, (int, float)) else None,
        float(lng) if isinstance(lng, (int, float)) else None,
    )


def _cma_rows_from_result(cma_result: CMAResult | None) -> list[dict[str, object]]:
    return [_comp_row_from_cma(comp) for comp in (cma_result.comps if cma_result else [])]


def _build_market_support_view(
    view: "PropertyView | PropertyBrief | None",
    cma_result: CMAResult | None,
    *,
    address: str | None = None,
    town: str | None = None,
    state: str | None = None,
) -> dict[str, object] | None:
    """F2: package the live-market comps from get_cma into a dedicated view.

    These rows are market-context evidence, explicitly NOT what fed fair
    value. Returned None when get_cma produced no usable comps, so the
    UI simply omits the card rather than showing an empty table.

    Browse callers pass a ``PropertyBrief``; decision callers pass a
    ``PropertyView``. Both expose ``address``/``town``/``state``.
    """
    if cma_result is None:
        return None
    comps = _cma_rows_from_result(cma_result)
    if not comps:
        return None
    resolved_address = address if address is not None else getattr(view, "address", None)
    resolved_town = town if town is not None else getattr(view, "town", None)
    resolved_state = state if state is not None else getattr(view, "state", None)
    return {
        "address": resolved_address,
        "town": resolved_town,
        "state": resolved_state,
        "comp_selection_summary": cma_result.comp_selection_summary,
        "comps": comps,
    }


def _build_comps_preview(
    pid: str,
    view: "PropertyView",
    *,
    cma_result: CMAResult | None = None,
) -> dict[str, object] | None:
    """Build the compact comps preview, preferring the shared CMA contract."""
    subject_ask = view.ask_price
    comps = _cma_rows_from_result(cma_result)
    if not comps:
        thesis = {"ask_price": subject_ask}
        try:
            comps = _cma_comps_for_property(pid, thesis)
        except Exception:
            return None
    return _comps_preview_from_cma(pid, subject_ask, comps)


def _format_browse_setup(brief: PropertyBrief) -> str:
    ask = brief.ask_price
    fair = brief.fair_value_base
    premium = brief.ask_premium_pct
    recommendation = (brief.recommendation or "").strip()
    if isinstance(ask, (int, float)) and isinstance(fair, (int, float)):
        if isinstance(premium, (int, float)) and premium >= 0.03:
            return (
                f"Quick take: this looks a little expensive at {_money(ask)}. "
                f"Briarwood's current read lands closer to {_money(fair)}, so this gets more interesting if the price softens."
            )
        if isinstance(premium, (int, float)) and premium <= -0.03:
            return (
                f"Quick take: this looks interesting at today's ask. "
                f"The list price of {_money(ask)} is running below Briarwood's current value read near {_money(fair)}."
            )
        return (
            f"Quick take: this is roughly in the zone at today's price. "
            f"The ask of {_money(ask)} sits close to Briarwood's current value read near {_money(fair)}."
        )
    if recommendation:
        return f"Quick take: {recommendation}"
    stance = (brief.decision_stance or "conditional").replace("_", " ")
    return f"Quick take: the current read is {stance}."


def _format_browse_support(brief: PropertyBrief) -> str:
    drivers = list(brief.key_value_drivers or [])
    if drivers:
        return "Why it stands out: " + "; ".join(drivers[:2]) + "."
    if brief.primary_value_source and str(brief.primary_value_source).strip().lower() != "unknown":
        return f"Why it stands out: the price read is leaning on {brief.primary_value_source.replace('_', ' ')}."
    if brief.best_path:
        return f"Why it stands out: the cleanest path right now looks like {brief.best_path.replace('_', ' ')}."
    return "Why it stands out: the current snapshot still points to a workable purchase read, even if the support is early."


def _humanize_trust_flag(flag: str) -> str:
    mapping = {
        "incomplete_carry_inputs": "taxes, insurance, or financing assumptions are still missing",
        "thin_comp_set": "the comparable sales support is still thin",
        "weak_town_context": "the town backdrop is still lightly documented",
        "zoning_unverified": "zoning still needs to be confirmed",
        "rent_support_thin": "the rent support is still thin",
    }
    return mapping.get(flag, flag.replace("_", " "))


def _format_browse_caution(brief: PropertyBrief) -> str:
    cautions = list(brief.trust_flags or [])
    if cautions:
        return "What I'd want to tighten up next: " + "; ".join(_humanize_trust_flag(flag) for flag in cautions[:3]) + "."
    risks = list(brief.key_risks or [])
    if risks:
        return "What I'd want to tighten up next: " + "; ".join(risks[:2]) + "."
    return "What I'd want to tighten up next: nothing major is flashing red yet, but this still needs a fuller underwriting pass."


def _format_next_step(brief: PropertyBrief) -> str:
    if brief.next_questions:
        return f"Best next question: {brief.next_questions[0]}"
    mapping = {
        "decision": "should I buy this at the current ask?",
        "scenario": "what does the forward scenario path do to value?",
        "deep_dive": "what is the deepest unresolved risk or assumption here?",
    }
    if brief.recommended_next_run:
        return f"Best next question: {mapping.get(brief.recommended_next_run, brief.recommended_next_run)}"
    return "Best next question: should I buy this at the current ask?"


def _strip_browse_label(line: str) -> str:
    if ":" not in line:
        return line.strip()
    return line.split(":", 1)[1].strip()


def _format_browse_decision_summary(brief: PropertyBrief) -> list[str]:
    decision_line = _strip_browse_label(_format_browse_setup(brief))
    why_parts = [
        _strip_browse_label(_format_browse_support(brief)).rstrip("."),
        _strip_browse_label(_format_browse_caution(brief)).rstrip("."),
    ]
    why_line = ". ".join(part for part in why_parts if part)
    next_move = (
        "Run a live CMA and pin down a realistic entry point"
        if brief.fair_value_base is not None
        else _strip_browse_label(_format_next_step(brief))
    )
    return [
        f"Decision: {decision_line}",
        f"Why: {why_line}.",
        f"Next move: {next_move}.",
    ]


def _format_browse_brief(brief: PropertyBrief, neighbors: list[dict[str, object]]) -> str:
    parts: list[str] = [brief.address or brief.property_id]
    if brief.beds is not None and brief.baths is not None:
        parts.append(f"{brief.beds}bd/{brief.baths}ba")
    if brief.ask_price is not None:
        parts.append(f"ask {_money(brief.ask_price)}")
    lines = [
        " — ".join(parts),
        *_format_browse_decision_summary(brief),
    ]
    return "\n".join(lines)


def _build_browse_comps_preview(
    pid: str,
    subject_ask: float | None,
    neighbors: list[dict[str, object]],
    *,
    cma_result: CMAResult | None = None,
) -> dict[str, object] | None:
    cma_rows = _cma_rows_from_result(cma_result)
    if cma_rows:
        return _comps_preview_from_cma(pid, subject_ask, cma_rows)
    rows: list[dict[str, object]] = []
    prices: list[float] = []
    for comp in neighbors:
        if comp.get("property_id") == pid:
            continue
        price = comp.get("ask_price") or comp.get("price")
        premium_pct = None
        if isinstance(price, (int, float)) and isinstance(subject_ask, (int, float)) and subject_ask:
            premium_pct = round((float(price) - float(subject_ask)) / float(subject_ask), 4)
            prices.append(float(price))
        rows.append(
            {
                "property_id": comp.get("property_id"),
                "address": comp.get("address"),
                "beds": comp.get("beds"),
                "baths": comp.get("baths"),
                "sqft": comp.get("sqft"),
                "price": price,
                "premium_pct": premium_pct,
            }
        )
        if len(rows) >= 4:
            break
    if not rows:
        return None
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


def _browse_what_must_be_true(brief: PropertyBrief) -> list[str]:
    prompts: list[str] = []
    for flag in list(brief.trust_flags or []):
        phrase = _humanize_trust_flag(flag)
        prompts.append(phrase[:1].upper() + phrase[1:] + ".")
    if not prompts and brief.key_risks:
        prompts.extend(f"{risk}." for risk in brief.key_risks[:2])
    return prompts[:3]


def _build_browse_value_thesis(
    brief: PropertyBrief,
    neighbors: list[dict[str, object]],
    *,
    cma_result: CMAResult | None = None,
) -> dict[str, object]:
    # F2: browse does not run the routed valuation pipeline, so we have no
    # comps that actually fed fair value. Leave `comps` empty here — live
    # market comps and saved-neighbor rows are surfaced separately via
    # `last_market_support_view` so the UI can label them honestly.
    comps: list[dict[str, object]] = []
    comp_selection_summary: str | None = None
    return {
        "address": brief.address,
        "town": brief.town,
        "state": brief.state,
        "ask_price": brief.ask_price,
        "fair_value_base": brief.fair_value_base,
        "premium_discount_pct": brief.ask_premium_pct,
        "pricing_view": brief.pricing_view,
        "primary_value_source": brief.primary_value_source,
        "net_opportunity_delta_pct": (-brief.ask_premium_pct) if isinstance(brief.ask_premium_pct, (int, float)) else None,
        "value_drivers": list(brief.key_value_drivers or []),
        "key_value_drivers": list(brief.key_value_drivers or []),
        "what_must_be_true": _browse_what_must_be_true(brief),
        "why_this_stance": [
            f"Current pricing looks {'ahead of' if isinstance(brief.ask_premium_pct, (int, float)) and brief.ask_premium_pct > 0 else 'supported by'} Briarwood's current fair-value read."
        ] + list(brief.key_value_drivers or [])[:2],
        "what_changes_my_view": [
            f"Confirm {_humanize_trust_flag(flag)}."
            for flag in list(brief.trust_flags or [])[:3]
            if _humanize_trust_flag(flag)
        ],
        "trust_summary": {
            "band": "Low confidence" if brief.trust_flags else "Moderate confidence",
            "trust_flags": list(brief.trust_flags or []),
            "blocked_thesis_warnings": list(brief.key_risks or [])[:2],
        },
        "contradiction_count": 0,
        "blocked_thesis_warnings": list(brief.key_risks or [])[:2],
        "comp_selection_summary": comp_selection_summary,
        "comps": comps,
    }


def _build_decision_value_thesis(
    pid: str,
    view: "PropertyView",
    *,
    cma_result: CMAResult | None = None,
) -> dict[str, object]:
    # F2: value_thesis.comps must be the comps that actually fed the fair
    # value computation. Pull them from the valuation module's output via
    # get_value_thesis, not from cma_result (which is live market support).
    comps: list[dict[str, object]] = []
    comp_selection_summary: str | None = None
    try:
        thesis = get_value_thesis(pid, overrides=view.overrides_applied or None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("valuation-module comps unavailable for %s: %s", pid, exc)
        thesis = None
    if isinstance(thesis, dict):
        raw_comps = thesis.get("comps")
        if isinstance(raw_comps, list):
            comps = [dict(row) for row in raw_comps if isinstance(row, dict)]
        summary = thesis.get("comp_selection_summary")
        if isinstance(summary, str) and summary.strip():
            comp_selection_summary = summary
    unified = dict(view.unified or {})
    value_drivers = list(unified.get("key_value_drivers") or [])
    net_delta_pct = -view.ask_premium_pct if isinstance(view.ask_premium_pct, (int, float)) else None
    valuation_x_risk = dict((unified.get("valuation_x_risk") or {}).get("adjustments") or {})
    # F5: carry the structured optionality_signal through to the value_thesis
    # view so the SSE projector can surface hidden upside levers. The signal
    # is computed by synthesis.structured.build_unified_output — when it's
    # missing (older runs, modules that didn't fire) we fall back to a
    # zero-item signal so the UI renders nothing rather than a broken card.
    optionality = unified.get("optionality_signal")
    if not isinstance(optionality, dict):
        optionality = {
            "primary_source": view.primary_value_source or "unknown",
            "hidden_upside_items": [],
            "summary": None,
        }
    return {
        "address": view.address,
        "town": view.town,
        "state": view.state,
        "ask_price": view.ask_price,
        "fair_value_base": view.fair_value_base,
        "value_low": view.value_low,
        "value_high": view.value_high,
        "premium_discount_pct": view.ask_premium_pct,
        "pricing_view": unified.get("pricing_view") or view.pricing_view,
        "primary_value_source": view.primary_value_source,
        "net_opportunity_delta_pct": net_delta_pct,
        "value_drivers": value_drivers,
        "key_value_drivers": value_drivers,
        "what_must_be_true": list(view.what_must_be_true),
        "why_this_stance": list(view.why_this_stance),
        "what_changes_my_view": list(view.what_changes_my_view),
        "trust_summary": dict(view.trust_summary),
        "contradiction_count": view.contradiction_count,
        "blocked_thesis_warnings": list(view.blocked_thesis_warnings),
        "risk_adjusted_fair_value": valuation_x_risk.get("risk_adjusted_fair_value"),
        "required_discount": valuation_x_risk.get("required_discount"),
        "comp_selection_summary": comp_selection_summary,
        "comps": comps,
        "optionality_signal": optionality,
    }


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
        *_format_browse_decision_summary(brief),
    ]
    return "\n".join(lines)


def _browse_surface_payload(
    *,
    brief: PropertyBrief,
    session: Session,
    neighbors: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "address": brief.address,
        "town": brief.town,
        "state": brief.state,
        "ask_price": brief.ask_price,
        "fair_value_base": brief.fair_value_base,
        "ask_premium_pct": brief.ask_premium_pct,
        "best_path": brief.best_path,
        "trust_flags": list(brief.trust_flags or []),
        "key_risks": list(brief.key_risks or []),
        "next_questions": list(brief.next_questions or []),
        "neighbor_count": len(neighbors),
        "town_summary": dict(session.last_town_summary or {}) if isinstance(session.last_town_summary, dict) else {},
        "value_thesis": dict(session.last_value_thesis_view or {}) if isinstance(session.last_value_thesis_view, dict) else {},
        "strategy": dict(session.last_strategy_view or {}) if isinstance(session.last_strategy_view, dict) else {},
        "rent_outlook": dict(session.last_rent_outlook_view or {}) if isinstance(session.last_rent_outlook_view, dict) else {},
        "projection": dict(session.last_projection_view or {}) if isinstance(session.last_projection_view, dict) else {},
    }


def _populate_browse_slots(
    session: Session,
    *,
    pid: str,
    brief: PropertyBrief,
    summary: dict[str, object] | None,
    neighbors: list[dict[str, object]],
    cma_result: CMAResult | None,
    projection: dict[str, object] | None,
    strategy_fit: dict[str, object] | None,
    rent_outlook: RentOutlook | None,
) -> None:
    try:
        session.last_town_summary = _build_town_summary(brief.town, brief.state)
    except Exception as exc:
        logger.warning("browse town summary build failed for %s: %s", pid, exc)
        session.last_town_summary = None

    session.last_comps_preview = _build_browse_comps_preview(
        pid,
        brief.ask_price,
        neighbors,
        cma_result=cma_result,
    )
    session.last_value_thesis_view = _build_browse_value_thesis(
        brief,
        neighbors,
        cma_result=cma_result,
    )
    try:
        session.last_market_support_view = _build_market_support_view(
            None,
            cma_result,
            address=brief.address,
            town=brief.town,
            state=brief.state,
        )
    except Exception as exc:
        logger.warning("browse market support build failed for %s: %s", pid, exc)
        session.last_market_support_view = None

    facts = summary or {}
    if projection:
        session.last_projection_view = {
            **projection,
            "address": facts.get("address") or brief.address,
            "town": facts.get("town") or brief.town,
            "state": facts.get("state") or brief.state,
        }

    if strategy_fit:
        session.last_strategy_view = {
            "address": facts.get("address") or brief.address,
            "town": facts.get("town") or brief.town,
            "state": facts.get("state") or brief.state,
            "best_path": strategy_fit.get("best_path"),
            "recommendation": strategy_fit.get("recommendation"),
            "pricing_view": strategy_fit.get("pricing_view"),
            "primary_value_source": strategy_fit.get("primary_value_source"),
            "rental_ease_label": strategy_fit.get("rental_ease_label"),
            "rental_ease_score": strategy_fit.get("rental_ease_score"),
            "rent_support_score": strategy_fit.get("rent_support_score"),
            "liquidity_score": strategy_fit.get("liquidity_score"),
            "monthly_cash_flow": strategy_fit.get("monthly_cash_flow"),
            "cash_on_cash_return": strategy_fit.get("cash_on_cash_return"),
            "annual_noi": strategy_fit.get("annual_noi"),
        }

    if rent_outlook:
        session.last_rent_outlook_view = {
            "address": facts.get("address") or brief.address,
            "town": facts.get("town") or brief.town,
            "state": facts.get("state") or brief.state,
            "entry_basis": rent_outlook.entry_basis,
            "monthly_rent": rent_outlook.current_monthly_rent,
            "effective_monthly_rent": rent_outlook.effective_monthly_rent,
            "rent_source_type": rent_outlook.rent_source_type,
            "rental_ease_label": rent_outlook.rental_ease_label,
            "rental_ease_score": rent_outlook.rental_ease_score,
            "annual_noi": rent_outlook.annual_noi,
            "horizon_years": rent_outlook.horizon_years,
            "future_rent_low": rent_outlook.future_rent_low,
            "future_rent_mid": rent_outlook.future_rent_mid,
            "future_rent_high": rent_outlook.future_rent_high,
            "zillow_market_rent": rent_outlook.zillow_market_rent,
            "zillow_rental_comp_count": rent_outlook.zillow_rental_comp_count,
            "market_context_note": rent_outlook.market_context_note,
            "basis_to_rent_framing": rent_outlook.basis_to_rent_framing,
            "owner_occupy_then_rent": rent_outlook.owner_occupy_then_rent,
            "carry_offset_ratio": rent_outlook.carry_offset_ratio,
            "break_even_rent": rent_outlook.break_even_rent,
            "break_even_probability": rent_outlook.break_even_probability,
            "adjusted_rent_confidence": rent_outlook.adjusted_rent_confidence,
            "rent_haircut_pct": rent_outlook.rent_haircut_pct,
            "burn_chart_payload": dict(rent_outlook.burn_chart_payload or {}),
            "ramp_chart_payload": dict(rent_outlook.ramp_chart_payload or {}),
        }


def _strategy_view_from_fit(
    facts: dict[str, object] | None,
    fit: dict[str, object],
    *,
    address: str | None,
    town: str | None,
    state: str | None,
) -> dict[str, object]:
    resolved = facts or {}
    return {
        "address": resolved.get("address") or address,
        "town": resolved.get("town") or town,
        "state": resolved.get("state") or state,
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


def _rent_outlook_view_from_result(
    facts: dict[str, object] | None,
    rent_payload: dict[str, object] | None,
    rent_outlook: RentOutlook,
    *,
    address: str | None,
    town: str | None,
    state: str | None,
) -> dict[str, object]:
    resolved = facts or {}
    payload = rent_payload or {}
    return {
        "address": resolved.get("address") or address,
        "town": resolved.get("town") or town,
        "state": resolved.get("state") or state,
        "entry_basis": rent_outlook.entry_basis,
        "monthly_rent": payload.get("monthly_rent", rent_outlook.current_monthly_rent),
        "effective_monthly_rent": payload.get(
            "effective_monthly_rent", rent_outlook.effective_monthly_rent
        ),
        "rent_source_type": payload.get("rent_source_type", rent_outlook.rent_source_type),
        "rental_ease_label": payload.get("rental_ease_label", rent_outlook.rental_ease_label),
        "rental_ease_score": payload.get("rental_ease_score", rent_outlook.rental_ease_score),
        "annual_noi": payload.get("annual_noi", rent_outlook.annual_noi),
        "horizon_years": rent_outlook.horizon_years,
        "future_rent_low": rent_outlook.future_rent_low,
        "future_rent_mid": rent_outlook.future_rent_mid,
        "future_rent_high": rent_outlook.future_rent_high,
        "zillow_market_rent": rent_outlook.zillow_market_rent,
        "zillow_rental_comp_count": rent_outlook.zillow_rental_comp_count,
        "market_context_note": rent_outlook.market_context_note,
        "basis_to_rent_framing": rent_outlook.basis_to_rent_framing,
        "owner_occupy_then_rent": rent_outlook.owner_occupy_then_rent,
        "carry_offset_ratio": rent_outlook.carry_offset_ratio,
        "break_even_rent": rent_outlook.break_even_rent,
        "break_even_probability": rent_outlook.break_even_probability,
        "adjusted_rent_confidence": rent_outlook.adjusted_rent_confidence,
        "rent_haircut_pct": rent_outlook.rent_haircut_pct,
        "burn_chart_payload": dict(rent_outlook.burn_chart_payload or {}),
        "ramp_chart_payload": dict(rent_outlook.ramp_chart_payload or {}),
    }


def _risk_view_from_profile(
    facts: dict[str, object] | None,
    profile: dict[str, object],
    *,
    address: str | None,
    town: str | None,
    state: str | None,
    bear_value: float | None = None,
    stress_value: float | None = None,
) -> dict[str, object]:
    resolved = facts or {}
    total_penalty = _normalize_penalty(profile.get("total_penalty"))
    if isinstance(total_penalty, (int, float)):
        if total_penalty >= 0.5:
            tier = "thin"
        elif total_penalty >= 0.25:
            tier = "moderate"
        else:
            tier = "strong"
    else:
        tier = None
    bear = (
        profile.get("bear_case_value")
        if isinstance(profile.get("bear_case_value"), (int, float))
        else bear_value
    )
    stress = (
        profile.get("stress_case_value")
        if isinstance(profile.get("stress_case_value"), (int, float))
        else stress_value
    )
    return {
        "address": resolved.get("address") or address,
        "town": resolved.get("town") or town,
        "state": resolved.get("state") or state,
        "ask_price": profile.get("ask_price"),
        "bear_value": bear,
        "stress_value": stress,
        "risk_flags": list(profile.get("risk_flags") or []),
        "trust_flags": list(profile.get("trust_flags") or []),
        "key_risks": list(profile.get("key_risks") or []),
        "total_penalty": total_penalty,
        "confidence_tier": tier,
    }


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
        session.last_partial_data_warnings.append(
            {
                "section": "lookup_narration",
                "reason": "llm_unavailable",
                "verdict_reliable": True,
            }
        )
        addr = summary.get("address", pid)
        price = summary.get("ask_price")
        price_s = _money(price)
        pricing_view = summary.get("pricing_view")
        if pricing_view:
            return f"{addr} is listed at {price_s}. Briarwood currently reads that price as {pricing_view.replace('_', ' ')}."
        return f"{addr} is listed at {price_s}. That's the latest price Briarwood has for it."

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


def _maybe_handle_via_claim(
    text: str,
    decision: RouterDecision,
    session: Session,
    llm: LLMClient | None,
    *,
    pid: str,
) -> str | None:
    """Phase 3 wedge entry point.

    Returns the rendered prose when the claim path both (a) was enabled for
    this property and (b) produced a claim the Editor accepted. Returns None
    in every other case — including Editor rejection — so the caller falls
    through to the legacy body. On rejection we also populate
    ``session.last_claim_rejected`` so the SSE adapter can surface the
    rejection without changing the wire contract the UI consumes.
    """
    from briarwood.agent.turn_manifest import record_wedge
    from briarwood.claims.archetypes import Archetype
    from briarwood.claims.pipeline import build_claim_for_property
    from briarwood.claims.representation import render_claim
    from briarwood.claims.routing import map_to_archetype
    from briarwood.editor import edit_claim
    from briarwood.feature_flags import claims_enabled_for
    from briarwood.value_scout import scout_claim

    if not claims_enabled_for(pid):
        record_wedge(fired=False, reason="claims_enabled_for=False")
        return None

    parser_output = getattr(decision, "parser_output", None)
    question_focus = getattr(parser_output, "question_focus", None)
    archetype = map_to_archetype(
        decision.answer_type,
        list(question_focus) if question_focus else None,
        has_pinned_listing=True,
    )
    if archetype != Archetype.VERDICT_WITH_COMPARISON:
        record_wedge(
            fired=False,
            reason=f"archetype != VERDICT_WITH_COMPARISON (got {archetype})",
        )
        return None

    try:
        claim = build_claim_for_property(pid, user_text=text)
    except Exception as exc:
        logger.warning("claims pipeline build failed: %s", exc)
        record_wedge(
            fired=True,
            success=False,
            reason=f"build_raised: {type(exc).__name__}: {exc}",
            archetype=archetype.value,
        )
        return None

    insight = scout_claim(claim)
    if insight is not None:
        claim = claim.model_copy(
            update={
                "surfaced_insight": insight,
                "comparison": claim.comparison.model_copy(
                    update={"emphasis_scenario_id": insight.scenario_id}
                ),
            }
        )

    verdict_label = claim.verdict.label
    result = edit_claim(claim)
    if not result.passed:
        logger.info(
            "claim rejected for pid=%s failures=%s", pid, result.failures
        )
        session.last_claim_rejected = {
            "archetype": archetype.value,
            "verdict_label": verdict_label,
            "failures": list(result.failures),
        }
        record_wedge(
            fired=True,
            success=False,
            reason=f"editor_rejected: {result.failures}",
            archetype=archetype.value,
        )
        return None

    try:
        rendered = render_claim(claim, llm=llm)
    except Exception as exc:
        logger.warning("claim rendering failed: %s", exc)
        record_wedge(
            fired=True,
            success=False,
            reason=f"render_raised: {type(exc).__name__}: {exc}",
            archetype=archetype.value,
        )
        return None

    session.last_claim_events = list(rendered.events)
    record_wedge(fired=True, success=True, archetype=archetype.value)
    return rendered.prose


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

    # Phase 3 wedge: feature-flagged claim-object pipeline. Rolls back by
    # flipping BRIARWOOD_CLAIMS_ENABLED to false — no branch here if the flag
    # is off. On any path failure we fall through to the legacy body below
    # (unchanged) so the wedge can never block a response.
    claim_response = _maybe_handle_via_claim(text, decision, session, llm, pid=pid)
    if claim_response is not None:
        session.current_property_id = pid
        return claim_response

    analysis_overrides, user_overrides = _analysis_overrides(
        text,
        pid=pid,
        session=session,
    )
    try:
        view = PropertyView.load(pid, overrides=analysis_overrides, depth="decision")
    except ToolUnavailable as exc:
        return f"I couldn't analyze that ({exc})."
    session.current_property_id = pid
    session.last_decision_view = _decision_view_to_dict(view)
    cma_result: CMAResult | None = None

    # Spoon-feed the first DECISION response with town context + comp preview
    # so the user doesn't need two follow-ups to get the full picture. Both
    # calls are file-backed and fast; individual enrichment failures don't
    # block the core decision, but F7 requires surfacing each one to the UI
    # via `session.last_partial_data_warnings` rather than swallowing silently.
    def _record_partial(section: str, exc: BaseException) -> None:
        reason = f"{type(exc).__name__}: {exc}".strip(": ")
        logger.warning("%s build failed: %s", section, exc)
        session.last_partial_data_warnings.append(
            {"section": section, "reason": reason, "verdict_reliable": True}
        )

    try:
        session.last_town_summary = _build_town_summary(view.town, view.state)
    except Exception as exc:
        session.last_town_summary = None
        _record_partial("town_summary", exc)
    _maybe_auto_fetch_town_research(
        town=view.town,
        state=view.state,
        session=session,
        record_partial=_record_partial,
    )
    try:
        cma_result = get_cma(pid, overrides=analysis_overrides)
    except Exception as exc:
        cma_result = None
        _record_partial("cma", exc)
    try:
        session.last_comps_preview = _build_comps_preview(pid, view, cma_result=cma_result)
    except Exception as exc:
        session.last_comps_preview = None
        _record_partial("comps_preview", exc)
    try:
        session.last_value_thesis_view = _build_decision_value_thesis(
            pid,
            view,
            cma_result=cma_result,
        )
    except Exception as exc:
        session.last_value_thesis_view = None
        _record_partial("value_thesis", exc)
    try:
        session.last_market_support_view = _build_market_support_view(view, cma_result)
    except Exception as exc:
        session.last_market_support_view = None
        _record_partial("market_support_comps", exc)

    # Populate the scenario view so the first DECISION response can emit a
    # bull/base/bear table + fan chart inline. Failures here must not block
    # the decision narrative — scenarios are enrichment, not the core answer.
    projection_chart_line = ""
    presentation_payload: dict[str, object] | None = None
    try:
        proj = get_projection(pid, overrides=analysis_overrides)
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
        _record_partial("projection", exc)

    def _finalize(response: str) -> str:
        _remember_surface_output(
            session,
            narrative=response,
            presentation_payload=presentation_payload,
        )
        return response + projection_chart_line

    # Auto-research hook: exactly one loop, only in decision mode, only when a
    # research-fixable trust flag is present. Visible "researching..." is
    # mandatory so the user never wonders where latency came from.
    # Skip research when overrides are present — what-if turns aren't about
    # new town context, they're about re-underwriting at a user-supplied basis.
    research_targets = set(view.trust_flags) & _AUTO_RESEARCH_FLAGS
    research_lines: list[str] = []
    if research_targets and not user_overrides:
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
                view = PropertyView.load(pid, overrides=analysis_overrides, depth="decision")
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

    property_summary: dict[str, object] | None = None
    try:
        property_summary = get_property_summary(pid)
    except ToolUnavailable:
        property_summary = {
            "address": view.address,
            "town": view.town,
            "state": view.state,
        }

    projection_view = (
        session.last_projection_view if isinstance(session.last_projection_view, dict) else {}
    )
    try:
        risk_profile = get_risk_profile(pid, overrides=analysis_overrides)
        risk_view = _risk_view_from_profile(
            property_summary,
            risk_profile,
            address=view.address,
            town=view.town,
            state=view.state,
            bear_value=projection_view.get("bear_case_value"),
            stress_value=projection_view.get("stress_case_value"),
        )
        if any(
            risk_view.get(key)
            for key in ("risk_flags", "trust_flags", "key_risks", "bear_value", "stress_value")
        ):
            session.last_risk_view = risk_view
        else:
            session.last_risk_view = None
    except Exception as exc:
        session.last_risk_view = None
        _record_partial("risk_profile", exc)

    try:
        strategy_fit = get_strategy_fit(pid, overrides=analysis_overrides)
        strategy_view = _strategy_view_from_fit(
            property_summary,
            strategy_fit,
            address=view.address,
            town=view.town,
            state=view.state,
        )
        if any(strategy_view.get(key) is not None for key in strategy_view if key not in {"address", "town", "state"}):
            session.last_strategy_view = strategy_view
        else:
            session.last_strategy_view = None
    except Exception as exc:
        session.last_strategy_view = None
        _record_partial("strategy_fit", exc)

    try:
        rent_payload = get_rent_estimate(pid, overrides=analysis_overrides)
        rent_outlook = get_rent_outlook(
            pid,
            years=3,
            overrides=analysis_overrides,
            rent_payload=rent_payload,
            property_summary=property_summary or {},
        )
        rent_view = _rent_outlook_view_from_result(
            property_summary,
            dict(rent_payload),
            rent_outlook,
            address=view.address,
            town=view.town,
            state=view.state,
        )
        if any(
            rent_view.get(key)
            for key in (
                "monthly_rent",
                "effective_monthly_rent",
                "future_rent_low",
                "future_rent_mid",
                "future_rent_high",
                "burn_chart_payload",
                "ramp_chart_payload",
            )
        ):
            session.last_rent_outlook_view = rent_view
        else:
            session.last_rent_outlook_view = None
    except Exception as exc:
        session.last_rent_outlook_view = None
        _record_partial("rent_outlook", exc)

    underwrite_digest = _decision_underwrite_digest(
        view,
        value_thesis_view=(
            session.last_value_thesis_view
            if isinstance(session.last_value_thesis_view, dict)
            else None
        ),
        risk_view=session.last_risk_view if isinstance(session.last_risk_view, dict) else None,
        strategy_view=(
            session.last_strategy_view
            if isinstance(session.last_strategy_view, dict)
            else None
        ),
        rent_view=(
            session.last_rent_outlook_view
            if isinstance(session.last_rent_outlook_view, dict)
            else None
        ),
        projection_view=(
            session.last_projection_view
            if isinstance(session.last_projection_view, dict)
            else None
        ),
    )
    session.last_decision_view = _decision_view_to_dict(
        view,
        underwrite_digest=underwrite_digest,
    )

    stance = view.decision_stance or "unknown"
    pvs = view.primary_value_source or "unknown"
    flags = list(view.trust_flags)
    # Decision narration shows the all-in basis — what the buyer actually
    # commits — not just the listing ask. Ask vs basis diverge whenever
    # capex is applied (renovation override, capex lane, etc.).
    basis = view.all_in_basis if view.all_in_basis is not None else view.ask_price
    premium = view.basis_premium_pct
    if not user_overrides:
        try:
            summary = property_summary or get_property_summary(pid)
            derived_brief = build_property_brief(pid, summary, dict(view.unified or {}))
            presentation_payload = get_property_presentation(
                pid,
                include_town_research=False,
                brief=derived_brief,
                cma=cma_result,
                contract_type="decision_summary",
                analysis_mode="decision",
            )
        except Exception as exc:
            logger.warning("decision presentation failed for %s: %s", pid, exc)
            presentation_payload = None

    if llm is None:
        session.last_partial_data_warnings.append(
            {
                "section": "decision_summary_narration",
                "reason": "llm_unavailable",
                "verdict_reliable": True,
            }
        )
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
        compact = _compose_compact_underwrite(
            view,
            underwrite_digest=underwrite_digest,
            research_lines=research_lines,
        )
        if compact.strip() and compact.strip() != f"Verdict: {stance.replace('_', ' ')}.":
            return _finalize(compact)
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
            f"My plain-English read: {stance.replace('_', ' ')}. "
            f"Briarwood's main value anchor is {pvs.replace('_', ' ')} and it puts fair value near {money(view.fair_value_base)} "
            f"against an all-in cost of {money(basis)} "
            f"(list price {money(view.ask_price)}, {pct} versus that anchor). "
            f"Confidence watchouts: {flags_s}."
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
        valuation_x_risk = dict((dict(view.unified or {}).get("valuation_x_risk") or {}).get("adjustments") or {})
        risk_adjusted_fair_value = valuation_x_risk.get("risk_adjusted_fair_value")
        required_discount = valuation_x_risk.get("required_discount")
        value_inputs = {
            "address": view.address,
            "ask_price": view.ask_price,
            "fair_value_base": view.fair_value_base,
            "value_low": view.value_low,
            "value_high": view.value_high,
            "ask_premium_pct": view.ask_premium_pct,
            "price_gap_pct": view.ask_premium_pct,
            "primary_value_source": support,
            "trust_flags": list(flags),
            "all_in_basis": view.all_in_basis,
            "risk_adjusted_fair_value": risk_adjusted_fair_value,
            "required_discount": required_discount,
        }
        cleaned, report = complete_and_verify(
            llm=llm,
            system=load_prompt("decision_value"),
            user=(
                f"user_question: {text}\n"
                f"address: {view.address}\n"
                f"ask_price: {view.ask_price}\n"
                f"fair_value_base: {view.fair_value_base}\n"
                f"value_range: {range_s}\n"
                f"ask_premium_pct: {view.ask_premium_pct}\n"
                f"primary_value_source: {support}\n"
                f"trust_flags: {caveat}\n"
                f"all_in_basis: {view.all_in_basis}\n"
                f"risk_adjusted_fair_value: {risk_adjusted_fair_value}\n"
                f"required_discount: {required_discount}\n"
            ),
            structured_inputs=value_inputs,
            tier="decision_value",
            max_tokens=180,
        )
        session.last_verifier_report = report
        return _finalize(cleaned)

    system = load_prompt("decision_summary")
    key_risks = list(view.key_risks or [])
    why_this_stance = list(view.why_this_stance or [])
    what_changes_my_view = list(view.what_changes_my_view or [])
    blocked_thesis_warnings = list(view.blocked_thesis_warnings or [])
    contradiction_count = view.contradiction_count
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
        "key_risks": key_risks,
        "why_this_stance": why_this_stance,
        "what_changes_my_view": what_changes_my_view,
        "contradiction_count": contradiction_count,
        "blocked_thesis_warnings": blocked_thesis_warnings,
        "lead_reason": underwrite_digest.get("lead_reason"),
        "primary_thesis": underwrite_digest.get("primary_thesis"),
        "top_supporting_facts": list(underwrite_digest.get("top_supporting_facts") or []),
        "top_risk_or_trust_caveat": underwrite_digest.get("top_risk_or_trust_caveat"),
        "flip_condition": underwrite_digest.get("flip_condition"),
        "next_surface_hook": underwrite_digest.get("next_surface_hook"),
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
        f"why_this_stance: {why_this_stance}\n"
        f"key_risks: {key_risks}\n"
        f"what_changes_my_view: {what_changes_my_view}\n"
        f"contradiction_count: {contradiction_count}\n"
        f"blocked_thesis_warnings: {blocked_thesis_warnings}\n"
        f"lead_reason: {underwrite_digest.get('lead_reason')}\n"
        f"primary_thesis: {underwrite_digest.get('primary_thesis')}\n"
        f"top_supporting_facts: {list(underwrite_digest.get('top_supporting_facts') or [])}\n"
        f"top_risk_or_trust_caveat: {underwrite_digest.get('top_risk_or_trust_caveat')}\n"
        f"flip_condition: {underwrite_digest.get('flip_condition')}\n"
        f"next_surface_hook: {underwrite_digest.get('next_surface_hook')}\n"
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
        "signal_items": build_town_signal_items(town, state, geocode=_geocode_town_signal_query),
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
_FLOOR_PRICE_RE = re.compile(r"\b(?:floor price|price floor|downside floor)\b", re.IGNORECASE)
_CASH_FLOW_RE = re.compile(
    r"\b(?:cash[ -]?flow(?: projection)?|run cash[ -]?flow|rental potential|rent potential)\b",
    re.IGNORECASE,
)
_COMP_SET_RE = re.compile(
    r"\b(?:full )?comp set\b|\bwhich comps\b|\bwhy were these comps chosen\b|\bdrill into (?:the )?cma\b",
    re.IGNORECASE,
)
_ENTRY_POINT_RE = re.compile(
    r"\b(?:good|best|right|ideal)\s+entry point\b|\bwhat should i offer\b|\boffer price\b|\bwhere (?:should|would) (?:i|we) (?:buy|come in)\b",
    re.IGNORECASE,
)
_TRUST_GAPS_RE = re.compile(
    r"\bwhat data is missing\b|\bmissing or estimated\b|\bwhat(?:'| i)?s estimated\b|\bwhat(?:'| i)?s missing\b",
    re.IGNORECASE,
)
_DOWNSIDE_DETAIL_RE = re.compile(
    r"\bdownside case\b|\bbear case\b|\bstress case\b|\bworst case\b|\bdownside\b",
    re.IGNORECASE,
)
_RENT_WORKABILITY_RE = re.compile(
    r"\bwhat rent would make this (?:deal )?work\b|\bwhat rent makes this work\b|\bwhat would it need to rent for\b|\bbreak[- ]even rent\b",
    re.IGNORECASE,
)
_VALUE_CHANGE_RE = re.compile(
    r"\bwhat would change (?:your|the) value view\b|\bwhat changes your view\b",
    re.IGNORECASE,
)


def _reference_ask_price(pid: str | None, session: Session) -> float | None:
    live = session.current_live_listing or session.selected_search_result or {}
    if isinstance(live, dict):
        live_pid = live.get("property_id") or live.get("external_id")
        ask_price = live.get("ask_price")
        if (
            pid
            and isinstance(live_pid, str)
            and live_pid == pid
            and isinstance(ask_price, (int, float))
        ):
            return float(ask_price)
    if pid:
        try:
            summary = get_property_summary(pid)
        except ToolUnavailable:
            summary = {}
        ask_price = summary.get("ask_price")
        if isinstance(ask_price, (int, float)):
            return float(ask_price)
    ask_price = live.get("ask_price") if isinstance(live, dict) else None
    if isinstance(ask_price, (int, float)):
        return float(ask_price)
    return None


def _normalize_penalty(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if numeric > 1.0:
        numeric /= 100.0
    return max(numeric, 0.0)


def _trust_payload_from_thesis(
    thesis: dict[str, object],
    facts: dict[str, object],
) -> dict[str, object]:
    trust_summary = dict(thesis.get("trust_summary") or {})
    return {
        "address": facts.get("address"),
        "town": facts.get("town"),
        "state": facts.get("state"),
        "confidence": trust_summary.get("confidence"),
        "band": trust_summary.get("band"),
        "field_completeness": trust_summary.get("field_completeness"),
        "estimated_reliance": trust_summary.get("estimated_reliance"),
        "contradiction_count": trust_summary.get("contradiction_count") or thesis.get("contradiction_count"),
        "blocked_thesis_warnings": list(
            trust_summary.get("blocked_thesis_warnings")
            or thesis.get("blocked_thesis_warnings")
            or []
        ),
        "trust_flags": list(trust_summary.get("trust_flags") or []),
        "why_this_stance": list(thesis.get("why_this_stance") or []),
        "what_changes_my_view": list(thesis.get("what_changes_my_view") or []),
    }


def _parse_turn_overrides(text: str, *, pid: str | None, session: Session) -> dict[str, object]:
    return parse_overrides(text, reference_price=_reference_ask_price(pid, session))


def _analysis_overrides(
    text: str,
    *,
    pid: str | None,
    session: Session,
) -> tuple[dict[str, object], dict[str, object]]:
    """Return (effective_overrides, explicit_user_overrides).

    Saved property metadata can lag the live listing ask. When the current
    pinned listing points at the same property and carries a fresher price,
    underwrite on that price for this turn without treating it like a user
    requested what-if scenario.
    """
    explicit = _parse_turn_overrides(text, pid=pid, session=session)
    effective = dict(explicit)
    if "ask_price" in effective or not pid:
        return effective, explicit

    live = session.current_live_listing or session.selected_search_result or {}
    if not isinstance(live, dict):
        return effective, explicit

    live_pid = live.get("property_id") or live.get("external_id")
    live_ask = live.get("ask_price")
    if not (
        isinstance(live_pid, str)
        and live_pid == pid
        and isinstance(live_ask, (int, float))
    ):
        return effective, explicit

    summary_ask = None
    try:
        summary = get_property_summary(pid)
    except ToolUnavailable:
        summary = {}
    raw_summary_ask = summary.get("ask_price") if isinstance(summary, dict) else None
    if isinstance(raw_summary_ask, (int, float)):
        summary_ask = float(raw_summary_ask)

    synced_ask = float(live_ask)
    if summary_ask is not None and abs(summary_ask - synced_ask) < 0.5:
        return effective, explicit

    effective["ask_price"] = synced_ask
    return effective, explicit


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
        if comp.get("source_label"):
            bits.append(str(comp["source_label"]))
        if comp.get("beds") is not None and comp.get("baths") is not None:
            bits.append(f"{comp['beds']}bd/{comp['baths']}ba")
        if comp.get("ask_price") is not None:
            bits.append(_money(comp.get("ask_price")))
        if isinstance(comp.get("blocks_to_beach"), (int, float)):
            bits.append(f"{comp['blocks_to_beach']:.1f} blocks to beach")
        tail = ", ".join(bits)
        lines.append(f"- {comp.get('property_id')}" + (f" — {tail}" if tail else ""))
    return lines


def _comp_row_from_cma(comp: ComparableProperty) -> dict[str, object]:
    return {
        "property_id": comp.property_id,
        "address": comp.address,
        "beds": comp.beds,
        "baths": comp.baths,
        "ask_price": comp.ask_price,
        "blocks_to_beach": comp.blocks_to_beach,
        "source_label": comp.source_label,
        "source_summary": comp.source_summary,
    }


def _comps_preview_from_cma(
    pid: str,
    subject_ask: float | None,
    comps: list[dict[str, object]],
) -> dict[str, object] | None:
    rows: list[dict[str, object]] = []
    prices: list[float] = []
    for comp in comps:
        if comp.get("property_id") == pid:
            continue
        price = comp.get("ask_price") or comp.get("price")
        premium_pct = None
        if isinstance(price, (int, float)) and isinstance(subject_ask, (int, float)) and subject_ask:
            premium_pct = round((float(price) - float(subject_ask)) / float(subject_ask), 4)
            prices.append(float(price))
        rows.append(
            {
                "property_id": comp.get("property_id"),
                "address": comp.get("address"),
                "beds": comp.get("beds"),
                "baths": comp.get("baths"),
                "sqft": comp.get("sqft"),
                "price": price,
                "premium_pct": premium_pct,
            }
        )
    if not rows:
        return None
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
    overrides, _ = _analysis_overrides(text, pid=pid, session=session)
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
        "entry_basis": rent_outlook.entry_basis,
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
        "market_context_note": rent_outlook.market_context_note,
        "basis_to_rent_framing": rent_outlook.basis_to_rent_framing,
        "owner_occupy_then_rent": rent_outlook.owner_occupy_then_rent,
        "carry_offset_ratio": rent_outlook.carry_offset_ratio,
        "break_even_rent": rent_outlook.break_even_rent,
        "break_even_probability": rent_outlook.break_even_probability,
        "adjusted_rent_confidence": rent_outlook.adjusted_rent_confidence,
        "rent_haircut_pct": rent_outlook.rent_haircut_pct,
        "burn_chart_payload": dict(rent_outlook.burn_chart_payload or {}),
        "ramp_chart_payload": dict(rent_outlook.ramp_chart_payload or {}),
    }

    if overrides or horizon_years is not None or _mentions_owner_occupy_then_rent(text):
        try:
            fit = get_strategy_fit(pid, overrides=overrides)
        except ToolUnavailable:
            fit = {}
        if fit:
            session.last_strategy_view = {
                "address": summary.get("address"),
                "town": summary.get("town"),
                "state": summary.get("state"),
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
    rent_workability_mode = bool(_RENT_WORKABILITY_RE.search(text))
    lines = [
        f"Plain-English rent read: this place looks closer to {money(monthly)} a month in rent (source: {source}).",
        f"After vacancy and management drag, the working monthly income is closer to {money(effective)}.",
    ]
    if label or isinstance(ease, (int, float)):
        ease_s = f"{ease:.0f}/100" if isinstance(ease, (int, float)) else "n/a"
        lines.append(f"Renting it out looks {label or 'unclear'} right now (ease score {ease_s}).")
    if isinstance(noi, (int, float)):
        lines.append(f"That works out to about {money(noi)} a year after operating costs.")
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
    if rent_workability_mode:
        break_even = rent_outlook.break_even_rent
        gap = (
            float(break_even) - float(effective)
            if isinstance(break_even, (int, float)) and isinstance(effective, (int, float))
            else None
        )
        targeted_lines: list[str] = []
        if gap is not None and gap > 0:
            targeted_lines.append(
                f"On the current assumptions, this does not work as a rental yet. Briarwood would want closer to {money(break_even)}/mo to break even versus an effective rent nearer {money(effective)}/mo."
            )
        elif isinstance(break_even, (int, float)):
            targeted_lines.append(
                f"On the current assumptions, the rental story works around {money(break_even)}/mo, which is roughly where Briarwood's break-even line sits."
            )
        else:
            targeted_lines.append(
                f"Briarwood can see the current rent around {money(effective)}, but it does not have a clean break-even threshold yet."
            )
        if isinstance(rent_outlook.break_even_probability, (int, float)):
            targeted_lines.append(
                f"The odds of actually reaching break-even inside the modeled hold are only about {rent_outlook.break_even_probability:.0%}."
            )
        if isinstance(rent_outlook.carry_offset_ratio, (int, float)):
            targeted_lines.append(
                f"Right now rent is only covering about {rent_outlook.carry_offset_ratio:.2f}x of monthly cost."
            )
        if rent_outlook.market_context_note:
            targeted_lines.append(rent_outlook.market_context_note)
        narrative, report = compose_section_followup(
            llm=llm,
            section="rent_workability",
            question=text,
            payload=asdict(rent_outlook),
            fallback=" ".join(targeted_lines),
        )
        session.last_verifier_report = report
        return narrative + chart_line if chart_line and not narrative.endswith(chart_line) else narrative
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
    overrides, _ = _analysis_overrides(text, pid=pid, session=session)
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
    basis_label = str(proj.get("basis_label") or "ask")

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

    if _FLOOR_PRICE_RE.search(text):
        lines = []
        if isinstance(bear, (int, float)):
            lines.append(
                f"Working floor: around {money(bear)} based on the bear case versus today's {basis_label} of {money(ask)}."
            )
        if isinstance(stress, (int, float)):
            lines.append(
                f"Hard-pullback floor: closer to {money(stress)} if the market really breaks against you."
            )
        if not lines:
            lines.append(
                f"Briarwood doesn't have a downside floor yet beyond the current {basis_label} of {money(ask)}."
            )
        return "\n".join(lines) + chart_line

    if llm is None:
        session.last_partial_data_warnings.append(
            {
                "section": "projection_narration",
                "reason": "llm_unavailable",
                "verdict_reliable": True,
            }
        )
        lines = [
            f"Most likely outcome: Briarwood's base case lands near {money(base)} over the next five years versus today's {basis_label} of {money(ask)}.",
            f"Upside case: {money(bull)} ({_delta(bull)}).",
            f"Downside case: {money(bear)} ({_delta(bear)}).",
        ]
        if isinstance(stress, (int, float)):
            lines.append(f"Hard-pullback case: {money(stress)} ({_delta(stress)}) using a historical drawdown overlay.")
        spread = proj.get("spread")
        if isinstance(spread, (int, float)):
            lines.append(f"The gap between upside and downside is about {money(spread)}.")
        return "\n".join(lines) + chart_line

    system = load_prompt("projection")
    user = (
        f"User question: {text}\n\n"
        f"overrides_applied: {overrides or 'none'}\n"
        f"basis_label: {basis_label}\n"
        f"ask_price: {ask}\n"
        f"bull_case_value: {bull} ({_delta(bull)})\n"
        f"base_case_value: {base} ({_delta(base)})\n"
        f"bear_case_value: {bear} ({_delta(bear)})\n"
        f"stress_case_value: {stress}\n"
        f"base_growth_rate: {proj.get('base_growth_rate')}\n"
        f"bull_growth_rate: {proj.get('bull_growth_rate')}\n"
        f"bear_growth_rate: {proj.get('bear_growth_rate')}\n"
    )
    fallback = lambda: f"Most likely outcome: about {money(base)} over five years versus today's {basis_label} of {money(ask)}."
    projection_inputs = {
        "overrides_applied": overrides or {},
        "basis_label": basis_label,
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
    overrides, _ = _analysis_overrides(text, pid=pid, session=session)
    trust_mode = bool(_TRUST_GAPS_RE.search(text))
    downside_mode = bool(_DOWNSIDE_DETAIL_RE.search(text))
    if trust_mode:
        try:
            thesis = get_value_thesis(pid, overrides=overrides)
        except ToolUnavailable as exc:
            return f"I couldn't pull the trust summary ({exc})."
        session.current_property_id = pid
        facts = _load_property_facts(pid)
        session.last_trust_view = _trust_payload_from_thesis(thesis, facts)
        flags = list(session.last_trust_view.get("trust_flags") or [])
        blocked = list(session.last_trust_view.get("blocked_thesis_warnings") or [])
        field_completeness = session.last_trust_view.get("field_completeness")
        estimated_reliance = session.last_trust_view.get("estimated_reliance")
        lines: list[str] = []
        if flags:
            lines.append(
                "The main things still weakening confidence are "
                + ", ".join(str(flag).replace("_", " ") for flag in flags[:3])
                + "."
            )
        if isinstance(field_completeness, (int, float)):
            lines.append(f"Field completeness is sitting around {field_completeness:.0%}.")
        if isinstance(estimated_reliance, (int, float)):
            lines.append(f"Estimated/defaulted inputs make up about {estimated_reliance:.0%} of the current read.")
        if blocked:
            lines.append("The biggest unresolved caution is " + str(blocked[0]) + ".")
        if not lines:
            lines.append("Nothing major is missing enough to materially weaken the read right now, but this still deserves normal underwriting discipline.")
        narrative, report = compose_section_followup(
            llm=llm,
            section="trust",
            question=text,
            payload=session.last_trust_view,
            fallback=" ".join(lines),
        )
        session.last_verifier_report = report
        return narrative
    try:
        profile = get_risk_profile(pid, overrides=overrides)
    except ToolUnavailable as exc:
        return f"I couldn't pull a risk profile ({exc})."
    session.current_property_id = pid

    from briarwood.agent.rendering import ChartUnavailable, render_chart as _render

    ask = profile.get("ask_price")
    bear = profile.get("bear_case_value")
    stress = profile.get("stress_case_value")
    if downside_mode and (bear is None or stress is None):
        try:
            projection = get_projection(pid, overrides=overrides)
        except ToolUnavailable:
            projection = {}
        bear = bear if isinstance(bear, (int, float)) else projection.get("bear_case_value")
        stress = stress if isinstance(stress, (int, float)) else projection.get("stress_case_value")
    risk_flags = profile.get("risk_flags") or []
    trust_flags = profile.get("trust_flags") or []

    facts = _load_property_facts(pid)
    total_penalty = _normalize_penalty(profile.get("total_penalty"))
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

    if downside_mode:
        lines = []
        if isinstance(bear, (int, float)) and isinstance(ask, (int, float)):
            lines.append(
                f"In Briarwood's downside case, value drifts closer to {money(bear)} versus today's reference price of {money(ask)}."
            )
        if isinstance(stress, (int, float)):
            lines.append(f"If the setup really breaks against you, the harder-pullback case is closer to {money(stress)}.")
        if risk_flags:
            lines.append(f"The main drivers behind that downside are {', '.join(risk_flags[:3])}.")
        if trust_flags:
            lines.append(f"Confidence is also being capped by {', '.join(trust_flags[:2])}.")
        if not lines:
            lines.append("Briarwood does not see a well-defined downside case yet beyond the current risk flags.")
        narrative, report = compose_section_followup(
            llm=llm,
            section="downside",
            question=text,
            payload=session.last_risk_view,
            fallback=" ".join(lines),
        )
        session.last_verifier_report = report
        return narrative + chart_line if chart_line and not narrative.endswith(chart_line) else narrative

    if llm is None:
        session.last_partial_data_warnings.append(
            {
                "section": "downside_risk_narration",
                "reason": "llm_unavailable",
                "verdict_reliable": True,
            }
        )
        lines = [f"Biggest downside check for {pid}:"]
        if risk_flags:
            lines.append(f"The main risk drivers are {', '.join(risk_flags)}.")
        if trust_flags:
            lines.append(f"Confidence is also limited by {', '.join(trust_flags)}.")
        if isinstance(bear, (int, float)) and isinstance(ask, (int, float)):
            lines.append(f"In a downside case, value falls closer to {money(bear)} versus the current ask of {money(ask)}.")
        if isinstance(stress, (int, float)):
            lines.append(f"In a deeper stress case, it compresses toward {money(stress)}.")
        if len(lines) == 1:
            lines.append("No major cached risk drivers are surfacing yet.")
        return "\n".join(lines) + chart_line

    system = load_prompt("risk")
    risk_inputs = {
        "risk_flags": list(risk_flags),
        "trust_flags": list(trust_flags),
        "ask_price": ask,
        "bear_case_value": bear,
        "stress_case_value": stress,
        "total_penalty": total_penalty,
        "key_risks": list(profile.get("key_risks") or []),
    }
    user = (
        f"User question: {text}\n\n"
        f"risk_flags: {risk_flags}\n"
        f"trust_flags: {trust_flags}\n"
        f"ask_price: {ask}\n"
        f"bear_case_value: {bear}\n"
        f"stress_case_value: {stress}\n"
        f"total_penalty: {total_penalty}\n"
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
    overrides, _ = _analysis_overrides(text, pid=pid, session=session)
    cma_mode = bool(_CMA_RE.search(text))
    comp_set_mode = bool(_COMP_SET_RE.search(text))
    entry_point_mode = bool(_ENTRY_POINT_RE.search(text))
    value_change_mode = bool(_VALUE_CHANGE_RE.search(text))
    try:
        thesis = get_value_thesis(pid, overrides=overrides)
        cma_result = get_cma(pid, overrides=overrides) if (cma_mode or comp_set_mode or entry_point_mode) else None
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
    # F2: value_thesis.comps must only be comps that fed fair value (valuation
    # module's comps_used). Live-market CMA rows are surfaced separately via
    # `last_market_support_view` so the UI can label each panel honestly.
    thesis_comps = list(thesis.get("comps") or [])
    cma_comps = [_comp_row_from_cma(comp) for comp in (cma_result.comps if cma_result else [])]
    comps = thesis_comps

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
        "why_this_stance": list(thesis.get("why_this_stance") or []),
        "what_changes_my_view": list(thesis.get("what_changes_my_view") or []),
        "trust_summary": dict(thesis.get("trust_summary") or {}),
        "contradiction_count": thesis.get("contradiction_count"),
        "blocked_thesis_warnings": list(thesis.get("blocked_thesis_warnings") or []),
        "risk_adjusted_fair_value": thesis.get("risk_adjusted_fair_value"),
        "required_discount": thesis.get("required_discount"),
        "comp_selection_summary": thesis.get("comp_selection_summary"),
        "comps": list(comps),
    }
    try:
        session.last_market_support_view = _build_market_support_view(
            None,
            cma_result,
            address=edge_facts.get("address"),
            town=edge_facts.get("town"),
            state=edge_facts.get("state"),
        )
    except Exception as exc:
        logger.warning("edge market support build failed for %s: %s", pid, exc)
        session.last_market_support_view = None
    if (cma_mode or comp_set_mode or entry_point_mode) and cma_result is not None:
        session.last_comps_preview = _comps_preview_from_cma(pid, ask, comps or cma_comps)

    if comp_set_mode:
        fallback_lines = [
            (thesis.get("comp_selection_summary") or (cma_result.comp_selection_summary if cma_result else None) or "These are the comps Briarwood is leaning on for this read.")
        ]
        if comps:
            chosen = [comp for comp in comps if comp.get("feeds_fair_value") is True]
            contextual = [comp for comp in comps if comp.get("feeds_fair_value") is False]
            if chosen:
                fallback_lines.append(
                    "The fair-value set is led by "
                    + "; ".join(
                        f"{comp.get('address')} ({comp.get('source_label') or 'comp'})"
                        for comp in chosen[:3]
                        if comp.get("address")
                    )
                    + "."
                )
            elif contextual:
                fallback_lines.append(
                    "Right now the visible comp table is still more contextual than fully selected into fair value."
                )
            reasons = [
                str(comp.get("inclusion_reason") or comp.get("source_summary") or "")
                for comp in comps[:2]
                if comp.get("inclusion_reason") or comp.get("source_summary")
            ]
            if reasons:
                fallback_lines.append("Why they are here: " + " ".join(reasons[:2]))
        narrative, report = compose_section_followup(
            llm=llm,
            section="comp_set",
            question=text,
            payload={
                "ask_price": ask,
                "fair_value_base": fair,
                "comp_selection_summary": thesis.get("comp_selection_summary") or (cma_result.comp_selection_summary if cma_result else None),
                "comps": list(comps),
            },
            fallback=" ".join(line for line in fallback_lines if line),
        )
        session.last_verifier_report = report
        return narrative + chart_line if chart_line and not narrative.endswith(chart_line) else narrative

    if entry_point_mode:
        target = thesis.get("risk_adjusted_fair_value") or fair
        required_discount = thesis.get("required_discount")
        fallback_lines = []
        if isinstance(target, (int, float)) and isinstance(ask, (int, float)):
            fallback_lines.append(
                f"The cleanest entry point is closer to {money(target)}, not the current ask of {money(ask)}."
            )
        elif isinstance(fair, (int, float)):
            fallback_lines.append(
                f"The deal gets more interesting closer to Briarwood's fair-value read around {money(fair)}."
            )
        if isinstance(required_discount, (int, float)):
            fallback_lines.append(
                f"That implies demanding roughly {required_discount:.0%} off today's pricing before getting more constructive."
            )
        if thesis.get("what_changes_my_view"):
            fallback_lines.append(str(list(thesis.get("what_changes_my_view") or [])[0]))
        narrative, report = compose_section_followup(
            llm=llm,
            section="entry_point",
            question=text,
            payload={
                "ask_price": ask,
                "fair_value_base": fair,
                "risk_adjusted_fair_value": thesis.get("risk_adjusted_fair_value"),
                "required_discount": required_discount,
                "what_changes_my_view": list(thesis.get("what_changes_my_view") or []),
            },
            fallback=" ".join(fallback_lines),
        )
        session.last_verifier_report = report
        return narrative + chart_line if chart_line and not narrative.endswith(chart_line) else narrative

    if value_change_mode:
        change_lines = list(thesis.get("what_changes_my_view") or [])
        if not change_lines:
            change_lines = list(thesis.get("what_must_be_true") or [])
        fallback = (
            "The fastest way to improve Briarwood's view is "
            + "; ".join(change_lines[:3])
            if change_lines
            else "There is not a single dominant change-driver yet beyond tightening the underwriting inputs."
        )
        narrative, report = compose_section_followup(
            llm=llm,
            section="value_change",
            question=text,
            payload={
                "what_changes_my_view": list(thesis.get("what_changes_my_view") or []),
                "what_must_be_true": list(thesis.get("what_must_be_true") or []),
                "trust_summary": dict(thesis.get("trust_summary") or {}),
            },
            fallback=fallback,
        )
        session.last_verifier_report = report
        return narrative + chart_line if chart_line and not narrative.endswith(chart_line) else narrative

    if llm is None:
        session.last_partial_data_warnings.append(
            {
                "section": "value_thesis_narration",
                "reason": "llm_unavailable",
                "verdict_reliable": True,
            }
        )
        lines = [f"Plain-English value read for {pid}:"]
        lines.append(
            f"The asking price is {money(ask)} versus a fair-value anchor around {money(fair)}"
            + (f" ({prem:+.1%})." if isinstance(prem, (int, float)) else ".")
        )
        if thesis.get("pricing_view"):
            lines.append(f"That leaves the deal looking {str(thesis['pricing_view']).replace('_', ' ')}.")
        if thesis.get("value_drivers"):
            drivers = thesis.get("value_drivers") or []
            lines.append(f"Main support for that view: {'; '.join(str(item) for item in drivers)}")
        if thesis.get("key_value_drivers"):
            lines.append(f"Value drivers: {'; '.join(thesis['key_value_drivers'])}")
        if thesis.get("what_must_be_true"):
            lines.append(f"What has to go right: {'; '.join(thesis['what_must_be_true'])}")
        comp_summary = thesis.get("comp_selection_summary") or (cma_result.comp_selection_summary if cma_result else None)
        if comp_summary:
            lines.append(f"Comp context: {comp_summary}")
        # F2: value_thesis comps are the valuation-module set. For CMA-mode
        # narrative we still want to list the live market comps when that is
        # what the user asked about — those rows live on cma_result, not thesis.
        narrative_comps = comps or cma_comps
        lines.extend(_format_cma_comp_lines(narrative_comps))
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
        "comp_selection_summary": thesis.get("comp_selection_summary") or (cma_result.comp_selection_summary if cma_result else None),
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
        f"comp_selection_summary: {thesis.get('comp_selection_summary') or (cma_result.comp_selection_summary if cma_result else 'none')}\n"
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
    fallback = f"The asking price is {money(ask)} versus a fair-value anchor around {money(fair)}."
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
    overrides, _ = _analysis_overrides(text, pid=pid, session=session)
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
        session.last_partial_data_warnings.append(
            {
                "section": "strategy_narration",
                "reason": "llm_unavailable",
                "verdict_reliable": True,
            }
        )
        lines = [f"Best way to play {pid} right now:"]
        if fit.get("best_path"):
            lines.append(f"The strongest path is {fit['best_path']}.")
        if fit.get("rental_ease_label"):
            coc = fit.get("cash_on_cash_return")
            coc_s = f"{coc:.1%}" if isinstance(coc, (int, float)) else "n/a"
            lines.append(
                f"If you rent it, the outlook is {fit['rental_ease_label']} "
                f"(ease {fit.get('rental_ease_score')}, monthly cash flow {money(fit.get('monthly_cash_flow'))}, "
                f"cash-on-cash {coc_s})."
            )
        if fit.get("pricing_view"):
            lines.append(f"On price alone, it looks {fit['pricing_view']}.")
        if fit.get("recommendation"):
            lines.append(str(fit["recommendation"]))
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


def _browse_chat_tier_artifact(
    pid: str,
    user_text: str,
    overrides: dict[str, object] | None,
) -> dict[str, object] | None:
    """Run the consolidated chat-tier plan for a BROWSE turn.

    Cycle 3 of OUTPUT_QUALITY_HANDOFF_PLAN.md replaces the BROWSE handler's
    ~5 separate ``run_routed_report`` invocations (one per tools.py call)
    with a single ``run_chat_tier_analysis`` call that runs all 23 scoped
    modules once. Returns ``None`` if the inputs.json is missing or
    property loading fails — callers fall through to the legacy per-tool
    path so the user still sees a response. The 13 modules previously
    dormant for chat-tier traffic (per AUDIT_OUTPUT_QUALITY_2026-04-25
    §9.3) — `comparable_sales`, `location_intelligence`,
    `strategy_classifier`, `arv_model`, etc. — are now part of the
    consolidated plan.
    """

    from briarwood.agent.overrides import inputs_with_overrides
    from briarwood.agent.router import AnswerType
    from briarwood.agent.tools import SAVED_PROPERTIES_DIR
    from briarwood.inputs.property_loader import load_property_from_json
    from briarwood.orchestrator import run_chat_tier_analysis
    from briarwood.runner_common import (
        _prepare_property_input,
        validate_property_input,
    )

    inputs_path = SAVED_PROPERTIES_DIR / pid / "inputs.json"
    if not inputs_path.exists():
        return None
    try:
        with inputs_with_overrides(inputs_path, overrides or {}) as effective_path:
            property_input = load_property_from_json(effective_path)
            validate_property_input(property_input)
            _prepare_property_input(property_input)
            property_data = property_input.to_dict()
        return run_chat_tier_analysis(
            property_data,
            AnswerType.BROWSE,
            user_text,
        )
    except Exception as exc:  # noqa: BLE001 — caller falls through to legacy per-tool path
        logger.warning("browse chat-tier consolidation failed for %s: %s", pid, exc)
        return None


def _module_metrics_from_artifact(
    artifact: dict[str, object],
    module_name: str,
) -> dict[str, object]:
    """Extract ``outputs[module].data.metrics`` from a chat-tier artifact.

    Mirrors the duck-typed accessor in tools.py functions
    (``get_projection``, ``get_strategy_fit``, ``get_rent_estimate``) so
    the inline replacements below produce the same field shapes.
    """

    module_results = artifact.get("module_results") or {}
    outputs = module_results.get("outputs") or {} if isinstance(module_results, dict) else {}
    entry = outputs.get(module_name)
    if not isinstance(entry, dict):
        return {}
    data = entry.get("data") or {}
    if not isinstance(data, dict):
        return {}
    metrics = data.get("metrics") or {}
    return metrics if isinstance(metrics, dict) else {}


def _browse_projection_from_artifact(
    artifact: dict[str, object],
    pid: str,
    overrides: dict[str, object] | None,
) -> dict[str, object] | None:
    """Inline equivalent of ``tools.get_projection`` over a chat-tier artifact."""

    metrics = _module_metrics_from_artifact(artifact, "resale_scenario")
    if not metrics:
        # Fallback: bull_base_bear is wrapped by resale_scenario today; if for
        # some reason resale_scenario is absent, try the underlying module.
        metrics = _module_metrics_from_artifact(artifact, "bull_base_bear")
    if not metrics:
        return None
    keys = (
        "ask_price",
        "bull_case_value",
        "base_case_value",
        "bear_case_value",
        "stress_case_value",
        "spread",
        "bull_total_adjustment_pct",
        "base_total_adjustment_pct",
        "bear_total_adjustment_pct",
        "bull_growth_rate",
        "base_growth_rate",
        "bear_growth_rate",
        "bcv_anchor",
    )
    payload: dict[str, object] = {"property_id": pid, **{k: metrics.get(k) for k in keys}}
    ask_override = (overrides or {}).get("ask_price")
    if isinstance(ask_override, (int, float)):
        payload["listing_ask_price"] = metrics.get("ask_price")
        payload["ask_price"] = float(ask_override)
        payload["basis_label"] = "entry basis"
    else:
        payload["basis_label"] = "ask"
    return payload


def _browse_strategy_fit_from_artifact(
    artifact: dict[str, object],
    pid: str,
) -> dict[str, object] | None:
    """Inline equivalent of ``tools.get_strategy_fit`` over a chat-tier artifact."""

    unified = artifact.get("unified_output") or {}
    if not isinstance(unified, dict):
        unified = {}
    rental = _module_metrics_from_artifact(artifact, "rental_option")
    carry = _module_metrics_from_artifact(artifact, "carry_cost")
    val = _module_metrics_from_artifact(artifact, "valuation")
    return {
        "property_id": pid,
        "best_path": unified.get("best_path"),
        "recommendation": unified.get("recommendation"),
        "primary_value_source": unified.get("primary_value_source"),
        "pricing_view": val.get("pricing_view"),
        "rental_ease_label": rental.get("rental_ease_label"),
        "rental_ease_score": rental.get("rental_ease_score"),
        "rent_support_score": rental.get("rent_support_score"),
        "liquidity_score": rental.get("liquidity_score"),
        "monthly_cash_flow": carry.get("monthly_cash_flow"),
        "cash_on_cash_return": carry.get("cash_on_cash_return"),
        "annual_noi": carry.get("annual_noi"),
    }


def _browse_rent_payload_from_artifact(
    artifact: dict[str, object],
    pid: str,
) -> dict[str, object]:
    """Inline equivalent of ``tools.get_rent_estimate`` over a chat-tier artifact."""

    carry = _module_metrics_from_artifact(artifact, "carry_cost")
    rental = _module_metrics_from_artifact(artifact, "rental_option")
    return {
        "property_id": pid,
        "monthly_rent": carry.get("monthly_rent"),
        "effective_monthly_rent": carry.get("effective_monthly_rent"),
        "rent_source_type": carry.get("rent_source_type"),
        "annual_noi": carry.get("annual_noi"),
        "monthly_cash_flow": carry.get("monthly_cash_flow"),
        "cash_on_cash_return": carry.get("cash_on_cash_return"),
        "rental_ease_score": rental.get("rental_ease_score"),
        "rental_ease_label": rental.get("rental_ease_label"),
        "rent_support_score": rental.get("rent_support_score"),
        "estimated_days_to_rent": rental.get("estimated_days_to_rent"),
    }


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
    overrides, _ = _analysis_overrides(text, pid=pid, session=session)
    try:
        summary = get_property_summary(pid)
    except ToolUnavailable:
        summary = {}

    chat_tier_artifact = _browse_chat_tier_artifact(pid, text, overrides)

    if chat_tier_artifact is not None:
        unified = chat_tier_artifact.get("unified_output") or {}
        if not isinstance(unified, dict):
            unified = {}
        try:
            brief = build_property_brief(pid, summary, unified)
        except Exception as exc:  # noqa: BLE001 — fall through to legacy path
            logger.warning("browse build_property_brief failed for %s: %s", pid, exc)
            chat_tier_artifact = None
    if chat_tier_artifact is None:
        # Legacy per-tool path. Preserved for cases where the consolidated
        # plan can't run (no inputs.json, validation failure). Cycle 5 plans
        # to retire this fallback once handler coverage is proven.
        try:
            brief = get_property_brief(pid, overrides=overrides)
        except ToolUnavailable as exc:
            return f"I couldn't build a property brief ({exc})."
    session.current_property_id = pid
    cma_result: CMAResult | None = None
    try:
        cma_result = get_cma(pid, overrides=overrides)
    except Exception as exc:
        logger.warning("browse CMA build failed for %s: %s", pid, exc)
        cma_result = None
    projection: dict[str, object] | None = None
    strategy_fit: dict[str, object] | None = None
    rent_outlook: RentOutlook | None = None
    rent_payload: dict[str, object] | None = None
    if chat_tier_artifact is not None:
        projection = _browse_projection_from_artifact(chat_tier_artifact, pid, overrides)
        strategy_fit = _browse_strategy_fit_from_artifact(chat_tier_artifact, pid)
        rent_payload = _browse_rent_payload_from_artifact(chat_tier_artifact, pid)
    else:
        try:
            projection = get_projection(pid, overrides=overrides)
        except Exception as exc:
            logger.warning("browse projection failed for %s: %s", pid, exc)
        try:
            strategy_fit = get_strategy_fit(pid, overrides=overrides)
        except Exception as exc:
            logger.warning("browse strategy fit failed for %s: %s", pid, exc)
        try:
            rent_payload = get_rent_estimate(pid, overrides=overrides)
        except Exception as exc:
            logger.warning("browse rent estimate failed for %s: %s", pid, exc)
    try:
        if rent_payload is not None:
            rent_outlook = get_rent_outlook(
                pid,
                years=3,
                overrides=overrides,
                rent_payload=rent_payload,
                property_summary=summary,
            )
    except Exception as exc:
        logger.warning("browse rent outlook failed for %s: %s", pid, exc)
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
            cma=cma_result,
            rent_outlook=rent_outlook,
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
    _populate_browse_slots(
        session,
        pid=pid,
        brief=brief,
        summary=summary if isinstance(summary, dict) else None,
        neighbors=neighbors,
        cma_result=cma_result,
        projection=projection,
        strategy_fit=strategy_fit,
        rent_outlook=rent_outlook,
    )
    _set_workflow_state(session, contract_type="property_brief", analysis_mode="browse")
    fallback = _format_browse_from_presentation(
        presentation_payload,
        brief,
        neighbors,
    ) or _format_browse_brief(brief, neighbors)

    # Cycle 4 of OUTPUT_QUALITY_HANDOFF_PLAN.md: when the consolidated chat-tier
    # artifact is available, run the Layer 3 LLM synthesizer over the full
    # UnifiedIntelligenceOutput before falling back to the narrow-slice
    # composer. The synthesizer sees the entire unified output (~all 23
    # modules' outputs co-resident) instead of the per-handler payload that
    # _browse_surface_payload builds, so its prose can lead with whatever
    # the user's intent contract demands and weave in any of the modules
    # that were dormant before Cycle 3.
    response: str = ""
    report: dict[str, object] | None = None
    if chat_tier_artifact is not None and llm is not None:
        unified = chat_tier_artifact.get("unified_output") or {}
        if isinstance(unified, dict) and unified:
            from briarwood.intent_contract import build_contract_from_answer_type
            from briarwood.synthesis.llm_synthesizer import synthesize_with_llm

            intent = build_contract_from_answer_type(
                decision.answer_type.value,
                float(decision.confidence or 0.0),
            )
            synth_prose, synth_report = synthesize_with_llm(
                unified=unified,
                intent=intent,
                llm=llm,
            )
            if synth_prose:
                response = synth_prose
                report = synth_report

    if not response:
        # Composer fallback. Triggers when (a) the chat-tier artifact is
        # missing (no inputs.json), (b) llm is None, or (c) the synthesizer
        # returned empty prose (verifier blocked, blank draft, exception).
        browse_inputs = _browse_surface_payload(brief=brief, session=session, neighbors=neighbors)
        response, report = compose_browse_surface(
            llm=llm,
            payload=browse_inputs,
            fallback=fallback,
        )
    _remember_surface_output(
        session,
        narrative=response,
        presentation_payload=presentation_payload,
    )
    if report is not None:
        session.last_verifier_report = report
    if promotion and promotion.property_id == pid:
        intro = (
            f"Briarwood {'saved' if promotion.created_new else 'reused'} {brief.address or pid} "
            f"as {pid} from live Zillow discovery."
        )
        response = "\n".join([intro, *_promotion_intake_lines(promotion), *_promotion_enrichment_lines(enrichment), response])
        session.last_surface_narrative = response
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
        decision.answer_type in {AnswerType.BROWSE, AnswerType.LOOKUP, AnswerType.SEARCH, AnswerType.DECISION}
        and session.current_property_id
        and _COMP_SET_RE.search(text)
    ):
        return RouterDecision(
            answer_type=AnswerType.EDGE,
            confidence=max(decision.confidence, 0.76),
            target_refs=[session.current_property_id],
            reason="comp-set rewrite",
            llm_suggestion=decision.llm_suggestion,
        )
    if (
        decision.answer_type in {AnswerType.BROWSE, AnswerType.LOOKUP, AnswerType.DECISION}
        and session.current_property_id
        and (_ENTRY_POINT_RE.search(text) or _VALUE_CHANGE_RE.search(text))
    ):
        return RouterDecision(
            answer_type=AnswerType.EDGE,
            confidence=max(decision.confidence, 0.76),
            target_refs=[session.current_property_id],
            reason="entry-point rewrite" if _ENTRY_POINT_RE.search(text) else "value-change rewrite",
            llm_suggestion=decision.llm_suggestion,
        )
    if (
        decision.answer_type in {AnswerType.BROWSE, AnswerType.LOOKUP, AnswerType.DECISION, AnswerType.RISK}
        and session.current_property_id
        and _TRUST_GAPS_RE.search(text)
    ):
        return RouterDecision(
            answer_type=AnswerType.RISK,
            confidence=max(decision.confidence, 0.76),
            target_refs=[session.current_property_id],
            reason="trust rewrite",
            llm_suggestion=decision.llm_suggestion,
        )
    if (
        decision.answer_type in {AnswerType.BROWSE, AnswerType.LOOKUP, AnswerType.DECISION, AnswerType.PROJECTION}
        and session.current_property_id
        and _DOWNSIDE_DETAIL_RE.search(text)
    ):
        return RouterDecision(
            answer_type=AnswerType.RISK,
            confidence=max(decision.confidence, 0.76),
            target_refs=[session.current_property_id],
            reason="downside-detail rewrite",
            llm_suggestion=decision.llm_suggestion,
        )
    if (
        decision.answer_type in {AnswerType.BROWSE, AnswerType.LOOKUP, AnswerType.DECISION, AnswerType.PROJECTION}
        and session.current_property_id
        and _RENT_WORKABILITY_RE.search(text)
    ):
        return RouterDecision(
            answer_type=AnswerType.RENT_LOOKUP,
            confidence=max(decision.confidence, 0.76),
            target_refs=[session.current_property_id],
            reason="rent-workability rewrite",
            llm_suggestion=decision.llm_suggestion,
        )
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
        decision.answer_type in {AnswerType.BROWSE, AnswerType.LOOKUP, AnswerType.DECISION}
        and session.current_property_id
        and _FLOOR_PRICE_RE.search(text)
    ):
        return RouterDecision(
            answer_type=AnswerType.PROJECTION,
            confidence=max(decision.confidence, 0.72),
            target_refs=[session.current_property_id],
            reason="floor-price rewrite",
            llm_suggestion=decision.llm_suggestion,
        )
    if (
        decision.answer_type in {AnswerType.BROWSE, AnswerType.LOOKUP, AnswerType.DECISION, AnswerType.PROJECTION}
        and session.current_property_id
        and _CASH_FLOW_RE.search(text)
    ):
        return RouterDecision(
            answer_type=AnswerType.RENT_LOOKUP,
            confidence=max(decision.confidence, 0.72),
            target_refs=[session.current_property_id],
            reason="cash-flow rewrite",
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
        overrides = _parse_turn_overrides(text, pid=session.current_property_id, session=session)
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
