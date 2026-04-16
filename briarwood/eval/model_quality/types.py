"""Data types shared across the model-quality harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Sensitivity:
    """Expected directional response to a single input change."""

    input_field: str
    delta: Any  # numeric delta (e.g. 0.2 = +20%) OR a replacement value
    output_field: str
    expected_direction: str  # "up" | "down" | "any" | "unchanged"
    min_move_pct: float = 0.0  # e.g. 0.05 = at least 5% relative change
    label: str = ""


@dataclass
class DecisionQuestionMap:
    """Maps a decision question to the output fields that should answer it."""

    should_i_buy: list[str] = field(default_factory=list)
    what_could_go_wrong: list[str] = field(default_factory=list)
    where_is_value: list[str] = field(default_factory=list)
    what_path: list[str] = field(default_factory=list)


@dataclass
class ModelSpec:
    """Declarative contract for what a specialist model should produce."""

    name: str
    invoke: Callable[[Any], dict[str, Any]]
    """Callable that takes a PropertyInput (or dict) and returns a dict with
    keys {data, confidence, warnings}."""

    required_inputs: list[str] = field(default_factory=list)
    expected_output_fields: list[str] = field(default_factory=list)
    numeric_bounds: dict[str, tuple[float, float]] = field(default_factory=dict)
    """Per-field {field_name: (lo, hi)} expected band for accuracy."""

    sensitivities: list[Sensitivity] = field(default_factory=list)
    explainability_fields: list[str] = field(default_factory=list)
    """Fields that should carry rationale / feature attributions."""

    decision_questions: DecisionQuestionMap = field(default_factory=DecisionQuestionMap)
    trust_drop_fields: list[str] = field(default_factory=list)
    """Input fields whose removal should cause confidence to drop."""


@dataclass
class Fixture:
    """One test property with inputs + optional expected-output bands."""

    fixture_id: str
    property_input: Any  # PropertyInput pydantic model
    kind: str  # "real" or "synthetic"
    expected: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


@dataclass
class CriterionResult:
    name: str
    passed: bool
    score: float  # 0.0–1.0
    details: list[str] = field(default_factory=list)


@dataclass
class ModelReport:
    model: str
    fixture_id: str
    results: dict[str, CriterionResult] = field(default_factory=dict)

    @property
    def overall_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.score for r in self.results.values()) / len(self.results)


__all__ = [
    "CriterionResult",
    "DecisionQuestionMap",
    "Fixture",
    "ModelReport",
    "ModelSpec",
    "Sensitivity",
]
