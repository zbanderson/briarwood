from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any, Protocol

from pydantic import ValidationError

from briarwood.local_intelligence.config import OpenAILocalIntelligenceConfig
from briarwood.local_intelligence.models import (
    ImpactDirection,
    SignalStatus,
    SignalType,
    SourceDocument,
    TimeHorizon,
    TownSignal,
    TownSignalDraft,
    TownSignalDraftBatch,
)
from briarwood.local_intelligence.prompts import LOCAL_INTELLIGENCE_SYSTEM_PROMPT, build_extraction_prompt
from briarwood.local_intelligence.validation import validate_signal_drafts

logger = logging.getLogger(__name__)


class LocalIntelligenceExtractor(Protocol):
    """Adapter boundary for structured town-signal extraction backends."""

    def extract(self, document: SourceDocument) -> list[TownSignal]:
        ...


class RuleBasedLocalIntelligenceExtractor:
    """Deterministic fallback extractor for local documents."""

    PROJECT_MARKERS = (
        "application",
        "proposal",
        "project",
        "redevelopment",
        "site plan",
        "variance",
        "subdivision",
        "overlay",
        "zone change",
        "zoning amendment",
        "ordinance",
        "streetscape",
        "drainage",
        "flood",
        "boardwalk",
        "employer",
        "hotel",
    )

    STATUS_PATTERNS = {
        SignalStatus.APPROVED: re.compile(r"\b(approved|adopted|granted|memorialized)\b", re.IGNORECASE),
        SignalStatus.REJECTED: re.compile(r"\b(denied|rejected|withdrawn)\b", re.IGNORECASE),
        SignalStatus.IN_PROGRESS: re.compile(r"\b(under construction|in progress|work has begun)\b", re.IGNORECASE),
        SignalStatus.FUNDED: re.compile(r"\b(funded|grant awarded|bond authorized)\b", re.IGNORECASE),
        SignalStatus.COMPLETED: re.compile(r"\b(completed|opened|delivered)\b", re.IGNORECASE),
        SignalStatus.PROPOSED: re.compile(r"\b(proposed|submitted|application filed|concept review)\b", re.IGNORECASE),
        SignalStatus.REVIEWED: re.compile(r"\b(reviewed|hearing opened|carried|continued|pending|tabled)\b", re.IGNORECASE),
    }

    def extract(self, document: SourceDocument) -> list[TownSignal]:
        chunks = _text_chunks(document.cleaned_text or document.raw_text)
        signals: list[TownSignal] = []
        for chunk in chunks:
            if not any(marker in chunk.lower() for marker in self.PROJECT_MARKERS):
                continue
            signal = self._signal_from_chunk(document, chunk)
            if signal is not None:
                signals.append(signal)
        return signals

    def _signal_from_chunk(self, document: SourceDocument, chunk: str) -> TownSignal | None:
        title = _extract_title(chunk)
        if not title:
            return None

        status = _extract_status(chunk, self.STATUS_PATTERNS)
        signal_type = _extract_signal_type(chunk)
        units = _extract_units(chunk)
        location = _extract_location(chunk)
        impact_direction = _impact_direction(signal_type, status, chunk)
        time_horizon = _time_horizon(status, signal_type)
        impact_magnitude = _impact_magnitude(units, signal_type, impact_direction)
        facts = _facts(signal_type, status, units, location, document.source_type.value)
        inference = _inference(signal_type, status, impact_direction, units)
        dimensions = _dimensions(signal_type, impact_direction)
        confidence = _confidence(status, units, location, signal_type)
        now = datetime.now(timezone.utc)
        excerpt = chunk.strip()

        signal_id = _signal_id(document.id, title, excerpt)
        metadata: dict[str, object] = {}
        if units is not None:
            metadata["units"] = units
        if location:
            metadata["location"] = location

        return TownSignal(
            id=signal_id,
            town=document.town,
            state=document.state,
            signal_type=signal_type,
            title=title,
            source_document_id=document.id,
            source_type=document.source_type,
            source_date=document.published_at,
            status=status,
            time_horizon=time_horizon,
            impact_direction=impact_direction,
            impact_magnitude=impact_magnitude,
            confidence=confidence,
            facts=facts,
            inference=inference,
            affected_dimensions=dimensions,
            evidence_excerpt=excerpt,
            created_at=now,
            updated_at=now,
            metadata=metadata,
        )


class OpenAILocalIntelligenceExtractor:
    """OpenAI-backed extraction adapter using schema-constrained JSON output."""

    def __init__(
        self,
        client: object | None = None,
        *,
        config: OpenAILocalIntelligenceConfig | None = None,
    ) -> None:
        self.config = config or OpenAILocalIntelligenceConfig.from_env()
        self.client = client or _build_default_client(self.config.timeout_seconds)

    def extract(self, document: SourceDocument) -> list[TownSignal]:
        if self.client is None:
            raise RuntimeError("OpenAI extraction client is not configured.")
        drafts = self.extract_signals_from_document(document)
        signals, warnings = validate_signal_drafts(document, drafts)
        for warning in warnings:
            logger.warning("Local intelligence validation warning for %s: %s", document.id, warning)
        return signals

    def extract_signals_from_document(self, document: SourceDocument) -> list[TownSignalDraft]:
        response = self._invoke_model(document)
        batch = self._parse_batch(response, document)
        return batch.signals

    def _invoke_model(self, document: SourceDocument) -> object:
        try:
            return self.client.responses.create(
                model=self.config.model,
                reasoning={"effort": self.config.reasoning_effort},
                input=[
                    {"role": "system", "content": [{"type": "input_text", "text": LOCAL_INTELLIGENCE_SYSTEM_PROMPT}]},
                    {"role": "user", "content": [{"type": "input_text", "text": build_extraction_prompt(document)}]},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "town_signal_draft_batch",
                        "strict": True,
                        "schema": TownSignalDraftBatch.model_json_schema(),
                    }
                },
                max_output_tokens=self.config.max_output_tokens,
            )
        except Exception as exc:  # pragma: no cover - network/provider failures are environment-specific
            logger.warning("OpenAI extraction request failed for %s: %s", document.id, exc)
            raise

    def _parse_batch(self, response: object, document: SourceDocument) -> TownSignalDraftBatch:
        output_text = _response_output_text(response)
        if not output_text:
            logger.warning("OpenAI extraction returned no output text for %s", document.id)
            return TownSignalDraftBatch()
        try:
            payload = json.loads(output_text)
            return TownSignalDraftBatch.model_validate(payload)
        except json.JSONDecodeError as exc:
            logger.warning("OpenAI extraction returned invalid JSON for %s: %s", document.id, exc)
            return TownSignalDraftBatch()
        except ValidationError as exc:
            logger.warning("OpenAI extraction returned malformed schema for %s: %s", document.id, exc)
            return TownSignalDraftBatch()


def _build_default_client(timeout_seconds: float) -> object | None:
    try:
        from openai import OpenAI
    except ImportError:
        return None
    return OpenAI(timeout=timeout_seconds)


def _response_output_text(response: object) -> str | None:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = getattr(response, "output", None)
    if not isinstance(output, list):
        return None

    fragments: list[str] = []
    for item in output:
        content = getattr(item, "content", None)
        if not isinstance(content, list):
            continue
        for part in content:
            text = getattr(part, "text", None)
            if isinstance(text, str) and text.strip():
                fragments.append(text)
    return "\n".join(fragments).strip() or None


def _text_chunks(text: str) -> list[str]:
    paragraphs = [chunk.strip() for chunk in re.split(r"\n{2,}|(?<=\.)\s{2,}", text) if chunk.strip()]
    return paragraphs or [line.strip() for line in text.splitlines() if line.strip()]


def _extract_units(text: str) -> int | None:
    matches = re.findall(
        r"\b(\d{1,4})\s+(?:(?:residential|market-rate|market rate|affordable|rental)\s+)?(?:unit|units|apartments|condos|townhomes|townhouses)\b",
        text,
        flags=re.IGNORECASE,
    )
    if not matches:
        return None
    return max(int(value) for value in matches)


def _extract_status(text: str, patterns: dict[SignalStatus, re.Pattern[str]]) -> SignalStatus:
    for status, pattern in patterns.items():
        if pattern.search(text):
            return status
    return SignalStatus.MENTIONED


def _extract_signal_type(text: str) -> SignalType:
    lower_text = text.lower()
    if any(token in lower_text for token in ("variance", "overlay", "zoning amendment", "rezoning", "zone change")):
        return SignalType.ZONING_CHANGE
    if any(token in lower_text for token in ("ordinance", "regulation", "short-term rental", "rent control")):
        return SignalType.REGULATION_CHANGE
    if any(token in lower_text for token in ("drainage", "sewer", "boardwalk", "transit", "roadwork", "streetscape", "infrastructure")):
        return SignalType.INFRASTRUCTURE
    if any(token in lower_text for token in ("flood", "stormwater", "resilience", "sea level")):
        return SignalType.CLIMATE_RISK
    if any(token in lower_text for token in ("hotel", "restaurant", "park", "amenity", "arts", "tourism")):
        return SignalType.AMENITY if "tourism" not in lower_text else SignalType.TOURISM
    if any(token in lower_text for token in ("employer", "office", "jobs", "distribution center")):
        return SignalType.EMPLOYER
    if any(token in lower_text for token in ("unit", "apartment", "condo", "townhome", "residential")):
        return SignalType.SUPPLY
    if any(token in lower_text for token in ("redevelopment", "site plan", "subdivision", "project", "application", "proposal")):
        return SignalType.DEVELOPMENT
    return SignalType.OTHER


def _extract_location(text: str) -> str | None:
    address_match = re.search(
        r"\b\d{1,5}\s+[A-Z][A-Za-z0-9'.-]*(?:\s+[A-Z][A-Za-z0-9'.-]*){0,4}\s(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Place|Pl|Court|Ct)\b",
        text,
    )
    if address_match:
        return address_match.group(0)
    location_match = re.search(r"\b(?:at|for|located at)\s+([^.;]{6,60})", text, flags=re.IGNORECASE)
    if location_match:
        return location_match.group(1).strip()
    return None


def _extract_title(text: str) -> str | None:
    quoted = re.search(r"['\"]([^'\"]{4,80})['\"]", text)
    if quoted:
        return quoted.group(1).strip()
    named = re.search(
        r"\b(?:project|application|redevelopment plan|site plan|proposal|ordinance)\s+(?:for|of)\s+([^.;]{4,80})",
        text,
        flags=re.IGNORECASE,
    )
    if named:
        return named.group(1).strip(" -")
    location = _extract_location(text)
    if location:
        return f"{location}"
    words = text.split()
    return " ".join(words[:6]).strip(" -") if len(words) >= 4 else None


def _impact_direction(signal_type: SignalType, status: SignalStatus, text: str) -> ImpactDirection:
    lower_text = text.lower()
    if signal_type == SignalType.CLIMATE_RISK:
        return ImpactDirection.NEGATIVE
    if any(token in lower_text for token in ("traffic concern", "parking issue", "flooding concern", "opposition")):
        return ImpactDirection.NEGATIVE if status != SignalStatus.APPROVED else ImpactDirection.MIXED
    if status in {SignalStatus.APPROVED, SignalStatus.FUNDED, SignalStatus.COMPLETED}:
        return ImpactDirection.POSITIVE
    if status == SignalStatus.REJECTED:
        return ImpactDirection.NEGATIVE if signal_type in {SignalType.AMENITY, SignalType.INFRASTRUCTURE, SignalType.EMPLOYER} else ImpactDirection.MIXED
    if signal_type in {SignalType.SUPPLY, SignalType.DEVELOPMENT}:
        return ImpactDirection.MIXED
    return ImpactDirection.NEUTRAL


def _time_horizon(status: SignalStatus, signal_type: SignalType) -> TimeHorizon:
    if status in {SignalStatus.FUNDED, SignalStatus.IN_PROGRESS, SignalStatus.COMPLETED}:
        return TimeHorizon.NEAR_TERM
    if signal_type in {SignalType.CLIMATE_RISK, SignalType.ZONING_CHANGE, SignalType.REGULATION_CHANGE}:
        return TimeHorizon.LONG_TERM
    return TimeHorizon.MEDIUM_TERM


def _impact_magnitude(units: int | None, signal_type: SignalType, direction: ImpactDirection) -> int:
    base = 2
    if units and units >= 40:
        base = 5
    elif units and units >= 15:
        base = 4
    elif units and units >= 5:
        base = 3
    elif signal_type in {SignalType.INFRASTRUCTURE, SignalType.CLIMATE_RISK, SignalType.REGULATION_CHANGE, SignalType.ZONING_CHANGE}:
        base = 4
    if direction == ImpactDirection.NEUTRAL:
        base = max(1, base - 1)
    return base


def _facts(
    signal_type: SignalType,
    status: SignalStatus,
    units: int | None,
    location: str | None,
    source_type: str,
) -> list[str]:
    facts = [
        f"Signal classified as {signal_type.value.replace('_', ' ')}.",
        f"Source type: {source_type.replace('_', ' ')}.",
        f"Status read as {status.value.replace('_', ' ')}.",
    ]
    if units is not None:
        facts.append(f"Document references approximately {units} units.")
    if location:
        facts.append(f"Location referenced: {location}.")
    return facts


def _inference(
    signal_type: SignalType,
    status: SignalStatus,
    impact_direction: ImpactDirection,
    units: int | None,
) -> str | None:
    if signal_type in {SignalType.SUPPLY, SignalType.DEVELOPMENT} and units is not None:
        return (
            f"This may influence future supply and pricing dynamics if the {units}-unit pipeline reaches delivery."
            if status != SignalStatus.REJECTED
            else f"The rejected pipeline likely reduces near-term new supply pressure from this proposal."
        )
    if signal_type == SignalType.CLIMATE_RISK:
        return "This may increase resilience-related costs or risk perception over time."
    if impact_direction == ImpactDirection.POSITIVE:
        return "This may support local quality, demand, or liquidity if implementation follows through."
    if impact_direction == ImpactDirection.NEGATIVE:
        return "This may create downside pressure or execution risk if the concern persists."
    return None


def _dimensions(signal_type: SignalType, impact_direction: ImpactDirection) -> list[str]:
    mapping = {
        SignalType.DEVELOPMENT: ["future_supply", "home_values"],
        SignalType.SUPPLY: ["future_supply", "rent_growth", "home_values"],
        SignalType.ZONING_CHANGE: ["regulatory_risk", "future_supply"],
        SignalType.REGULATION_CHANGE: ["regulatory_risk", "liquidity"],
        SignalType.INFRASTRUCTURE: ["neighborhood_quality", "amenity_trajectory", "home_values"],
        SignalType.EMPLOYER: ["liquidity", "rent_growth"],
        SignalType.TOURISM: ["rent_growth", "amenity_trajectory", "liquidity"],
        SignalType.CLIMATE_RISK: ["climate_risk", "resilience_risk", "home_values"],
        SignalType.AMENITY: ["neighborhood_quality", "amenity_trajectory", "home_values"],
        SignalType.OTHER: ["home_values"],
    }
    dimensions = list(mapping.get(signal_type, ["home_values"]))
    if impact_direction == ImpactDirection.NEGATIVE and "regulatory_risk" not in dimensions and signal_type in {SignalType.OTHER, SignalType.DEVELOPMENT}:
        dimensions.append("regulatory_risk")
    return dimensions


def _confidence(status: SignalStatus, units: int | None, location: str | None, signal_type: SignalType) -> float:
    score = 0.35
    if status != SignalStatus.MENTIONED:
        score += 0.2
    if units is not None:
        score += 0.2
    if location:
        score += 0.1
    if signal_type != SignalType.OTHER:
        score += 0.1
    return round(min(score, 0.92), 2)


def _signal_id(document_id: str, title: str, excerpt: str) -> str:
    seed = f"{document_id}|{title.lower()}|{excerpt[:120].lower()}"
    return f"sig-{sha1(seed.encode('utf-8')).hexdigest()[:12]}"
