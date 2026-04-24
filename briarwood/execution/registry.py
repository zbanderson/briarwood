from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from briarwood.modules.arv_model_scoped import run_arv_model
from briarwood.modules.carry_cost import run_carry_cost
from briarwood.modules.comparable_sales_scoped import run_comparable_sales
from briarwood.modules.confidence import run_confidence
from briarwood.modules.current_value_scoped import run_current_value
from briarwood.modules.hold_to_rent import run_hold_to_rent
from briarwood.modules.hybrid_value_scoped import run_hybrid_value
from briarwood.modules.income_support_scoped import run_income_support
from briarwood.modules.legal_confidence import run_legal_confidence
from briarwood.modules.location_intelligence_scoped import run_location_intelligence
from briarwood.modules.margin_sensitivity_scoped import run_margin_sensitivity
from briarwood.modules.market_value_history_scoped import run_market_value_history
from briarwood.modules.opportunity_cost import run_opportunity_cost
from briarwood.modules.rental_option_scoped import run_rental_option
from briarwood.modules.renovation_impact_scoped import run_renovation_impact
from briarwood.modules.rent_stabilization import run_rent_stabilization
from briarwood.modules.resale_scenario_scoped import run_resale_scenario
from briarwood.modules.risk_model import run_risk_model
from briarwood.modules.scarcity_support_scoped import run_scarcity_support
from briarwood.modules.strategy_classifier import run_strategy_classifier
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
            depends_on=["valuation", "legal_confidence"],
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
            depends_on=[],
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
            name="opportunity_cost",
            depends_on=["valuation", "resale_scenario"],
            required_context_keys=["property_data"],
            optional_context_keys=["assumptions", "prior_outputs"],
            runner=run_opportunity_cost,
            description=(
                "Q5 capital-allocation-vs-alternatives module. Projects the "
                "property's terminal value over the hold horizon and compares "
                "it to passive benchmarks (T-bill, S&P). Appreciation-only."
            ),
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
        ModuleSpec(
            name="strategy_classifier",
            depends_on=[],
            required_context_keys=["property_data"],
            optional_context_keys=["property_summary"],
            runner=run_strategy_classifier,
            description=(
                "Rule-based property-strategy classifier. Labels a subject "
                "as owner_occ_sfh / owner_occ_duplex / owner_occ_with_adu / "
                "pure_rental / value_add_sfh / redevelopment_play / "
                "scarcity_hold. Deterministic; no LLM."
            ),
        ),
        ModuleSpec(
            name="market_value_history",
            depends_on=[],
            required_context_keys=["property_data"],
            optional_context_keys=["property_summary", "market_context"],
            runner=run_market_value_history,
            description=(
                "Town/county market-trend history via Zillow ZHVI: current "
                "level, 1yr/3yr/5yr change %, time-series points, geography "
                "name/type. Geography-level — not property-specific."
            ),
        ),
        ModuleSpec(
            name="current_value",
            depends_on=[],
            required_context_keys=["property_data"],
            optional_context_keys=["property_summary", "comp_context", "market_context"],
            runner=run_current_value,
            description=(
                "Pre-macro fair-value anchor. Composes comparable_sales + "
                "market_value_history + income_support + hybrid_value "
                "in-process; does NOT apply the HPI-momentum macro nudge. "
                "Use when scenario modeling or stress testing requires "
                "isolating macro-side effects; otherwise use `valuation`."
            ),
        ),
        ModuleSpec(
            name="income_support",
            depends_on=[],
            required_context_keys=["property_data"],
            optional_context_keys=["property_summary", "market_context", "comp_context"],
            runner=run_income_support,
            description=(
                "Raw DSCR / rent-coverage / income-support ratio for LOOKUP "
                "intents. Exposes income_support_ratio, rent_coverage, "
                "price_to_rent, monthly_cash_flow, rent_support_classification. "
                "Use `rental_option` for the full rent-path strategy answer; "
                "use this tool when the caller just needs the underwriting "
                "ratio directly."
            ),
        ),
        ModuleSpec(
            name="scarcity_support",
            depends_on=[],
            required_context_keys=["property_data"],
            optional_context_keys=["property_summary", "market_context"],
            runner=run_scarcity_support,
            description=(
                "Town/segment scarcity signal: scarcity_support_score (0-100), "
                "scarcity_label, buyer_takeaway. Supports RESEARCH / "
                "MICRO_LOCATION / BROWSE intents about inventory competition."
            ),
        ),
        ModuleSpec(
            name="location_intelligence",
            depends_on=[],
            required_context_keys=["property_data"],
            optional_context_keys=["property_summary", "comp_context"],
            runner=run_location_intelligence,
            description=(
                "Landmark-proximity benchmarking against same-town geo peer "
                "comp buckets. Produces per-category scores (beach / downtown "
                "/ park / train / ski), percentile benefits, narratives, and "
                "a rolled-up location score. Supports MICRO_LOCATION / "
                "RESEARCH / BROWSE intents."
            ),
        ),
        ModuleSpec(
            name="comparable_sales",
            depends_on=[],
            required_context_keys=["property_data"],
            optional_context_keys=["property_summary", "comp_context", "market_context"],
            runner=run_comparable_sales,
            description=(
                "Comp-based fair-value anchor (Engine A, saved comps). "
                "Produces comparable_value, comp_count, direct / "
                "income-adjusted / location / lot / blended value ranges, "
                "hybrid-decomposition fields when applicable. Distinct from "
                "the user-facing CMA tool (Engine B, live-Zillow first) at "
                "get_cma()."
            ),
        ),
        ModuleSpec(
            name="hybrid_value",
            depends_on=["comparable_sales", "income_support"],
            required_context_keys=["property_data"],
            optional_context_keys=["prior_outputs", "comp_context"],
            runner=run_hybrid_value,
            description=(
                "Decomposed valuation for multi-unit / primary+ADU "
                "properties. Splits value into primary-house + rear-income "
                "capitalized + optionality premium + market-friction / "
                "feedback adjustments. Only meaningful for hybrid subjects; "
                "non-hybrid subjects receive an explicit is_hybrid=False "
                "payload with zero confidence. Composite wrapper — requires "
                "comparable_sales and income_support to have run cleanly."
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
