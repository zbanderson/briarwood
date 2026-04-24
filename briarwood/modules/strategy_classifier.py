"""Phase 3 Layer-2 module: property strategy classification.

The spec §2/§3 calls out that every downstream domain model should know what
*kind* of deal it is looking at before it runs:

- ``owner_occ_sfh``        — owner-occupied single family, no rental component
- ``owner_occ_duplex``     — owner lives in one unit, rents the other(s)
- ``owner_occ_with_adu``   — primary + detached ADU / back house
- ``pure_rental``          — no owner occupancy, rented as investment
- ``value_add_sfh``        — condition/layout indicates reno upside drives value
- ``redevelopment_play``   — land value > structure value; teardown/subdivide
- ``scarcity_hold``        — pricing & signals imply optionality, not current yield

The classifier is deterministic (pure rule-based). It does not use an LLM. It
produces a structured ``StrategyClassification`` that records *which rule fired*
so downstream modules and tests can reason about the label honestly.

Runs at Layer 2 — between intake and any domain model — and can be called
directly or stored in ``ExecutionContext.prior_outputs`` so the bridges in
Phase 4 (especially ``primary_value_source``) can consult it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from briarwood.execution.context import ExecutionContext
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_error,
)
from briarwood.routing_schema import ModulePayload
from briarwood.schemas import OccupancyStrategy, PropertyInput


class PropertyStrategyType(str, Enum):
    OWNER_OCC_SFH = "owner_occ_sfh"
    OWNER_OCC_DUPLEX = "owner_occ_duplex"
    OWNER_OCC_WITH_ADU = "owner_occ_with_adu"
    PURE_RENTAL = "pure_rental"
    VALUE_ADD_SFH = "value_add_sfh"
    REDEVELOPMENT_PLAY = "redevelopment_play"
    SCARCITY_HOLD = "scarcity_hold"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class StrategyClassification:
    strategy: PropertyStrategyType
    rationale: list[str] = field(default_factory=list)
    confidence: float = 0.0
    rule_fired: str = ""
    candidates: list[PropertyStrategyType] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["strategy"] = self.strategy.value
        data["candidates"] = [c.value for c in self.candidates]
        return data


# ─── Core classifier ──────────────────────────────────────────────────────────


def classify_strategy(property_input: PropertyInput) -> StrategyClassification:
    """Classify a property into one of the named strategies.

    Rule order matters — the first matching rule wins. Subsequent candidates
    are recorded so the caller can see what else applied.
    """

    rationale: list[str] = []
    candidates: list[PropertyStrategyType] = []

    has_adu = bool(property_input.adu_type) or bool(property_input.has_back_house)
    has_extra_units = bool(property_input.additional_units)
    property_type = (property_input.property_type or "").lower()
    is_multi_family = any(
        token in property_type for token in ("duplex", "multi", "2-family", "3-family", "fourplex")
    )
    occupancy = property_input.occupancy_strategy

    # 1. Redevelopment — land-value signals override everything else.
    if _is_redevelopment_signal(property_input):
        return StrategyClassification(
            strategy=PropertyStrategyType.REDEVELOPMENT_PLAY,
            rationale=[
                "Lot size / price ratio and condition indicators suggest the buyer is paying for land, not the structure."
            ],
            confidence=0.65,
            rule_fired="redevelopment_play",
            candidates=[],
        )

    # 2. Multi-family with owner intent → duplex path
    if is_multi_family and occupancy == OccupancyStrategy.OWNER_OCCUPY_PARTIAL:
        rationale.append("Multi-family property with owner_occupy_partial intent.")
        return StrategyClassification(
            strategy=PropertyStrategyType.OWNER_OCC_DUPLEX,
            rationale=rationale,
            confidence=0.85,
            rule_fired="multi_family_owner_occupy_partial",
        )

    # 3. Has ADU/back-house with owner intent
    if has_adu and occupancy in (
        OccupancyStrategy.OWNER_OCCUPY_PARTIAL,
        OccupancyStrategy.OWNER_OCCUPY_FULL,
    ):
        rationale.append("Accessory unit present; owner intends to occupy the primary residence.")
        return StrategyClassification(
            strategy=PropertyStrategyType.OWNER_OCC_WITH_ADU,
            rationale=rationale,
            confidence=0.80,
            rule_fired="adu_owner_occupy",
        )

    # 4. Pure rental (investor intent)
    if occupancy == OccupancyStrategy.FULL_RENTAL:
        rationale.append("Declared full_rental occupancy → pure investment.")
        return StrategyClassification(
            strategy=PropertyStrategyType.PURE_RENTAL,
            rationale=rationale,
            confidence=0.85,
            rule_fired="full_rental_declared",
        )

    # 5. Value-add SFH — condition signals or capex_lane suggest reno play
    if _is_value_add_signal(property_input):
        rationale.append("Condition / capex lane indicates renovation upside drives the deal.")
        # Value-add often coexists with other occupancy patterns; record candidates.
        if has_adu:
            candidates.append(PropertyStrategyType.OWNER_OCC_WITH_ADU)
        return StrategyClassification(
            strategy=PropertyStrategyType.VALUE_ADD_SFH,
            rationale=rationale,
            confidence=0.70,
            rule_fired="value_add_condition",
            candidates=candidates,
        )

    # 6. Scarcity hold — strong town signals + residential, no clear income/reno path
    if _is_scarcity_hold_signal(property_input):
        rationale.append("Town scarcity / desirability signals dominate without an income or reno thesis.")
        return StrategyClassification(
            strategy=PropertyStrategyType.SCARCITY_HOLD,
            rationale=rationale,
            confidence=0.55,
            rule_fired="scarcity_hold_residual",
        )

    # 7. Default — single family owner-occ, or unknown when inputs too thin.
    if is_multi_family:
        rationale.append("Multi-family property without clear occupancy intent; defaulting to pure_rental.")
        return StrategyClassification(
            strategy=PropertyStrategyType.PURE_RENTAL,
            rationale=rationale,
            confidence=0.55,
            rule_fired="multi_family_default_pure_rental",
        )

    if occupancy == OccupancyStrategy.OWNER_OCCUPY_FULL or occupancy is None:
        # Owner-occ SFH is the most common residential outcome; accept it as
        # the default but flag low confidence when occupancy was not declared.
        confidence = 0.70 if occupancy == OccupancyStrategy.OWNER_OCCUPY_FULL else 0.45
        rationale.append(
            "Single-family, no rental/reno signal; treating as owner-occupied SFH."
            if occupancy == OccupancyStrategy.OWNER_OCCUPY_FULL
            else "Occupancy undeclared; defaulting to owner-occupied SFH with low confidence."
        )
        return StrategyClassification(
            strategy=PropertyStrategyType.OWNER_OCC_SFH,
            rationale=rationale,
            confidence=confidence,
            rule_fired="owner_occ_sfh_default",
        )

    return StrategyClassification(
        strategy=PropertyStrategyType.UNKNOWN,
        rationale=["No rule matched; inputs are too thin to classify."],
        confidence=0.0,
        rule_fired="none",
    )


# ─── Rule helpers ─────────────────────────────────────────────────────────────


def _is_redevelopment_signal(p: PropertyInput) -> bool:
    """Return True when the deal looks like a teardown / land play."""

    lot_size_acres = p.lot_size
    price = p.purchase_price
    sqft = p.sqft
    condition = (p.condition_profile or "").lower()

    # Explicit capex lane flag overrides ratios.
    capex_lane = (p.capex_lane or "").lower()
    if "redevelop" in capex_lane or "teardown" in capex_lane:
        return True

    # Heuristic: very large lot + small / old / poor-condition structure + high price.
    # This is a conservative signal — only fires when the delta is obvious.
    if (
        lot_size_acres is not None
        and lot_size_acres >= 0.5
        and sqft is not None
        and sqft < 1200
        and price is not None
        and price >= 800_000
    ):
        return True

    if "teardown" in condition or "needs_rebuild" in condition:
        return True

    return False


def _is_value_add_signal(p: PropertyInput) -> bool:
    """Condition / capex indicators that say the thesis is renovation upside."""

    condition = (p.condition_profile or "").lower()
    capex = (p.capex_lane or "").lower()

    if any(token in condition for token in ("needs_work", "dated", "fixer", "handyman", "as-is")):
        return True
    if any(token in capex for token in ("major_renovation", "gut", "full_reno", "value_add")):
        return True
    return False


def _is_scarcity_hold_signal(p: PropertyInput) -> bool:
    """Placeholder for now — real scarcity signal will come from town module.

    In Phase 4 the ``primary_value_source`` bridge will feed scarcity_score from
    market_signals into this classifier. For Phase 3 we return False unless
    explicit flags are set, so we do not over-claim "scarcity" just because a
    property has no other thesis.
    """

    return False


# ─── Scoped runner (so orchestrator can call it like any other module) ───────


def run_strategy_classifier(context: ExecutionContext) -> dict[str, object]:
    """Scoped-module entry point. Returns a ModulePayload dict.

    Error contract (DECISIONS.md 2026-04-24): standalone wrapper. Any
    exception raised while building ``PropertyInput`` or classifying returns
    ``module_payload_from_error`` (``mode="fallback"``, ``confidence=0.08``).
    ``classify_strategy`` itself is deterministic and rule-only, but the
    ``PropertyInput`` builder can raise on adversarial contexts.
    """

    try:
        property_input = build_property_input_from_context(context)
        classification = classify_strategy(property_input)
        payload = ModulePayload(
            module_name="strategy_classifier",
            summary=f"Strategy: {classification.strategy.value} (rule: {classification.rule_fired})",
            score=classification.confidence,
            confidence=classification.confidence,
            data={
                "module_name": "strategy_classifier",
                "strategy": classification.strategy.value,
                "rationale": list(classification.rationale),
                "rule_fired": classification.rule_fired,
                "candidates": [c.value for c in classification.candidates],
                "classification": classification.to_dict(),
            },
            assumptions_used={
                "classifier_version": "phase3/v1",
                "property_id": property_input.property_id,
                "deterministic": True,
            },
            warnings=(
                [f"Strategy classified with confidence {classification.confidence:.2f}"]
                if classification.confidence < 0.50
                else []
            ),
        )
        return payload.model_dump()
    except Exception as exc:  # noqa: BLE001
        return module_payload_from_error(
            module_name="strategy_classifier",
            context=context,
            summary="Strategy classification unavailable — inputs too sparse or malformed to classify.",
            warnings=[f"Strategy-classifier fallback: {type(exc).__name__}: {exc}"],
            assumptions_used={
                "classifier_version": "phase3/v1",
                "deterministic": True,
                "fallback_reason": "sparse_or_malformed_inputs",
            },
            required_fields=["town", "state", "sqft", "beds"],
        ).model_dump()


__all__ = [
    "PropertyStrategyType",
    "StrategyClassification",
    "classify_strategy",
    "run_strategy_classifier",
]
