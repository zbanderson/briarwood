from __future__ import annotations

from dataclasses import dataclass


IDENTITY_FIELDS = {"address", "town", "state", "zip", "zip_code", "latitude", "longitude"}
STRUCTURAL_FIELDS = {"beds", "baths", "sqft", "lot_size", "year_built", "stories", "garage_spaces", "units", "unit_count", "property_type"}
SALE_FIELDS = {"last_sale_price", "last_sale_date", "sale_price", "sale_date"}
TAX_FIELDS = {"tax_amount", "tax_year", "assessed_value", "assessed_total", "market_value", "taxes"}
RENT_FIELDS = {"estimated_rent", "rental_avm", "observed_rent", "estimated_monthly_rent"}


@dataclass(frozen=True, slots=True)
class FieldPolicy:
    group: str
    priority_order: tuple[str, ...]
    allow_user_override_replacement: bool = False


FIELD_POLICIES: dict[str, FieldPolicy] = {}


def _register(fields: set[str], policy: FieldPolicy) -> None:
    for field_name in fields:
        FIELD_POLICIES[field_name] = policy


_register(
    IDENTITY_FIELDS,
    FieldPolicy(
        group="identity",
        priority_order=("user_override", "public_record", "modiv", "attom", "listing_text", "geocoded_fallback", "inferred"),
    ),
)
_register(
    STRUCTURAL_FIELDS,
    FieldPolicy(
        group="structural",
        priority_order=("user_override", "modiv", "public_record", "attom", "listing_text", "inferred"),
    ),
)
_register(
    SALE_FIELDS,
    FieldPolicy(
        group="sale",
        priority_order=("sr1a", "attom_sale_detail", "user_confirmed", "listing_text", "inferred"),
    ),
)
_register(
    TAX_FIELDS,
    FieldPolicy(
        group="tax",
        priority_order=("user_confirmed_tax_bill", "attom_assessment", "nj_tax_context", "listing_text", "inferred"),
    ),
)
_register(
    RENT_FIELDS,
    FieldPolicy(
        group="rent",
        priority_order=("user_confirmed", "observed_market_rent", "attom_rental_avm", "briarwood_estimate"),
    ),
)


def get_field_policy(field_name: str) -> FieldPolicy:
    return FIELD_POLICIES.get(
        field_name,
        FieldPolicy(group="other", priority_order=("user_override", "public_record", "attom", "listing_text", "inferred")),
    )


def source_rank(field_name: str, source: str, *, is_user_override: bool = False) -> int:
    if is_user_override:
        return 0
    policy = get_field_policy(field_name)
    normalized_source = _canonical_source_label(source)
    try:
        return policy.priority_order.index(normalized_source)
    except ValueError:
        return len(policy.priority_order) + 1


def field_group(field_name: str) -> str:
    return get_field_policy(field_name).group


def _canonical_source_label(source: str) -> str:
    normalized = (source or "").strip().lower()
    if "user" in normalized and "tax" in normalized and "bill" in normalized:
        return "user_confirmed_tax_bill"
    if "user" in normalized or "manual override" in normalized:
        return "user_override"
    if "user confirmed" in normalized:
        return "user_confirmed"
    if "sr1a" in normalized:
        return "sr1a"
    if "modiv" in normalized or "mod-iv" in normalized:
        return "modiv"
    if "public" in normalized:
        return "public_record"
    if "attom" in normalized and "sale" in normalized:
        return "attom_sale_detail"
    if "attom" in normalized and "assessment" in normalized:
        return "attom_assessment"
    if "attom" in normalized and "rental" in normalized:
        return "attom_rental_avm"
    if "attom" in normalized:
        return "attom"
    if "lease" in normalized or "observed rent" in normalized or "market rent" in normalized:
        return "observed_market_rent"
    if "listing" in normalized:
        return "listing_text"
    if "tax context" in normalized or "nj tax" in normalized:
        return "nj_tax_context"
    if "geocode" in normalized:
        return "geocoded_fallback"
    if "estimate" in normalized or "inferred" in normalized or "fallback" in normalized or "briarwood" in normalized:
        return "inferred" if "briarwood" not in normalized else "briarwood_estimate"
    return normalized or "inferred"
