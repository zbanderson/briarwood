from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SourceType(str, Enum):
    NEWS = "news"
    PLANNING_BOARD_MINUTES = "planning_board_minutes"
    ZONING_BOARD_MINUTES = "zoning_board_minutes"
    ORDINANCE = "ordinance"
    REDEVELOPMENT_PLAN = "redevelopment_plan"
    INFRASTRUCTURE_UPDATE = "infrastructure_update"
    OTHER = "other"


class SignalType(str, Enum):
    DEVELOPMENT = "development"
    ZONING_CHANGE = "zoning_change"
    REGULATION_CHANGE = "regulation_change"
    INFRASTRUCTURE = "infrastructure"
    EMPLOYER = "employer"
    TOURISM = "tourism"
    CLIMATE_RISK = "climate_risk"
    AMENITY = "amenity"
    SUPPLY = "supply"
    OTHER = "other"


class SignalStatus(str, Enum):
    MENTIONED = "mentioned"
    PROPOSED = "proposed"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    FUNDED = "funded"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


class ImpactDirection(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"
    NEUTRAL = "neutral"


class TimeHorizon(str, Enum):
    NEAR_TERM = "near_term"
    MEDIUM_TERM = "medium_term"
    LONG_TERM = "long_term"


class ReconciliationStatus(str, Enum):
    NEW = "new"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    STATUS_TRANSITION = "status_transition"


class SourceDocument(BaseModel):
    """Normalized source document ready for extraction."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    town: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)
    source_type: SourceType
    title: str = Field(min_length=1)
    url: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    raw_text: str = ""
    cleaned_text: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TownSignal(BaseModel):
    """Structured town-level signal extracted from one or more source documents."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    town: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)
    signal_type: SignalType
    title: str = Field(min_length=1)
    canonical_key: str | None = None
    source_document_id: str = Field(min_length=1)
    source_type: SourceType
    source_date: datetime | None = None
    source_url: str | None = None
    status: SignalStatus
    time_horizon: TimeHorizon
    impact_direction: ImpactDirection
    impact_magnitude: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0.0, le=1.0)
    facts: list[str] = Field(default_factory=list)
    inference: str | None = None
    affected_dimensions: list[str] = Field(default_factory=list)
    evidence_excerpt: str = ""
    created_at: datetime
    updated_at: datetime
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_transition_at: datetime | None = None
    occurrence_count: int = Field(default=1, ge=1)
    reconciliation_status: ReconciliationStatus | None = None
    previous_status: SignalStatus | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TownSignalDraft(BaseModel):
    """Model-facing draft before Briarwood canonical validation and persistence."""

    model_config = ConfigDict(extra="forbid")

    signal_type: SignalType
    title: str = Field(min_length=1)
    status: SignalStatus
    time_horizon: TimeHorizon
    impact_direction: ImpactDirection
    impact_magnitude: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0.0, le=1.0)
    facts: list[str] = Field(default_factory=list)
    inference: str | None = None
    affected_dimensions: list[str] = Field(default_factory=list)
    evidence_excerpt: str = Field(min_length=1)
    location: str | None = None
    units: int | None = Field(default=None, ge=0)
    rationale: str | None = None


class TownSignalDraftBatch(BaseModel):
    """Structured LLM output wrapper for one source document."""

    model_config = ConfigDict(extra="forbid")

    signals: list[TownSignalDraft] = Field(default_factory=list)


class TownSummary(BaseModel):
    """Compact, trust-oriented town pulse summary."""

    model_config = ConfigDict(extra="forbid")

    town: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)
    bullish_signals: list[str] = Field(default_factory=list)
    bearish_signals: list[str] = Field(default_factory=list)
    watch_items: list[str] = Field(default_factory=list)
    confidence_label: str = Field(min_length=1)
    narrative_summary: str = Field(min_length=1)
    generated_at: datetime


class LocalIntelligenceRun(BaseModel):
    """Full output bundle from ingestion through town summary generation."""

    model_config = ConfigDict(extra="forbid")

    town: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)
    documents: list[SourceDocument] = Field(default_factory=list)
    signals: list[TownSignal] = Field(default_factory=list)
    summary: TownSummary
    warnings: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)


class TownPulseView(BaseModel):
    """Lightweight presentation hook for future Dash and report surfaces."""

    model_config = ConfigDict(extra="forbid")

    heading: str
    confidence_label: str
    bullish_items: list[str] = Field(default_factory=list)
    bearish_items: list[str] = Field(default_factory=list)
    watch_items: list[str] = Field(default_factory=list)
    narrative_summary: str
