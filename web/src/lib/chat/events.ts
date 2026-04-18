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
  url: string;          // path under /artifacts/, served by FastAPI StaticFiles
  title?: string | null;
  kind?: string | null; // e.g. "value_opportunity", "scenario_fan", "radar_score"
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
  spread?: number | null;
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
  | CompsPreviewEvent;

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
