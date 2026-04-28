// Phase 4b Cycle 3 — category → drill-in mapping for Scout Finds cards.
//
// Per Open Design Decision #4: drilldowns are limited to existing module
// drill-in routes only for v1. Each category maps to a follow-up prompt
// that, when fired into the chat, routes through the existing AnswerType
// classifier and lands on the relevant module's drill-in surface (the
// same UX the inline "Drill into rent" / "Drill into comps" buttons
// already produce). Ad-hoc deep links are deferred until Cycle 6+
// telemetry shows whether anchor-level precision matters.
//
// New categories (the LLM scout is permitted to invent them) fall back
// to a generic "tell me more about this angle" prompt — at minimum the
// user gets a follow-up turn without a 404.

export type ScoutDrillIn = {
  /** Follow-up prompt sent into the chat when the user clicks Drill in. */
  prompt: string;
  /** Button label shown to the user. */
  label: string;
};

const ROUTES: Record<string, ScoutDrillIn> = {
  rent_angle: {
    prompt: "What rent would make this deal work?",
    label: "Drill into rent",
  },
  town_trend: {
    prompt: "What's driving the town outlook?",
    label: "Drill into town context",
  },
  adu_signal: {
    prompt: "What's the accessory-unit angle here?",
    label: "Drill into ADU signal",
  },
  comp_anomaly: {
    prompt: "Why were these comps chosen?",
    label: "Drill into comps",
  },
  carry_yield_mismatch: {
    prompt: "How does the carry math work at this rent?",
    label: "Drill into carry math",
  },
  optionality: {
    prompt: "What hidden upside should I underwrite?",
    label: "Drill into optionality",
  },
};

const FALLBACK: ScoutDrillIn = {
  prompt: "Tell me more about this angle.",
  label: "Drill in",
};

/** Resolve the drill-in for a category. Unknown / null categories fall
 *  back to a generic follow-up prompt rather than a no-op. */
export function drillInForCategory(category: string | null | undefined): ScoutDrillIn {
  if (!category) return FALLBACK;
  return ROUTES[category] ?? FALLBACK;
}

/** Categories with explicit drill-ins. Useful for tests and for the
 *  category-badge formatter (so unknown categories can be styled
 *  differently if we choose to). */
export function knownScoutCategories(): readonly string[] {
  return Object.freeze(Object.keys(ROUTES));
}

/** Public copy of the fallback drill-in, exported for tests. */
export const SCOUT_FALLBACK_DRILL_IN: ScoutDrillIn = FALLBACK;
