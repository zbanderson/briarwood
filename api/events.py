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


def chart(url: str, *, title: str | None = None, kind: str | None = None) -> dict[str, Any]:
    """Visual artifact emitted by handlers (PROJECTION/RISK/EDGE/RENT_LOOKUP/
    VISUALIZE all generate Plotly HTML files). `url` should be a path the
    browser can load; FastAPI serves these via /artifacts/."""
    return {"type": EVENT_CHART, "url": url, "title": title, "kind": kind}


def scenario_table(
    rows: list[dict[str, Any]],
    *,
    address: str | None = None,
    ask_price: float | None = None,
    spread: float | None = None,
) -> dict[str, Any]:
    """Bull/base/bear projection rows for the UI to render as a table.

    Each row carries scenario name, projected value, delta vs ask, growth rate,
    and total adjustment %. Optional `address` + `ask_price` give the card a
    header without forcing the UI to cross-reference the listing event."""
    return {
        "type": EVENT_SCENARIO_TABLE,
        "address": address,
        "ask_price": ask_price,
        "spread": spread,
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
    as a follow-up to every property read."""
    return {"type": EVENT_TOWN_SUMMARY, **payload}


def comps_preview(payload: dict[str, Any]) -> dict[str, Any]:
    """Top 3-5 sold comps used in the valuation, shown inline on the first
    DECISION response. Each row: address, sale price, beds/baths/sqft,
    sold date. Footer carries the aggregate (count, median price, avg PPSF)."""
    return {"type": EVENT_COMPS_PREVIEW, **payload}


def encode_sse(event: dict[str, Any]) -> str:
    """Encode a single event as an SSE `data:` line."""
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"


def encode_stream(events: Iterable[dict[str, Any]]) -> Iterator[str]:
    for ev in events:
        yield encode_sse(ev)
