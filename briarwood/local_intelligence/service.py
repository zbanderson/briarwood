from __future__ import annotations

import logging
import time
from typing import Any

from briarwood.local_intelligence.adapters import LocalIntelligenceExtractor, RuleBasedLocalIntelligenceExtractor
from briarwood.local_intelligence.collector import MunicipalDocumentCollector
from briarwood.local_intelligence.models import LocalIntelligenceRun, SourceDocument, TownSignal, TownSummary
from briarwood.local_intelligence.normalize import normalize_source_documents
from briarwood.local_intelligence.reconcile import reconcile_signals
from briarwood.local_intelligence.storage import JsonLocalSignalStore, LocalSignalStore
from briarwood.local_intelligence.summarize import build_town_summary

logger = logging.getLogger(__name__)


class LocalIntelligenceService:
    """Orchestrate ingestion, extraction, reconciliation, and town summary generation."""

    def __init__(
        self,
        *,
        extractor: LocalIntelligenceExtractor | None = None,
        store: LocalSignalStore | None = None,
        collector: MunicipalDocumentCollector | None = None,
    ) -> None:
        self.extractor = extractor or RuleBasedLocalIntelligenceExtractor()
        self.store = store or JsonLocalSignalStore()
        self.collector = collector or MunicipalDocumentCollector()

    def analyze(
        self,
        *,
        town: str,
        state: str,
        raw_documents: list[SourceDocument | dict[str, Any]] | None,
        existing_signals: list[TownSignal] | None = None,
    ) -> LocalIntelligenceRun:
        documents = normalize_source_documents(raw_documents, town=town, state=state)
        warnings: list[str] = []
        if not documents and self.collector is not None:
            try:
                auto_documents = self.collector.collect(town=town, state=state)
            except Exception as exc:  # pragma: no cover - environment/network specific
                logger.warning("Auto-collecting local documents failed for %s, %s: %s", town, state, exc)
                auto_documents = []
                warnings.append("Automatic municipal document collection failed.")
            if auto_documents:
                documents = normalize_source_documents(auto_documents, town=town, state=state)
                warnings.append(f"Auto-collected {len(documents)} local source document(s) from municipal sources.")
        persisted_signals = existing_signals if existing_signals is not None else self.store.load_town_signals(town=town, state=state)
        if not documents:
            return LocalIntelligenceRun(
                town=town,
                state=state,
                documents=[],
                signals=persisted_signals,
                summary=_empty_summary(town, state) if not persisted_signals else build_town_summary(town=town, state=state, signals=persisted_signals),
                warnings=warnings + ["No local source documents were provided."],
                missing_inputs=["local_documents"],
            )

        extracted_signals = []
        for document in documents:
            try:
                signals = self.extractor.extract(document)
            except Exception as exc:
                logger.warning("Local intelligence extraction failed for %s: %s", document.id, exc)
                warnings.append(f"Extraction failed for '{document.title}'.")
                continue
            if not signals:
                warnings.append(f"No structured signals were extracted from '{document.title}'.")
            extracted_signals.extend(signals)

        reconciled = reconcile_signals(extracted_signals, existing_signals=persisted_signals)
        self.store.save_town_signals(town=town, state=state, signals=reconciled)
        summary = build_town_summary(town=town, state=state, signals=reconciled)
        if not reconciled:
            warnings.append("Documents were present, but no supported town signals were extracted.")

        return LocalIntelligenceRun(
            town=town,
            state=state,
            documents=documents,
            signals=reconciled,
            summary=summary,
            warnings=warnings,
            missing_inputs=[],
        )


    def research(
        self,
        *,
        town: str,
        state: str,
        focus: list[str] | None = None,
        budget_seconds: float = 30.0,
    ) -> LocalIntelligenceRun:
        """Exploratory research: re-collect documents with a focus hint, re-extract,
        reconcile into the signal store, and return a fresh summary.

        Unlike ``analyze``, this path intentionally bypasses the warm cache
        (the focus hint is the entire point) and honors a wall-clock budget.
        Partial results are returned on timeout rather than raising.
        """
        started = time.monotonic()
        warnings: list[str] = []
        documents_raw: list[dict[str, Any]] = []
        if self.collector is not None:
            try:
                documents_raw = self.collector.collect(
                    town=town, state=state, use_cache=False, focus=focus or []
                )
            except Exception as exc:  # pragma: no cover - environment/network
                logger.warning("Research collection failed for %s, %s: %s", town, state, exc)
                warnings.append("Research document collection failed.")
                documents_raw = []

        documents = normalize_source_documents(documents_raw, town=town, state=state)
        persisted_signals = self.store.load_town_signals(town=town, state=state)

        extracted_signals = []
        for document in documents:
            if time.monotonic() - started > budget_seconds:
                warnings.append("Research budget exceeded — used partial results.")
                break
            try:
                signals = self.extractor.extract(document)
            except Exception as exc:
                logger.warning("Research extraction failed for %s: %s", document.id, exc)
                warnings.append(f"Extraction failed for '{document.title}'.")
                continue
            extracted_signals.extend(signals)

        reconciled = reconcile_signals(extracted_signals, existing_signals=persisted_signals)
        if reconciled != persisted_signals:
            self.store.save_town_signals(town=town, state=state, signals=reconciled)
        summary = build_town_summary(town=town, state=state, signals=reconciled) if reconciled else _empty_summary(town, state)
        if not documents:
            warnings.append("No new documents were retrieved.")

        return LocalIntelligenceRun(
            town=town,
            state=state,
            documents=documents,
            signals=reconciled,
            summary=summary,
            warnings=warnings,
            missing_inputs=[] if reconciled else ["local_documents"],
        )


def _empty_summary(town: str, state: str) -> TownSummary:
    return TownSummary(
        town=town,
        state=state,
        bullish_signals=[],
        bearish_signals=[],
        watch_items=[],
        confidence_label="Low",
        narrative_summary=f"Briarwood does not yet have enough local source material to summarize {town}, {state}.",
        generated_at=build_town_summary(town=town, state=state, signals=[]).generated_at,
    )
