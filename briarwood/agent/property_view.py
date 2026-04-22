"""Unified property view — single loader seam for every handler.

Three independent views of a property used to exist in parallel:

1. Listing view — ``summary.json`` held the canonical ``ask_price``.
2. Analysis view — ``value_position.ask_price`` in the unified output was
   silently aliased to ``all_in_basis`` (purchase_price + capex), so the same
   nominal field meant different things in browse vs decision.
3. Scenario view — what-if overrides rewrote ``purchase_price`` in a tempfile
   but the downstream field labels kept calling it "ask", hiding the shift.

``PropertyView`` collapses those into one contract: ``ask_price`` is the
working ask for the current turn. By default that comes from ``summary.json``;
if the user or the chat surface supplied a fresher turn-specific ask override,
that value wins for both display and analysis. ``all_in_basis`` remains a
distinct named derived field, and explicit user overrides are carried through
so the narration layer can say what changed.
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
    trust_summary: Mapping[str, Any] = field(default_factory=dict)
    what_must_be_true: tuple[str, ...] = ()
    key_risks: tuple[str, ...] = ()
    why_this_stance: tuple[str, ...] = ()
    what_changes_my_view: tuple[str, ...] = ()
    contradiction_count: int = 0
    blocked_thesis_warnings: tuple[str, ...] = ()

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
        same pid + override set. The default source is ``summary.json``;
        turn-specific ask overrides intentionally replace it so the analysis
        and the UI stay on the same working price.
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
        ask_price = _as_float(overrides.get("ask_price"))
        if ask_price is None:
            ask_price = _as_float(summary.get("ask_price"))
        return cls(
            pid=pid,
            address=summary.get("address"),
            town=summary.get("town"),
            state=summary.get("state"),
            beds=summary.get("beds"),
            baths=summary.get("baths"),
            ask_price=ask_price,
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
            # The display ask stays pinned to the working turn input chosen in
            # _from_summary — never overwritten by the analysis layer.
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
            trust_summary=dict(unified.get("trust_summary") or {}),
            what_must_be_true=tuple(unified.get("what_must_be_true") or ()),
            key_risks=tuple(unified.get("key_risks") or ()),
            why_this_stance=tuple(unified.get("why_this_stance") or ()),
            what_changes_my_view=tuple(unified.get("what_changes_my_view") or ()),
            contradiction_count=int(unified.get("contradiction_count") or 0),
            blocked_thesis_warnings=tuple(unified.get("blocked_thesis_warnings") or ()),
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
