"use client";

import { cn } from "@/lib/cn";
import type { ScoutInsightItem } from "@/lib/chat/events";
import { drillInForCategory } from "@/lib/chat/scout-routes";

// Phase 4b Cycle 3 — dedicated drilldown surface for Scout Finds.
//
// Renders 1-2 insight cards under the synthesizer prose and above the
// rest of the BROWSE card stack. The synthesizer's `## What's
// Interesting` beat already weaves the highest-confidence insight into
// prose; this surface carries the rest of the cap-2 set so the user
// can drill in without re-asking. Each card has a category badge,
// the headline, a one-line reason, and a "Drill in →" button that
// fires a category-keyed follow-up prompt back into the chat.
//
// Empty state renders nothing (no "no insights found" placeholder) —
// see SCOUT_HANDOFF_PLAN.md Cycle 3.
//
// Section name `ScoutFinds` per memory `project_brand_evolution.md`:
// brand split puts user-facing copy under the Scout / Finds vocabulary;
// internal symbols (Python module paths, SSE event types) stay
// Briarwood-namespaced. The component name is a placeholder — the
// owner expects to revisit when the product brand finalizes.

type Props = {
  insights: ScoutInsightItem[];
  onPrompt?: (prompt: string) => void;
};

export function ScoutFinds({ insights, onPrompt }: Props) {
  if (!insights || insights.length === 0) return null;

  // Defensive cap to 2 even if the SSE event delivers more — the cap-2
  // policy lives in the LLM scout itself but the UI guards against
  // surface drift.
  const items = insights.slice(0, 2);

  return (
    <section
      aria-label="Scout Finds"
      className={cn(
        "mt-4 rounded-2xl border border-[var(--color-border-subtle)]",
        "bg-[var(--color-surface)] p-4",
      )}
    >
      <div className="flex items-baseline justify-between gap-3">
        <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
          Scout Finds
        </div>
        <div className="text-[11px] text-[var(--color-text-faint)]">
          Angles you didn&rsquo;t ask about
        </div>
      </div>
      <div className="mt-3 flex flex-col gap-3">
        {items.map((insight, idx) => (
          <ScoutFindCard
            key={`${insight.category ?? "uncat"}-${idx}`}
            insight={insight}
            onPrompt={onPrompt}
          />
        ))}
      </div>
    </section>
  );
}

export function ScoutFindCard({
  insight,
  onPrompt,
}: {
  insight: ScoutInsightItem;
  onPrompt?: (prompt: string) => void;
}) {
  const drillIn = drillInForCategory(insight.category);
  const confidencePct =
    insight.confidence != null && Number.isFinite(insight.confidence)
      ? `${Math.round(insight.confidence * 100)}%`
      : null;

  return (
    <div
      className={cn(
        "rounded-xl border border-[var(--color-border-subtle)]",
        "bg-[var(--color-bg-sunken)] p-3",
      )}
    >
      <div className="flex items-center gap-2">
        {insight.category && (
          <span
            className={cn(
              "shrink-0 rounded-full border border-[var(--color-border-subtle)]",
              "bg-[var(--color-surface)] px-2 py-0.5",
              "text-[10px] font-medium uppercase tracking-wider",
              "text-[var(--color-text-muted)]",
            )}
          >
            {formatCategory(insight.category)}
          </span>
        )}
        {confidencePct && (
          <span className="text-[10px] text-[var(--color-text-faint)]">
            confidence {confidencePct}
          </span>
        )}
      </div>
      <div className="mt-1.5 text-[14px] font-semibold leading-snug text-[var(--color-text)]">
        {insight.headline}
      </div>
      {insight.reason && (
        <div className="mt-1 text-[13px] leading-snug text-[var(--color-text-muted)]">
          {insight.reason}
        </div>
      )}
      {onPrompt && (
        <div className="mt-2">
          <button
            type="button"
            onClick={() => onPrompt(drillIn.prompt)}
            className={cn(
              "rounded-full border border-[var(--color-border-subtle)] px-3 py-1.5",
              "text-xs text-[var(--color-text-muted)]",
              "hover:text-[var(--color-text)]",
              "hover:border-[var(--color-border)] hover:bg-[var(--color-surface)]",
              "transition-colors",
            )}
          >
            {drillIn.label} →
          </button>
        </div>
      )}
    </div>
  );
}

function formatCategory(category: string): string {
  // "rent_angle" → "Rent angle". Cheap formatter; sufficient for the
  // cap-2 surface. Custom labels can land in a per-category map later.
  return category
    .replace(/_/g, " ")
    .replace(/^\w/, (c) => c.toUpperCase());
}
