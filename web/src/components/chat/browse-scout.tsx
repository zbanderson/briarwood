"use client";

import type { ScoutInsightItem } from "@/lib/chat/events";
import { cn } from "@/lib/cn";
import { ScoutFindCard } from "./scout-finds";

// Phase 4c Cycle 2 — Section B ("What did Scout dig up?").
//
// Scout is Briarwood's apex differentiator (per project_scout_apex.md);
// Section B's job is to make that legible at a glance without breaking the
// rebuild's "no nested boxed cards" discipline. The treatment lands
// intentionally between "tone-only" and "distinctive frame" on the
// Cycle-2 spectrum: warm-amber top + left rules form a magazine-sidebar
// L-bracket (not a four-sided card), a faint warm tonal background
// distinguishes the section from A and C, and a small sparkle glyph next
// to the sentence-case sub-head signals discovery without going cute.
// Cards inside keep their own chrome — they ARE the value units.
//
// Empty state still renders the section so the user always sees that
// Scout is part of the surface; the body collapses to a single italic
// teaser line ("Scout was quiet on this one.") rather than vanishing.
// This is deliberate — Scout being the selling feature outweighs the
// strict "honest UI hides empty sections" rule for this one slot.

type Props = {
  insights: ScoutInsightItem[];
  onPrompt?: (prompt: string) => void;
};

export function BrowseScout({ insights, onPrompt }: Props) {
  const items = (insights ?? []).slice(0, 2);
  const isEmpty = items.length === 0;

  return (
    <section
      aria-label="What did Scout dig up?"
      className={cn(
        // Section spacing matches BrowseSection so A → B → C share rhythm.
        "mt-6 pt-5 pb-5",
        // Magazine-sidebar L-bracket: warm top + left rules, no right or
        // bottom rule. Left rule sits flush against the bubble's content
        // edge; the warm tonal background extends to the bubble's right
        // edge so the section reads as a pull-quote, not a stacked card.
        "border-t-2 border-t-amber-500/35",
        "border-l-2 border-l-amber-500/35",
        "bg-amber-500/[0.04]",
        // Inset content from the warm left rule. Right padding keeps
        // text from kissing the bubble edge.
        "pl-5 pr-4",
      )}
    >
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-center gap-2">
          <SparkleGlyph />
          <h3 className="text-[15px] font-semibold leading-snug text-[var(--color-text)]">
            What did Scout dig up?
          </h3>
        </div>
        <div className="text-[11px] text-[var(--color-text-faint)]">
          Angles you didn&rsquo;t ask about
        </div>
      </div>

      <div className="mt-3">
        {isEmpty ? (
          <p className="text-[13px] italic leading-snug text-[var(--color-text-faint)]">
            Scout was quiet on this one.
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            {items.map((insight, idx) => (
              <ScoutFindCard
                key={`${insight.category ?? "uncat"}-${idx}`}
                insight={insight}
                onPrompt={onPrompt}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function SparkleGlyph() {
  // Inline SVG so we don't depend on an icon library or font glyph for the
  // section's defining visual signature. Four-pointed sparkle / spark in
  // amber — reads as discovery without the literalism of a paw print or
  // magnifying glass.
  return (
    <svg
      aria-hidden="true"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="currentColor"
      className="shrink-0 text-amber-400/90"
    >
      <path d="M12 1 L13.5 10.5 L23 12 L13.5 13.5 L12 23 L10.5 13.5 L1 12 L10.5 10.5 Z" />
    </svg>
  );
}
