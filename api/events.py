"""Structured SSE event protocol.

The frontend useChat hook consumes these event objects directly. Designing the
contract early — even while echoing — so structured payloads (listings, maps,
follow-up suggestions) interleave with text deltas in a single stream.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Iterator

# Event type names — kept in sync with web/lib/chat/events.ts
EVENT_TEXT_DELTA = "text_delta"
EVENT_TOOL_CALL = "tool_call"
EVENT_TOOL_RESULT = "tool_result"
EVENT_LISTINGS = "listings"
EVENT_MAP = "map"
EVENT_SUGGESTIONS = "suggestions"
EVENT_CONVERSATION = "conversation"
EVENT_MESSAGE = "message"
EVENT_DONE = "done"
EVENT_ERROR = "error"
EVENT_CHART = "chart"
EVENT_VERDICT = "verdict"
EVENT_SCENARIO_TABLE = "scenario_table"
EVENT_COMPARISON_TABLE = "comparison_table"
EVENT_TOWN_SUMMARY = "town_summary"
EVENT_COMPS_PREVIEW = "comps_preview"
EVENT_RISK_PROFILE = "risk_profile"
EVENT_VALUE_THESIS = "value_thesis"
EVENT_VALUATION_COMPS = "valuation_comps"
EVENT_MARKET_SUPPORT_COMPS = "market_support_comps"
EVENT_STRATEGY_PATH = "strategy_path"
EVENT_RENT_OUTLOOK = "rent_outlook"
EVENT_TRUST_SUMMARY = "trust_summary"
EVENT_RESEARCH_UPDATE = "research_update"
EVENT_MODULES_RAN = "modules_ran"
EVENT_VERIFIER_REPORT = "verifier_report"
EVENT_GROUNDING_ANNOTATIONS = "grounding_annotations"
EVENT_PARTIAL_DATA_WARNING = "partial_data_warning"


def text_delta(content: str) -> dict[str, Any]:
    return {"type": EVENT_TEXT_DELTA, "content": content}


def tool_call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"type": EVENT_TOOL_CALL, "name": name, "args": args}


def tool_result(name: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"type": EVENT_TOOL_RESULT, "name": name, "data": data}


def listings(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": EVENT_LISTINGS, "items": items}


def map_payload(center: list[float], pins: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": EVENT_MAP, "center": center, "pins": pins}


def suggestions(items: list[str]) -> dict[str, Any]:
    return {"type": EVENT_SUGGESTIONS, "items": items}


def conversation_event(conversation_id: str, title: str) -> dict[str, Any]:
    return {"type": EVENT_CONVERSATION, "id": conversation_id, "title": title}


def message_event(message_id: str, role: str) -> dict[str, Any]:
    return {"type": EVENT_MESSAGE, "id": message_id, "role": role}


def done() -> dict[str, Any]:
    return {"type": EVENT_DONE}


def error(message: str) -> dict[str, Any]:
    return {"type": EVENT_ERROR, "message": message}


def chart(
    url: str | None = None,
    *,
    title: str | None = None,
    kind: str | None = None,
    spec: dict[str, Any] | None = None,
    provenance: list[str] | None = None,
    advisor: dict[str, Any] | None = None,
    supports_claim: str | None = None,
    why_this_chart: str | None = None,
) -> dict[str, Any]:
    """Visual artifact or native chart spec emitted by handlers.

    `url` remains the backward-compatible HTML artifact path for visualize/debug
    flows. `spec` carries typed data for native chat charts in core workflows.
    """
    payload: dict[str, Any] = {"type": EVENT_CHART}
    if url is not None:
        payload["url"] = url
    if title is not None:
        payload["title"] = title
    if kind is not None:
        payload["kind"] = kind
    if spec is not None:
        payload["spec"] = spec
    if provenance is not None:
        payload["provenance"] = provenance
    if advisor is not None:
        payload["advisor"] = advisor
    if supports_claim is not None:
        payload["supports_claim"] = supports_claim
    if why_this_chart is not None:
        payload["why_this_chart"] = why_this_chart
    return payload


def scenario_table(
    rows: list[dict[str, Any]],
    *,
    address: str | None = None,
    ask_price: float | None = None,
    basis_label: str | None = None,
    spread: float | None = None,
) -> dict[str, Any]:
    """Bull/base/bear projection rows for the UI to render as a table.

    Each row carries scenario name, projected value, delta vs ask, growth rate,
    and total adjustment %. Optional `address` + `ask_price` give the card a
    header without forcing the UI to cross-reference the listing event.

    `spread` is the bull-minus-bear dollar gap produced by `ScenarioOutput`
    (bull_base_bear module). AUDIT 1.4.4: emit `spread_unit="dollars"` as a
    literal so the UI never has to guess whether this field is a currency
    amount or a percentage — the latter exists in other modules under similar
    names and the two must not mix.
    """
    return {
        "type": EVENT_SCENARIO_TABLE,
        "address": address,
        "ask_price": ask_price,
        "basis_label": basis_label,
        "spread": spread,
        "spread_unit": "dollars",
        "rows": rows,
    }


def comparison_table(properties: list[dict[str, Any]]) -> dict[str, Any]:
    """Side-by-side property comparison for the UI to render as a table."""
    return {"type": EVENT_COMPARISON_TABLE, "properties": properties}


def verdict(payload: dict[str, Any]) -> dict[str, Any]:
    """Structured decision-tier output (stance, fair value, premium, trust
    flags, etc.) so the UI can render a verdict card instead of parsing
    LLM-narrated prose. Source fields come from PropertyView at decision depth."""
    return {"type": EVENT_VERDICT, **payload}


def town_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Town-level context card: median price, median PPSF, raw confidence tier,
    and 2-3 key signals from seeded local-intelligence docs. Emitted on first
    DECISION response so the user doesn't have to ask 'what about this town?'
    as a follow-up to every property read. Payload may also carry
    `signal_items` for richer line-item drill-ins."""
    return {"type": EVENT_TOWN_SUMMARY, **payload}


def comps_preview(payload: dict[str, Any]) -> dict[str, Any]:
    """Top 3-5 sold comps used in the valuation, shown inline on the first
    DECISION response. Each row: address, sale price, beds/baths/sqft,
    sold date. Footer carries the aggregate (count, median price, avg PPSF)."""
    return {"type": EVENT_COMPS_PREVIEW, **payload}


def risk_profile(payload: dict[str, Any]) -> dict[str, Any]:
    """Structured risk output (risk_flags, trust_flags, bear/stress values,
    key_risks, total_penalty, confidence_tier). Source fields come from
    get_risk_profile() via session.last_risk_view."""
    return {"type": EVENT_RISK_PROFILE, **payload}


def value_thesis(payload: dict[str, Any]) -> dict[str, Any]:
    """Structured edge-tier output: ask vs fair value, premium/discount, pricing
    view, primary value source, value drivers, what must be true, comp
    selection summary + selected comp rows. From get_value_thesis() + optional
    get_cma() via session.last_value_thesis_view."""
    return {"type": EVENT_VALUE_THESIS, **payload}


def valuation_comps(payload: dict[str, Any]) -> dict[str, Any]:
    """Comps that actually fed the fair value computation.

    F2 split: sourced from the valuation module's ``comparable_sales``
    output (``comps_used``). Each row carries ``feeds_fair_value`` provenance
    so the UI can label these as the evidence behind the price read — not
    market-context comps. Never populated from live Zillow market search.
    """
    return {"type": EVENT_VALUATION_COMPS, "source": "valuation_module", **payload}


def market_support_comps(payload: dict[str, Any]) -> dict[str, Any]:
    """Live market comps for context, not fair-value evidence.

    F2 split: sourced from ``get_cma()`` which prefers live Zillow listings
    with a saved-comp fallback. These rows support the user's read of the
    current market but did not feed Briarwood's fair value. Always labeled
    as market support in the UI so the provenance is unambiguous.
    """
    return {"type": EVENT_MARKET_SUPPORT_COMPS, "source": "live_market", **payload}


def strategy_path(payload: dict[str, Any]) -> dict[str, Any]:
    """Structured strategy-fit output: best path, recommendation, rental ease,
    cash flow, liquidity, cash-on-cash return. From get_strategy_fit() via
    session.last_strategy_view."""
    return {"type": EVENT_STRATEGY_PATH, **payload}


def rent_outlook(payload: dict[str, Any]) -> dict[str, Any]:
    """Structured rent-lookup output: monthly/effective rent, rent source,
    rental ease, annual NOI, multi-year horizon range, Zillow market rent.
    From get_rent_estimate() + get_rent_outlook() via session.last_rent_outlook_view."""
    return {"type": EVENT_RENT_OUTLOOK, **payload}


def trust_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """User-facing trust / truthfulness card."""
    return {"type": EVENT_TRUST_SUMMARY, **payload}


def research_update(payload: dict[str, Any]) -> dict[str, Any]:
    """Structured town-research output: confidence, narrative, bullish/bearish
    signals, watch items, document count, warnings. Payload may also carry
    `signal_items` for richer line-item drill-ins. From research_town() via
    session.last_research_view."""
    return {"type": EVENT_RESEARCH_UPDATE, **payload}


def modules_ran(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Module-attribution badge row. Each item is `{module, label, contributed_to}`
    where `contributed_to` lists the structured event types this module's output
    reached (e.g. `["verdict", "scenario_table"]`). Only modules whose output
    actually surfaced in the response should appear — modules that ran but
    produced nothing the user sees are excluded by design."""
    return {"type": EVENT_MODULES_RAN, "items": items}


def grounding_annotations(
    anchors: list[dict[str, Any]],
    *,
    ungrounded_declaration: bool = False,
) -> dict[str, Any]:
    """Citation anchors extracted from LLM-emitted `[[Module:field:value]]`
    markers. Each anchor is `{module, field, value}`. The UI uses these to
    wrap cited values in hover tooltips sourced from the named module.

    `ungrounded_declaration` mirrors the verifier signal — true when the LLM
    said "we don't have a model output for that." The UI renders the message
    bubble in a muted variant so the distinction is visually obvious without
    the user having to read the prose closely."""
    return {
        "type": EVENT_GROUNDING_ANNOTATIONS,
        "anchors": anchors,
        "ungrounded_declaration": ungrounded_declaration,
    }


def verifier_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Advisory grounding-verifier report. Emitted at end-of-turn so dev tooling
    (browser DevTools, log scrapers) can surface violation rates without the
    user-facing UI surfacing them. Step 5 keeps this advisory-only — Step 7
    introduces strict mode behind `BRIARWOOD_STRICT_REGEN`."""
    return {"type": EVENT_VERIFIER_REPORT, **payload}


def partial_data_warning(
    section: str,
    reason: str,
    *,
    verdict_reliable: bool = True,
) -> dict[str, Any]:
    """F7: surface a non-core enrichment failure to the UI.

    Emitted when a best-effort enrichment (town context, CMA preview, session
    load, etc.) raises but the core decision can still stream. `section` is a
    short machine-readable tag (e.g. ``"town_summary"``). `reason` is a short
    human-readable cause. ``verdict_reliable`` is False only when the failure
    affects the core decision itself — the UI tones the banner accordingly.
    """
    return {
        "type": EVENT_PARTIAL_DATA_WARNING,
        "section": section,
        "reason": reason,
        "verdict_reliable": bool(verdict_reliable),
    }


def encode_sse(event: dict[str, Any]) -> str:
    """Encode a single event as an SSE `data:` line."""
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"


def encode_stream(events: Iterable[dict[str, Any]]) -> Iterator[str]:
    for ev in events:
        yield encode_sse(ev)
