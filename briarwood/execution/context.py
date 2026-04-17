from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutionContext(BaseModel):
    """Normalized shared context for Briarwood V2 scoped module execution.

    This object is the common input passed to scoped module runners. It keeps
    the execution boundary explicit and compact by carrying only structured
    context needed for module planning and module-to-module handoff.

    Raw user text and large freeform blobs should not be stored here.
    """

    model_config = ConfigDict(extra="forbid")

    property_id: str | None = None
    property_data: dict[str, Any] = Field(default_factory=dict)
    property_summary: dict[str, Any] = Field(default_factory=dict)
    parser_output: dict[str, Any] = Field(default_factory=dict)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    prior_outputs: dict[str, Any] = Field(default_factory=dict)
    market_context: dict[str, Any] = Field(default_factory=dict)
    comp_context: dict[str, Any] = Field(default_factory=dict)
    macro_context: dict[str, Any] = Field(default_factory=dict)

    def store_module_output(self, module_name: str, output: dict[str, Any]) -> None:
        """Store one scoped module output into ``prior_outputs`` by module name."""

        self.prior_outputs[str(module_name)] = dict(output)

    def get_module_output(self, module_name: str) -> dict[str, Any] | None:
        """Return a prior module output by module name when available."""

        value = self.prior_outputs.get(str(module_name))
        return value if isinstance(value, dict) else None

    def debug_summary(self) -> dict[str, Any]:
        """Return a compact summary showing which execution context slices exist."""

        return {
            "property_id": self.property_id,
            "has_property_data": bool(self.property_data),
            "has_property_summary": bool(self.property_summary),
            "has_parser_output": bool(self.parser_output),
            "has_assumptions": bool(self.assumptions),
            "prior_output_modules": sorted(self.prior_outputs.keys()),
            "has_market_context": bool(self.market_context),
            "has_comp_context": bool(self.comp_context),
            "has_macro_context": bool(self.macro_context),
        }


__all__ = ["ExecutionContext"]
