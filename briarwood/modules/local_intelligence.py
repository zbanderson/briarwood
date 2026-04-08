from __future__ import annotations

from briarwood.evidence import build_section_evidence
from briarwood.local_intelligence.models import (
    ImpactDirection,
    LocalIntelligenceRun,
    SignalStatus,
    SignalType,
)
from briarwood.local_intelligence.service import LocalIntelligenceService
from briarwood.schemas import (
    LocalIntelligenceConfidence,
    LocalIntelligenceOutput,
    LocalIntelligenceProject,
    LocalIntelligenceScores,
    LocalIntelligenceSummary,
    ModuleResult,
    PropertyInput,
)


class LocalIntelligenceModule:
    """Compatibility bridge from the new Local Intelligence subsystem into ModuleResult."""

    name = "local_intelligence"

    def __init__(self, *, service: LocalIntelligenceService | None = None) -> None:
        self.service = service or LocalIntelligenceService()

    def run(self, property_input: PropertyInput) -> ModuleResult:
        run = self.service.analyze(
            town=property_input.town,
            state=property_input.state,
            raw_documents=list(property_input.local_documents),
        )
        payload = self._legacy_output(run, property_input.town_population)
        summary_text = self._summary_text(run)
        notes = list(run.warnings)
        notes.append(
            "Local intelligence separates source-backed facts from Briarwood inference and is not a substitute for formal zoning or entitlement review."
        )

        return ModuleResult(
            module_name=self.name,
            metrics=self._metrics(run, payload.scores),
            score=payload.scores.development_activity_score,
            confidence=payload.confidence.score,
            summary=summary_text,
            payload=payload,
            section_evidence=build_section_evidence(
                property_input,
                categories=["market_history", "scarcity_inputs"],
                notes=notes,
                extra_missing_inputs=list(run.missing_inputs),
            ),
        )

    def _legacy_output(
        self,
        run: LocalIntelligenceRun,
        town_population: int | None,
    ) -> LocalIntelligenceOutput:
        projects = [self._signal_to_project(signal) for signal in run.signals]
        summary = LocalIntelligenceSummary(
            total_projects=len(projects),
            total_units=sum(project.units or 0 for project in projects),
            approved_projects=sum(1 for project in projects if project.status == "approved"),
            rejected_projects=sum(1 for project in projects if project.status == "rejected"),
            pending_projects=sum(1 for project in projects if project.status in {"proposed", "reviewed", "mentioned"}),
        )
        scores = self._scores(run, summary, town_population)
        confidence = LocalIntelligenceConfidence(
            score=self._confidence(run),
            notes=self._confidence_notes(run),
        )
        narrative = self._narrative(run)
        return LocalIntelligenceOutput(
            projects=projects,
            summary=summary,
            scores=scores,
            narrative=narrative,
            confidence=confidence,
            signals=list(run.signals),
        )

    def _signal_to_project(self, signal) -> LocalIntelligenceProject:
        metadata = signal.metadata
        signal_type = signal.signal_type.value.replace("_", "-")
        status = signal.status.value
        notes = signal.inference
        return LocalIntelligenceProject(
            name=signal.title,
            type=signal_type,
            units=_int_or_none(metadata.get("units")),
            status=status,
            location=_str_or_none(metadata.get("location")),
            notes=notes,
            confidence=round(float(signal.confidence), 2),
            impact_direction=signal.impact_direction.value,
            evidence_excerpt=signal.evidence_excerpt,
            time_horizon=signal.time_horizon.value,
            facts=list(signal.facts),
        )

    def _scores(
        self,
        run: LocalIntelligenceRun,
        summary: LocalIntelligenceSummary,
        town_population: int | None,
    ) -> LocalIntelligenceScores:
        positive_count = sum(1 for signal in run.signals if signal.impact_direction == ImpactDirection.POSITIVE)
        negative_count = sum(1 for signal in run.signals if signal.impact_direction == ImpactDirection.NEGATIVE)
        weighted_supply_units = sum(
            _int_or_none(signal.metadata.get("units")) or 0
            for signal in run.signals
            if signal.signal_type in {SignalType.SUPPLY, SignalType.DEVELOPMENT}
        )
        development_activity_score = _clamp((summary.total_projects * 12.0) + (weighted_supply_units * 0.45))
        if town_population and town_population > 0:
            units_per_1000 = (weighted_supply_units / town_population) * 1000.0
            supply_pipeline_score = _clamp(units_per_1000 * 18.0)
        else:
            supply_pipeline_score = _clamp(weighted_supply_units * 0.5)
        status_values = [signal.status for signal in run.signals]
        decision_count = sum(1 for status in status_values if status in {SignalStatus.APPROVED, SignalStatus.REJECTED})
        if decision_count == 0:
            regulatory_trend_score = 50.0
        else:
            approved = sum(1 for status in status_values if status == SignalStatus.APPROVED)
            regulatory_trend_score = _clamp(20.0 + ((approved / decision_count) * 80.0))
        sentiment_score = _clamp(50.0 + ((positive_count - negative_count) * 8.0))
        return LocalIntelligenceScores(
            development_activity_score=round(development_activity_score, 1),
            supply_pipeline_score=round(supply_pipeline_score, 1),
            regulatory_trend_score=round(regulatory_trend_score, 1),
            sentiment_score=round(sentiment_score, 1),
        )

    def _confidence(self, run: LocalIntelligenceRun) -> float:
        if not run.signals:
            return 0.0
        average_signal_confidence = sum(signal.confidence for signal in run.signals) / len(run.signals)
        document_factor = min(len(run.documents) / 3.0, 1.0) * 0.25
        signal_factor = min(len(run.signals) / 5.0, 1.0) * 0.2
        score = min(0.95, average_signal_confidence * 0.55 + document_factor + signal_factor)
        return round(score, 2)

    def _confidence_notes(self, run: LocalIntelligenceRun) -> list[str]:
        notes = [f"Based on {len(run.documents)} local source document(s)."] if run.documents else []
        notes.extend(run.warnings)
        if any("related_source_document_ids" in signal.metadata for signal in run.signals):
            notes.append("Overlapping signals were reconciled across multiple source documents.")
        if not run.signals:
            notes.append("No source-backed town signals were extracted from the supplied documents.")
        return _dedupe(notes)

    def _narrative(self, run: LocalIntelligenceRun) -> list[str]:
        bullets = [run.summary.narrative_summary]
        bullets.extend(run.summary.bullish_signals[:2])
        bullets.extend(run.summary.bearish_signals[:2])
        bullets.extend(run.summary.watch_items[:1])
        return bullets[:4]

    def _metrics(self, run: LocalIntelligenceRun, scores: LocalIntelligenceScores) -> dict[str, float | int | str]:
        total_units = sum(_int_or_none(signal.metadata.get("units")) or 0 for signal in run.signals)
        approved = sum(1 for signal in run.signals if signal.status == SignalStatus.APPROVED)
        rejected = sum(1 for signal in run.signals if signal.status == SignalStatus.REJECTED)
        pending = sum(1 for signal in run.signals if signal.status in {SignalStatus.PROPOSED, SignalStatus.REVIEWED, SignalStatus.MENTIONED})
        market_momentum_score = round(
            (0.45 * scores.development_activity_score)
            + (0.35 * scores.regulatory_trend_score)
            + (0.20 * (100.0 - scores.supply_pipeline_score)),
            1,
        )
        return {
            "total_projects": len(run.signals),
            "total_units": total_units,
            "approved_projects": approved,
            "rejected_projects": rejected,
            "pending_projects": pending,
            "development_activity_score": scores.development_activity_score,
            "supply_pipeline_score": scores.supply_pipeline_score,
            "regulatory_trend_score": scores.regulatory_trend_score,
            "sentiment_score": scores.sentiment_score,
            "market_momentum_score": market_momentum_score,
        }

    def _summary_text(self, run: LocalIntelligenceRun) -> str:
        if not run.documents:
            return (
                "Local development intelligence is unavailable because no town planning, zoning, redevelopment, or related source documents were provided."
            )
        return run.summary.narrative_summary


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = " ".join(str(value).split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _int_or_none(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
