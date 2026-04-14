from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IntentType(str, Enum):
    """Top-level user intent for Briarwood's decision-routing engine."""

    BUY_DECISION = "buy_decision"
    OWNER_OCCUPANT_SHORT_HOLD = "owner_occupant_short_hold"
    OWNER_OCCUPANT_THEN_RENT = "owner_occupant_then_rent"
    RENOVATE_THEN_SELL = "renovate_then_sell"
    HOUSE_HACK_MULTI_UNIT = "house_hack_multi_unit"


class AnalysisDepth(str, Enum):
    """Requested analysis scope for the current decision run."""

    SNAPSHOT = "snapshot"
    DECISION = "decision"
    SCENARIO = "scenario"
    DEEP_DIVE = "deep_dive"


class CoreQuestion(str, Enum):
    """Primary decision question the user wants Briarwood to answer."""

    SHOULD_I_BUY = "should_i_buy"
    WHAT_COULD_GO_WRONG = "what_could_go_wrong"
    WHERE_IS_VALUE = "where_is_value"
    BEST_PATH = "best_path"
    FUTURE_INCOME = "future_income"


class OccupancyType(str, Enum):
    """Occupancy posture inferred or stated by the user."""

    OWNER_OCCUPANT = "owner_occupant"
    INVESTOR = "investor"
    UNKNOWN = "unknown"


class ExitOption(str, Enum):
    """Likely exit path or strategy option for the property."""

    SELL = "sell"
    RENT = "rent"
    HOLD = "hold"
    REDEVELOP = "redevelop"
    UNKNOWN = "unknown"


class DecisionType(str, Enum):
    """Normalized user-facing decision class."""

    BUY = "buy"
    MIXED = "mixed"
    PASS = "pass"


class DecisionStance(str, Enum):
    """Phase 5 decision stance (finer-grained than DecisionType).

    Derived deterministically from module results + interaction trace + trust
    state. Used by synthesis to make the recommendation's *reason* legible
    (e.g., "interesting_but_fragile" vs "execution_dependent").
    """

    STRONG_BUY = "strong_buy"
    BUY_IF_PRICE_IMPROVES = "buy_if_price_improves"
    INTERESTING_BUT_FRAGILE = "interesting_but_fragile"
    EXECUTION_DEPENDENT = "execution_dependent"
    PASS_UNLESS_CHANGES = "pass_unless_changes"
    PASS = "pass"
    CONDITIONAL = "conditional"  # trust gate fires — no strong stance possible


class ModuleName(str, Enum):
    """Canonical analysis modules available to the routing engine."""

    VALUATION = "valuation"
    CARRY_COST = "carry_cost"
    RISK_MODEL = "risk_model"
    CONFIDENCE = "confidence"
    RESALE_SCENARIO = "resale_scenario"
    RENTAL_OPTION = "rental_option"
    RENT_STABILIZATION = "rent_stabilization"
    HOLD_TO_RENT = "hold_to_rent"
    RENOVATION_IMPACT = "renovation_impact"
    ARV_MODEL = "arv_model"
    MARGIN_SENSITIVITY = "margin_sensitivity"
    UNIT_INCOME_OFFSET = "unit_income_offset"
    LEGAL_CONFIDENCE = "legal_confidence"


CORE_QUESTIONS: tuple[CoreQuestion, ...] = (
    CoreQuestion.SHOULD_I_BUY,
    CoreQuestion.WHAT_COULD_GO_WRONG,
    CoreQuestion.WHERE_IS_VALUE,
    CoreQuestion.BEST_PATH,
    CoreQuestion.FUTURE_INCOME,
)
"""Ordered canonical set of top-level questions Briarwood can answer."""


INTENT_TO_QUESTIONS: dict[IntentType, tuple[CoreQuestion, ...]] = {
    IntentType.BUY_DECISION: (
        CoreQuestion.SHOULD_I_BUY,
        CoreQuestion.WHAT_COULD_GO_WRONG,
        CoreQuestion.WHERE_IS_VALUE,
    ),
    IntentType.OWNER_OCCUPANT_SHORT_HOLD: (
        CoreQuestion.SHOULD_I_BUY,
        CoreQuestion.BEST_PATH,
        CoreQuestion.WHAT_COULD_GO_WRONG,
    ),
    IntentType.OWNER_OCCUPANT_THEN_RENT: (
        CoreQuestion.SHOULD_I_BUY,
        CoreQuestion.FUTURE_INCOME,
        CoreQuestion.BEST_PATH,
    ),
    IntentType.RENOVATE_THEN_SELL: (
        CoreQuestion.WHERE_IS_VALUE,
        CoreQuestion.BEST_PATH,
        CoreQuestion.WHAT_COULD_GO_WRONG,
    ),
    IntentType.HOUSE_HACK_MULTI_UNIT: (
        CoreQuestion.SHOULD_I_BUY,
        CoreQuestion.FUTURE_INCOME,
        CoreQuestion.BEST_PATH,
    ),
}
"""Default question emphasis for each intent type."""


INTENT_TO_MODULES: dict[IntentType, tuple[ModuleName, ...]] = {
    IntentType.BUY_DECISION: (
        ModuleName.VALUATION,
        ModuleName.CARRY_COST,
        ModuleName.RISK_MODEL,
        ModuleName.CONFIDENCE,
    ),
    IntentType.OWNER_OCCUPANT_SHORT_HOLD: (
        ModuleName.VALUATION,
        ModuleName.CARRY_COST,
        ModuleName.RISK_MODEL,
        ModuleName.RESALE_SCENARIO,
        ModuleName.CONFIDENCE,
    ),
    IntentType.OWNER_OCCUPANT_THEN_RENT: (
        ModuleName.VALUATION,
        ModuleName.CARRY_COST,
        ModuleName.RISK_MODEL,
        ModuleName.RENTAL_OPTION,
        ModuleName.HOLD_TO_RENT,
        ModuleName.CONFIDENCE,
    ),
    IntentType.RENOVATE_THEN_SELL: (
        ModuleName.VALUATION,
        ModuleName.RENOVATION_IMPACT,
        ModuleName.ARV_MODEL,
        ModuleName.MARGIN_SENSITIVITY,
        ModuleName.RESALE_SCENARIO,
        ModuleName.RISK_MODEL,
        ModuleName.CONFIDENCE,
    ),
    IntentType.HOUSE_HACK_MULTI_UNIT: (
        ModuleName.VALUATION,
        ModuleName.CARRY_COST,
        ModuleName.RENTAL_OPTION,
        ModuleName.UNIT_INCOME_OFFSET,
        ModuleName.RENT_STABILIZATION,
        ModuleName.LEGAL_CONFIDENCE,
        ModuleName.RISK_MODEL,
        ModuleName.CONFIDENCE,
    ),
}
"""Baseline module families implied by user intent."""


DEPTH_BASELINE_MODULES: dict[AnalysisDepth, tuple[ModuleName, ...]] = {
    AnalysisDepth.SNAPSHOT: (
        ModuleName.VALUATION,
        ModuleName.CONFIDENCE,
    ),
    AnalysisDepth.DECISION: (
        ModuleName.VALUATION,
        ModuleName.CARRY_COST,
        ModuleName.RISK_MODEL,
        ModuleName.CONFIDENCE,
    ),
    AnalysisDepth.SCENARIO: (
        ModuleName.VALUATION,
        ModuleName.CARRY_COST,
        ModuleName.RISK_MODEL,
        ModuleName.RESALE_SCENARIO,
        ModuleName.RENTAL_OPTION,
        ModuleName.CONFIDENCE,
    ),
    AnalysisDepth.DEEP_DIVE: (
        ModuleName.VALUATION,
        ModuleName.CARRY_COST,
        ModuleName.RISK_MODEL,
        ModuleName.CONFIDENCE,
        ModuleName.RESALE_SCENARIO,
        ModuleName.RENTAL_OPTION,
        ModuleName.RENT_STABILIZATION,
        ModuleName.HOLD_TO_RENT,
        ModuleName.RENOVATION_IMPACT,
        ModuleName.ARV_MODEL,
        ModuleName.MARGIN_SENSITIVITY,
        ModuleName.UNIT_INCOME_OFFSET,
        ModuleName.LEGAL_CONFIDENCE,
    ),
}
"""Baseline module expansion for each analysis depth."""


QUESTION_FOCUS_TO_MODULE_HINTS: dict[CoreQuestion, tuple[ModuleName, ...]] = {
    CoreQuestion.SHOULD_I_BUY: (
        ModuleName.VALUATION,
        ModuleName.CARRY_COST,
        ModuleName.RISK_MODEL,
        ModuleName.CONFIDENCE,
    ),
    CoreQuestion.WHAT_COULD_GO_WRONG: (
        ModuleName.RISK_MODEL,
        ModuleName.CONFIDENCE,
        ModuleName.LEGAL_CONFIDENCE,
    ),
    CoreQuestion.WHERE_IS_VALUE: (
        ModuleName.VALUATION,
        ModuleName.RENOVATION_IMPACT,
        ModuleName.ARV_MODEL,
        ModuleName.MARGIN_SENSITIVITY,
    ),
    CoreQuestion.BEST_PATH: (
        ModuleName.RESALE_SCENARIO,
        ModuleName.HOLD_TO_RENT,
        ModuleName.RENTAL_OPTION,
        ModuleName.CARRY_COST,
    ),
    CoreQuestion.FUTURE_INCOME: (
        ModuleName.RENTAL_OPTION,
        ModuleName.RENT_STABILIZATION,
        ModuleName.UNIT_INCOME_OFFSET,
        ModuleName.HOLD_TO_RENT,
    ),
}
"""Question-driven module hints for targeted synthesis and routing."""


class ParserOutput(BaseModel):
    """Normalized output from conversational intent parsing."""

    model_config = ConfigDict(extra="forbid")

    intent_type: IntentType
    analysis_depth: AnalysisDepth
    question_focus: list[str] = Field(default_factory=list)
    hold_period_years: float | None = Field(default=None, ge=0)
    occupancy_type: OccupancyType
    renovation_plan: bool | None = None
    exit_options: list[ExitOption] = Field(default_factory=list)
    has_additional_units: bool | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    missing_inputs: list[str] = Field(default_factory=list)

    @field_validator("question_focus", mode="before")
    @classmethod
    def _normalize_question_focus(cls, value: Any) -> list[str]:
        """Normalize question focus values to stripped lowercase strings."""

        if value is None:
            return []
        if isinstance(value, str):
            items = [value]
        else:
            items = list(value)
        normalized: list[str] = []
        for item in items:
            text = str(item).strip().lower()
            if text:
                normalized.append(text)
        return normalized


class ModulePayload(BaseModel):
    """Standard output contract for one routed analysis module.

    The ``module_name``, ``score``, and ``summary`` fields are optional
    migration aids.  They promote frequently-read values to top-level
    attributes so consumers can access them without digging into ``data``.
    Existing V2 code that does not set these fields is unaffected.
    """

    model_config = ConfigDict(extra="forbid")

    data: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    assumptions_used: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    # ── Migration fields (optional, backward-compatible) ──────────────
    module_name: str = ""
    score: float | None = None
    summary: str = ""


class EngineOutput(BaseModel):
    """Collected outputs from Briarwood-native analysis modules."""

    model_config = ConfigDict(extra="forbid")

    outputs: dict[str, ModulePayload] = Field(default_factory=dict)

    def get(self, module_name: ModuleName | str) -> ModulePayload | None:
        """Return one module payload by canonical module name."""

        key = module_name.value if isinstance(module_name, ModuleName) else str(module_name)
        return self.outputs.get(key)


class UnifiedIntelligenceOutput(BaseModel):
    """Final synthesized decision response shown to the user.

    Phase 5 extends this with structured fields that let synthesis be reasoned
    about and reproduced without the LLM — the LLM can still provide narrative
    translation, but the decision is derivable from the interaction trace.
    """

    model_config = ConfigDict(extra="forbid")

    recommendation: str = Field(min_length=1)
    decision: DecisionType
    best_path: str = Field(min_length=1)
    key_value_drivers: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    analysis_depth_used: AnalysisDepth
    next_questions: list[str] = Field(default_factory=list)
    recommended_next_run: str | None = None
    supporting_facts: dict[str, Any] = Field(default_factory=dict)

    # Phase 5 structured fields. Defaults kept permissive so pre-Phase-5
    # synthesizers that don't populate them still validate.
    decision_stance: DecisionStance = DecisionStance.CONDITIONAL
    primary_value_source: str = "unknown"
    value_position: dict[str, Any] = Field(default_factory=dict)
    what_must_be_true: list[str] = Field(default_factory=list)
    next_checks: list[str] = Field(default_factory=list)
    trust_flags: list[str] = Field(default_factory=list)
    interaction_trace: dict[str, Any] = Field(default_factory=dict)


class RoutingDecision(BaseModel):
    """Resolved routing plan between parser output and module execution."""

    model_config = ConfigDict(extra="forbid")

    intent_type: IntentType
    analysis_depth: AnalysisDepth
    core_questions: list[CoreQuestion] = Field(default_factory=list)
    selected_modules: list[ModuleName] = Field(default_factory=list)
    parser_output: ParserOutput


__all__ = [
    "AnalysisDepth",
    "CORE_QUESTIONS",
    "CoreQuestion",
    "DEPTH_BASELINE_MODULES",
    "DecisionStance",
    "DecisionType",
    "EngineOutput",
    "ExitOption",
    "INTENT_TO_MODULES",
    "INTENT_TO_QUESTIONS",
    "IntentType",
    "ModuleName",
    "ModulePayload",
    "OccupancyType",
    "ParserOutput",
    "QUESTION_FOCUS_TO_MODULE_HINTS",
    "RoutingDecision",
    "UnifiedIntelligenceOutput",
]
