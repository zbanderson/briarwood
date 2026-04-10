from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CORE_ENDPOINTS = ("property_detail", "assessment_detail", "sale_detail")
CONDITIONAL_ENDPOINTS = ("rental_avm", "building_permits", "assessment_history")
BATCH_ENDPOINTS = ("sales_trend", "community_demographics")


@dataclass(slots=True)
class AnalysisRequestContext:
    analysis_id: str
    missing_rent: bool = False
    redevelopment_case: bool = False
    tax_risk_review: bool = False
    multi_unit_ambiguity: bool = False


@dataclass(slots=True)
class ApiBudgetTracker:
    call_counts: dict[str, int] = field(default_factory=dict)
    cache_hits: dict[str, int] = field(default_factory=dict)
    field_fills: dict[str, int] = field(default_factory=dict)
    match_failures: dict[str, int] = field(default_factory=dict)
    analysis_footprints: dict[str, dict[str, int]] = field(default_factory=dict)

    def record_call(self, *, endpoint: str, analysis_id: str, from_cache: bool) -> None:
        self.call_counts[endpoint] = self.call_counts.get(endpoint, 0) + 1
        if from_cache:
            self.cache_hits[endpoint] = self.cache_hits.get(endpoint, 0) + 1
        footprint = self.analysis_footprints.setdefault(analysis_id, {})
        footprint[endpoint] = footprint.get(endpoint, 0) + 1

    def record_field_fill(self, *, field_name: str) -> None:
        self.field_fills[field_name] = self.field_fills.get(field_name, 0) + 1

    def record_match_failure(self, *, endpoint: str) -> None:
        self.match_failures[endpoint] = self.match_failures.get(endpoint, 0) + 1

    def cache_hit_rate(self, endpoint: str) -> float:
        calls = self.call_counts.get(endpoint, 0)
        if calls == 0:
            return 0.0
        return self.cache_hits.get(endpoint, 0) / calls

    def fill_rate(self, field_name: str, *, total_analyses: int) -> float:
        if total_analyses <= 0:
            return 0.0
        return self.field_fills.get(field_name, 0) / total_analyses

    def analysis_call_footprint(self, analysis_id: str) -> dict[str, int]:
        return dict(self.analysis_footprints.get(analysis_id, {}))


class ApiStrategy:
    def __init__(self, *, tracker: ApiBudgetTracker | None = None) -> None:
        self.tracker = tracker or ApiBudgetTracker()

    def plan_endpoints(self, context: AnalysisRequestContext) -> dict[str, tuple[str, ...]]:
        conditional: list[str] = []
        if context.missing_rent:
            conditional.append("rental_avm")
        if context.redevelopment_case:
            conditional.append("building_permits")
        if context.tax_risk_review:
            conditional.append("assessment_history")
        if context.multi_unit_ambiguity and "building_permits" not in conditional:
            conditional.append("building_permits")
        return {
            "core": CORE_ENDPOINTS,
            "conditional": tuple(conditional),
            "batch": BATCH_ENDPOINTS,
        }

    def track_response(
        self,
        *,
        endpoint: str,
        analysis_id: str,
        from_cache: bool,
        normalized_payload: dict[str, Any] | None,
        expected_fields: list[str] | None = None,
        match_failed: bool = False,
    ) -> None:
        self.tracker.record_call(endpoint=endpoint, analysis_id=analysis_id, from_cache=from_cache)
        if match_failed:
            self.tracker.record_match_failure(endpoint=endpoint)
        expected = expected_fields or []
        payload = normalized_payload or {}
        for field_name in expected:
            if payload.get(field_name) not in (None, "", [], {}):
                self.tracker.record_field_fill(field_name=field_name)
