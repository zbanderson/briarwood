from __future__ import annotations

from briarwood.schemas import PropertyInput


MODELED_FIELDS = {
    "purchase_price",
    "beds",
    "baths",
    "sqft",
    "lot_size",
    "year_built",
    "property_type",
    "architectural_style",
    "condition_profile",
    "capex_lane",
    "stories",
    "garage_spaces",
    "taxes",
    "insurance",
    "monthly_hoa",
    "estimated_monthly_rent",
    "unit_rents",
    "rent_confidence_override",
    "back_house_monthly_rent",
    "down_payment_percent",
    "interest_rate",
    "loan_term_years",
    "days_on_market",
    "listing_date",
    "listing_description",
    "price_history",
    "vacancy_rate",
    "condition_confirmed",
    "capex_confirmed",
    "repair_capex_budget",
    "manual_comp_inputs",
    "town_population_trend",
    "town_price_trend",
    "school_rating",
    "flood_risk",
    "town_population",
    "market_price_to_rent_benchmark",
    "landmark_points",
    "zone_flags",
    "local_documents",
    "latitude",
    "longitude",
}

DESCRIPTIVE_FIELDS = {
    "address",
    "town",
    "state",
    "county",
    "source_url",
    "garage_type",
    "has_detached_garage",
    "has_back_house",
    "adu_type",
    "adu_sqft",
    "has_basement",
    "basement_finished",
    "has_pool",
    "parking_spaces",
    "corner_lot",
    "driveway_off_street",
    "seasonal_monthly_rent",
    "monthly_maintenance_reserve_override",
    "strategy_intent",
    "hold_period_years",
    "risk_tolerance",
}


def audit_property_fields(property_input: PropertyInput) -> tuple[list[str], list[str]]:
    populated_fields = [
        field_name
        for field_name, value in property_input.to_dict().items()
        if field_name not in {"facts", "market_signals", "user_assumptions", "source_metadata", "property_id"}
        and value not in (None, "", [], {}, 0, 0.0, False)
    ]
    modeled = sorted(field_name for field_name in populated_fields if field_name in MODELED_FIELDS)
    non_modeled = sorted(field_name for field_name in populated_fields if field_name not in MODELED_FIELDS)
    return modeled, non_modeled
