"""Translation layer between the Briarwood Python agent pipeline and the
FastAPI SSE wire format.

Wiring is introduced one intent tier at a time.
- Tier 1: SEARCH (discovery queries like "homes in Belmar").
- Tier 2: BROWSE (single-property opinion like "what do you think of 1600 L St").
- Tier 3: DECISION (full underwrite cascade — fires when the user pins a
  listing and clicks 'Run analysis', or escalates to "should I buy this?").
- Tier 4: All remaining intent tiers (LOOKUP / PROJECTION / STRATEGY / RISK /
  EDGE / RENT_LOOKUP / MICRO_LOCATION / COMPARISON / RESEARCH / VISUALIZE /
  CHITCHAT) flow through a generic `dispatch_stream`. They share the same
  shape: text in → narrative text + optional focal property card + tier-aware
  follow-up suggestions.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, AsyncIterator

import briarwood  # noqa: F401 — side-effect: loads .env so OPENAI_API_KEY is available
from briarwood.agent.dispatch import dispatch
from briarwood.agent.llm import LLMClient, default_client
from briarwood.agent.router import AnswerType, RouterDecision, classify
from briarwood.agent.session import SESSION_DIR, Session
from briarwood.agent.tools import (
    _existing_or_slugified_property_id,
    _json_ready,
    search_listings,
)
from briarwood.data_sources.google_maps_client import GoogleMapsClient
from briarwood.listing_intake.service import ListingIntakeService

from api import events

_SAVED_ROOT = Path("data/saved_properties")
_ARTIFACTS_ROOT = Path("data/agent_artifacts").resolve()
_ZIP_RE = re.compile(r"\b(\d{5})\b")
_ZILLOW_URL_RE = re.compile(r"https?://(?:www\.)?zillow\.com/\S+", re.IGNORECASE)
# Chart paths from handlers come in two formats:
#   "\nChart: file:///abs/path.html"          (projection/risk/edge/rent_lookup)
#   "Rendered radar_score for pid: file:///abs/path.html"  (visualize)
_CHART_LINE_RE = re.compile(
    r"(?:Chart|Rendered\s+(\S+)\s+for\s+\S+):\s*file://(\S+\.(?:html|png|svg))",
    re.IGNORECASE,
)


_llm_client: LLMClient | None = None
_llm_initialized = False

_maps_client: GoogleMapsClient | None = None
_geocode_disabled_logged = False  # so we only log the "enable API" hint once


def get_llm() -> LLMClient | None:
    """Return a process-wide LLMClient, or None if no API key is configured.

    briarwood's package __init__ loads .env so OPENAI_API_KEY is populated.
    default_client() tolerates missing keys by returning None.
    """
    global _llm_client, _llm_initialized
    if not _llm_initialized:
        _llm_client = default_client()
        _llm_initialized = True
    return _llm_client


def get_maps_client() -> GoogleMapsClient:
    global _maps_client
    if _maps_client is None:
        _maps_client = GoogleMapsClient()
    return _maps_client


def _geocode(address: str) -> tuple[float | None, float | None]:
    """Best-effort geocode via Google Maps Platform. Caches on disk so repeats
    are free. Returns (None, None) if the Geocoding API is unavailable."""
    global _geocode_disabled_logged
    if not address:
        return (None, None)
    client = get_maps_client()
    if not client.is_configured:
        return (None, None)
    try:
        resp = client.geocode(address)
    except Exception as exc:  # network hiccup etc — never break the turn
        print(f"[geocode] exception for {address!r}: {exc}", flush=True)
        return (None, None)
    payload = resp.normalized_payload or {}
    lat, lng = payload.get("latitude"), payload.get("longitude")
    if lat is None and isinstance(resp.raw_payload, dict):
        status = resp.raw_payload.get("status")
        if status and status != "OK" and not _geocode_disabled_logged:
            print(
                f"[geocode] Google Maps returned status={status!r}: "
                f"{resp.raw_payload.get('error_message')!r}. "
                f"Map pins will be skipped until the Geocoding API is enabled.",
                flush=True,
            )
            _geocode_disabled_logged = True
    return (float(lat) if lat is not None else None, float(lng) if lng is not None else None)


def classify_turn(text: str) -> RouterDecision:
    return classify(text, client=get_llm())


# ---------- Session continuity ----------


def _load_or_create_session(conversation_id: str | None) -> Session:
    """Map a web `conversation_id` to a persisted agent `Session`.

    The conversation_id (12-char hex from api.store) is used directly as the
    session_id. Returns the loaded session when one exists on disk so prior-turn
    state (current_property_id, last_*_view, turns) is available; otherwise a
    fresh Session keyed to the same id is returned and saved on first use."""
    if not conversation_id:
        return Session()
    path = SESSION_DIR / f"{conversation_id}.json"
    if path.exists():
        try:
            return Session.load(conversation_id)
        except (json.JSONDecodeError, KeyError) as exc:
            print(f"[session] load failed for {conversation_id}: {exc}; starting fresh", flush=True)
    return Session(session_id=conversation_id)


def _finalize_session(
    session: Session,
    user_text: str,
    assistant_text: str,
    answer_type: AnswerType,
) -> None:
    """Record the turn in session memory and persist to disk so the next turn
    in the same conversation rehydrates with full context."""
    try:
        session.record(user_text, assistant_text, answer_type.value)
        session.save()
    except Exception as exc:  # noqa: BLE001 — never break a turn on persistence
        print(f"[session] save failed for {session.session_id}: {exc}", flush=True)


# ---------- Listing translation ----------


def _load_saved_facts(property_id: str) -> dict[str, Any] | None:
    path = _SAVED_ROOT / property_id / "inputs.json"
    try:
        return json.loads(path.read_text()).get("facts") or {}
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _parse_zip(address: str | None) -> str | None:
    if not address:
        return None
    m = _ZIP_RE.search(address)
    return m.group(1) if m else None


def _to_listing_from_saved(match: dict[str, Any]) -> dict[str, Any]:
    """Index/search_listings() row → our Listing TS type. Enriches lat/lng +
    zip from the saved property's facts; falls back to a Google Maps geocode
    when facts don't carry coordinates."""
    pid = str(match.get("property_id") or "")
    facts = _load_saved_facts(pid) if pid else None
    lat = facts.get("latitude") if facts else None
    lng = facts.get("longitude") if facts else None
    sqft = (facts or {}).get("sqft") or match.get("sqft") or 0
    year_built = (facts or {}).get("year_built")
    address = match.get("address") or (facts or {}).get("address") or ""
    if (lat is None or lng is None) and address:
        lat, lng = _geocode(address)

    return {
        "id": pid or address or "unknown",
        "address_line": address,
        "city": match.get("town") or (facts or {}).get("town") or "",
        "state": match.get("state") or (facts or {}).get("state") or "",
        "zip": _parse_zip(address),
        "price": int(match.get("ask_price") or (facts or {}).get("purchase_price") or 0),
        "beds": int(match.get("beds") or (facts or {}).get("beds") or 0),
        "baths": float(match.get("baths") or (facts or {}).get("baths") or 0),
        "sqft": int(sqft or 0),
        "lot_sqft": int((facts or {}).get("lot_size") or 0) or None,
        "year_built": int(year_built) if year_built else None,
        "status": "active",
        "lat": float(lat) if lat is not None else None,
        "lng": float(lng) if lng is not None else None,
    }


def _to_listing_from_live(entry: dict[str, Any]) -> dict[str, Any]:
    """session.last_live_listing_results entries come from _serialize_live_listing
    in dispatch.py. Zillow discovery doesn't surface lat/lng, so we geocode the
    address via Google Maps Platform. Results are cached on disk in
    data/cache/google_maps/ so repeats are free."""
    ext_id = entry.get("external_id") or entry.get("address") or "live"
    address = entry.get("address") or ""
    lat, lng = _geocode(address) if address else (None, None)
    return {
        "id": str(ext_id),
        "address_line": address,
        "city": entry.get("town") or "",
        "state": entry.get("state") or "",
        "zip": entry.get("zip_code"),
        "price": int(entry.get("ask_price") or 0),
        "beds": int(entry.get("beds") or 0),
        "baths": float(entry.get("baths") or 0),
        "sqft": int(entry.get("sqft") or 0),
        "status": (entry.get("listing_status") or "active").lower(),
        "source_url": entry.get("listing_url"),
        "lat": lat,
        "lng": lng,
    }


def _pins_and_center(listings: list[dict[str, Any]]) -> tuple[list[float], list[dict[str, Any]]]:
    geo = [l for l in listings if l.get("lat") is not None and l.get("lng") is not None]
    if not geo:
        return ([0.0, 0.0], [])
    pins = [
        {
            "id": l["id"],
            "lat": l["lat"],
            "lng": l["lng"],
            "label": f"${l['price'] // 1000}k" if l.get("price") else l["address_line"],
        }
        for l in geo
    ]
    center_lng = sum(p["lng"] for p in pins) / len(pins)
    center_lat = sum(p["lat"] for p in pins) / len(pins)
    return ([center_lng, center_lat], pins)


def _build_listings(session: Session) -> list[dict[str, Any]]:
    """Reconstruct the structured listing payload that handle_search produced
    as text. Prefer live Zillow results (stored in session.last_live_listing_results),
    fall back to a saved-corpus re-query using the filters handle_search persisted
    into session.search_context."""
    live = session.last_live_listing_results or []
    if live:
        return [_to_listing_from_live(e) for e in live[:6]]

    ctx = session.current_search_context or session.search_context or {}
    filters: dict[str, Any] = {}
    if ctx.get("town"):
        filters["town"] = ctx["town"]
    if ctx.get("state"):
        filters["state"] = ctx["state"]
    inner = ctx.get("filters")
    if isinstance(inner, dict):
        filters.update(inner)
    if not filters:
        return []
    try:
        matches = search_listings(filters)
    except Exception:
        return []
    return [_to_listing_from_saved(m) for m in matches[:6]]


# ---------- Zillow URL ingestion ----------


def extract_zillow_url(text: str) -> str | None:
    """Find the first Zillow URL in a chat message, or None."""
    if not text:
        return None
    m = _ZILLOW_URL_RE.search(text)
    if not m:
        return None
    return m.group(0).rstrip(".,;)>]\"'")


def ingest_zillow_url(url: str) -> tuple[dict[str, Any] | None, str | None]:
    """Hydrate a Zillow URL via SearchAPI, write the canonical record into
    data/saved_properties/, and return (pinned_listing, error).

    The pinned listing is shaped like a frontend Listing card and is suitable
    for `decision_stream(pinned_listing=...)`. On failure (no usable address
    or no ask price), returns (None, reason)."""
    try:
        result = ListingIntakeService().intake(url)
    except Exception as exc:  # noqa: BLE001 — boundary
        return None, f"intake raised: {exc}"

    normalized = result.normalized_property_data
    if not normalized.address:
        return None, "intake could not parse an address from the URL"
    if not normalized.price:
        return None, "intake hydrated an address but no ask price was found"

    pid = _existing_or_slugified_property_id(normalized.address)
    canonical = normalized.to_canonical_input(property_id=pid)
    payload = _json_ready(asdict(canonical))

    pdir = _SAVED_ROOT / pid
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "inputs.json").write_text(json.dumps(payload, indent=2) + "\n")

    facts = payload.get("facts") or {}
    listing = _to_listing_from_facts(pid, facts)
    listing["source_url"] = url
    return listing, None


# ---------- Streamers ----------


async def _stream_text(text: str, *, chunk_delay: float = 0.015) -> AsyncIterator[dict[str, Any]]:
    for word in text.split(" "):
        yield events.text_delta(word + " ")
        await asyncio.sleep(chunk_delay)


def _extract_charts(response_text: str) -> tuple[str, list[dict[str, Any]]]:
    """Pull `file://...` chart URLs out of the narrative and translate them
    into chart events. Returns (cleaned_narrative, [chart_events]).

    Handlers write absolute filesystem paths under data/agent_artifacts/. We
    rewrite those into /artifacts/{relative} URLs that FastAPI's StaticFiles
    mount can serve, then strip the original line from the narrative so the
    chat bubble doesn't show a raw `file://` URL the browser can't load."""
    charts: list[dict[str, Any]] = []
    cleaned_lines: list[str] = []
    for line in response_text.splitlines():
        m = _CHART_LINE_RE.search(line)
        if not m:
            cleaned_lines.append(line)
            continue
        kind = m.group(1)  # only set for the visualize-style match
        abs_path = m.group(2)
        try:
            rel = Path(abs_path).resolve().relative_to(_ARTIFACTS_ROOT)
        except (ValueError, OSError):
            # Path isn't under our artifacts dir — leave the line in narrative
            # rather than emit an unservable URL.
            cleaned_lines.append(line)
            continue
        url = f"/artifacts/{rel.as_posix()}"
        charts.append(events.chart(url, kind=kind))
    cleaned = "\n".join(cleaned_lines).strip()
    return cleaned, charts


def _verdict_from_view(view: dict[str, Any]) -> dict[str, Any]:
    """Project the saved decision view into the verdict event payload. UI
    consumes this to render a stance badge + price/value comparison + trust
    flags, instead of parsing it back out of LLM-narrated prose."""
    return {
        "address": view.get("address"),
        "town": view.get("town"),
        "state": view.get("state"),
        "stance": view.get("decision_stance"),
        "primary_value_source": view.get("primary_value_source"),
        "ask_price": view.get("ask_price"),
        "all_in_basis": view.get("all_in_basis"),
        "fair_value_base": view.get("fair_value_base"),
        "value_low": view.get("value_low"),
        "value_high": view.get("value_high"),
        "ask_premium_pct": view.get("ask_premium_pct"),
        "basis_premium_pct": view.get("basis_premium_pct"),
        "trust_flags": list(view.get("trust_flags") or []),
        "what_must_be_true": list(view.get("what_must_be_true") or []),
        "key_risks": list(view.get("key_risks") or []),
        "overrides_applied": dict(view.get("overrides_applied") or {}),
    }


def _scenario_table_from_view(view: dict[str, Any]) -> dict[str, Any]:
    """Project the saved get_projection() dict into a scenario_table event.

    Each scenario row has a value, delta vs ask, growth rate, and total
    adjustment %. Stress is included only when the engine produced one."""
    ask = view.get("ask_price")

    def _delta(v: Any) -> float | None:
        if isinstance(v, (int, float)) and isinstance(ask, (int, float)) and ask:
            return round((v - ask) / ask, 4)
        return None

    rows: list[dict[str, Any]] = []
    for label, value_key, growth_key, adj_key in (
        ("Bull", "bull_case_value", "bull_growth_rate", "bull_total_adjustment_pct"),
        ("Base", "base_case_value", "base_growth_rate", "base_total_adjustment_pct"),
        ("Bear", "bear_case_value", "bear_growth_rate", "bear_total_adjustment_pct"),
    ):
        value = view.get(value_key)
        rows.append(
            {
                "scenario": label,
                "value": value,
                "delta_pct": _delta(value),
                "growth_rate": view.get(growth_key),
                "adjustment_pct": view.get(adj_key),
            }
        )
    stress = view.get("stress_case_value")
    if isinstance(stress, (int, float)):
        rows.append(
            {
                "scenario": "Stress",
                "value": stress,
                "delta_pct": _delta(stress),
                "growth_rate": None,
                "adjustment_pct": None,
            }
        )
    address = view.get("address")
    town = view.get("town")
    state = view.get("state")
    if not address and (town or state):
        address = ", ".join([p for p in (town, state) if p])
    return {
        "rows": rows,
        "address": address,
        "ask_price": ask,
        "spread": view.get("spread"),
    }


def _comparison_table_from_view(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project the enriched underwrite_matches list into table-ready rows."""
    out: list[dict[str, Any]] = []
    for r in rows:
        if "error" in r:
            out.append(
                {
                    "property_id": r.get("property_id"),
                    "address": r.get("address"),
                    "error": r.get("error"),
                }
            )
            continue
        vp = r.get("value_position") or {}
        out.append(
            {
                "property_id": r.get("property_id"),
                "address": r.get("address"),
                "town": r.get("town"),
                "state": r.get("state"),
                "stance": r.get("decision_stance"),
                "primary_value_source": r.get("primary_value_source"),
                "premium_pct": vp.get("premium_discount_pct"),
                "ask_price": vp.get("ask_price") or r.get("ask_price"),
                "fair_value_base": vp.get("fair_value_base"),
                "beds": r.get("beds"),
                "baths": r.get("baths"),
                "sqft": r.get("sqft"),
                "trust_flags": list(r.get("trust_flags") or []),
            }
        )
    return out


def _suggestions_for_search(session: Session) -> list[str]:
    ctx = session.current_search_context or session.search_context or {}
    town = ctx.get("town")
    if town:
        return [
            f"Only 3+ bedrooms in {town}",
            f"Under $900k in {town}",
            f"Walk to the beach in {town}",
            f"Compare {town} to nearby towns",
        ]
    return [
        "Belmar, NJ — 3+ bed near the beach",
        "Avon-by-the-Sea under $1.1M",
        "Show schools and walkability",
    ]


def _chat_text_from_search(response_text: str, listings: list[dict[str, Any]]) -> str:
    """handle_search emits a CLI-style bulleted listing dump. For the chat UI
    the cards render that detail below — so collapse the response to its
    narrative intro and drop the per-item bullets + 'Next best move' footer."""
    if not response_text:
        return ""
    intro_lines = []
    for line in response_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") or stripped.startswith("http"):
            # bulleted item or URL continuation — cards cover this
            continue
        if stripped.lower().startswith("next best move"):
            break
        if stripped:
            intro_lines.append(stripped)
    intro = " ".join(intro_lines)
    if listings and not intro:
        intro = f"Here are {len(listings)} that might fit. Tap a card to dig in."
    return intro


async def search_stream(
    text: str,
    decision: RouterDecision,
    conversation_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """SEARCH tier adapter: run handle_search via dispatch in a threadpool,
    stream a cleaned-up text intro, then emit structured listings + map + suggestions."""
    llm = get_llm()
    session = _load_or_create_session(conversation_id)

    loop = asyncio.get_running_loop()
    try:
        response_text = await loop.run_in_executor(
            None, dispatch, text, decision, session, llm
        )
    except Exception as exc:
        yield events.text_delta(f"Search failed: {exc}")
        yield events.suggestions(_suggestions_for_search(session))
        return

    listings = _build_listings(session)
    intro = _chat_text_from_search(response_text, listings)

    async for ev in _stream_text(intro):
        yield ev

    if listings:
        yield events.listings(listings)
        center, pins = _pins_and_center(listings)
        if pins:
            yield events.map_payload(center, pins)

    yield events.suggestions(_suggestions_for_search(session))
    _finalize_session(session, text, intro, decision.answer_type)


# ---------- BROWSE tier ----------


def _to_listing_from_facts(pid: str, facts: dict[str, Any]) -> dict[str, Any]:
    """Saved-property facts → Listing card. lat/lng keys exist in the schema
    but aren't always populated, so fall back to a Google Maps geocode (cached
    on disk) when missing."""
    address = facts.get("address") or ""
    lat = facts.get("latitude")
    lng = facts.get("longitude")
    if (lat is None or lng is None) and address:
        lat, lng = _geocode(address)
    return {
        "id": pid,
        "address_line": address,
        "city": facts.get("town") or "",
        "state": facts.get("state") or "",
        "zip": _parse_zip(address),
        "price": int(facts.get("ask_price") or facts.get("purchase_price") or 0),
        "beds": int(facts.get("beds") or 0),
        "baths": float(facts.get("baths") or 0),
        "sqft": int(facts.get("sqft") or 0),
        "lot_sqft": int(facts.get("lot_size") or 0) or None,
        "year_built": int(facts["year_built"]) if facts.get("year_built") else None,
        "status": "active",
        "lat": float(lat) if lat is not None else None,
        "lng": float(lng) if lng is not None else None,
    }


def _focal_listing_from_session(session: Session) -> dict[str, Any] | None:
    """Reconstruct the property card for the browse focal point.

    Two paths: saved-corpus pid (cheap fact lookup) or live Zillow listing
    cached on the session (geocode required)."""
    pid = session.current_property_id
    if pid:
        facts = _load_saved_facts(pid)
        if facts:
            return _to_listing_from_facts(pid, facts)
    live = session.current_live_listing
    if isinstance(live, dict):
        return _to_listing_from_live(live)
    return None


_NEXT_QUESTION_RE = re.compile(r"^next best question:\s*(.+)$", re.IGNORECASE)


def _chat_text_from_browse(response_text: str, focal: dict[str, Any] | None) -> str:
    """handle_browse leads with an identifier line ('1600 L St — 4bd/3ba — ask $899k')
    that the focal card already shows. Strip that one line; keep the rest of the
    narrative (setup / support / caution / next-step) for the chat bubble."""
    if not response_text:
        return ""
    lines = response_text.splitlines()
    if focal and lines:
        first = lines[0].strip()
        addr = (focal.get("address_line") or "").lower()
        if addr and first.lower().startswith(addr[:20]):
            lines = lines[1:]
    return "\n".join(line for line in lines if line.strip()).strip()


def _suggestions_for_browse(response_text: str, focal: dict[str, Any] | None) -> list[str]:
    """Blend the model's surfaced 'Next best question' with escalation chips
    that mirror the Run-analysis CTA in the detail panel."""
    suggestions: list[str] = []
    for line in response_text.splitlines():
        m = _NEXT_QUESTION_RE.match(line.strip())
        if m:
            suggestions.append(m.group(1).strip())
            break
    if focal:
        addr = focal.get("address_line") or "this property"
        price = focal.get("price")
        suggestions.append(f"Should I buy {addr} at the ask?")
        if isinstance(price, int) and price > 0:
            target = int(price * 0.95 / 1000) * 1000
            suggestions.append(f"What if I offered ${target:,}?")
        suggestions.append("Compare to nearby sales")
    else:
        suggestions.extend(
            [
                "Search homes in Belmar",
                "Compare Belmar vs. Avon-by-the-Sea",
            ]
        )
    seen: set[str] = set()
    deduped: list[str] = []
    for s in suggestions:
        if s and s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped[:4]


async def browse_stream(
    text: str,
    decision: RouterDecision,
    conversation_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """BROWSE tier adapter: run handle_browse via dispatch in a threadpool,
    then emit a focal listing card + cleaned narrative + escalation suggestions."""
    llm = get_llm()
    session = _load_or_create_session(conversation_id)

    loop = asyncio.get_running_loop()
    try:
        response_text = await loop.run_in_executor(
            None, dispatch, text, decision, session, llm
        )
    except Exception as exc:
        yield events.text_delta(f"Browse failed: {exc}")
        yield events.suggestions(_suggestions_for_browse("", None))
        return

    focal = _focal_listing_from_session(session)
    intro = _chat_text_from_browse(response_text, focal)

    async for ev in _stream_text(intro):
        yield ev

    if focal:
        yield events.listings([focal])
        if focal.get("lat") is not None and focal.get("lng") is not None:
            center, pins = _pins_and_center([focal])
            if pins:
                yield events.map_payload(center, pins)

    yield events.suggestions(_suggestions_for_browse(response_text, focal))
    _finalize_session(session, text, intro, decision.answer_type)


# ---------- DECISION tier ----------


def _frontend_listing_to_backend(pinned: dict[str, Any]) -> dict[str, Any]:
    """Translate the frontend Listing shape (address_line/city/price/source_url)
    into the backend live-listing shape (address/town/ask_price/listing_url)
    that `promote_discovered_listing` and `_select_live_listing_from_session`
    expect. Without this translation, follow-up turns on a discovered listing
    fail at promotion time because the address key is missing."""
    return {
        "address": pinned.get("address_line") or pinned.get("address"),
        "town": pinned.get("city") or pinned.get("town"),
        "state": pinned.get("state"),
        "zip_code": pinned.get("zip") or pinned.get("zip_code"),
        "ask_price": pinned.get("price") or pinned.get("ask_price"),
        "beds": pinned.get("beds"),
        "baths": pinned.get("baths"),
        "sqft": pinned.get("sqft"),
        "property_type": pinned.get("property_type"),
        "listing_status": pinned.get("status") or pinned.get("listing_status"),
        "listing_url": pinned.get("source_url") or pinned.get("listing_url"),
        "external_id": pinned.get("id") or pinned.get("external_id"),
        "source": pinned.get("source"),
    }


def _seed_session_for_pinned(
    session: Session, pinned: dict[str, Any] | None
) -> str | None:
    """Prime session state from a frontend-pinned listing so handle_decision's
    resolver doesn't have to re-parse the address from text. Returns the seeded
    pid (or None if the pin is a live listing without a saved counterpart)."""
    if not pinned:
        return None
    pid_hint = str(pinned.get("id") or "")
    if pid_hint and (_SAVED_ROOT / pid_hint).exists():
        session.current_property_id = pid_hint
        return pid_hint
    if pinned.get("source_url"):
        backend_shape = _frontend_listing_to_backend(pinned)
        session.current_live_listing = backend_shape
        session.selected_search_result = backend_shape
    return None


def _suggestions_for_decision(focal: dict[str, Any] | None) -> list[str]:
    """Decision-tier follow-ups: scenario what-ifs and risk dives. The user
    has already escalated past browse, so chips lean operational."""
    if not focal:
        return [
            "Compare to nearby sales",
            "What's the biggest risk?",
            "Show me the comp set",
        ]
    price = focal.get("price")
    chips: list[str] = []
    if isinstance(price, int) and price > 0:
        target = int(price * 0.95 / 1000) * 1000
        chips.append(f"What if I offered ${target:,}?")
        stretch = int(price * 0.90 / 1000) * 1000
        chips.append(f"What about ${stretch:,}?")
    chips.extend(
        [
            "What's the biggest risk?",
            "Show me the comp set",
        ]
    )
    return chips[:4]


async def decision_stream(
    text: str,
    decision: RouterDecision,
    pinned_listing: dict[str, Any] | None = None,
    conversation_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """DECISION tier adapter: seed session from the pinned listing, run
    handle_decision via dispatch in a threadpool, then re-emit the focal
    listing card + the decision narrative + scenario suggestions.

    The decision narrative is dense (LLM-composed paragraph with stance,
    fair value, basis, premium, trust flags). Streamed as text deltas; richer
    structured 'verdict' events can layer in later without breaking the
    transport contract."""
    llm = get_llm()
    session = _load_or_create_session(conversation_id)
    seeded_pid = _seed_session_for_pinned(session, pinned_listing)

    # The router may have classified the text as BROWSE (e.g. "Analyze X..."
    # from the Run-analysis CTA). dispatch routes by answer_type, so coerce
    # to DECISION here — the caller already decided this turn is decision-tier.
    if decision.answer_type != AnswerType.DECISION:
        decision = dataclasses.replace(decision, answer_type=AnswerType.DECISION)

    loop = asyncio.get_running_loop()
    try:
        response_text = await loop.run_in_executor(
            None, dispatch, text, decision, session, llm
        )
    except Exception as exc:
        yield events.text_delta(f"Decision analysis failed: {exc}")
        yield events.suggestions(_suggestions_for_decision(pinned_listing))
        return

    # Re-emit the focal property card so the assistant turn has visual context
    # even after the detail panel closes. Prefer the live session state — it
    # may have been refined by the resolver — but fall back to the original pin.
    focal = _focal_listing_from_session(session) or pinned_listing
    cleaned, chart_events = _extract_charts(response_text)

    async for ev in _stream_text(cleaned):
        yield ev

    if isinstance(session.last_decision_view, dict):
        yield events.verdict(_verdict_from_view(session.last_decision_view))

    # Town context card (median price/ppsf, confidence tier, seeded signals).
    # Built by handle_decision from town aggregates + local_intelligence files.
    if isinstance(session.last_town_summary, dict):
        yield events.town_summary(session.last_town_summary)

    # Top comps used in the valuation, so the user sees the evidence base
    # without having to ask "show me the comp set" as a follow-up.
    if isinstance(session.last_comps_preview, dict):
        yield events.comps_preview(session.last_comps_preview)

    # Bull/base/bear scenario table lives on session.last_projection_view,
    # populated by handle_decision when the scenario subrun succeeds. Emitted
    # inline so the first DECISION response carries the scenario story
    # alongside the verdict, not as a follow-up. Skipped if the scenario
    # values are all zero/missing — renders as an empty card otherwise.
    if isinstance(session.last_projection_view, dict):
        pv = session.last_projection_view
        if any(isinstance(pv.get(k), (int, float)) and pv.get(k)
               for k in ("bull_case_value", "base_case_value", "bear_case_value")):
            payload = _scenario_table_from_view(pv)
            yield events.scenario_table(
                payload["rows"],
                address=payload["address"],
                ask_price=payload["ask_price"],
                spread=payload["spread"],
            )

    if focal:
        yield events.listings([focal])
        if focal.get("lat") is not None and focal.get("lng") is not None:
            center, pins = _pins_and_center([focal])
            if pins:
                yield events.map_payload(center, pins)

    for chart_ev in chart_events:
        yield chart_ev

    yield events.suggestions(_suggestions_for_decision(focal))
    _finalize_session(session, text, cleaned, decision.answer_type)


# ---------- Generic adapter for remaining tiers ----------


def _suggestions_for_tier(
    answer_type: AnswerType, focal: dict[str, Any] | None
) -> list[str]:
    """Tier-aware follow-up chips. Most tiers nudge toward the next reasonable
    move (decision-tier escalation, scenario projection, comp dive). When no
    focal property is in scope, fall back to discovery-style chips."""
    if focal is None:
        return [
            "Find me a starter home in Belmar",
            "Compare Belmar vs. Avon-by-the-Sea",
            "What's happening in the Asbury Park market?",
        ]

    addr = focal.get("address_line") or "this property"
    price = focal.get("price")
    offer_chip: str | None = None
    if isinstance(price, int) and price > 0:
        target = int(price * 0.95 / 1000) * 1000
        offer_chip = f"What if I offered ${target:,}?"

    by_tier: dict[AnswerType, list[str]] = {
        AnswerType.LOOKUP: [
            f"Should I buy {addr}?",
            "Compare to nearby sales",
            "What's the rental potential?",
        ],
        AnswerType.PROJECTION: [
            offer_chip or "Run a stretch offer scenario",
            "What's the floor price?",
            "Run cash-flow as a rental",
        ],
        AnswerType.STRATEGY: [
            f"Should I buy {addr} at the ask?",
            "Run scenarios at a lower offer",
            "What changes if I rent it instead?",
        ],
        AnswerType.RISK: [
            "What's the worst case?",
            "How can I de-risk this?",
            "Show me the comp set",
        ],
        AnswerType.EDGE: [
            "Run renovation scenarios",
            "What's the value gap?",
            "Compare to recent sales",
        ],
        AnswerType.RENT_LOOKUP: [
            "Should I buy as a rental?",
            "Run cash-flow projection",
            "Compare to mortgage cost",
        ],
        AnswerType.MICRO_LOCATION: [
            f"Should I buy {addr}?",
            "What's the school district?",
            "Compare to nearby sales",
        ],
        AnswerType.COMPARISON: [
            "Pick a winner",
            "Run scenarios on each",
            "What's the differentiator?",
        ],
        AnswerType.RESEARCH: [
            "Show me listings here",
            "What's a good entry point?",
            "Compare to nearby towns",
        ],
        AnswerType.VISUALIZE: [
            f"Should I buy {addr}?",
            "Run scenarios",
            "Show me the comp set",
        ],
        AnswerType.CHITCHAT: [
            "Find me a starter home in Belmar",
            "Compare Belmar vs. Avon-by-the-Sea",
            "What's happening in the Asbury Park market?",
        ],
    }
    chips = [c for c in by_tier.get(answer_type, []) if c]
    seen: set[str] = set()
    deduped: list[str] = []
    for c in chips:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped[:4]


async def dispatch_stream(
    text: str,
    decision: RouterDecision,
    pinned_listing: dict[str, Any] | None = None,
    conversation_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Generic adapter for all intent tiers without bespoke rendering needs.

    Most handlers (lookup, projection, strategy, risk, edge, rent_lookup,
    micro_location, research, visualize) populate `session.current_property_id`
    and return a narrative string. Comparison and chitchat skip the property
    focus but still produce text. We translate that uniformly: stream text,
    surface the focal listing card if one is in scope, attach tier-aware chips."""
    llm = get_llm()
    session = _load_or_create_session(conversation_id)
    _seed_session_for_pinned(session, pinned_listing)

    loop = asyncio.get_running_loop()
    try:
        response_text = await loop.run_in_executor(
            None, dispatch, text, decision, session, llm
        )
    except Exception as exc:
        yield events.text_delta(f"{decision.answer_type.value.title()} failed: {exc}")
        yield events.suggestions(_suggestions_for_tier(decision.answer_type, pinned_listing))
        return

    focal = _focal_listing_from_session(session) or pinned_listing
    cleaned, chart_events = _extract_charts(response_text)

    async for ev in _stream_text(cleaned):
        yield ev

    if isinstance(session.last_projection_view, dict):
        payload = _scenario_table_from_view(session.last_projection_view)
        yield events.scenario_table(
            payload["rows"],
            address=payload["address"],
            ask_price=payload["ask_price"],
            spread=payload["spread"],
        )

    if isinstance(session.last_comparison_view, list) and session.last_comparison_view:
        yield events.comparison_table(
            _comparison_table_from_view(session.last_comparison_view)
        )

    if focal:
        yield events.listings([focal])
        if focal.get("lat") is not None and focal.get("lng") is not None:
            center, pins = _pins_and_center([focal])
            if pins:
                yield events.map_payload(center, pins)

    for chart_ev in chart_events:
        yield chart_ev

    yield events.suggestions(_suggestions_for_tier(decision.answer_type, focal))
    _finalize_session(session, text, cleaned, decision.answer_type)
