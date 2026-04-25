"""FastAPI app exposing the chat bridge.

Run locally:
    uvicorn api.main:app --reload --port 8000

The Next.js client (web/) proxies POST /api/chat through its own route handler
and re-streams to the browser. SSE wire format is owned here; see api/events.py.
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api import events
from api.mock_listings import looks_like_listing_query, map_payload_for, mock_listings_for
from api.pipeline_adapter import (
    browse_stream,
    classify_turn,
    decision_stream,
    dispatch_stream,
    extract_zillow_url,
    ingest_zillow_url,
    search_stream,
)
from api.store import get_store
from briarwood.data_sources.google_maps_client import GoogleMapsClient

# Kept as an import-time guard: any module that touches the agent pipeline
# needs briarwood's .env autoload to have run first.
from briarwood.agent.router import AnswerType  # noqa: E402
from briarwood.agent.turn_manifest import (
    end_turn,
    record_classification,
    record_dispatch,
    record_note,
    start_turn,
)

app = FastAPI(title="Briarwood Web API", version="0.1.0")

# CORS — Next dev server runs on :3000. Lock down for prod later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Chart artifacts: handlers (PROJECTION/RISK/EDGE/RENT_LOOKUP/VISUALIZE) write
# Plotly HTML files to data/agent_artifacts/{session_id}/. Mount that dir so
# the chat UI can iframe them via the URLs we emit in `chart` events.
_ARTIFACTS_DIR = Path("data/agent_artifacts")
_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/artifacts", StaticFiles(directory=str(_ARTIFACTS_DIR)), name="artifacts")


# --- Request / response shapes ---

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    conversation_id: str | None = None
    # When set, the user has pinned a specific listing as the subject of this
    # turn (e.g. clicked "Run analysis" in the detail panel). The echo stream
    # uses this to emit listing-aware intros + suggestions; the real router
    # will use it to dispatch the decision/valuation cascade.
    pinned_listing: dict[str, Any] | None = None


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: int
    updated_at: int


class ConversationDetail(ConversationSummary):
    messages: list[dict[str, Any]] = Field(default_factory=list)


class CreateConversationRequest(BaseModel):
    title: str | None = None


class RenameRequest(BaseModel):
    title: str


# --- Conversation endpoints ---

@app.get("/api/conversations", response_model=list[ConversationSummary])
def list_conversations() -> list[dict[str, Any]]:
    return get_store().list_conversations()


@app.post("/api/conversations", response_model=ConversationSummary)
def create_conversation(body: CreateConversationRequest) -> dict[str, Any]:
    return get_store().create_conversation(title=body.title)


@app.get("/api/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str) -> dict[str, Any]:
    conv = get_store().get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conv


@app.patch("/api/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, body: RenameRequest) -> dict[str, str]:
    get_store().rename_conversation(conversation_id, body.title)
    return {"status": "ok"}


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict[str, str]:
    get_store().delete_conversation(conversation_id)
    return {"status": "ok"}


# --- Chat streaming endpoint ---

def _derive_title(text: str) -> str:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return "New chat"
    return cleaned[:60] + ("…" if len(cleaned) > 60 else "")


async def _echo_stream(
    user_text: str,
    pinned_listing: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Placeholder generator. Will be replaced by the real router/orchestrator
    bridge once the wire format is locked in. Until then, it emits enough
    structured payloads (text + listings + map + suggestions) to exercise the
    full UI render path end-to-end."""
    if pinned_listing is not None:
        async for ev in _echo_pinned(user_text, pinned_listing):
            yield ev
        return

    is_listing_query = looks_like_listing_query(user_text)

    if is_listing_query:
        intro = "Here are a few places that might fit. Tap a card to dig in."
    else:
        intro = f"Echo: {user_text}"

    for word in intro.split():
        yield events.text_delta(word + " ")
        await asyncio.sleep(0.025)

    if is_listing_query:
        listings = mock_listings_for(user_text)
        if listings:
            yield events.listings(listings)
            map_args = map_payload_for(listings)
            yield events.map_payload(map_args["center"], map_args["pins"])
            yield events.suggestions(
                [
                    "Narrow to under $900k",
                    "Show schools nearby",
                    "Compare to last year",
                    "Only 4+ bedrooms",
                ]
            )
            return

    yield events.suggestions(
        [
            "Find me a starter home in Belmar",
            "Compare Belmar vs. Avon-by-the-Sea",
            "What's happening in the Asbury Park market?",
        ]
    )


async def _echo_pinned(
    user_text: str,
    listing: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    """Listing-aware echo branch. Fires when the user has pinned a specific
    property (e.g. via the detail panel's 'Run analysis' CTA)."""
    address = listing.get("address_line", "this property")
    city = listing.get("city", "")
    price = listing.get("price")
    price_str = f"${price:,}" if isinstance(price, int) else "the list price"

    intro = (
        f"Looking at {address}"
        f"{' in ' + city if city else ''} — at {price_str}, "
        "here's what stands out. Comps, scenarios, and a decision summary "
        "will render inline once the orchestrator bridge is wired in."
    )
    for word in intro.split():
        yield events.text_delta(word + " ")
        await asyncio.sleep(0.02)

    # Re-emit the pinned listing so the assistant turn has visual context
    # even after the panel closes.
    yield events.listings([listing])
    lat, lng = listing.get("lat"), listing.get("lng")
    if lat is not None and lng is not None:
        pin = {
            "id": listing.get("id", "pinned"),
            "lat": lat,
            "lng": lng,
            "label": f"${price // 1000}k" if isinstance(price, int) else "Pinned",
        }
        yield events.map_payload([lng, lat], [pin])

    yield events.suggestions(
        [
            "Compare to nearby sales",
            "What's the school district?",
            f"Run scenarios at {price_str} offer" if isinstance(price, int) else "Run offer scenarios",
            "Estimate renovation costs",
        ]
    )


@app.post("/api/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages must not be empty")

    last = req.messages[-1]
    if last.role != "user":
        raise HTTPException(status_code=400, detail="last message must be from user")

    store = get_store()
    conversation_id = req.conversation_id
    created_new = False
    if conversation_id is None:
        conv = store.create_conversation(title=_derive_title(last.content))
        conversation_id = conv["id"]
        created_new = True
    else:
        conv = store.get_conversation(conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="conversation not found")

    # Persist the user turn before streaming the assistant response.
    user_msg = store.add_message(conversation_id, "user", last.content)

    async def event_source() -> AsyncIterator[str]:
        # Per-turn manifest — populated as the turn unfolds, emitted to
        # stderr at the end when BRIARWOOD_TRACE=1. Always created, even
        # when the turn errors out, so the failure case is observable too.
        start_turn(user_text=last.content, conversation_id=conversation_id)
        try:
            async for chunk in _event_source_inner():
                yield chunk
        finally:
            end_turn()

    async def _event_source_inner() -> AsyncIterator[str]:
        # Surface conversation id immediately so the client can navigate.
        if created_new:
            yield events.encode_sse(events.conversation_event(conversation_id, conv["title"] if not created_new else _derive_title(last.content)))
        yield events.encode_sse(events.message_event(user_msg["id"], "user"))

        # Pasted Zillow URL → run intake (SearchAPI hydration), persist as a
        # saved property, and short-circuit straight to decision_stream with
        # the freshly-ingested listing as the pin. Without this branch a URL
        # paste would either route through SEARCH/BROWSE on the slug-derived
        # text or, worse, dispatch on a stale saved record with null financials.
        pinned_listing = req.pinned_listing
        url_in_text = extract_zillow_url(last.content) if pinned_listing is None else None
        if url_in_text:
            print(f"[chat] zillow url detected: {url_in_text}", flush=True)
            ingested, ingest_err = ingest_zillow_url(url_in_text)
            if ingested is not None:
                print(
                    f"[chat] zillow ingest ok: pid={ingested.get('id')} "
                    f"price={ingested.get('price')}",
                    flush=True,
                )
                pinned_listing = ingested
            else:
                print(f"[chat] zillow ingest failed: {ingest_err}", flush=True)
                yield events.encode_sse(
                    events.error(
                        f"Couldn't load that Zillow listing: {ingest_err}. "
                        "Paste the listing details (price, beds/baths, sqft) "
                        "and I'll run the analysis on what you provide."
                    )
                )

        # Classify every turn, then route by intent tier. SEARCH / BROWSE /
        # DECISION have specialized adapters; everything else (LOOKUP /
        # PROJECTION / STRATEGY / RISK / EDGE / RENT_LOOKUP / MICRO_LOCATION /
        # COMPARISON / RESEARCH / VISUALIZE / CHITCHAT) flows through the
        # generic dispatch_stream. _echo_stream is now only a fallback for
        # router failures.
        classify_raised = False
        try:
            decision = classify_turn(last.content)
        except Exception as exc:  # noqa: BLE001 — router fail → echo fallback
            decision = None
            classify_raised = True
            yield events.encode_sse(
                events.error(f"router classify failed, using echo: {exc}")
            )

        # NEW-V-010: classify_turn returns None (no exception) when no LLM
        # provider is configured. Surface that as an explicit error and stop;
        # do NOT fall through to _echo_stream, which serves mock listings.
        if decision is None and not classify_raised:
            yield events.encode_sse(
                events.error(
                    "LLM service unavailable — check configuration "
                    "(OPENAI_API_KEY / ANTHROPIC_API_KEY)."
                )
            )
            yield events.encode_sse(events.done())
            return

        if decision is not None:
            print(
                f"[chat] classify: {decision.answer_type.value} "
                f"conf={decision.confidence:.2f} reason={decision.reason!r}",
                flush=True,
            )
            record_classification(
                answer_type=decision.answer_type.value,
                confidence=decision.confidence,
                reason=decision.reason,
            )
        elif classify_raised:
            record_note("classify_turn raised; falling back to echo")

        # Pinned listing + canonical "Analyze X..." text = the Run-analysis CTA
        # in the detail panel. Treat that click as explicit decision-tier
        # escalation, since the router would otherwise classify it as BROWSE.
        # A URL-pasted message also lands here once ingestion has populated
        # pinned_listing above — promote that to decision-tier as well.
        is_run_analysis_click = (
            pinned_listing is not None
            and last.content.strip().lower().startswith("analyze ")
        )
        is_url_paste_decision = pinned_listing is not None and url_in_text is not None

        if decision is None:
            stream = _echo_stream(last.content, pinned_listing)
            record_dispatch("echo")
        elif (
            is_run_analysis_click
            or is_url_paste_decision
            or decision.answer_type == AnswerType.DECISION
        ):
            stream = decision_stream(
                last.content, decision, pinned_listing, conversation_id=conversation_id
            )
            record_dispatch("decision_stream")
        elif decision.answer_type == AnswerType.SEARCH and not pinned_listing:
            stream = search_stream(last.content, decision, conversation_id=conversation_id)
            record_dispatch("search_stream")
        elif decision.answer_type == AnswerType.BROWSE and not pinned_listing:
            stream = browse_stream(last.content, decision, conversation_id=conversation_id)
            record_dispatch("browse_stream")
        else:
            stream = dispatch_stream(
                last.content, decision, pinned_listing, conversation_id=conversation_id
            )
            record_dispatch("dispatch_stream")

        collected_text: list[str] = []
        collected_events: list[dict[str, Any]] = []
        try:
            async for ev in stream:
                if ev["type"] == events.EVENT_TEXT_DELTA:
                    collected_text.append(ev["content"])
                else:
                    collected_events.append(ev)
                yield events.encode_sse(ev)
        except Exception as exc:  # noqa: BLE001 — boundary handler
            yield events.encode_sse(events.error(str(exc)))
            yield events.encode_sse(events.done())
            return

        assistant_text = "".join(collected_text).strip()
        assistant_msg = store.add_message(
            conversation_id, "assistant", assistant_text, events=collected_events
        )
        yield events.encode_sse(events.message_event(assistant_msg["id"], "assistant"))
        yield events.encode_sse(events.done())

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/street-view")
def street_view(
    latitude: float | None = Query(None),
    longitude: float | None = Query(None),
    location: str | None = Query(None),
    size: str = Query("640x360"),
    fov: int = Query(90),
    pitch: int = Query(0),
) -> Response:
    client = GoogleMapsClient()
    if not client.is_configured:
        raise HTTPException(status_code=503, detail="GOOGLE_MAPS_API_KEY is not configured")

    image_url: str | None
    if isinstance(location, str) and location.strip():
        image_url = client.street_view_image_url_for_location(
            location=location,
            size=size,
            fov=fov,
            pitch=pitch,
        )
    elif latitude is not None and longitude is not None:
        image_url = client.street_view_image_url(
            latitude=latitude,
            longitude=longitude,
            size=size,
            fov=fov,
            pitch=pitch,
        )
    else:
        raise HTTPException(status_code=400, detail="Either location or latitude/longitude is required")
    if not image_url:
        raise HTTPException(status_code=503, detail="Street View URL could not be generated")

    request = Request(
        image_url,
        headers={
            "User-Agent": "Briarwood/1.0",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=12.0) as upstream:
            body = upstream.read()
            content_type = upstream.headers.get("Content-Type", "image/jpeg")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
        raise HTTPException(
            status_code=exc.code if isinstance(exc.code, int) else 502,
            detail=detail or "Google Street View request failed",
        ) from exc
    except URLError as exc:
        raise HTTPException(status_code=502, detail=f"Google Street View unavailable: {exc}") from exc

    return Response(
        content=body,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
