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
from urllib.parse import parse_qs, urlencode, urlparse

import logging

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

import briarwood  # noqa: F401 — side-effect: loads .env so OPENAI_API_KEY is available
from briarwood.agent.dispatch import dispatch
from briarwood.agent.llm import LLMClient, default_client
from briarwood.agent.presentation_advisor import advise_visual_surfaces
from briarwood.agent.router import AnswerType, RouterDecision, classify
from briarwood.agent.session import SESSION_DIR, Session
from briarwood.representation import RepresentationAgent
from briarwood.routing_schema import (
    AnalysisDepth,
    DecisionStance,
    DecisionType,
    UnifiedIntelligenceOutput,
)
from briarwood.agent.tools import (
    _existing_or_slugified_property_id,
    _json_ready,
    search_listings,
)
from briarwood.data_sources.google_maps_client import GoogleMapsClient
from briarwood.listing_intake.service import ListingIntakeService

from api import events

_logger = logging.getLogger(__name__)

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
    fresh Session keyed to the same id is returned and saved on first use.

    Clears `last_verifier_report` so stale reports from the previous turn don't
    leak into the current one — the handler repopulates it if an LLM runs."""
    if not conversation_id:
        return Session()
    path = SESSION_DIR / f"{conversation_id}.json"
    if path.exists():
        try:
            session = Session.load(conversation_id)
        except (json.JSONDecodeError, KeyError) as exc:
            print(f"[session] load failed for {conversation_id}: {exc}; starting fresh", flush=True)
            session = Session(session_id=conversation_id)
    else:
        session = Session(session_id=conversation_id)
    session.clear_response_views()
    return session


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


def _load_saved_enrichment(property_id: str) -> dict[str, Any] | None:
    path = _SAVED_ROOT / property_id / "enrichment.json"
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _parse_zip(address: str | None) -> str | None:
    if not address:
        return None
    m = _ZIP_RE.search(address)
    return m.group(1) if m else None


def _street_view_image_url(
    *,
    latitude: float | None,
    longitude: float | None,
    property_id: str | None = None,
) -> str | None:
    def _proxy_from_location(location: str | None) -> str | None:
        if not isinstance(location, str) or not location.strip():
            return None
        query = urlencode(
            {
                "location": location.strip(),
                "size": "640x360",
                "fov": 90,
                "pitch": 0,
            }
        )
        return f"/api/street-view?{query}"

    if property_id:
        enrichment = _load_saved_enrichment(property_id)
        google = dict((enrichment or {}).get("google") or {})
        cached = google.get("street_view_image_url")
        if isinstance(cached, str) and cached.strip():
            parsed = urlparse(cached)
            location = parse_qs(parsed.query).get("location", [None])[0]
            proxied = _proxy_from_location(location)
            if proxied:
                return proxied
            if latitude is None or longitude is None:
                return cached
    if latitude is None or longitude is None:
        return None
    query = urlencode(
        {
            "latitude": f"{float(latitude):.6f}",
            "longitude": f"{float(longitude):.6f}",
            "size": "640x360",
            "fov": 90,
            "pitch": 0,
        }
    )
    return f"/api/street-view?{query}"


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
    street_view = _street_view_image_url(
        latitude=float(lat) if lat is not None else None,
        longitude=float(lng) if lng is not None else None,
        property_id=pid or None,
    )

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
        "streetViewImageUrl": street_view,
    }


def _to_listing_from_live(entry: dict[str, Any]) -> dict[str, Any]:
    """session.last_live_listing_results entries come from _serialize_live_listing
    in dispatch.py. Zillow discovery doesn't surface lat/lng, so we geocode the
    address via Google Maps Platform. Results are cached on disk in
    data/cache/google_maps/ so repeats are free."""
    ext_id = entry.get("external_id") or entry.get("address") or "live"
    address = entry.get("address") or ""
    lat, lng = _geocode(address) if address else (None, None)
    street_view = _street_view_image_url(
        latitude=float(lat) if lat is not None else None,
        longitude=float(lng) if lng is not None else None,
    )
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
        "streetViewImageUrl": street_view,
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


# ---------- Module attribution ----------
#
# Each emitted structured event maps back to the Briarwood module that produced
# it. The plan calls for surfacing those modules to the user as a chip row so
# they see which machinery contributed to the response, instead of getting
# narrated prose with no provenance.
#
# Step 4 attributes by emitted slot only — the LLM-emitted `[[...]]` markers
# arrive in Step 6 and will layer in additional attribution then. A module that
# ran but produced no emitted output is excluded by design ("ran but didn't
# contribute" is not the same as "contributed").
_MODULE_REGISTRY: list[tuple[str, str, str]] = [
    (events.EVENT_VERDICT,          "valuation_model",   "Valuation Model"),
    (events.EVENT_TRUST_SUMMARY,    "confidence",        "Confidence Engine"),
    (events.EVENT_TOWN_SUMMARY,     "town_context",      "Town Context"),
    (events.EVENT_COMPS_PREVIEW,    "comp_set",          "Comp Set"),
    (events.EVENT_VALUATION_COMPS,     "valuation_model",   "Valuation Model"),
    (events.EVENT_MARKET_SUPPORT_COMPS, "cma",              "CMA"),
    (events.EVENT_SCENARIO_TABLE,   "projection_engine", "Projection Engine"),
    (events.EVENT_COMPARISON_TABLE, "comparison_runner", "Comparison Runner"),
    (events.EVENT_VALUE_THESIS,     "value_thesis",      "Value Thesis"),
    (events.EVENT_RISK_PROFILE,     "risk_profile",      "Risk Profile"),
    (events.EVENT_STRATEGY_PATH,    "strategy_fit",      "Strategy Fit"),
    (events.EVENT_RENT_OUTLOOK,     "rent_outlook",      "Rent Outlook"),
    (events.EVENT_RESEARCH_UPDATE,  "town_research",     "Town Research"),
    (events.EVENT_LISTINGS,         "listing_discovery", "Listing Discovery"),
    (events.EVENT_MAP,              "geocoder",          "Geocoder"),
    (events.EVENT_CHART,            "visualizer",        "Visualizer"),
]

# AUDIT 1.5.4: grounding anchors carry prompt-facing module labels (see
# `briarwood.agent.prompt_modules.PROMPT_MODULE_LABELS`). Mapping them to the
# registry's module_id lets us credit a module that the cascade ran but whose
# dedicated SSE event didn't surface — e.g., valuation informs a risk-only
# turn, but without this mapping the badge row would show only "Risk Profile".
# `contributed_to="narrative"` signals the citation came from the LLM prose,
# not a structured card, so the UI can render it with a lighter weight.
_PROMPT_LABEL_TO_MODULE: dict[str, tuple[str, str]] = {
    "ValuationModel":      ("valuation_model",      "Valuation Model"),
    "ValueThesis":         ("value_thesis",         "Value Thesis"),
    "RiskProfile":         ("risk_profile",         "Risk Profile"),
    "ProjectionEngine":    ("projection_engine",    "Projection Engine"),
    "RentOutlook":         ("rent_outlook",         "Rent Outlook"),
    "StrategyFit":         ("strategy_fit",         "Strategy Fit"),
    "TownResearch":        ("town_research",        "Town Research"),
    "DecisionSynthesizer": ("decision_synthesizer", "Decision Synthesizer"),
}
_NARRATIVE_SLOT = "narrative"


class _ModuleTracker:
    """Accumulates which modules contributed to a turn, ordered by first
    contribution. Each call to `record(event_type)` looks up the module that
    produces that event and records the contribution. Modules with no matching
    event are silently ignored — the registry is the source of truth."""

    def __init__(self) -> None:
        self._modules: dict[str, dict[str, Any]] = {}

    def record(self, event_type: str | None) -> None:
        if not event_type:
            return
        for et, mid, label in _MODULE_REGISTRY:
            if et != event_type:
                continue
            entry = self._modules.setdefault(
                mid, {"module": mid, "label": label, "contributed_to": []}
            )
            if et not in entry["contributed_to"]:
                entry["contributed_to"].append(et)
            return

    def record_anchor(self, module_label: str | None) -> None:
        """Credit a module cited via a grounding anchor (LLM prose). Unknown
        labels are ignored — `PROMPT_MODULE_LABELS` is the allowlist, and the
        `_PROMPT_LABEL_TO_MODULE` mapping is the source of truth here."""
        if not module_label:
            return
        mapping = _PROMPT_LABEL_TO_MODULE.get(module_label)
        if mapping is None:
            return
        mid, label = mapping
        entry = self._modules.setdefault(
            mid, {"module": mid, "label": label, "contributed_to": []}
        )
        if _NARRATIVE_SLOT not in entry["contributed_to"]:
            entry["contributed_to"].append(_NARRATIVE_SLOT)

    def items(self) -> list[dict[str, Any]]:
        return list(self._modules.values())


async def _track_modules(
    stream: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """Wrap a streamer; pass events through unchanged and emit a `modules_ran`
    event at the end iff at least one module contributed. Errors propagate
    without flushing — main.py owns the error/done envelope."""
    tracker = _ModuleTracker()
    async for ev in stream:
        if isinstance(ev, dict):
            tracker.record(ev.get("type"))
            # AUDIT 1.5.4: a narrative-only turn (no structured cards) still
            # cites modules via grounding anchors. Credit them too so the
            # `modules_ran` badge row reflects the full cascade, not just the
            # modules whose dedicated events fired.
            if ev.get("type") == events.EVENT_GROUNDING_ANNOTATIONS:
                for anchor in ev.get("anchors") or ():
                    if isinstance(anchor, dict):
                        tracker.record_anchor(anchor.get("module"))
        yield ev
    items = tracker.items()
    if items:
        yield events.modules_ran(items)


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


class _DecisionView(BaseModel):
    """Typed round-trip for the decision-view dict persisted on the session.

    AUDIT 1.2.4: `_verdict_from_view` used to pluck keys from an untyped dict
    via `.get()`, which silently absorbed field renames and type drift between
    the producer (`_decision_view_to_dict` in dispatch.py) and the consumer
    (this projector). Validating through Pydantic surfaces that drift at
    readtime.

    `extra="ignore"` is intentional: persisted session JSON on disk may carry
    keys that predate schema changes, and we don't want to break replay.
    Unknown-field drift is caught on the write side via the dispatch-layer
    snapshot shape; here we only need to guarantee the subset we project."""

    model_config = ConfigDict(extra="ignore")

    address: str | None = None
    town: str | None = None
    state: str | None = None
    decision_stance: str | None = None
    primary_value_source: str | None = None

    @field_validator("decision_stance")
    @classmethod
    def _stance_must_be_known(cls, value: str | None) -> str | None:
        """AUDIT O.7: reject legacy decision-engine labels (BUY / LEAN BUY /
        NEUTRAL / LEAN PASS / AVOID from briarwood.decision_engine, used only
        by the Dash + reports stack). If one ever appears on the session view,
        surface it as a validation error so the projector falls back to an
        empty verdict rather than letting an unknown vocabulary reach the UI."""
        if value is None:
            return None
        allowed = {s.value for s in DecisionStance}
        if value not in allowed:
            raise ValueError(f"unknown decision_stance: {value!r}")
        return value
    ask_price: float | None = None
    all_in_basis: float | None = None
    fair_value_base: float | None = None
    value_low: float | None = None
    value_high: float | None = None
    ask_premium_pct: float | None = None
    basis_premium_pct: float | None = None
    trust_flags: list[str] = Field(default_factory=list)
    trust_summary: dict[str, Any] = Field(default_factory=dict)
    what_must_be_true: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    why_this_stance: list[str] = Field(default_factory=list)
    what_changes_my_view: list[str] = Field(default_factory=list)
    contradiction_count: int | None = None
    blocked_thesis_warnings: list[str] = Field(default_factory=list)
    overrides_applied: dict[str, Any] = Field(default_factory=dict)


def _verdict_from_view(view: dict[str, Any]) -> dict[str, Any]:
    """Project the saved decision view into the verdict event payload. UI
    consumes this to render a stance badge + price/value comparison + trust
    flags, instead of parsing it back out of LLM-narrated prose.

    AUDIT 1.2.4: validate through `_DecisionView` before projecting. A shape
    mismatch (type drift, unexpected None where a list is required, etc.) logs
    a warning and falls back to an empty verdict so the UI still renders."""

    try:
        model = _DecisionView.model_validate(view)
    except ValidationError as exc:
        _logger.warning("decision view failed validation (%s): %s", type(exc).__name__, exc)
        model = _DecisionView()

    return {
        "address": model.address,
        "town": model.town,
        "state": model.state,
        "stance": model.decision_stance,
        "primary_value_source": model.primary_value_source,
        "ask_price": model.ask_price,
        "all_in_basis": model.all_in_basis,
        "fair_value_base": model.fair_value_base,
        "value_low": model.value_low,
        "value_high": model.value_high,
        "ask_premium_pct": model.ask_premium_pct,
        "basis_premium_pct": model.basis_premium_pct,
        "trust_flags": list(model.trust_flags),
        "what_must_be_true": list(model.what_must_be_true),
        "key_risks": list(model.key_risks),
        "trust_summary": dict(model.trust_summary),
        "why_this_stance": list(model.why_this_stance),
        "what_changes_my_view": list(model.what_changes_my_view),
        "contradiction_count": model.contradiction_count,
        "blocked_thesis_warnings": list(model.blocked_thesis_warnings),
        "overrides_applied": dict(model.overrides_applied),
    }


def _trust_summary_from_view(view: dict[str, Any]) -> dict[str, Any] | None:
    trust_summary = dict(view.get("trust_summary") or {})
    if not trust_summary and not list(view.get("trust_flags") or []):
        return None
    return {
        "confidence": trust_summary.get("confidence"),
        "band": trust_summary.get("band"),
        "field_completeness": trust_summary.get("field_completeness"),
        "estimated_reliance": trust_summary.get("estimated_reliance"),
        "contradiction_count": trust_summary.get("contradiction_count") or view.get("contradiction_count"),
        "blocked_thesis_warnings": list(
            trust_summary.get("blocked_thesis_warnings")
            or view.get("blocked_thesis_warnings")
            or []
        ),
        "trust_flags": list(trust_summary.get("trust_flags") or view.get("trust_flags") or []),
        "why_this_stance": list(view.get("why_this_stance") or []),
        "what_changes_my_view": list(view.get("what_changes_my_view") or []),
    }


def _valuation_comps_from_view(view: dict[str, Any]) -> dict[str, Any] | None:
    """Project the valuation-module comps (comps that fed fair value) from the
    value_thesis view. F2: these are the ``comparable_sales`` module's
    ``comps_used`` rows, NOT live Zillow market comps. Every row must carry
    valuation-module provenance — enforced at emission by
    ``_assert_valuation_module_comps``.
    """
    rows = list(view.get("comps") or [])
    if not rows:
        return None
    return {
        "address": view.get("address"),
        "town": view.get("town"),
        "state": view.get("state"),
        "summary": view.get("comp_selection_summary"),
        "rows": rows,
    }


def _market_support_comps_from_view(view: dict[str, Any] | None) -> dict[str, Any] | None:
    """Project the market-support comps (live Zillow / saved fallback) from a
    dedicated session view. F2: these are sourced from ``get_cma()`` and are
    explicitly NOT the comps that fed fair value.
    """
    if not isinstance(view, dict):
        return None
    rows = list(view.get("comps") or [])
    if not rows:
        return None
    return {
        "address": view.get("address"),
        "town": view.get("town"),
        "state": view.get("state"),
        "summary": view.get("comp_selection_summary"),
        "rows": rows,
    }


def _assert_valuation_module_comps(payload: dict[str, Any]) -> None:
    """Raise AssertionError if any row in a valuation_comps payload did not
    originate from the valuation module's ``comps_used`` set.

    F2 contract guard: the valuation_comps event promises rows that fed the
    fair value computation. ``briarwood.agent.tools._selected_comp_rows``
    — the canonical projection of ``comparable_sales.comps_used`` —
    stamps ``feeds_fair_value=True`` on every row by construction
    (provenance can override, but falls back to True). Any row without that
    flag is either a live-market context comp or a browse-path neighbor —
    neither belongs in this event.
    """
    rows = payload.get("rows") or []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise AssertionError(
                f"valuation_comps row {index} is not a dict: {row!r}"
            )
        if row.get("feeds_fair_value") is not True:
            raise AssertionError(
                "valuation_comps event must only carry comps that fed the fair "
                f"value computation; row {index} has feeds_fair_value="
                f"{row.get('feeds_fair_value')!r} (source_label="
                f"{row.get('source_label')!r}, selected_by="
                f"{row.get('selected_by')!r})."
            )


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
        "basis_label": view.get("basis_label"),
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


_RISK_FLAG_LABELS: dict[str, str] = {
    "older_housing_stock": "Older housing stock",
    "long_marketing_period": "Long marketing period",
    "flood_zone": "Flood exposure",
    "high_vacancy": "High vacancy",
    "weak_town_context": "Weak town context",
    "valuation_anchor_divergence": "Valuation anchors diverge",
    "incomplete_carry_inputs": "Incomplete carry inputs",
    "zoning_unverified": "Zoning unverified",
    "thin_comp_set": "Thin comp set",
}


def _native_scenario_chart(view: dict[str, Any]) -> dict[str, Any] | None:
    if not any(
        isinstance(view.get(k), (int, float)) and view.get(k) is not None
        for k in ("bull_case_value", "base_case_value", "bear_case_value")
    ):
        return None
    return events.chart(
        title="5-year value range",
        kind="scenario_fan",
        spec={
            "kind": "scenario_fan",
            "ask_price": view.get("ask_price"),
            "basis_label": view.get("basis_label"),
            "bull_case_value": view.get("bull_case_value"),
            "base_case_value": view.get("base_case_value"),
            "bear_case_value": view.get("bear_case_value"),
            "stress_case_value": view.get("stress_case_value"),
        },
        provenance=["Projection Engine", "scenario_x_risk"],
    )


def _native_value_chart(view: dict[str, Any]) -> dict[str, Any] | None:
    if not any(
        isinstance(view.get(k), (int, float)) and view.get(k) is not None
        for k in ("ask_price", "fair_value_base", "premium_discount_pct")
    ):
        return None
    return events.chart(
        title="Ask vs fair value",
        kind="value_opportunity",
        spec={
            "kind": "value_opportunity",
            "ask_price": view.get("ask_price"),
            "fair_value_base": view.get("fair_value_base"),
            "premium_discount_pct": view.get("premium_discount_pct"),
            "value_drivers": list(view.get("key_value_drivers") or view.get("value_drivers") or []),
        },
        provenance=[
            "Value Thesis",
            "Valuation",
            *([] if not list(view.get("comps") or []) else ["CMA"]),
        ],
    )


def _native_cma_chart(
    view: dict[str, Any] | None,
    *,
    market_view: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """F2: the "where the comps sit" positioning chart visualizes live-market
    support around the subject, so rows come from ``last_market_support_view``
    when available. ``view`` (value_thesis_view) still supplies the subject's
    anchors — ask, fair value, value band — but its ``comps`` list now only
    holds valuation-module rows, which are a narrower set. Falling back to the
    value-thesis comps keeps existing turns that populate both views from
    regressing; callers that want strict separation pass ``market_view``.
    """
    view = view or {}
    market_view = market_view or {}
    candidate_rows = list(market_view.get("comps") or []) or list(view.get("comps") or [])
    rows = [row for row in candidate_rows if isinstance(row, dict)]
    priced_rows = [row for row in rows if isinstance(row.get("ask_price"), (int, float))]
    if not priced_rows:
        return None
    return events.chart(
        title="Where the comps sit",
        kind="cma_positioning",
        spec={
            "kind": "cma_positioning",
            "subject_address": view.get("address") or market_view.get("address"),
            "subject_ask": view.get("ask_price"),
            "fair_value_base": view.get("fair_value_base"),
            "value_low": view.get("value_low"),
            "value_high": view.get("value_high"),
            "comps": [
                {
                    "address": row.get("address"),
                    "ask_price": row.get("ask_price"),
                    "source_label": row.get("source_label"),
                    "selected_by": row.get("selected_by"),
                    "feeds_fair_value": row.get("feeds_fair_value"),
                }
                for row in priced_rows[:8]
            ],
        },
        provenance=["CMA", "Value Thesis"],
    )


def _native_risk_chart(view: dict[str, Any]) -> dict[str, Any] | None:
    """Build the risk_bar chart spec.

    AUDIT 1.4.3: `value` used to be rendered as "N pts" with no unit
    declared in the spec, and when `total_penalty` was missing every bar
    silently collapsed to the same fallback (0.12) without any signal that
    it was synthesized. The spec now carries:

    - `value_unit="penalty_share"` — `value` is a fraction of the total
      risk penalty in [0, 1]. Removes the "pts of what?" ambiguity.
    - `value_source="computed" | "fallback"` — when `total_penalty` is
      missing, every bar falls back to a shared default; flagging the
      source lets the frontend mute the bar values rather than render
      identical uninformative widths.
    """
    risk_flags = list(view.get("risk_flags") or [])
    trust_flags = list(view.get("trust_flags") or [])
    if not risk_flags and not trust_flags:
        return None
    total_penalty = view.get("total_penalty")
    has_total = isinstance(total_penalty, (int, float)) and risk_flags
    per_risk = float(total_penalty) / len(risk_flags) if has_total else 0.12
    value_source = "computed" if has_total else "fallback"
    items: list[dict[str, Any]] = []
    for flag in risk_flags:
        items.append(
            {
                "label": _RISK_FLAG_LABELS.get(flag, str(flag).replace("_", " ").title()),
                "value": per_risk,
                "tone": "risk",
            }
        )
    trust_weight = max(per_risk * 0.6, 0.08) if risk_flags else 0.08
    for flag in trust_flags:
        items.append(
            {
                "label": _RISK_FLAG_LABELS.get(flag, str(flag).replace("_", " ").title()),
                "value": trust_weight,
                "tone": "trust",
            }
        )
    return events.chart(
        title="Risk drivers",
        kind="risk_bar",
        spec={
            "kind": "risk_bar",
            "ask_price": view.get("ask_price"),
            "bear_value": view.get("bear_value"),
            "stress_value": view.get("stress_value"),
            "value_unit": "penalty_share",
            "value_source": value_source,
            "items": items,
        },
        provenance=["Risk Profile", "Confidence Engine"],
    )


def _native_rent_chart(view: dict[str, Any]) -> dict[str, Any] | None:
    payload = dict(view.get("burn_chart_payload") or {})
    series = list(payload.get("series") or [])
    if not series:
        return None
    points: list[dict[str, Any]] = []
    for row in series:
        if not isinstance(row, dict):
            continue
        year = row.get("year")
        if not isinstance(year, (int, float)):
            continue
        points.append(
            {
                "year": int(year),
                "rent_base": row.get("rent_base"),
                "rent_bull": row.get("rent_bull"),
                "rent_bear": row.get("rent_bear"),
                "monthly_obligation": row.get("monthly_obligation"),
            }
        )
    if not points:
        return None
    title = "Rent vs monthly cost"
    return events.chart(
        title=title,
        kind="rent_burn",
        spec={
            "kind": "rent_burn",
            "title": title,
            "working_label": "Working rent outlook",
            "market_label": "Zillow market regime",
            "market_context_note": view.get("market_context_note"),
            "market_rent": view.get("zillow_market_rent"),
            "market_rent_low": view.get("zillow_market_rent_low"),
            "market_rent_high": view.get("zillow_market_rent_high"),
            "points": points,
        },
        provenance=[
            "Rent Outlook",
            "rent_x_cost",
            *([] if not view.get("rent_haircut_pct") else ["rent_x_risk"]),
        ],
    )


def _native_rent_ramp_chart(view: dict[str, Any]) -> dict[str, Any] | None:
    payload = dict(view.get("ramp_chart_payload") or {})
    series = list(payload.get("series") or [])
    if not series:
        return None
    points: list[dict[str, Any]] = []
    for row in series:
        if not isinstance(row, dict):
            continue
        year = row.get("year")
        if not isinstance(year, (int, float)):
            continue
        points.append(
            {
                "year": int(year),
                "net_0": row.get("net_0"),
                "net_3": row.get("net_3"),
                "net_5": row.get("net_5"),
            }
        )
    if not points:
        return None
    title = "Can rent catch up?"
    return events.chart(
        title=title,
        kind="rent_ramp",
        spec={
            "kind": "rent_ramp",
            "title": title,
            "current_rent": payload.get("current_rent"),
            "monthly_obligation": payload.get("monthly_obligation"),
            "today_cash_flow": payload.get("today_cash_flow"),
            "break_even_years": dict(payload.get("break_even_years") or {}),
            "points": points,
        },
        provenance=[
            "Rent Outlook",
            "rent_x_cost",
            *([] if not view.get("rent_haircut_pct") else ["rent_x_risk"]),
        ],
    )


def _visual_advice_payload(session: Session) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if isinstance(session.last_value_thesis_view, dict):
        payload["value"] = dict(session.last_value_thesis_view)
        valuation_payload = _valuation_comps_from_view(session.last_value_thesis_view)
        if valuation_payload is not None:
            payload["cma"] = valuation_payload
    if isinstance(session.last_rent_outlook_view, dict):
        payload["rent"] = dict(session.last_rent_outlook_view)
    if isinstance(session.last_projection_view, dict):
        payload["scenario"] = dict(session.last_projection_view)
    if isinstance(session.last_risk_view, dict):
        payload["risk"] = dict(session.last_risk_view)
    trust_source = None
    if isinstance(session.last_decision_view, dict):
        trust_source = _trust_summary_from_view(session.last_decision_view)
    elif isinstance(session.last_value_thesis_view, dict):
        trust_source = _trust_summary_from_view(session.last_value_thesis_view)
    elif isinstance(session.last_rent_outlook_view, dict):
        trust_source = _trust_summary_from_view(session.last_rent_outlook_view)
    if isinstance(trust_source, dict) and trust_source:
        payload["trust"] = trust_source
    return payload


def _load_visual_advice(session: Session, llm: LLMClient | None) -> dict[str, dict[str, str]]:
    if isinstance(getattr(session, "last_visual_advice", None), dict):
        return dict(session.last_visual_advice or {})
    payload = _visual_advice_payload(session)
    advice = advise_visual_surfaces(llm=llm, payload=payload) or {}
    session.last_visual_advice = advice
    return advice


def _apply_chart_advice(
    chart_event: dict[str, Any] | None,
    advice: dict[str, dict[str, str]],
    section: str,
) -> dict[str, Any] | None:
    if chart_event is None:
        return None
    section_advice = advice.get(section)
    if not section_advice:
        return chart_event
    patched = dict(chart_event)
    patched["advisor"] = {
        "title": None,
        "summary": section_advice.get("summary"),
        "companion": section_advice.get("companion"),
        "preferred_surface": section_advice.get("preferred_surface"),
    }
    return patched


_CHART_ID_TO_ADVICE_SECTION: dict[str, str] = {
    "value_opportunity": "value",
    "cma_positioning": "cma",
    "risk_bar": "risk",
    "rent_burn": "rent",
    "rent_ramp": "rent",
    "scenario_fan": "scenario",
}


def _unified_from_session(session: Session) -> UnifiedIntelligenceOutput | None:
    """Reconstruct a best-effort UnifiedIntelligenceOutput for the
    Representation Agent from the session views produced by `handle_decision`.

    The session persists a projected view of the verdict, not the raw routed
    output. We synthesize the fields the Agent reads (stance, value position,
    trust flags, drivers, risks, reasoning) from the decision + value-thesis
    views. Non-representation fields (`recommendation`, `best_path`, etc.) are
    filled with inert defaults so the Pydantic model validates without
    pretending the surface has information it does not."""
    decision_view = (
        session.last_decision_view
        if isinstance(session.last_decision_view, dict)
        else None
    )
    value_view = (
        session.last_value_thesis_view
        if isinstance(session.last_value_thesis_view, dict)
        else {}
    )
    if not decision_view:
        return None

    stance_raw = decision_view.get("decision_stance")
    try:
        stance = DecisionStance(stance_raw) if stance_raw else DecisionStance.CONDITIONAL
    except ValueError:
        stance = DecisionStance.CONDITIONAL

    trust_summary_raw = decision_view.get("trust_summary")
    trust_summary = dict(trust_summary_raw) if isinstance(trust_summary_raw, dict) else {}
    confidence_raw = trust_summary.get("confidence")
    confidence = (
        max(0.0, min(1.0, float(confidence_raw)))
        if isinstance(confidence_raw, (int, float))
        else 0.5
    )

    key_value_drivers = list(
        value_view.get("key_value_drivers")
        or value_view.get("value_drivers")
        or []
    )

    return UnifiedIntelligenceOutput(
        recommendation="Decision summary pending.",
        decision=DecisionType.MIXED,
        best_path="review",
        key_value_drivers=key_value_drivers,
        key_risks=list(decision_view.get("key_risks") or []),
        confidence=confidence,
        analysis_depth_used=AnalysisDepth.DECISION,
        decision_stance=stance,
        primary_value_source=decision_view.get("primary_value_source") or "unknown",
        value_position={
            "ask_price": decision_view.get("ask_price"),
            "fair_value_base": decision_view.get("fair_value_base"),
            "ask_premium_pct": decision_view.get("ask_premium_pct"),
            "basis_premium_pct": decision_view.get("basis_premium_pct"),
        },
        what_must_be_true=list(decision_view.get("what_must_be_true") or []),
        trust_flags=list(decision_view.get("trust_flags") or []),
        trust_summary=trust_summary,
        contradiction_count=int(decision_view.get("contradiction_count") or 0),
        blocked_thesis_warnings=list(decision_view.get("blocked_thesis_warnings") or []),
        why_this_stance=list(decision_view.get("why_this_stance") or []),
        what_changes_my_view=list(decision_view.get("what_changes_my_view") or []),
    )


def _representation_module_views(
    session: Session,
) -> dict[str, dict[str, Any] | None]:
    """Snapshot the session views the Representation Agent may cite.

    Keys mirror `briarwood.representation.agent.KNOWN_SOURCE_VIEWS`. A view
    that was not populated by this turn is passed as `None` so the agent
    can tell "the module did not run" from "the module ran and had no
    usable data"."""
    return {
        "last_decision_view": session.last_decision_view
        if isinstance(session.last_decision_view, dict)
        else None,
        "last_value_thesis_view": session.last_value_thesis_view
        if isinstance(session.last_value_thesis_view, dict)
        else None,
        "last_market_support_view": session.last_market_support_view
        if isinstance(session.last_market_support_view, dict)
        else None,
        "last_risk_view": session.last_risk_view
        if isinstance(session.last_risk_view, dict)
        else None,
        "last_strategy_view": session.last_strategy_view
        if isinstance(session.last_strategy_view, dict)
        else None,
        "last_rent_outlook_view": session.last_rent_outlook_view
        if isinstance(session.last_rent_outlook_view, dict)
        else None,
        "last_projection_view": session.last_projection_view
        if isinstance(session.last_projection_view, dict)
        else None,
    }


def _representation_charts(
    session: Session,
    user_question: str,
    visual_advice: dict[str, dict[str, str]],
    llm: LLMClient | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run the Representation Agent and return advisor-patched chart events
    plus a serializable view of the selections for telemetry.

    Returns `([], [])` when the session has no verdict yet — callers should
    still emit whatever non-chart cards they have. Never raises: agent
    failures degrade to an empty selection list."""
    unified = _unified_from_session(session)
    if unified is None:
        return [], []
    module_views = _representation_module_views(session)
    try:
        agent = RepresentationAgent(llm_client=llm)
        plan = agent.plan(
            unified,
            user_question=user_question,
            module_views=module_views,
        )
    except Exception as exc:
        _logger.warning("representation agent failed: %s", exc)
        return [], []

    market_view = module_views.get("last_market_support_view")
    raw_events = agent.render_events(plan, module_views, market_view=market_view)
    patched: list[dict[str, Any]] = []
    for ev in raw_events:
        kind = ev.get("kind") or ""
        section = _CHART_ID_TO_ADVICE_SECTION.get(kind, kind)
        patched_event = _apply_chart_advice(ev, visual_advice, section)
        patched.append(patched_event if patched_event is not None else ev)
    selections = [s.model_dump(mode="json") for s in plan.selections]
    try:
        session.last_representation_plan = {"selections": selections}
    except Exception:
        # session dataclass may not declare this slot yet; it is advisory
        # telemetry only and doesn't need to persist to land the feature.
        pass
    return patched, selections


def _append_chart_once(
    bucket: list[dict[str, Any]],
    chart_event: dict[str, Any] | None,
) -> bool:
    """Append a chart event only if its kind/url combo is not already present."""
    if chart_event is None:
        return False
    kind = chart_event.get("kind")
    url = chart_event.get("url")
    spec = chart_event.get("spec")
    for existing in bucket:
        if existing.get("kind") != kind:
            continue
        if url and existing.get("url") == url:
            return False
        if spec and existing.get("spec") == spec:
            return False
        if not url and not spec:
            return False
    bucket.append(chart_event)
    return True


def _contract_next_actions(session: Session) -> list[str]:
    payload = (
        session.last_presentation_payload
        if isinstance(session.last_presentation_payload, dict)
        else None
    )
    if not payload:
        return []
    actions = payload.get("next_actions")
    if not isinstance(actions, list):
        return []
    return [str(action).strip() for action in actions if isinstance(action, str) and action.strip()]


def _slot_derived_chips(session: Session) -> list[str]:
    """Build follow-up chips from populated session slots.

    Each slot yields at most one chip, ordered by how "hot" the thread is:
    risk dives first (user just saw key_risks — the top one is the most
    likely next question), then value thesis, scenarios, comps, strategy,
    rent, research. Duplicates are trimmed by the caller via a seen-set.
    """
    chips: list[str] = list(_contract_next_actions(session))

    risk = session.last_risk_view if isinstance(session.last_risk_view, dict) else None
    if risk:
        key_risks = risk.get("key_risks")
        if isinstance(key_risks, list) and key_risks:
            top = key_risks[0]
            if isinstance(top, str) and top.strip():
                chips.append(f"Tell me more about {top.strip()}")

    thesis = (
        session.last_value_thesis_view
        if isinstance(session.last_value_thesis_view, dict)
        else None
    )
    if thesis and any(
        thesis.get(k) for k in ("value_drivers", "key_value_drivers", "what_must_be_true")
    ):
        chips.append("What are the key value drivers?")
        if thesis.get("what_changes_my_view") or thesis.get("blocked_thesis_warnings"):
            chips.append("What would change your value view?")

    projection = (
        session.last_projection_view
        if isinstance(session.last_projection_view, dict)
        else None
    )
    if projection and any(
        isinstance(projection.get(k), (int, float)) and projection.get(k)
        for k in ("bull_case_value", "base_case_value", "bear_case_value")
    ):
        chips.append("What would a 10% price cut do?")

    comps = (
        session.last_comps_preview
        if isinstance(session.last_comps_preview, dict)
        else None
    )
    if comps:
        total = comps.get("count")
        displayed = comps.get("comps")
        displayed_n = len(displayed) if isinstance(displayed, list) else 0
        if isinstance(total, int) and total > displayed_n:
            remaining = total - displayed_n
            chips.append(f"Show me the remaining {remaining} comps")
        else:
            chips.append("Why were these comps chosen?")

    strategy = (
        session.last_strategy_view
        if isinstance(session.last_strategy_view, dict)
        else None
    )
    if strategy and strategy.get("best_path"):
        chips.append("Walk through the recommended path")

    rent = (
        session.last_rent_outlook_view
        if isinstance(session.last_rent_outlook_view, dict)
        else None
    )
    if rent and rent.get("monthly_rent"):
        chips.append("What's the cash-on-cash if I rent it?")
        if isinstance(rent.get("break_even_rent"), (int, float)):
            chips.append("What rent would make this work?")

    town = (
        session.last_town_summary
        if isinstance(session.last_town_summary, dict)
        else None
    )
    if town:
        doc_count = town.get("doc_count")
        if isinstance(doc_count, int) and doc_count > 0:
            chips.append("What's driving the town outlook?")

    # F2: value_thesis_view carries the valuation-module comps that fed fair
    # value; last_market_support_view carries the live-market context comps.
    # Two distinct chips so the user picks which panel to drill into.
    thesis_view = session.last_value_thesis_view
    if isinstance(thesis_view, dict) and thesis_view.get("comps"):
        chips.append("Which comps actually fed fair value?")
    market_view = session.last_market_support_view
    if isinstance(market_view, dict) and market_view.get("comps"):
        chips.append("How does the live market look around here?")

    return chips


def _blend_chips(primary: list[str], fallback: list[str], limit: int = 4) -> list[str]:
    """Dedup-merge slot-derived chips with tier defaults. Slot chips come
    first because they're freshly grounded in what just rendered; defaults
    pad the list up to `limit` for variety when slots are sparse."""
    seen: set[str] = set()
    out: list[str] = []
    for chip in (*primary, *fallback):
        if chip and chip not in seen:
            seen.add(chip)
            out.append(chip)
            if len(out) >= limit:
                break
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


def search_stream(
    text: str,
    decision: RouterDecision,
    conversation_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    return _track_modules(_search_stream_impl(text, decision, conversation_id))


async def _search_stream_impl(
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
    if isinstance(session.last_verifier_report, dict):
        report = session.last_verifier_report
        anchors = report.get("anchors") or []
        if anchors or report.get("ungrounded_declaration"):
            yield events.grounding_annotations(
                list(anchors),
                ungrounded_declaration=bool(report.get("ungrounded_declaration")),
            )
        yield events.verifier_report(report)
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
    street_view = _street_view_image_url(
        latitude=float(lat) if lat is not None else None,
        longitude=float(lng) if lng is not None else None,
        property_id=pid,
    )
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
        "streetViewImageUrl": street_view,
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


def _surface_narrative(session: Session | None, fallback: str) -> str:
    if session and isinstance(session.last_surface_narrative, str) and session.last_surface_narrative.strip():
        return session.last_surface_narrative
    return fallback


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


def _suggestions_for_browse(
    response_text: str,
    focal: dict[str, Any] | None,
    session: Session | None = None,
) -> list[str]:
    """Blend the model's surfaced 'Next best question' with escalation chips
    that mirror the Run-analysis CTA in the detail panel. Slot-derived chips
    (from `session.last_*`) take priority when available."""
    slot_chips = _slot_derived_chips(session) if session else []

    suggestions: list[str] = []
    if session and session.current_property_id and session.last_answer_contract != "cma":
        suggestions.append("Run a live CMA with market comps")
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
    return _blend_chips(slot_chips, suggestions)


def browse_stream(
    text: str,
    decision: RouterDecision,
    conversation_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    return _track_modules(_browse_stream_impl(text, decision, conversation_id))


async def _browse_stream_impl(
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
        yield events.suggestions(_suggestions_for_browse("", None, session))
        return

    focal = _focal_listing_from_session(session)
    surface_text = _surface_narrative(session, response_text)
    intro = _chat_text_from_browse(surface_text, focal)
    visual_advice = _load_visual_advice(session, llm)

    primary_events: list[dict[str, Any]] = []
    secondary_events: list[dict[str, Any]] = []
    native_chart_emitted = False

    if isinstance(session.last_town_summary, dict):
        primary_events.append(events.town_summary(session.last_town_summary))

    if isinstance(session.last_comps_preview, dict):
        primary_events.append(events.comps_preview(session.last_comps_preview))

    if isinstance(session.last_value_thesis_view, dict):
        primary_events.append(events.value_thesis(session.last_value_thesis_view))
        valuation_payload = _valuation_comps_from_view(session.last_value_thesis_view)
        if valuation_payload is not None:
            _assert_valuation_module_comps(valuation_payload)
            primary_events.append(events.valuation_comps(valuation_payload))
        market_payload = _market_support_comps_from_view(
            session.last_market_support_view if isinstance(session.last_market_support_view, dict) else None
        )
        if market_payload is not None:
            primary_events.append(events.market_support_comps(market_payload))
        trust_payload = session.last_trust_view or _trust_summary_from_view(session.last_value_thesis_view)
        if trust_payload is not None:
            primary_events.append(events.trust_summary(trust_payload))
        native_chart = _apply_chart_advice(
            _native_value_chart(session.last_value_thesis_view),
            visual_advice,
            "value",
        )
        if _append_chart_once(secondary_events, native_chart):
            native_chart_emitted = True
        cma_chart = _apply_chart_advice(
            _native_cma_chart(
                session.last_value_thesis_view,
                market_view=session.last_market_support_view
                if isinstance(session.last_market_support_view, dict)
                else None,
            ),
            visual_advice,
            "cma",
        )
        if _append_chart_once(secondary_events, cma_chart):
            native_chart_emitted = True

    if isinstance(session.last_strategy_view, dict):
        primary_events.append(events.strategy_path(session.last_strategy_view))

    if isinstance(session.last_rent_outlook_view, dict):
        primary_events.append(events.rent_outlook(session.last_rent_outlook_view))
        native_chart = _apply_chart_advice(
            _native_rent_chart(session.last_rent_outlook_view),
            visual_advice,
            "rent",
        )
        if _append_chart_once(secondary_events, native_chart):
            native_chart_emitted = True
        native_ramp_chart = _apply_chart_advice(
            _native_rent_ramp_chart(session.last_rent_outlook_view),
            visual_advice,
            "rent",
        )
        if _append_chart_once(secondary_events, native_ramp_chart):
            native_chart_emitted = True

    if isinstance(session.last_projection_view, dict):
        payload = _scenario_table_from_view(session.last_projection_view)
        secondary_events.append(
            events.scenario_table(
                payload["rows"],
                address=payload["address"],
                ask_price=payload["ask_price"],
                basis_label=payload["basis_label"],
                spread=payload["spread"],
            )
        )
        native_chart = _apply_chart_advice(
            _native_scenario_chart(session.last_projection_view),
            visual_advice,
            "scenario",
        )
        if _append_chart_once(secondary_events, native_chart):
            native_chart_emitted = True

    for ev in primary_events:
        yield ev

    async for ev in _stream_text(intro):
        yield ev

    for ev in secondary_events:
        yield ev

    if focal:
        yield events.listings([focal])
        if focal.get("lat") is not None and focal.get("lng") is not None:
            center, pins = _pins_and_center([focal])
            if pins:
                yield events.map_payload(center, pins)

    if not native_chart_emitted:
        _, chart_events = _extract_charts(surface_text)
        for chart_ev in chart_events:
            yield chart_ev

    yield events.suggestions(_suggestions_for_browse(surface_text, focal, session))
    if isinstance(session.last_verifier_report, dict):
        report = session.last_verifier_report
        anchors = report.get("anchors") or []
        if anchors or report.get("ungrounded_declaration"):
            yield events.grounding_annotations(
                list(anchors),
                ungrounded_declaration=bool(report.get("ungrounded_declaration")),
            )
        yield events.verifier_report(report)
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


def _suggestions_for_decision(
    focal: dict[str, Any] | None,
    session: Session | None = None,
) -> list[str]:
    """Decision-tier follow-ups: scenario what-ifs and risk dives. The user
    has already escalated past browse, so chips lean operational. Slot chips
    (derived from the structured cards just rendered) come first."""
    slot_chips = _slot_derived_chips(session) if session else []

    if not focal:
        return _blend_chips(
            slot_chips,
            [
                "Compare to nearby sales",
                "What's the biggest risk?",
                "Show me the comp set",
            ],
        )
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
    return _blend_chips(slot_chips, chips)


def decision_stream(
    text: str,
    decision: RouterDecision,
    pinned_listing: dict[str, Any] | None = None,
    conversation_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    return _track_modules(
        _decision_stream_impl(text, decision, pinned_listing, conversation_id)
    )


async def _decision_stream_impl(
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
        yield events.suggestions(_suggestions_for_decision(pinned_listing, session))
        return

    # Re-emit the focal property card so the assistant turn has visual context
    # even after the detail panel closes. Prefer the live session state — it
    # may have been refined by the resolver — but fall back to the original pin.
    focal = _focal_listing_from_session(session) or pinned_listing
    surface_text = _surface_narrative(session, response_text)
    cleaned, chart_events = _extract_charts(surface_text)
    visual_advice = _load_visual_advice(session, llm)

    primary_events: list[dict[str, Any]] = []
    projection_secondary: list[dict[str, Any]] = []
    native_projection_chart_emitted = False

    if isinstance(session.last_decision_view, dict):
        primary_events.append(events.verdict(_verdict_from_view(session.last_decision_view)))

    if isinstance(session.last_town_summary, dict):
        primary_events.append(events.town_summary(session.last_town_summary))

    if isinstance(session.last_comps_preview, dict):
        primary_events.append(events.comps_preview(session.last_comps_preview))

    # Value thesis / CMA / risk / strategy / rent carry the module-level evidence
    # behind the verdict. Each is gated on its session view being populated; if a
    # given module did not run (or ran but left no view), the corresponding card
    # is silently skipped, matching the _dispatch_stream_impl contract.
    if isinstance(session.last_value_thesis_view, dict):
        primary_events.append(events.value_thesis(session.last_value_thesis_view))
        valuation_payload = _valuation_comps_from_view(session.last_value_thesis_view)
        if valuation_payload is not None:
            _assert_valuation_module_comps(valuation_payload)
            primary_events.append(events.valuation_comps(valuation_payload))
        market_payload = _market_support_comps_from_view(
            session.last_market_support_view if isinstance(session.last_market_support_view, dict) else None
        )
        if market_payload is not None:
            primary_events.append(events.market_support_comps(market_payload))

    if isinstance(session.last_risk_view, dict):
        primary_events.append(events.risk_profile(session.last_risk_view))

    if isinstance(session.last_strategy_view, dict):
        primary_events.append(events.strategy_path(session.last_strategy_view))

    if isinstance(session.last_rent_outlook_view, dict):
        primary_events.append(events.rent_outlook(session.last_rent_outlook_view))

    # Representation Agent (AUDIT 1.4 / 1.7): decision-tier charts are now
    # picked by the Representation Agent against the registered chart catalog,
    # backed by the UnifiedIntelligenceOutput we reconstruct from session
    # views. The hardcoded `_native_*_chart` fan-out used to emit the same
    # six charts whenever the corresponding view was populated — the agent
    # replaces that with a claim-driven selection.
    representation_charts, _representation_selections = _representation_charts(
        session,
        text,
        visual_advice,
        llm,
    )
    for chart_ev in representation_charts:
        if _append_chart_once(projection_secondary, chart_ev):
            native_projection_chart_emitted = True

    if isinstance(session.last_decision_view, dict):
        trust_payload = session.last_trust_view or _trust_summary_from_view(session.last_decision_view)
        if trust_payload is not None:
            primary_events.append(events.trust_summary(trust_payload))

    for ev in primary_events:
        yield ev

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
            projection_secondary.append(
                events.scenario_table(
                    payload["rows"],
                    address=payload["address"],
                    ask_price=payload["ask_price"],
                    basis_label=payload["basis_label"],
                    spread=payload["spread"],
                )
            )
            # The scenario_fan chart that used to accompany this table is
            # now the Representation Agent's call — it was emitted above as
            # part of `representation_charts` if the agent picked it.

    async for ev in _stream_text(cleaned):
        yield ev

    for ev in projection_secondary:
        yield ev

    if focal:
        yield events.listings([focal])
        if focal.get("lat") is not None and focal.get("lng") is not None:
            center, pins = _pins_and_center([focal])
            if pins:
                yield events.map_payload(center, pins)

    if not native_projection_chart_emitted:
        for chart_ev in chart_events:
            yield chart_ev

    yield events.suggestions(_suggestions_for_decision(focal, session))
    if isinstance(session.last_verifier_report, dict):
        report = session.last_verifier_report
        anchors = report.get("anchors") or []
        if anchors or report.get("ungrounded_declaration"):
            yield events.grounding_annotations(
                list(anchors),
                ungrounded_declaration=bool(report.get("ungrounded_declaration")),
            )
        yield events.verifier_report(report)
    _finalize_session(session, text, cleaned, decision.answer_type)


# ---------- Generic adapter for remaining tiers ----------


def _suggestions_for_tier(
    answer_type: AnswerType,
    focal: dict[str, Any] | None,
    session: Session | None = None,
) -> list[str]:
    """Tier-aware follow-up chips. Most tiers nudge toward the next reasonable
    move (decision-tier escalation, scenario projection, comp dive). When no
    focal property is in scope, fall back to discovery-style chips. Slot
    chips (derived from populated structured views) take priority."""
    slot_chips = _slot_derived_chips(session) if session else []

    if focal is None:
        return _blend_chips(
            slot_chips,
            [
                "Find me a starter home in Belmar",
                "Compare Belmar vs. Avon-by-the-Sea",
                "What's happening in the Asbury Park market?",
            ],
        )

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
    return _blend_chips(slot_chips, chips)


def dispatch_stream(
    text: str,
    decision: RouterDecision,
    pinned_listing: dict[str, Any] | None = None,
    conversation_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    return _track_modules(
        _dispatch_stream_impl(text, decision, pinned_listing, conversation_id)
    )


async def _dispatch_stream_impl(
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
        yield events.suggestions(_suggestions_for_tier(decision.answer_type, pinned_listing, session))
        return

    focal = _focal_listing_from_session(session) or pinned_listing
    surface_text = _surface_narrative(session, response_text)
    cleaned, chart_events = _extract_charts(surface_text)
    visual_advice = _load_visual_advice(session, llm)

    primary_events: list[dict[str, Any]] = []
    secondary_events: list[dict[str, Any]] = []
    native_chart_emitted = False

    # Tier-specific structured cards. Each handler populates at most one of
    # these slots per turn; emit whichever is present before the prose so the
    # user sees the actual model output while the narration catches up.
    if isinstance(session.last_town_summary, dict):
        primary_events.append(events.town_summary(session.last_town_summary))

    if isinstance(session.last_comps_preview, dict):
        primary_events.append(events.comps_preview(session.last_comps_preview))

    if isinstance(session.last_value_thesis_view, dict):
        primary_events.append(events.value_thesis(session.last_value_thesis_view))
        valuation_payload = _valuation_comps_from_view(session.last_value_thesis_view)
        if valuation_payload is not None:
            _assert_valuation_module_comps(valuation_payload)
            primary_events.append(events.valuation_comps(valuation_payload))
        market_payload = _market_support_comps_from_view(
            session.last_market_support_view if isinstance(session.last_market_support_view, dict) else None
        )
        if market_payload is not None:
            primary_events.append(events.market_support_comps(market_payload))
        trust_payload = session.last_trust_view or _trust_summary_from_view(session.last_value_thesis_view)
        if trust_payload is not None:
            primary_events.append(events.trust_summary(trust_payload))
        native_chart = _apply_chart_advice(
            _native_value_chart(session.last_value_thesis_view),
            visual_advice,
            "value",
        )
        if _append_chart_once(secondary_events, native_chart):
            native_chart_emitted = True
        cma_chart = _apply_chart_advice(
            _native_cma_chart(
                session.last_value_thesis_view,
                market_view=session.last_market_support_view
                if isinstance(session.last_market_support_view, dict)
                else None,
            ),
            visual_advice,
            "cma",
        )
        if _append_chart_once(secondary_events, cma_chart):
            native_chart_emitted = True

    if isinstance(session.last_risk_view, dict):
        primary_events.append(events.risk_profile(session.last_risk_view))
        native_chart = _apply_chart_advice(
            _native_risk_chart(session.last_risk_view),
            visual_advice,
            "risk",
        )
        if _append_chart_once(secondary_events, native_chart):
            native_chart_emitted = True

    if isinstance(session.last_strategy_view, dict):
        primary_events.append(events.strategy_path(session.last_strategy_view))

    if isinstance(session.last_rent_outlook_view, dict):
        primary_events.append(events.rent_outlook(session.last_rent_outlook_view))
        trust_payload = session.last_trust_view or _trust_summary_from_view(session.last_rent_outlook_view)
        if trust_payload is not None:
            primary_events.append(events.trust_summary(trust_payload))
        native_chart = _apply_chart_advice(
            _native_rent_chart(session.last_rent_outlook_view),
            visual_advice,
            "rent",
        )
        if _append_chart_once(secondary_events, native_chart):
            native_chart_emitted = True
        native_ramp_chart = _apply_chart_advice(
            _native_rent_ramp_chart(session.last_rent_outlook_view),
            visual_advice,
            "rent",
        )
        if _append_chart_once(secondary_events, native_ramp_chart):
            native_chart_emitted = True

    if isinstance(session.last_research_view, dict):
        primary_events.append(events.research_update(session.last_research_view))

    if isinstance(session.last_projection_view, dict):
        payload = _scenario_table_from_view(session.last_projection_view)
        secondary_events.append(
            events.scenario_table(
                payload["rows"],
                address=payload["address"],
                ask_price=payload["ask_price"],
                basis_label=payload["basis_label"],
                spread=payload["spread"],
            )
        )
        native_chart = _apply_chart_advice(
            _native_scenario_chart(session.last_projection_view),
            visual_advice,
            "scenario",
        )
        if _append_chart_once(secondary_events, native_chart):
            native_chart_emitted = True

    if isinstance(session.last_comparison_view, list) and session.last_comparison_view:
        secondary_events.append(
            events.comparison_table(
                _comparison_table_from_view(session.last_comparison_view)
            )
        )

    for ev in primary_events:
        yield ev

    async for ev in _stream_text(cleaned):
        yield ev

    for ev in secondary_events:
        yield ev

    if focal:
        yield events.listings([focal])
        if focal.get("lat") is not None and focal.get("lng") is not None:
            center, pins = _pins_and_center([focal])
            if pins:
                yield events.map_payload(center, pins)

    if not native_chart_emitted:
        for chart_ev in chart_events:
            yield chart_ev

    yield events.suggestions(_suggestions_for_tier(decision.answer_type, focal, session))
    if isinstance(session.last_verifier_report, dict):
        report = session.last_verifier_report
        anchors = report.get("anchors") or []
        if anchors or report.get("ungrounded_declaration"):
            yield events.grounding_annotations(
                list(anchors),
                ungrounded_declaration=bool(report.get("ungrounded_declaration")),
            )
        yield events.verifier_report(report)
    _finalize_session(session, text, cleaned, decision.answer_type)
