// Mirror of api/events.py — keep these in sync.

export type TextDeltaEvent = { type: "text_delta"; content: string };
export type ToolCallEvent = { type: "tool_call"; name: string; args: Record<string, unknown> };
export type ToolResultEvent = { type: "tool_result"; name: string; data: Record<string, unknown> };
export type ListingsEvent = { type: "listings"; items: Listing[] };
export type MapEvent = { type: "map"; center: [number, number]; pins: MapPin[] };
export type SuggestionsEvent = { type: "suggestions"; items: string[] };
export type ConversationEvent = { type: "conversation"; id: string; title: string };
export type MessageEvent = { type: "message"; id: string; role: "user" | "assistant" };
export type DoneEvent = { type: "done" };
export type ErrorEvent = { type: "error"; message: string };
export type ChartEvent = {
  type: "chart";
  url?: string | null;  // path under /artifacts/, served by FastAPI StaticFiles
  title?: string | null;
  kind?: string | null; // e.g. "value_opportunity", "scenario_fan", "radar_score"
  spec?: ChartSpec | null;
  provenance?: string[] | null;
  supports_claim?: string | null;
  why_this_chart?: string | null;
  advisor?: {
    title?: string | null;
    summary?: string | null;
    companion?: string | null;
    preferred_surface?: string | null;
  } | null;
};
export type ScenarioFanChartSpec = {
  kind: "scenario_fan";
  ask_price?: number | null;
  basis_label?: string | null;
  bull_case_value?: number | null;
  base_case_value?: number | null;
  bear_case_value?: number | null;
  stress_case_value?: number | null;
};
export type CmaPositioningChartSpec = {
  kind: "cma_positioning";
  subject_address?: string | null;
  subject_ask?: number | null;
  fair_value_base?: number | null;
  value_low?: number | null;
  value_high?: number | null;
  comps: Array<{
    address?: string | null;
    ask_price?: number | null;
    source_label?: string | null;
    selected_by?: string | null;
    feeds_fair_value?: boolean | null;
  }>;
};
export type RiskBarChartSpec = {
  kind: "risk_bar";
  ask_price?: number | null;
  bear_value?: number | null;
  stress_value?: number | null;
  // AUDIT 1.4.3: unit + source tags for the bar values. `value_unit` tells the
  // frontend `value` is a share of total penalty in [0, 1]. `value_source` flags
  // whether the per-flag split was computed from a real `total_penalty` or
  // collapsed to a fallback default (every bar identical — low signal).
  value_unit?: "penalty_share";
  value_source?: "computed" | "fallback";
  items: Array<{
    label: string;
    value: number;
    tone: "risk" | "trust";
  }>;
};
export type RentBurnChartSpec = {
  kind: "rent_burn";
  title?: string | null;
  working_label?: string | null;
  market_label?: string | null;
  market_context_note?: string | null;
  market_rent?: number | null;
  market_rent_low?: number | null;
  market_rent_high?: number | null;
  points: Array<{
    year: number;
    rent_base?: number | null;
    rent_bull?: number | null;
    rent_bear?: number | null;
    monthly_obligation?: number | null;
  }>;
};
export type RentRampChartSpec = {
  kind: "rent_ramp";
  title?: string | null;
  current_rent?: number | null;
  monthly_obligation?: number | null;
  today_cash_flow?: number | null;
  break_even_years?: Record<string, number | null>;
  points: Array<{
    year: number;
    net_0?: number | null;
    net_3?: number | null;
    net_5?: number | null;
  }>;
};
export type ValueOpportunityChartSpec = {
  kind: "value_opportunity";
  ask_price?: number | null;
  fair_value_base?: number | null;
  premium_discount_pct?: number | null;
  value_drivers?: string[];
};
export type HorizontalBarWithRangesScenario = {
  id: string;
  label: string;
  low: number;
  high: number;
  median: number;
  is_subject?: boolean | null;
  flag?: "value_opportunity" | "caution" | "none" | null;
  flag_reason?: string | null;
  sample_size?: number | null;
};
export type HorizontalBarWithRangesChartSpec = {
  kind: "horizontal_bar_with_ranges";
  unit?: string | null;
  scenarios: HorizontalBarWithRangesScenario[];
  emphasis_scenario_id?: string | null;
};
export type ChartSpec =
  | ScenarioFanChartSpec
  | CmaPositioningChartSpec
  | RiskBarChartSpec
  | RentBurnChartSpec
  | RentRampChartSpec
  | ValueOpportunityChartSpec
  | HorizontalBarWithRangesChartSpec;
export type VerdictTrustSummary = {
  confidence?: number | null;
  band?: string | null;
  field_completeness?: number | null;
  estimated_reliance?: number | null;
  contradiction_count?: number | null;
  blocked_thesis_warnings?: string[];
  trust_flags?: string[];
  why_this_stance?: string[];
  what_changes_my_view?: string[];
};
export type VerdictEvent = {
  type: "verdict";
  address?: string | null;
  town?: string | null;
  state?: string | null;
  stance?: string | null;          // "buy", "buy_if_price_improves", "pass_unless_changes", ...
  primary_value_source?: string | null;
  ask_price?: number | null;
  all_in_basis?: number | null;
  fair_value_base?: number | null;
  value_low?: number | null;
  value_high?: number | null;
  ask_premium_pct?: number | null; // fraction (0.10 = +10%)
  basis_premium_pct?: number | null;
  trust_flags: string[];
  what_must_be_true: string[];
  key_risks: string[];
  // F10: surface the full decision view the backend already projects.
  trust_summary?: VerdictTrustSummary | null;
  why_this_stance?: string[];
  what_changes_my_view?: string[];
  contradiction_count?: number | null;
  blocked_thesis_warnings?: string[];
  lead_reason?: string | null;
  evidence_items?: string[];
  next_step_teaser?: string | null;
  overrides_applied: Record<string, unknown>;
};

export type ScenarioRow = {
  scenario: string;              // "Bull" | "Base" | "Bear" | "Stress"
  value: number | null;
  delta_pct: number | null;      // fraction vs ask
  growth_rate: number | null;    // fraction (annualized)
  adjustment_pct: number | null; // fraction (total adjustment)
};
export type ScenarioTableEvent = {
  type: "scenario_table";
  address?: string | null;
  ask_price?: number | null;
  basis_label?: string | null;
  spread?: number | null;
  // AUDIT 1.4.4: bull-minus-bear dollar gap. `spread_unit` is emitted as a
  // literal so the UI never has to infer whether this field is currency or
  // percentage — other modules carry a `spread_pct` that must not be mixed
  // into this event.
  spread_unit?: "dollars";
  rows: ScenarioRow[];
};

export type ComparisonRow = {
  property_id: string;
  address?: string | null;
  town?: string | null;
  state?: string | null;
  stance?: string | null;
  primary_value_source?: string | null;
  premium_pct?: number | null;
  ask_price?: number | null;
  fair_value_base?: number | null;
  beds?: number | null;
  baths?: number | null;
  sqft?: number | null;
  trust_flags?: string[];
  error?: string;
};
export type ComparisonTableEvent = {
  type: "comparison_table";
  properties: ComparisonRow[];
};

export type TownSignalItem = {
  id: string;
  bucket: "bullish" | "bearish" | "watch";
  title: string;
  status: string;
  display_line: string;
  project_summary: string;
  signal_type: string;
  location_label?: string | null;
  development_lat?: number | null;
  development_lng?: number | null;
  confidence?: number | null;
  facts: string[];
  inference?: string | null;
  evidence_excerpt: string;
  source_document_id: string;
  source_title?: string | null;
  source_type: string;
  source_url?: string | null;
  source_date?: string | null;
};

export type TownSummaryEvent = {
  type: "town_summary";
  town: string;
  state?: string | null;
  median_price?: number | null;
  median_ppsf?: number | null;
  sold_count?: number | null;
  confidence_raw?: number | null;     // 0-1
  confidence_tier?: "strong" | "moderate" | "thin" | null;
  doc_count?: number | null;
  bullish_signals: string[];
  bearish_signals: string[];
  signal_items?: TownSignalItem[];
};

export type CompsPreviewRow = {
  property_id?: string | null;
  address?: string | null;
  beds?: number | null;
  baths?: number | null;
  sqft?: number | null;
  price?: number | null;
  premium_pct?: number | null; // comp price vs subject ask (fraction)
};
export type CompsPreviewEvent = {
  type: "comps_preview";
  subject_pid?: string | null;
  subject_ask?: number | null;
  count: number;
  median_price?: number | null;
  comps: CompsPreviewRow[];
};

export type RiskProfileEvent = {
  type: "risk_profile";
  address?: string | null;
  town?: string | null;
  state?: string | null;
  ask_price?: number | null;
  bear_value?: number | null;
  stress_value?: number | null;
  risk_flags: string[];
  trust_flags: string[];
  key_risks: string[];
  total_penalty?: number | null;
  confidence_tier?: "strong" | "moderate" | "thin" | null;
};

export type ValueThesisCompRow = {
  property_id?: string | null;
  address?: string | null;
  beds?: number | null;
  baths?: number | null;
  ask_price?: number | null;
  blocks_to_beach?: number | null;
  source_label?: string | null;
  source_summary?: string | null;
  inclusion_reason?: string | null;
  selected_by?: string | null;
  feeds_fair_value?: boolean | null;
};
export type HiddenUpsideItem = {
  kind: string;
  source_module: string;
  label: string;
  magnitude_usd?: number | null;
  magnitude_pct?: number | null;
  confidence?: number | null;
  rationale?: string | null;
};
export type OptionalitySignal = {
  primary_source?: string | null;
  hidden_upside_items: HiddenUpsideItem[];
  summary?: string | null;
};
export type ValueThesisEvent = {
  type: "value_thesis";
  address?: string | null;
  town?: string | null;
  state?: string | null;
  ask_price?: number | null;
  fair_value_base?: number | null;
  premium_discount_pct?: number | null;
  pricing_view?: string | null;
  primary_value_source?: string | null;
  value_drivers: string[];
  key_value_drivers: string[];
  what_must_be_true: string[];
  why_this_stance?: string[];
  what_changes_my_view?: string[];
  trust_summary?: TrustSummaryEvent | null;
  contradiction_count?: number | null;
  blocked_thesis_warnings?: string[];
  comp_selection_summary?: string | null;
  comps: ValueThesisCompRow[];
  net_opportunity_delta_pct?: number | null;
  risk_adjusted_fair_value?: number | null;
  required_discount?: number | null;
  // F5: hidden upside levers surfaced as a first-class signal.
  optionality_signal?: OptionalitySignal | null;
};

/**
 * F2: comps that actually fed the fair value computation. Sourced from the
 * valuation module's ``comparable_sales.comps_used`` — never live market.
 * The ``source`` discriminator is stamped server-side so TS can narrow on it
 * even though ``CmaTableEvent`` no longer exists.
 */
export type ValuationCompsEvent = {
  type: "valuation_comps";
  source: "valuation_module";
  address?: string | null;
  town?: string | null;
  state?: string | null;
  summary?: string | null;
  rows: ValueThesisCompRow[];
};

/**
 * F2: live market comps for context, NOT fair-value evidence. Sourced from
 * ``get_cma()`` which prefers live Zillow listings with a saved-comp fallback.
 */
export type MarketSupportCompsEvent = {
  type: "market_support_comps";
  source: "live_market";
  address?: string | null;
  town?: string | null;
  state?: string | null;
  summary?: string | null;
  rows: ValueThesisCompRow[];
};

export type StrategyPathEvent = {
  type: "strategy_path";
  address?: string | null;
  town?: string | null;
  state?: string | null;
  best_path?: string | null;
  recommendation?: string | null;
  pricing_view?: string | null;
  primary_value_source?: string | null;
  rental_ease_label?: string | null;
  rental_ease_score?: number | null;
  rent_support_score?: number | null;
  liquidity_score?: number | null;
  monthly_cash_flow?: number | null;
  cash_on_cash_return?: number | null;
  annual_noi?: number | null;
};

export type RentOutlookEvent = {
  type: "rent_outlook";
  address?: string | null;
  town?: string | null;
  state?: string | null;
  entry_basis?: number | null;
  monthly_rent?: number | null;
  effective_monthly_rent?: number | null;
  rent_source_type?: string | null;
  rental_ease_label?: string | null;
  rental_ease_score?: number | null;
  annual_noi?: number | null;
  horizon_years?: number | null;
  future_rent_low?: number | null;
  future_rent_mid?: number | null;
  future_rent_high?: number | null;
  zillow_market_rent?: number | null;
  zillow_rental_comp_count?: number | null;
  market_context_note?: string | null;
  basis_to_rent_framing?: string | null;
  owner_occupy_then_rent?: string | null;
  carry_offset_ratio?: number | null;
  break_even_rent?: number | null;
  break_even_probability?: number | null;
  adjusted_rent_confidence?: number | null;
  rent_haircut_pct?: number | null;
};

export type TrustSummaryEvent = {
  type: "trust_summary";
  confidence?: number | null;
  band?: string | null;
  field_completeness?: number | null;
  estimated_reliance?: number | null;
  contradiction_count?: number | null;
  blocked_thesis_warnings: string[];
  trust_flags: string[];
  why_this_stance?: string[];
  what_changes_my_view?: string[];
};

export type PartialDataWarningEvent = {
  type: "partial_data_warning";
  section: string;              // e.g. "town_summary", "cma_preview", "session_load"
  reason: string;               // short human-readable cause
  verdict_reliable: boolean;    // true if the core decision still stands
};

export type ResearchUpdateEvent = {
  type: "research_update";
  town: string;
  state: string;
  confidence_label?: string | null;
  narrative_summary?: string | null;
  bullish_signals: string[];
  bearish_signals: string[];
  watch_items: string[];
  signal_items?: TownSignalItem[];
  document_count?: number | null;
  warnings: string[];
};

export type ModuleAttribution = {
  module: string;             // canonical id, e.g. "valuation_model"
  label: string;              // human label, e.g. "Valuation Model"
  contributed_to: string[];   // event types this module supplied data to
};
export type ModulesRanEvent = {
  type: "modules_ran";
  items: ModuleAttribution[];
};

export type VerifierViolation = {
  kind: "ungrounded_number" | "ungrounded_entity" | "forbidden_hedge";
  sentence: string;
  value: string;
  reason: string;
};
export type GroundingAnchor = {
  module: string;
  field: string;
  value: string;
};
export type CriticNumericCheck = {
  ok: boolean;
  missing: string[];
};
export type CriticTelemetry = {
  enabled: boolean;
  mode: "off" | "shadow" | "on";
  ran: boolean;
  original_draft?: string;
  verdict?: "keep" | "revise" | "flag_only";
  notes?: string;
  rewritten_text?: string;
  applied_rewrite?: boolean;
  numeric_check?: CriticNumericCheck;
};
export type VerifierReportEvent = {
  type: "verifier_report";
  tier?: string | null;
  sentences_total: number;
  sentences_with_violations: number;
  ungrounded_declaration: boolean;
  anchor_count: number;
  anchors?: GroundingAnchor[];
  violations: VerifierViolation[];
  critic?: CriticTelemetry;
};
export type GroundingAnnotationsEvent = {
  type: "grounding_annotations";
  anchors: GroundingAnchor[];
  ungrounded_declaration: boolean;
};

export type ChatEvent =
  | TextDeltaEvent
  | ToolCallEvent
  | ToolResultEvent
  | ListingsEvent
  | MapEvent
  | SuggestionsEvent
  | ConversationEvent
  | MessageEvent
  | DoneEvent
  | ErrorEvent
  | ChartEvent
  | VerdictEvent
  | ScenarioTableEvent
  | ComparisonTableEvent
  | TownSummaryEvent
  | CompsPreviewEvent
  | RiskProfileEvent
  | ValueThesisEvent
  | ValuationCompsEvent
  | MarketSupportCompsEvent
  | StrategyPathEvent
  | RentOutlookEvent
  | TrustSummaryEvent
  | PartialDataWarningEvent
  | ResearchUpdateEvent
  | ModulesRanEvent
  | VerifierReportEvent
  | GroundingAnnotationsEvent;

// Structured payloads.

export type ListingStatus = "active" | "pending" | "contingent" | "sold";

export type Listing = {
  id: string;
  address_line: string;        // "123 Ocean Ave"
  city: string;
  state: string;               // 2-letter
  zip?: string;
  price: number;
  beds: number;
  baths: number;
  sqft: number;
  lot_sqft?: number;
  year_built?: number;
  status: ListingStatus;
  photo_url?: string;
  streetViewImageUrl?: string;
  source_url?: string;         // Zillow / MLS / etc.
  lat?: number;
  lng?: number;
  // Color hint for the placeholder gradient when no photo is available.
  // Pure cosmetic — the backend can omit this.
  hue?: number;
};

export type MapPin = {
  id: string;
  lat: number;
  lng: number;
  label?: string;
};
