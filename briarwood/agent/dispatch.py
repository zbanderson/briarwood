"""Per-answer-type handlers.

Each handler takes (user_text, router_decision, session, llm_client) and
returns a short response string. Handlers call at most TWO tools. This is
enforced by convention and by test coverage — no generic tool-use loop.
"""

from __future__ import annotations

import re

from briarwood.agent.llm import LLMClient
from briarwood.agent.router import AnswerType, RouterDecision
from briarwood.agent.session import Session
from briarwood.agent.fuzzy_terms import translate
from briarwood.agent.feedback import log_turn as _log_untracked
from briarwood.agent.overrides import parse_overrides, summarize as _override_summary
from briarwood.agent.property_view import PropertyView
from briarwood.agent.tools import (
    ToolUnavailable,
    analyze_property,
    get_projection,
    get_property_summary,
    get_rent_estimate,
    get_risk_profile,
    get_strategy_fit,
    get_value_thesis,
    render_chart,
    research_town,
    search_listings,
    underwrite_matches,
)

MAX_TOOLS_PER_TURN = 2

# Trust flags that trigger auto-research in decision mode. Plan §Phase C:
# only these two — zoning_unverified and weak_town_context. Other flags
# (incomplete_carry_inputs, thin_comp_set) reflect user-input gaps, not
# external data gaps.
_AUTO_RESEARCH_FLAGS = {"weak_town_context", "zoning_unverified"}


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


def _resolve_property_id(
    decision: RouterDecision, session: Session, text: str | None = None
) -> str | None:
    """Resolve a property id from the router refs, then from free text, then session.

    The router extracts hyphenated refs only. Users also type "526 W End Ave"
    or "526 west end avenue avon" — those fall through to the resolver.

    Session fallback is skipped when the user clearly *tried* to reference a
    property (hyphenated slug, street number) but it didn't resolve. Otherwise
    a failed lookup for 1223 silently becomes an answer about the stale 526.
    """
    for ref in decision.target_refs:
        if _SAVED_DIR_EXISTS(ref):
            return ref

    if text:
        from briarwood.agent.resolver import resolve_property_id

        pid, _ = resolve_property_id(text)
        if pid:
            return pid

    if _text_references_unknown_property(decision, text):
        return None

    return session.current_property_id


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


# ---------- LOOKUP ----------


def handle_lookup(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    pid = _resolve_property_id(decision, session, text)
    if pid is None:
        return "Which property? I don't have one loaded yet."
    try:
        summary = get_property_summary(pid)
    except ToolUnavailable as exc:
        return f"I couldn't find summary data ({exc})."
    session.current_property_id = pid

    if llm is None:
        addr = summary.get("address", pid)
        price = summary.get("ask_price")
        price_s = f"${price:,.0f}" if isinstance(price, (int, float)) else "n/a"
        return f"{addr} — ask {price_s}, BCV ${summary.get('bcv', 0):,.0f}, {summary.get('pricing_view', '')}."

    system = (
        "Answer a factual real-estate lookup from the provided property summary. "
        "Be 1-2 sentences. Never invent numbers."
    )
    user = f"Question: {text}\n\nSummary JSON:\n{summary}"
    return llm.complete(system=system, user=user, max_tokens=120).strip()


# ---------- DECISION ----------


def handle_decision(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    pid = _resolve_property_id(decision, session, text)
    if pid is None:
        return "Which property should I underwrite?"
    overrides = parse_overrides(text)
    try:
        view = PropertyView.load(pid, overrides=overrides, depth="decision")
    except ToolUnavailable as exc:
        return f"I couldn't analyze that ({exc})."
    session.current_property_id = pid

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

    if llm is None:
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
        return base

    system = (
        "Compose a 3-5 sentence decision summary from the structured fields provided. "
        "Lead with the stance, cite the trust flags, quote the numbers verbatim — never invent. "
        "Distinguish ask_price (listing) from all_in_basis (post-capex commitment) when they differ. "
        "If a research_update line is provided, include it verbatim."
    )
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
    return llm.complete(system=system, user=user, max_tokens=260).strip()


# ---------- SEARCH (Phase B placeholder) ----------


def handle_search(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    translation = translate(text)
    if not translation.filters:
        return (
            "I couldn't translate that into concrete filters. "
            "Try wording like '3 beds near the beach under $1.5M'."
        )

    matches = search_listings(translation.filters)
    if not matches:
        return (
            f"No matches for {translation.filters}. "
            f"(matched phrases: {translation.matched_phrases or 'none'})"
        )

    lines = [
        f"Matched {len(matches)} of the saved corpus on filters {translation.filters}:"
    ]
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
    session.current_property_id = matches[0]["property_id"]
    return "\n".join(lines)


# ---------- COMPARISON (Phase A: defers to decision) ----------


def handle_comparison(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    refs = [ref for ref in decision.target_refs if _SAVED_DIR_EXISTS(ref)]
    if len(refs) < 2:
        return "Comparison needs two valid property ids I've seen before."
    results = underwrite_matches(refs[:2])
    lines = ["Comparison:"]
    for r in results:
        if "error" in r:
            lines.append(f"- {r['property_id']}: {r['error']}")
            continue
        vp = r.get("value_position") or {}
        premium = vp.get("premium_discount_pct")
        premium_s = f"{premium:+.1%}" if isinstance(premium, (int, float)) else "n/a"
        flags = ", ".join(r.get("trust_flags") or []) or "none"
        lines.append(
            f"- {r['property_id']}: {r.get('decision_stance')} ({premium_s}), flags: {flags}"
        )
    return "\n".join(lines)


# ---------- RESEARCH ----------


def handle_research(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    return (
        "Town research (external sources) arrives in Phase C. "
        "Phase A only serves cached town signals when a property is loaded."
    )


# ---------- VISUALIZE ----------


_CHART_KIND_KEYWORDS = (
    ("verdict_gauge", re.compile(r"\b(verdict|gauge|stance chart)\b", re.IGNORECASE)),
    ("value_opportunity", re.compile(r"\b(value (picture|chart|opportunity)|ask vs (fair|value))\b", re.IGNORECASE)),
)


def _infer_chart_kind(text: str) -> str:
    for kind, pattern in _CHART_KIND_KEYWORDS:
        if pattern.search(text):
            return kind
    return "value_opportunity"  # default: the chart that answers "what's the picture?"


def handle_visualize(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    pid = _resolve_property_id(decision, session, text)
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
        return "Which property? Give me a saved property id to estimate rent on."
    try:
        rent = get_rent_estimate(pid)
    except ToolUnavailable as exc:
        return f"I couldn't estimate rent ({exc})."
    session.current_property_id = pid

    money = lambda v: f"${v:,.0f}" if isinstance(v, (int, float)) else "n/a"
    monthly = rent.get("monthly_rent")
    effective = rent.get("effective_monthly_rent")
    source = rent.get("rent_source_type") or "estimated"
    label = rent.get("rental_ease_label")
    ease = rent.get("rental_ease_score")
    noi = rent.get("annual_noi")

    lines = [
        f"Estimated monthly rent: {money(monthly)} (source: {source}).",
        f"Effective rent after vacancy/management: {money(effective)}.",
    ]
    if label or isinstance(ease, (int, float)):
        ease_s = f"{ease:.0f}/100" if isinstance(ease, (int, float)) else "n/a"
        lines.append(f"Rental profile: {label or 'n/a'} (ease {ease_s}).")
    if isinstance(noi, (int, float)):
        lines.append(f"Annual NOI: {money(noi)}.")
    return " ".join(lines)


# ---------- PROJECTION ----------


def handle_projection(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    pid = _resolve_property_id(decision, session, text)
    if pid is None:
        return "Which property should I project forward?"
    overrides = parse_overrides(text)
    try:
        proj = get_projection(pid, overrides=overrides)
    except ToolUnavailable as exc:
        return f"I couldn't build a projection ({exc})."
    session.current_property_id = pid

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

    system = (
        "You compose a short 3-5 sentence forward-looking briefing from a real-estate "
        "bull/base/bear scenario payload. Lead with the base case vs ask, then contrast "
        "bull and bear as the upside/downside range. Quote all dollar figures verbatim. "
        "Do not invent numbers."
    )
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
    narrative = llm.complete(system=system, user=user, max_tokens=300).strip()
    return (narrative or f"Base {money(base)} ({_delta(base)}).") + chart_line


# ---------- MICRO_LOCATION ----------


def handle_micro_location(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    pid = _resolve_property_id(decision, session, text)
    if pid is None:
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

    system = (
        "You compose a 3-5 sentence downside briefing from a risk payload. Lead with the "
        "biggest driver, name bear/stress dollar figures verbatim, and end with what would "
        "make this deal break. Do not invent numbers or flags."
    )
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
    narrative = llm.complete(system=system, user=user, max_tokens=300).strip()
    return (narrative or "No material risk drivers surfaced.") + chart_line


# ---------- EDGE ----------


def handle_edge(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    pid = _resolve_property_id(decision, session, text)
    if pid is None:
        return "Which property? Give me a saved property id."
    overrides = parse_overrides(text)
    try:
        thesis = get_value_thesis(pid, overrides=overrides)
    except ToolUnavailable as exc:
        return f"I couldn't build a value thesis ({exc})."
    session.current_property_id = pid

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

    if llm is None:
        lines = [f"Value thesis for {pid}:"]
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
        return "\n".join(lines) + chart_line

    system = (
        "You compose a 3-5 sentence value-thesis read. Lead with ask vs fair value and the "
        "premium/discount. Name the primary value source and the top anchors driving fair "
        "value. End with what has to be true for the edge to exist. Quote dollars verbatim."
    )
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
    )
    narrative = llm.complete(system=system, user=user, max_tokens=300).strip()
    return (narrative or f"Ask {money(ask)} vs fair {money(fair)}.") + chart_line


# ---------- STRATEGY ----------


def handle_strategy(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    pid = _resolve_property_id(decision, session, text)
    if pid is None:
        return "Which property? Give me a saved property id."
    overrides = parse_overrides(text)
    try:
        fit = get_strategy_fit(pid, overrides=overrides)
    except ToolUnavailable as exc:
        return f"I couldn't score strategy fit ({exc})."
    session.current_property_id = pid

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

    system = (
        "You compose a 3-5 sentence 'best way to play this' briefing. Compare the viable "
        "paths (primary / rental / flip / hold) using the payload. Recommend one. Quote all "
        "figures verbatim. Do not invent strategies that aren't supported by the data."
    )
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
    narrative = llm.complete(system=system, user=user, max_tokens=300).strip()
    return narrative or (fit.get("best_path") or "No strategy fit cached.")


# ---------- BROWSE ----------


def handle_browse(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    """Quick first read on a property: summary + similar nearby listings.

    Deliberately avoids the underwrite cascade. Browse is the default for
    open-ended questions ("what do you think of X?") — decision unlocks only
    on explicit buy/pass phrasing.
    """
    pid = _resolve_property_id(decision, session, text)
    if pid is None:
        return "Which property would you like a quick read on?"
    try:
        view = PropertyView.load(pid, depth="browse")
    except ToolUnavailable as exc:
        return f"I couldn't find summary data ({exc})."
    session.current_property_id = pid

    filters: dict = {}
    if view.town:
        filters["town"] = view.town
    if view.state:
        filters["state"] = view.state
    if isinstance(view.beds, int):
        filters["beds_min"] = max(1, view.beds - 1)
        filters["beds_max"] = view.beds + 1
    if isinstance(view.ask_price, (int, float)) and view.ask_price > 0:
        filters["min_price"] = view.ask_price * 0.75
        filters["max_price"] = view.ask_price * 1.25

    try:
        neighbors = search_listings(filters) if filters else []
    except Exception:
        neighbors = []
    neighbors = [n for n in neighbors if n.get("property_id") != pid][:5]

    money = lambda v: f"${v:,.0f}" if isinstance(v, (int, float)) else "n/a"

    # Build the head conditionally — never emit "?" for missing fields. The
    # prior behavior ("{beds or '?'}bd/{baths or '?'}ba") let the LLM parrot
    # the literal ? as "bedroom count unspecified", which was the Bug A
    # narration leak. Also: browse no longer surfaces fair value or pricing
    # view — valuation math is the decision tier's job (intent-tier direction).
    parts: list[str] = [view.address or view.pid]
    if view.beds is not None and view.baths is not None:
        parts.append(f"{view.beds}bd/{view.baths}ba")
    if view.ask_price is not None:
        parts.append(f"ask {money(view.ask_price)}")
    head = " — ".join(parts)

    if neighbors:
        similar_lines = [f"Similar in {view.town or 'the area'}:"]
        for n in neighbors:
            bits: list[str] = []
            if n.get("address"):
                bits.append(n["address"])
            if n.get("beds") is not None and n.get("baths") is not None:
                bits.append(f"{n['beds']}bd/{n['baths']}ba")
            if n.get("ask_price") is not None:
                bits.append(money(n.get("ask_price")))
            if isinstance(n.get("blocks_to_beach"), (int, float)):
                bits.append(f"{n['blocks_to_beach']:.1f} blocks to beach")
            tail = ", ".join(bits) if bits else ""
            similar_lines.append(f"- {n['property_id']}" + (f" — {tail}" if tail else ""))
        similar_block = "\n".join(similar_lines)
    else:
        similar_block = f"(no similar listings cached in {view.town or 'the area'} yet.)"

    if llm is None:
        return head + "\n\n" + similar_block + "\n\nWant a full underwrite?"

    system = (
        "You give a 2-3 sentence first read on a property. This is BROWSE mode — a quick "
        "orientation, not an underwrite. Do NOT say 'buy', 'pass', 'stance', give a verdict, "
        "or mention fair value, premium, or valuation. If Subject does not mention a fact "
        "(beds, baths, price), DO NOT fill it in, guess, or say 'unspecified' — simply omit "
        "that fact. Never invent numbers. Do not include the similar-listings list in your "
        "output — that will be appended deterministically. End with exactly: 'Want a full underwrite?'"
    )
    user = (
        f"User question: {text}\n\n"
        f"Subject: {head}\n"
        f"Has comparables cached: {bool(neighbors)}"
    )
    narrative = llm.complete(system=system, user=user, max_tokens=180).strip()
    if not narrative:
        narrative = head
    return narrative + "\n\n" + similar_block


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
    if not session.current_property_id:
        return decision
    if not _is_browse_affirmative(text):
        return decision
    return RouterDecision(
        answer_type=AnswerType.DECISION,
        confidence=max(decision.confidence, 0.7),
        target_refs=[session.current_property_id],
        reason="browse-followup escalate",
        llm_suggestion=decision.llm_suggestion,
    )


def dispatch(
    text: str, decision: RouterDecision, session: Session, llm: LLMClient | None
) -> str:
    decision = _escalate_browse_affirmative(text, decision, session)
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
