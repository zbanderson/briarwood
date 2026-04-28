"use client";

import { cn } from "@/lib/cn";
import type {
  ChartEvent,
  GroundingAnchor,
  ValueThesisEvent,
  VerdictEvent,
} from "@/lib/chat/events";
import { BrowseSection } from "./browse-section";
import { ChartFrame } from "./chart-frame";
import { GroundedText } from "./grounded-text";

// Phase 4c Cycle 1 — Section A ("THE READ").
//
// "Above the fold" content: stance pill + headline (subject line + ask /
// fair value / stance) + masthead `market_trend` chart + flowed
// synthesizer prose. The user should be able to glean the verdict + key
// context within 2-3 seconds of looking at this section.
//
// Absorbs the standalone `VerdictCard` (the stance pill becomes the
// section's lead chip; ask / fair value / value range collapse into a
// one-line headline) and the standalone `GroundedText` (now the section's
// body). The standalone components remain exported for non-BROWSE tiers.

type Props = {
  // BROWSE turns don't emit a `verdict` event today (only DECISION
  // does), but the type is accepted so the same component could host
  // a future BROWSE→verdict promotion. Today the headline anchors on
  // `valueThesis` (which BROWSE emits via session.last_value_thesis_view).
  verdict?: VerdictEvent;
  valueThesis?: ValueThesisEvent;
  charts: ChartEvent[];
  proseContent: string;
  isStreaming?: boolean;
  anchors?: GroundingAnchor[];
  ungroundedDeclaration?: boolean;
};

// Tone map covers the full `DecisionStance` vocabulary plus two legacy
// labels (`buy`, `pass`) so back-compat with any older verdict event holds.
// `conditional` (trust gate) deliberately maps to no tone — the pill falls
// through to the neutral border so the UI doesn't suggest a stance the
// model itself declined to take.
const STANCE_TONE: Record<string, string> = {
  strong_buy: "bg-emerald-500/20 text-emerald-200 border-emerald-500/40",
  buy: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  buy_if_price_improves:
    "bg-amber-500/15 text-amber-200 border-amber-500/30",
  interesting_but_fragile:
    "bg-amber-500/15 text-amber-200 border-amber-500/30",
  execution_dependent:
    "bg-amber-500/15 text-amber-200 border-amber-500/30",
  pass_unless_changes: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  pass: "bg-rose-500/15 text-rose-300 border-rose-500/30",
};

function stanceLabel(s: string | null | undefined): string {
  if (!s) return "Undecided";
  return s
    .split("_")
    .map((w) => (w[0]?.toUpperCase() ?? "") + w.slice(1))
    .join(" ");
}

function compactMoney(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const v = Math.abs(n);
  if (v >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000) return `$${Math.round(n / 1_000)}K`;
  return `$${Math.round(n).toLocaleString()}`;
}

export function BrowseRead({
  verdict,
  valueThesis,
  charts,
  proseContent,
  isStreaming,
  anchors,
  ungroundedDeclaration,
}: Props) {
  // Coalesce headline anchors across the two events that carry them:
  // `valueThesis` is BROWSE's primary surface (session.last_value_thesis_view);
  // `verdict` is DECISION's primary surface. Stance is lifted onto
  // `value_thesis` for BROWSE in Phase 4c Cycle 2, so prefer it; fall back
  // to `verdict` for non-BROWSE callers that still set this component's
  // props from the verdict event.
  const stance = valueThesis?.stance ?? verdict?.stance ?? null;
  const tone = stance ? STANCE_TONE[stance] : undefined;
  const addressParts = [
    valueThesis?.address ?? verdict?.address ?? null,
    valueThesis?.town ?? verdict?.town ?? null,
    valueThesis?.state ?? verdict?.state ?? null,
  ].filter((part): part is string => Boolean(part));
  const subjectLine = addressParts.join(", ");
  const ask = valueThesis?.ask_price ?? verdict?.ask_price ?? null;
  const fair = valueThesis?.fair_value_base ?? verdict?.fair_value_base ?? null;

  // Pick the masthead chart. `market_trend` is the canonical context
  // chart for BROWSE (Phase 3 Cycle B). When absent, the section
  // simply has no masthead — Section A still flows headline → prose.
  const masthead = charts.find((c) => c.kind === "market_trend") ?? null;

  return (
    <BrowseSection label="The Read" showRule={false} ariaLabel="The Read">
      {/* Lead row: stance pill + subject line */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {subjectLine && (
            <div className="truncate text-[13px] text-[var(--color-text-muted)]">
              {subjectLine}
            </div>
          )}
          <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[15px] font-semibold leading-snug text-[var(--color-text)]">
            <span>Ask {compactMoney(ask)}</span>
            <span className="text-[var(--color-text-faint)]">·</span>
            <span>Fair value {compactMoney(fair)}</span>
          </div>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider",
            tone ?? "border-[var(--color-border-subtle)] text-[var(--color-text-muted)]",
          )}
        >
          {stanceLabel(stance)}
        </span>
      </div>

      {/* Masthead chart — market_trend when present */}
      {masthead && <ChartFrame chart={masthead} />}

      {/* Body prose — the synthesizer's full markdown output */}
      {(proseContent || isStreaming) && (
        <div className="mt-4">
          {proseContent ? (
            <GroundedText
              content={proseContent}
              anchors={anchors ?? []}
              muted={ungroundedDeclaration === true}
            />
          ) : (
            // Streaming placeholder — matches the existing dot-pulse so
            // there's no gap before the first text_delta arrives.
            <span
              className="dot-pulse inline-flex items-center gap-1 text-[var(--color-text-faint)]"
              aria-label="Assistant is typing"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-current" />
              <span className="h-1.5 w-1.5 rounded-full bg-current" />
              <span className="h-1.5 w-1.5 rounded-full bg-current" />
            </span>
          )}
        </div>
      )}
    </BrowseSection>
  );
}
