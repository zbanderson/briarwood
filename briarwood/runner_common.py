"""Shared utilities used by the routed runner path.

Hosts `build_engine` (lifted from the deleted `runner_legacy.py`) plus
property-input preparation and validation shared across callers.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from briarwood.engine import AnalysisEngine
from briarwood.decision_model.scoring_config import BullBaseBearSettings, RiskSettings
from briarwood.modules.bull_base_bear import BullBaseBearModule
from briarwood.modules.comparable_sales import ComparableSalesModule
from briarwood.modules.cost_valuation import CostValuationModule
from briarwood.modules.current_value import CurrentValueModule
from briarwood.modules.hybrid_value import HybridValueModule
from briarwood.modules.income_support import IncomeSupportModule
from briarwood.modules.liquidity_signal import LiquiditySignalModule
from briarwood.modules.local_intelligence import LocalIntelligenceModule
from briarwood.modules.location_context import build_default_town_county_service
from briarwood.modules.location_intelligence import LocationIntelligenceModule
from briarwood.modules.market_momentum_signal import MarketMomentumSignalModule
from briarwood.modules.market_value_history import MarketValueHistoryModule
from briarwood.modules.property_data_quality import PropertyDataQualityModule
from briarwood.modules.property_snapshot import PropertySnapshotModule
from briarwood.modules.rental_ease import RentalEaseModule
from briarwood.modules.renovation_scenario import RenovationScenarioModule
from briarwood.modules.risk_constraints import RiskConstraintsModule
from briarwood.modules.scarcity_support import ScarcitySupportModule
from briarwood.modules.teardown_scenario import TeardownScenarioModule
from briarwood.modules.town_county_outlook import TownCountyOutlookModule
from briarwood.modules.value_drivers import ValueDriversModule
from briarwood.schemas import AnalysisReport, PropertyInput
from briarwood.settings import CostValuationSettings
from briarwood.routing_schema import (
    EngineOutput,
    RoutingDecision,
    UnifiedIntelligenceOutput,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RoutedAnalysisResult:
    """Bundle the routing-layer artifacts with an optional legacy-engine report.

    When scoped execution handles the full module set, ``report`` is None —
    the full engine never ran.
    """

    report: AnalysisReport | None
    routing_decision: RoutingDecision
    engine_output: EngineOutput
    unified_output: UnifiedIntelligenceOutput
    property_summary: dict[str, Any]
    execution_mode: str = "legacy_fallback"


def build_engine(
    *,
    cost_settings: CostValuationSettings | None = None,
    bull_base_bear_settings: BullBaseBearSettings | None = None,
    risk_settings: RiskSettings | None = None,
) -> AnalysisEngine:
    market_value_history_module = MarketValueHistoryModule()
    comparable_sales_module = ComparableSalesModule(market_value_history_module=market_value_history_module)
    income_support_module = IncomeSupportModule(settings=cost_settings)
    hybrid_value_module = HybridValueModule(
        comparable_sales_module=comparable_sales_module,
        income_support_module=income_support_module,
    )
    current_value_module = CurrentValueModule(
        comparable_sales_module=comparable_sales_module,
        market_value_history_module=market_value_history_module,
        income_support_module=income_support_module,
        hybrid_value_module=hybrid_value_module,
    )
    risk_constraints_module = RiskConstraintsModule(settings=risk_settings)
    town_county_service = build_default_town_county_service()
    town_county_outlook_module = TownCountyOutlookModule(service=town_county_service)
    scarcity_support_module = ScarcitySupportModule(service=town_county_service)
    location_intelligence_module = LocationIntelligenceModule()
    local_intelligence_module = LocalIntelligenceModule()
    renovation_scenario_module = RenovationScenarioModule(
        comparable_sales_module=comparable_sales_module,
        current_value_module=current_value_module,
    )
    teardown_scenario_module = TeardownScenarioModule(
        comparable_sales_module=comparable_sales_module,
        current_value_module=current_value_module,
        income_support_module=income_support_module,
    )
    rental_ease_module = RentalEaseModule(
        income_support_module=income_support_module,
        town_county_outlook_module=town_county_outlook_module,
        scarcity_support_module=scarcity_support_module,
    )
    liquidity_signal_module = LiquiditySignalModule(
        comparable_sales_module=comparable_sales_module,
        rental_ease_module=rental_ease_module,
        town_county_outlook_module=town_county_outlook_module,
    )
    market_momentum_signal_module = MarketMomentumSignalModule(
        market_value_history_module=market_value_history_module,
        town_county_outlook_module=town_county_outlook_module,
        local_intelligence_module=local_intelligence_module,
    )

    return AnalysisEngine(
        modules=[
            PropertySnapshotModule(),
            PropertyDataQualityModule(),
            market_value_history_module,
            comparable_sales_module,
            hybrid_value_module,
            current_value_module,
            CostValuationModule(settings=cost_settings),
            income_support_module,
            rental_ease_module,
            liquidity_signal_module,
            BullBaseBearModule(
                settings=bull_base_bear_settings,
                current_value_module=current_value_module,
                market_value_history_module=market_value_history_module,
                town_county_outlook_module=town_county_outlook_module,
                risk_constraints_module=risk_constraints_module,
                scarcity_support_module=scarcity_support_module,
            ),
            risk_constraints_module,
            town_county_outlook_module,
            scarcity_support_module,
            location_intelligence_module,
            local_intelligence_module,
            market_momentum_signal_module,
            renovation_scenario_module,
            teardown_scenario_module,
            ValueDriversModule(),
        ]
    )


def _prepare_property_input(property_input: PropertyInput) -> None:
    """Apply smart defaults and geocoding to a PropertyInput before analysis."""
    from briarwood.defaults import apply_smart_defaults
    from briarwood.geocoder import apply_geocoding

    # Apply smart defaults for missing financing, costs, and condition
    defaults_result = apply_smart_defaults(property_input)
    property_input.defaults_applied = defaults_result.fields

    # Geocoding is opt-in for app responsiveness. It can introduce slow
    # network waits during report loading, especially in Dash callbacks.
    if os.environ.get("BRIARWOOD_ENABLE_GEOCODING", "").strip().lower() not in {"1", "true", "yes"}:
        return

    # Geocode address if lat/lon missing (enables location_intelligence module).
    # Geocoding is best-effort: network/import failures must not block analysis,
    # but we log them so silent degradation of location_intelligence is debuggable.
    try:
        if apply_geocoding(property_input):
            property_input.geocoded = True
    except (OSError, ValueError, RuntimeError) as exc:
        logger.warning(
            "Geocoding skipped for %s: %s", property_input.address, exc
        )


def validate_property_input(property_input: PropertyInput) -> None:
    """Fail fast on obviously invalid inputs before running analysis."""

    numeric_validations = {
        "purchase_price": property_input.purchase_price,
        "beds": property_input.beds,
        "baths": property_input.baths,
        "sqft": property_input.sqft,
        "lot_size": property_input.lot_size,
        "taxes": property_input.taxes,
        "insurance": property_input.insurance,
        "monthly_hoa": property_input.monthly_hoa,
        "estimated_monthly_rent": property_input.estimated_monthly_rent,
    }
    invalid_negative = [
        field_name
        for field_name, value in numeric_validations.items()
        if value is not None and value < 0
    ]
    if invalid_negative:
        raise ValueError(
            "Property input contains negative values for fields that must be non-negative: "
            + ", ".join(sorted(invalid_negative))
        )

    if not property_input.address:
        raise ValueError("Property input is missing address.")
    if not property_input.town or not property_input.state:
        raise ValueError("Property input must include town and state.")
