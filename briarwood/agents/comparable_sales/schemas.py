from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ComparableValueRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low: float | None = None
    midpoint: float | None = None
    high: float | None = None
    comp_count: int = 0
    confidence: float = Field(default=0.0, ge=0, le=1)
    explanation: str = ""


class BaseCompSelectionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    address: str
    sale_price: float
    distance_miles: float | None = None
    similarity_score: float = Field(ge=0, le=1)
    match_reasons: list[str] = Field(default_factory=list)
    mismatch_flags: list[str] = Field(default_factory=list)
    selection_tier: str = ""


class BaseCompSupportSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comp_count: int = 0
    same_town_count: int = 0
    median_distance: float | None = None
    support_quality: str = Field(default="thin", pattern="^(strong|moderate|thin)$")
    notes: list[str] = Field(default_factory=list)


class BaseCompSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_comps: list[BaseCompSelectionItem] = Field(default_factory=list)
    base_shell_value: float | None = None
    support_summary: BaseCompSupportSummary = Field(default_factory=BaseCompSupportSummary)


class FeatureAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    amount: float | None = None
    method: str
    support_type: str
    note: str = ""


class LocationAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    amount: float | None = None
    method: str
    support_type: str
    note: str = ""


class TownTransferAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    amount: float | None = None
    from_town: str | None = None
    to_town: str | None = None
    method: str
    support_type: str
    note: str = ""


class SupportSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direct_support_count: int = 0
    translated_support_count: int = 0
    same_town_count: int = 0
    income_support_count: int = 0
    location_support_count: int = 0
    primary_mode: str = ""
    notes: list[str] = Field(default_factory=list)


class ComparableCompAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_shell_value: float | None = None
    cottage_adu_value: float | None = None
    feature_adjustments: dict[str, FeatureAdjustment] = Field(default_factory=dict)
    location_adjustments: dict[str, LocationAdjustment] = Field(default_factory=dict)
    town_transfer_adjustments: dict[str, TownTransferAdjustment] = Field(default_factory=dict)
    town_context_adjustment: float | None = None
    market_friction_discount: float | None = None
    market_feedback_adjustment: float | None = None
    adjusted_fair_value: float | None = None
    adjusted_value: float | None = None
    support_summary: SupportSummary = Field(default_factory=SupportSummary)
    confidence: float = Field(default=0.0, ge=0, le=1)
    market_feedback: dict[str, object] | None = None
    top_drivers: list[str] = Field(default_factory=list)
    watch_items: list[str] = Field(default_factory=list)
    feature_engine: dict[str, object] | None = None
    location_engine: dict[str, object] | None = None
    town_transfer_engine: dict[str, object] | None = None
    confidence_engine: dict[str, object] | None = None


class ComparableSale(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    address: str
    town: str
    state: str
    property_type: str | None = None
    architectural_style: str | None = None
    condition_profile: str | None = Field(default=None, pattern="^(renovated|updated|maintained|dated|needs_work)$")
    capex_lane: str | None = Field(default=None, pattern="^(light|moderate|heavy)$")
    list_price: float | None = Field(default=None, gt=0)
    listing_status: str | None = Field(default=None, pattern="^(for_sale|sold|pending|coming_soon|active)$")
    sale_price: float = Field(gt=0)
    sale_date: str
    verification_status: str | None = Field(
        default=None,
        pattern="^(manual|broker_verified|public_record|estimated)$",
    )
    source_name: str | None = None
    source_quality: str | None = None
    source_ref: str | None = None
    source_notes: str | None = None
    reviewed_at: str | None = None
    comp_status: str | None = Field(default=None, pattern="^(seeded|reviewed|approved)$")
    address_verification_status: str | None = Field(default=None, pattern="^(verified|questioned|unverified)$")
    sale_verification_status: str | None = Field(
        default=None,
        pattern="^(seeded|public_record_matched|public_record_verified|mls_verified|questioned)$",
    )
    verification_source_type: str | None = Field(default=None, pattern="^(manual_review|public_record|mls|broker_review)$")
    verification_source_name: str | None = None
    verification_source_id: str | None = None
    last_verified_by: str | None = None
    last_verified_at: str | None = None
    verification_notes: str | None = None
    beds: int | None = Field(default=None, ge=0)
    baths: float | None = Field(default=None, ge=0)
    sqft: int | None = Field(default=None, ge=0)
    lot_size: float | None = Field(default=None, ge=0)
    latitude: float | None = Field(default=None, validation_alias=AliasChoices("latitude", "lat"))
    longitude: float | None = Field(default=None, validation_alias=AliasChoices("longitude", "lon", "lng"))
    days_on_market: int | None = Field(default=None, ge=0)
    distance_to_subject_miles: float | None = Field(default=None, ge=0)
    year_built: int | None = Field(default=None, ge=1800, le=2200)
    stories: float | None = Field(default=None, ge=0)
    garage_spaces: int | None = Field(default=None, ge=0)
    location_tags: list[str] = Field(default_factory=list)
    micro_location_notes: list[str] = Field(default_factory=list)
    canonical_address: str | None = None
    quality_status: str | None = Field(default=None, pattern="^(accepted|accepted_with_warnings|needs_review|rejected)$")
    quality_issues: list[str] = Field(default_factory=list)
    quality_score: float | None = Field(default=None, ge=0, le=1)
    source_provenance: dict[str, object] = Field(default_factory=dict)


class ComparableSalesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    town: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)
    property_type: str | None = None
    architectural_style: str | None = None
    condition_profile: str | None = Field(default=None, pattern="^(renovated|updated|maintained|dated|needs_work)$")
    capex_lane: str | None = Field(default=None, pattern="^(light|moderate|heavy)$")
    beds: int | None = Field(default=None, ge=0)
    baths: float | None = Field(default=None, ge=0)
    sqft: int | None = Field(default=None, ge=0)
    lot_size: float | None = Field(default=None, ge=0)
    year_built: int | None = Field(default=None, ge=1800, le=2200)
    stories: float | None = Field(default=None, ge=0)
    garage_spaces: int | None = Field(default=None, ge=0)
    latitude: float | None = None
    longitude: float | None = None
    listing_description: str | None = None
    market_value_today: float | None = Field(default=None, gt=0)
    market_history_points: list[dict[str, object]] = Field(default_factory=list)
    manual_sales: list[dict[str, object]] = Field(default_factory=list)
    manual_comp_only: bool = False
    has_accessory_unit: bool = False
    adu_type: str | None = None
    days_on_market: int | None = Field(default=None, ge=0)
    listing_price: float | None = Field(default=None, gt=0)
    subject_is_nonstandard: bool = False

    # Multi-unit decomposition fields — set by ComparableSalesModule when
    # the subject has additional rental units (ADU, back house, etc.) so
    # the agent comps the *primary dwelling* and values extra units via
    # income capitalization.
    is_hybrid_valuation: bool = False
    primary_dwelling_beds: int | None = Field(default=None, ge=0)
    primary_dwelling_baths: float | None = Field(default=None, ge=0)
    primary_dwelling_sqft: int | None = Field(default=None, ge=0)
    additional_unit_annual_income: float | None = Field(default=None, ge=0)
    additional_unit_cap_rate: float | None = Field(default=None, gt=0, lt=0.20)
    additional_unit_count: int | None = Field(default=None, ge=0)


class AdjustedComparable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str
    property_type: str | None = None
    sale_date: str
    source_name: str | None = None
    source_quality: str | None = None
    source_ref: str | None = None
    reviewed_at: str | None = None
    comp_status: str | None = None
    capex_lane: str | None = None
    address_verification_status: str | None = None
    sale_verification_status: str | None = None
    verification_source_type: str | None = None
    verification_source_name: str | None = None
    verification_source_id: str | None = None
    last_verified_by: str | None = None
    last_verified_at: str | None = None
    verification_notes: str | None = None
    sale_price: float
    time_adjusted_price: float
    adjusted_price: float
    comp_confidence_weight: float = Field(ge=0, le=1)
    similarity_score: float = Field(ge=0, le=1)
    fit_label: str = Field(pattern="^(strong|usable|stretch)$")
    bedrooms: int | None = Field(default=None, ge=0)
    bathrooms: float | None = Field(default=None, ge=0)
    sqft: int | None = Field(default=None, ge=0)
    lot_size: float | None = Field(default=None, ge=0)
    distance_to_subject_miles: float | None = Field(default=None, ge=0)
    year_built: int | None = Field(default=None, ge=1800, le=2200)
    stories: float | None = Field(default=None, ge=0)
    garage_spaces: int | None = Field(default=None, ge=0)
    sale_age_days: int = Field(ge=0)
    time_adjustment_pct: float
    subject_adjustment_pct: float
    why_comp: list[str]
    cautions: list[str]
    adjustments_summary: list[str]
    segmentation_bucket: str | None = None
    proximity_score: float | None = Field(default=None, ge=0, le=1)
    recency_score: float | None = Field(default=None, ge=0, le=1)
    data_quality_score: float | None = Field(default=None, ge=0, le=1)
    weighted_score: float | None = Field(default=None, ge=0, le=1)
    base_similarity_score: float | None = Field(default=None, ge=0, le=1)
    base_selection_tier: str | None = None
    source_summary: str | None = None
    location_tags: list[str] = Field(default_factory=list)
    condition_profile: str | None = None
    micro_location_notes: list[str] = Field(default_factory=list)


class ComparableSalesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comparable_value: float | None
    comp_count: int
    confidence: float = Field(ge=0, le=1)
    comps_used: list[AdjustedComparable]
    rejected_count: int = 0
    rejection_reasons: dict[str, int] = Field(default_factory=dict)
    freshest_sale_date: str | None = None
    median_sale_age_days: int | None = None
    dataset_name: str | None = None
    dataset_as_of: str | None = None
    base_comp_selection: BaseCompSelection | None = None
    curation_summary: str | None = None
    verification_summary: str | None = None
    direct_value_range: ComparableValueRange | None = None
    income_adjusted_value_range: ComparableValueRange | None = None
    location_adjustment_range: ComparableValueRange | None = None
    lot_adjustment_range: ComparableValueRange | None = None
    blended_value_range: ComparableValueRange | None = None
    comp_confidence_score: float | None = Field(default=None, ge=0, le=1)
    comp_analysis: ComparableCompAnalysis | None = None
    # Hybrid valuation fields for multi-unit properties
    is_hybrid_valuation: bool = False
    primary_dwelling_value: float | None = None
    additional_unit_income_value: float | None = None
    additional_unit_count: int | None = None
    additional_unit_annual_income: float | None = None
    additional_unit_cap_rate: float | None = None
    hybrid_valuation_note: str | None = None
    assumptions: list[str]
    unsupported_claims: list[str]
    warnings: list[str]
    summary: str


class ActiveListingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    address: str
    town: str
    state: str
    list_price: float = Field(gt=0)
    listing_status: str = Field(pattern="^(for_sale|pending|coming_soon|active)$")
    property_type: str | None = None
    architectural_style: str | None = None
    condition_profile: str | None = Field(default=None, pattern="^(renovated|updated|maintained|dated|needs_work)$")
    capex_lane: str | None = Field(default=None, pattern="^(light|moderate|heavy)$")
    source_name: str | None = None
    source_ref: str | None = None
    source_notes: str | None = None
    days_on_market: int | None = Field(default=None, ge=0)
    beds: int | None = Field(default=None, ge=0)
    baths: float | None = Field(default=None, ge=0)
    sqft: int | None = Field(default=None, ge=0)
    lot_size: float | None = Field(default=None, ge=0)
    year_built: int | None = Field(default=None, ge=1800, le=2200)
    garage_spaces: int | None = Field(default=None, ge=0)
    latitude: float | None = Field(default=None, validation_alias=AliasChoices("latitude", "lat"))
    longitude: float | None = Field(default=None, validation_alias=AliasChoices("longitude", "lon", "lng"))
    notes: str | None = None
    canonical_address: str | None = None
    quality_status: str | None = Field(default=None, pattern="^(accepted|accepted_with_warnings|needs_review|rejected)$")
    quality_issues: list[str] = Field(default_factory=list)
    quality_score: float | None = Field(default=None, ge=0, le=1)
    source_provenance: dict[str, object] = Field(default_factory=dict)
