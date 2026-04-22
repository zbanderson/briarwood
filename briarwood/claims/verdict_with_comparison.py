from typing import Literal

from pydantic import BaseModel, Field, model_validator

from briarwood.claims.archetypes import Archetype
from briarwood.claims.base import (
    Caveat,
    Confidence,
    NextQuestion,
    Provenance,
    SurfacedInsight,
)


class Subject(BaseModel):
    property_id: str
    address: str
    beds: int
    baths: float
    sqft: int
    ask_price: float
    status: Literal["active", "pending", "sold", "unknown"] = "unknown"


class Verdict(BaseModel):
    label: Literal["value_find", "fair", "overpriced", "insufficient_data"]
    headline: str
    basis_fmv: float
    ask_vs_fmv_delta_pct: float
    method: str
    comp_count: int
    comp_radius_mi: float
    comp_window_months: int
    confidence: Confidence


class ComparisonScenario(BaseModel):
    id: str
    label: str
    metric_range: tuple[float, float]
    metric_median: float
    is_subject: bool = False
    sample_size: int
    flag: Literal["value_opportunity", "caution", "none"] = "none"
    flag_reason: str | None = None

    @model_validator(mode="after")
    def validate_range_ordering(self) -> "ComparisonScenario":
        low, high = self.metric_range
        if low > high:
            raise ValueError(
                f"metric_range low ({low}) must be <= high ({high}) for scenario {self.id}"
            )
        return self


class Comparison(BaseModel):
    metric: Literal["price_per_sqft"]
    unit: str = "$/sqft"
    scenarios: list[ComparisonScenario]
    chart_rule: Literal["horizontal_bar_with_ranges"]
    emphasis_scenario_id: str | None = None

    @model_validator(mode="after")
    def validate_emphasis_exists(self) -> "Comparison":
        if self.emphasis_scenario_id:
            ids = {s.id for s in self.scenarios}
            if self.emphasis_scenario_id not in ids:
                raise ValueError(
                    f"emphasis_scenario_id {self.emphasis_scenario_id} not in scenarios"
                )
        return self


class VerdictWithComparisonClaim(BaseModel):
    archetype: Literal[Archetype.VERDICT_WITH_COMPARISON] = Archetype.VERDICT_WITH_COMPARISON
    subject: Subject
    verdict: Verdict
    bridge_sentence: str
    comparison: Comparison
    caveats: list[Caveat] = Field(default_factory=list)
    next_questions: list[NextQuestion] = Field(default_factory=list)
    provenance: Provenance
    surfaced_insight: SurfacedInsight | None = None
