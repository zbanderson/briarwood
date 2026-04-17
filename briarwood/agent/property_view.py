"""Unified property view — single loader seam for every handler.

Three independent views of a property used to exist in parallel:

1. Listing view — ``summary.json`` held the canonical ``ask_price``.
2. Analysis view — ``value_position.ask_price`` in the unified output was
   silently aliased to ``all_in_basis`` (purchase_price + capex), so the same
   nominal field meant different things in browse vs decision.
3. Scenario view — what-if overrides rewrote ``purchase_price`` in a tempfile
   but the downstream field labels kept calling it "ask", hiding the shift.

``PropertyView`` collapses those into one contract: ``ask_price`` is always
the listing ask (from ``summary.json``), ``all_in_basis`` is a distinct named
derived field, and overrides are carried explicitly so the narration layer
can say what changed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from briarwood.agent.tools import (
    ToolUnavailable,
    analyze_property,
    get_property_summary,
)


Depth = Literal["browse", "decision"]


@dataclass(frozen=True, slots=True)
class PropertyView:
    """Every handler consumes this. One load path, one shape."""

    pid: str

    # Listing facts — populated at every depth.
    address: str | None
    town: str | None
    state: str | None
    beds: int | None
    baths: float | None
    ask_price: float | None
    bcv: float | None
    pricing_view: str | None

    # Analysis fields — populated only at depth="decision".
    fair_value_base: float | None = None
    value_low: float | None = None
    value_high: float | None = None
    all_in_basis: float | None = None
    ask_premium_pct: float | None = None
    basis_premium_pct: float | None = None
    decision_stance: str | None = None
    primary_value_source: str | None = None
    trust_flags: tuple[str, ...] = ()
    what_must_be_true: tuple[str, ...] = ()
    key_risks: tuple[str, ...] = ()

    # Scenario layer.
    overrides_applied: Mapping[str, Any] = field(default_factory=dict)

    # Escape hatch for handlers that still need the raw unified dict
    # (comparison, projection, strategy). Callers should migrate off this
    # once the named fields cover their needs.
    unified: Mapping[str, Any] | None = None

    @classmethod
    def load(
        cls,
        pid: str,
        *,
        overrides: Mapping[str, Any] | None = None,
        depth: Depth = "browse",
    ) -> "PropertyView":
        """Load the view for ``pid`` at the given depth.

        depth="browse"   — reads summary.json only (cheap, no pipeline).
        depth="decision" — also runs analyze_property with any overrides.

        Invariant: ``view.ask_price`` is identical at both depths for the
        same pid. Listing ask comes from summary.json; the analysis
        pipeline never gets to rename it.
        """
        summary = get_property_summary(pid)
        base = cls._from_summary(pid, summary, overrides or {})
        if depth == "browse":
            return base

        unified = analyze_property(pid, overrides=dict(overrides or {}))
        return base._with_unified(unified)

    @classmethod
    def _from_summary(
        cls,
        pid: str,
        summary: Mapping[str, Any],
        overrides: Mapping[str, Any],
    ) -> "PropertyView":
        return cls(
            pid=pid,
            address=summary.get("address"),
            town=summary.get("town"),
            state=summary.get("state"),
            beds=summary.get("beds"),
            baths=summary.get("baths"),
            ask_price=_as_float(summary.get("ask_price")),
            bcv=_as_float(summary.get("bcv")),
            pricing_view=summary.get("pricing_view"),
            overrides_applied=dict(overrides),
        )

    def _with_unified(self, unified: Mapping[str, Any]) -> "PropertyView":
        """Return a new view with analysis fields populated from the unified dict."""
        vp = unified.get("value_position") or {}
        stance = unified.get("decision_stance")
        if hasattr(stance, "value"):
            stance = stance.value

        return PropertyView(
            pid=self.pid,
            address=self.address,
            town=self.town,
            state=self.state,
            beds=self.beds,
            baths=self.baths,
            # Listing ask stays pinned to summary.json — never overwritten by
            # the analysis layer. This is the core invariant of PropertyView.
            ask_price=self.ask_price,
            bcv=self.bcv,
            pricing_view=self.pricing_view,
            fair_value_base=_as_float(vp.get("fair_value_base")),
            value_low=_as_float(vp.get("value_low")),
            value_high=_as_float(vp.get("value_high")),
            all_in_basis=_as_float(vp.get("all_in_basis")),
            ask_premium_pct=_as_float(vp.get("ask_premium_pct")),
            basis_premium_pct=_as_float(
                vp.get("basis_premium_pct") or vp.get("premium_discount_pct")
            ),
            decision_stance=stance,
            primary_value_source=unified.get("primary_value_source"),
            trust_flags=tuple(unified.get("trust_flags") or ()),
            what_must_be_true=tuple(unified.get("what_must_be_true") or ()),
            key_risks=tuple(unified.get("key_risks") or ()),
            overrides_applied=self.overrides_applied,
            unified=unified,
        )


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


__all__ = ["PropertyView", "ToolUnavailable"]
