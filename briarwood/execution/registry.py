from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from briarwood.modules.arv_model_scoped import run_arv_model
from briarwood.modules.carry_cost import run_carry_cost
from briarwood.modules.confidence import run_confidence
from briarwood.modules.hold_to_rent import run_hold_to_rent
from briarwood.modules.legal_confidence import run_legal_confidence
from briarwood.modules.margin_sensitivity_scoped import run_margin_sensitivity
from briarwood.modules.rental_option_scoped import run_rental_option
from briarwood.modules.renovation_impact_scoped import run_renovation_impact
from briarwood.modules.rent_stabilization import run_rent_stabilization
from briarwood.modules.resale_scenario_scoped import run_resale_scenario
from briarwood.modules.risk_model import run_risk_model
from briarwood.modules.town_development_index import run_town_development_index
from briarwood.modules.unit_income_offset import run_unit_income_offset
from briarwood.modules.valuation import run_valuation


Runner = Callable[..., dict[str, Any]]


@dataclass(slots=True)
class ModuleSpec:
    """Formal execution spec for one Briarwood V2 scoped module."""

    name: str
    depends_on: list[str] = field(default_factory=list)
    required_context_keys: list[str] = field(default_factory=list)
    optional_context_keys: list[str] = field(default_factory=list)
    runner: Runner | None = None
    description: str | None = None


def _not_implemented_runner(module_name: str) -> Runner:
    """Return a stub runner for modules not yet wired into scoped execution."""

    def _runner(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        """Raise a clear error until the scoped runner is implemented."""

        raise NotImplementedError(
            f"Scoped runner for module '{module_name}' is not implemented yet."
        )

    return _runner


def build_module_registry() -> dict[str, ModuleSpec]:
    """Build the Briarwood V2 module registry with first-pass dependencies."""

    specs = [
        ModuleSpec(
            name="valuation",
            depends_on=[],
            required_context_keys=["property_data"],
            optional_context_keys=["property_summary", "comp_context", "market_context"],
            runner=run_valuation,
            description="Current value / valuation anchor module.",
        ),
        ModuleSpec(
            name="carry_cost",
            depends_on=[],
            required_context_keys=["property_data", "assumptions"],
            optional_context_keys=["property_summary"],
            runner=run_carry_cost,
            description="Carry, financing, and ownership-cost module.",
        ),
        ModuleSpec(
            name="risk_model",
            depends_on=["valuation"],
            required_context_keys=["property_data"],
            optional_context_keys=["prior_outputs", "market_context"],
            runner=run_risk_model,
            description="Decision risk and fragility module.",
        ),
        ModuleSpec(
            name="confidence",
            depends_on=[],
            required_context_keys=["property_data"],
            optional_context_keys=["prior_outputs"],
            runner=run_confidence,
            description="Confidence and evidence-quality module.",
        ),
        ModuleSpec(
            name="resale_scenario",
            depends_on=["valuation", "carry_cost", "town_development_index"],
            required_context_keys=["property_data", "assumptions"],
            optional_context_keys=["prior_outputs", "market_context"],
            runner=run_resale_scenario,
            description="Forward resale scenario module.",
        ),
        ModuleSpec(
            name="rental_option",
            depends_on=["valuation"],
            required_context_keys=["property_data"],
            optional_context_keys=["prior_outputs", "market_context", "comp_context"],
            runner=run_rental_option,
            description="Rental option and rent-path module.",
        ),
        ModuleSpec(
            name="rent_stabilization",
            depends_on=[],
            required_context_keys=["property_data"],
            optional_context_keys=["market_context", "comp_context"],
            runner=run_rent_stabilization,
            description="Rent durability and stabilization module.",
        ),
        ModuleSpec(
            name="hold_to_rent",
            depends_on=["carry_cost", "rent_stabilization"],
            required_context_keys=["property_data", "assumptions"],
            optional_context_keys=["prior_outputs", "market_context"],
            runner=run_hold_to_rent,
            description="Hold-to-rent path module.",
        ),
        ModuleSpec(
            name="renovation_impact",
            depends_on=[],
            required_context_keys=["property_data", "assumptions"],
            optional_context_keys=["property_summary"],
            runner=run_renovation_impact,
            description="Renovation scope and impact module.",
        ),
        ModuleSpec(
            name="arv_model",
            depends_on=["valuation", "renovation_impact"],
            required_context_keys=["property_data", "assumptions"],
            optional_context_keys=["prior_outputs", "comp_context"],
            runner=run_arv_model,
            description="After-repair value module.",
        ),
        ModuleSpec(
            name="margin_sensitivity",
            depends_on=["arv_model", "renovation_impact", "carry_cost"],
            required_context_keys=["property_data", "assumptions"],
            optional_context_keys=["prior_outputs"],
            runner=run_margin_sensitivity,
            description="Margin sensitivity module for renovation paths.",
        ),
        ModuleSpec(
            name="unit_income_offset",
            depends_on=["carry_cost"],
            required_context_keys=["property_data", "assumptions"],
            optional_context_keys=["prior_outputs", "comp_context"],
            runner=run_unit_income_offset,
            description="Additional-unit or offset-income module.",
        ),
        ModuleSpec(
            name="legal_confidence",
            depends_on=[],
            required_context_keys=["property_data"],
            optional_context_keys=["market_context", "prior_outputs"],
            runner=run_legal_confidence,
            description="Legality confidence module for use-permission uncertainty.",
        ),
        ModuleSpec(
            name="town_development_index",
            depends_on=[],
            required_context_keys=["property_data"],
            optional_context_keys=["property_summary"],
            runner=run_town_development_index,
            description=(
                "Rolling town-level development velocity derived from "
                "planning/zoning minutes. Feeds forward-looking modules."
            ),
        ),
    ]

    registry = {spec.name: spec for spec in specs}
    validate_registry(registry)
    return registry


def validate_registry(registry: dict[str, ModuleSpec]) -> None:
    """Validate that a module registry is internally consistent."""

    if not isinstance(registry, dict):
        raise TypeError("registry must be a dict[str, ModuleSpec].")

    seen_names: set[str] = set()
    for key, spec in registry.items():
        if not isinstance(spec, ModuleSpec):
            raise TypeError(f"Registry entry for '{key}' is not a ModuleSpec.")
        if not spec.name:
            raise ValueError(f"Registry entry '{key}' is missing a module name.")
        if spec.name in seen_names:
            raise ValueError(f"Duplicate module name detected: {spec.name}")
        seen_names.add(spec.name)
        if key != spec.name:
            raise ValueError(
                f"Registry key '{key}' must match ModuleSpec.name '{spec.name}'."
            )
        if spec.runner is None or not callable(spec.runner):
            raise ValueError(f"Module '{spec.name}' must define a callable runner.")

    known_modules = set(registry.keys())
    for spec in registry.values():
        for dependency in spec.depends_on:
            if dependency not in known_modules:
                raise ValueError(
                    f"Module '{spec.name}' depends on unknown module '{dependency}'."
                )


__all__ = [
    "ModuleSpec",
    "build_module_registry",
    "validate_registry",
]
