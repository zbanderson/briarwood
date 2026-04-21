"""Project a ``UnifiedIntelligenceOutput`` to a legacy display verdict.

The canonical verdict is produced by ``briarwood/synthesis/structured.py``
and uses the routed ``DecisionStance`` / ``DecisionType`` vocabulary. A few
compatibility surfaces (Dash ``quick_decision``, Dash ``view_models``, the
tear-sheet ``thesis_section`` and ``conclusion_section``) still render in
the older ``BUY / LEAN BUY / NEUTRAL / LEAN PASS / AVOID`` vocabulary.

This projector is the **only** place that maps one to the other. It never
recomputes a verdict; it only relabels the routed output so that surfaces
which have not yet migrated can keep rendering.

Stance mapping (approved 2026-04-20). Seven routed stances → five legacy
labels; three routed stances collapse at this surface, which loses nuance
at the label tier and is why ``LegacyVerdict`` also carries
``is_trust_gate_fallback`` and passes through the routed stance for any
consumer that wants to render more faithfully.

    ┌───────────────────────────────┬────────────┬────────────────────────────────────┐
    │ DecisionStance                │ Legacy     │ Notes                              │
    ├───────────────────────────────┼────────────┼────────────────────────────────────┤
    │ STRONG_BUY                    │ BUY        │ clean                              │
    │ BUY_IF_PRICE_IMPROVES         │ LEAN BUY   │ clean                              │
    │ EXECUTION_DEPENDENT           │ LEAN BUY   │ conditional yes; caveat in prose   │
    │ INTERESTING_BUT_FRAGILE       │ NEUTRAL    │ value there, risk dominates        │
    │ CONDITIONAL                   │ NEUTRAL    │ trust-gate fallback                │
    │ PASS_UNLESS_CHANGES           │ LEAN PASS  │ clean                              │
    │ PASS                          │ AVOID      │ currently unemitted by classifier  │
    └───────────────────────────────┴────────────┴────────────────────────────────────┘

The same table lives in ``briarwood/projections/README.md`` and
``STATE_OF_1.0.md``; keep all three in sync.
"""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from briarwood.routing_schema import DecisionStance, UnifiedIntelligenceOutput


LEGACY_LABEL_BUY = "BUY"
LEGACY_LABEL_LEAN_BUY = "LEAN BUY"
LEGACY_LABEL_NEUTRAL = "NEUTRAL"
LEGACY_LABEL_LEAN_PASS = "LEAN PASS"
LEGACY_LABEL_AVOID = "AVOID"


STANCE_TO_LEGACY_LABEL: Mapping[DecisionStance, str] = {
    DecisionStance.STRONG_BUY: LEGACY_LABEL_BUY,
    DecisionStance.BUY_IF_PRICE_IMPROVES: LEGACY_LABEL_LEAN_BUY,
    DecisionStance.EXECUTION_DEPENDENT: LEGACY_LABEL_LEAN_BUY,
    DecisionStance.INTERESTING_BUT_FRAGILE: LEGACY_LABEL_NEUTRAL,
    DecisionStance.CONDITIONAL: LEGACY_LABEL_NEUTRAL,
    DecisionStance.PASS_UNLESS_CHANGES: LEGACY_LABEL_LEAN_PASS,
    DecisionStance.PASS: LEGACY_LABEL_AVOID,
}


class LegacyVerdict(BaseModel):
    """Display-shape verdict for surfaces still on the legacy vocabulary.

    Fields mirror what the deleted ``decision_engine.DecisionOutput`` exposed
    so rewiring the four consumer surfaces (Wednesday) is a field-for-field
    swap, not a schema migration.
    """

    model_config = ConfigDict(extra="forbid")

    recommendation: str = Field(min_length=1)
    """Legacy label. One of BUY / LEAN BUY / NEUTRAL / LEAN PASS / AVOID."""

    conviction: float = Field(ge=0.0, le=1.0)
    """Routed aggregate confidence, surfaced directly (no blending).

    See STATE_OF_1.0.md 'Known limitations' — this number is not directly
    comparable to pre-1.0 conviction values; the bands have been deleted.
    """

    primary_reason: str
    """Top-line explanation line, sourced from ``why_this_stance[0]`` when
    present, otherwise a deterministic fallback constructed from
    ``value_position``."""

    secondary_reason: str
    """Supporting line, sourced from the first ``key_risks`` entry when
    present, otherwise the second ``why_this_stance`` entry."""

    required_beliefs: list[str] = Field(default_factory=list)
    """Pass-through of ``what_must_be_true``, capped at 3 for UI parity."""

    decision_stance: DecisionStance
    """Pass-through of the canonical routed stance so surfaces that want to
    render with more nuance than the five-label vocabulary allows can do so
    without re-reading the ``UnifiedIntelligenceOutput`` directly."""

    is_trust_gate_fallback: bool = False
    """True when ``decision_stance == CONDITIONAL``. Distinguishes the
    trust-gate NEUTRAL from ``INTERESTING_BUT_FRAGILE`` NEUTRAL so downstream
    surfaces can render a trust-gate caveat instead of a fragility caveat."""


def project_to_legacy(unified: UnifiedIntelligenceOutput) -> LegacyVerdict:
    """Relabel a routed ``UnifiedIntelligenceOutput`` for legacy surfaces."""

    stance = unified.decision_stance
    recommendation = STANCE_TO_LEGACY_LABEL.get(stance, LEGACY_LABEL_NEUTRAL)

    primary_reason, secondary_reason = _extract_reasons(unified)
    required_beliefs = list(unified.what_must_be_true[:3])

    return LegacyVerdict(
        recommendation=recommendation,
        conviction=round(float(unified.confidence), 2),
        primary_reason=primary_reason,
        secondary_reason=secondary_reason,
        required_beliefs=required_beliefs,
        decision_stance=stance,
        is_trust_gate_fallback=(stance == DecisionStance.CONDITIONAL),
    )


def _extract_reasons(unified: UnifiedIntelligenceOutput) -> tuple[str, str]:
    """Pick the two narrative lines legacy surfaces want.

    Primary: first ``why_this_stance`` entry, falling back to the routed
    ``recommendation`` line (always populated) so the projector never
    emits an empty ``primary_reason``.

    Secondary: first ``key_risks`` entry when present; otherwise the second
    ``why_this_stance`` entry; otherwise a deterministic fallback describing
    the value position when it exists.
    """

    why = [line for line in unified.why_this_stance if line]
    risks = [line for line in unified.key_risks if line]

    primary = why[0] if why else unified.recommendation

    if risks:
        secondary = risks[0]
    elif len(why) > 1:
        secondary = why[1]
    else:
        secondary = _value_position_fallback(unified.value_position)

    return primary, secondary


def _value_position_fallback(value_position: dict[str, Any]) -> str:
    """Deterministic one-line description of the value position.

    Used only when the routed output produced no ``key_risks`` and only one
    ``why_this_stance`` line. Keeps the legacy surface's ``secondary_reason``
    field populated rather than empty — surfaces treat empty as missing.
    """

    premium_pct = value_position.get("premium_discount_pct")
    if isinstance(premium_pct, (int, float)):
        if premium_pct <= -0.05:
            return f"Fair value sits about {abs(premium_pct):.0%} above the basis."
        if premium_pct >= 0.05:
            return f"Basis sits about {premium_pct:.0%} above fair value."
        return "Basis is close to fair value; execution matters more than headline gap."
    return "The current evidence stack does not fully resolve the case."
