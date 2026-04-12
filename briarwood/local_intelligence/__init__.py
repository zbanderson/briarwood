"""Local Intelligence subsystem for town-level document ingestion and synthesis."""

from .adapters import (
    LocalIntelligenceExtractor,
    OpenAILocalIntelligenceExtractor,
    RuleBasedLocalIntelligenceExtractor,
)
from .collector import MunicipalDocumentCollector, MunicipalSourceSeed
from .classification import (
    TOWN_PULSE_BUCKET_DEFINITIONS,
    TOWN_PULSE_BUCKET_LABELS,
    bucket_town_signals,
    classify_town_signal,
    rank_town_signals,
)
from .config import OpenAILocalIntelligenceConfig
from .models import (
    ImpactDirection,
    LocalIntelligenceRun,
    ReconciliationStatus,
    SignalStatus,
    SignalType,
    SourceDocument,
    SourceType,
    TimeHorizon,
    TownSignalDraft,
    TownSignalDraftBatch,
    TownPulseView,
    TownSignal,
    TownSummary,
)
from .service import LocalIntelligenceService
from .storage import JsonLocalSignalStore, LocalSignalStore

__all__ = [
    "ImpactDirection",
    "LocalIntelligenceExtractor",
    "LocalIntelligenceRun",
    "LocalIntelligenceService",
    "OpenAILocalIntelligenceConfig",
    "OpenAILocalIntelligenceExtractor",
    "RuleBasedLocalIntelligenceExtractor",
    "MunicipalDocumentCollector",
    "MunicipalSourceSeed",
    "TOWN_PULSE_BUCKET_DEFINITIONS",
    "TOWN_PULSE_BUCKET_LABELS",
    "ReconciliationStatus",
    "JsonLocalSignalStore",
    "LocalSignalStore",
    "SignalStatus",
    "SignalType",
    "SourceDocument",
    "SourceType",
    "TimeHorizon",
    "TownSignalDraft",
    "TownSignalDraftBatch",
    "TownPulseView",
    "TownSignal",
    "TownSummary",
    "bucket_town_signals",
    "classify_town_signal",
    "rank_town_signals",
]
