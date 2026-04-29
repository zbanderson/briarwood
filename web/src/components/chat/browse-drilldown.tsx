"use client";

import { useId, useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";

// Phase 4c Cycle 3 — Section C drilldown row primitive ("Civic Ledger" spec).
//
// Closed: chevron + label + summary chip on a 1px top rule. Open: same row +
// expanded body slot. Independent open state per row (multiple may be open).
// Owner-locked: NO four-sided boxed frames around drilldowns; NO mini-cards.
// The row's only frame is the 1px top rule and a `bg-[var(--color-surface)]/40`
// hover plate. Embedded charts and structured cards inside the open body
// render WITHOUT extra borders — the body is the section content, not a
// card-in-a-card.

type Props = {
  /** Sentence-case noun (e.g. "Comps", "Value thesis", "Projection"). */
  label: string;
  /** Right-aligned naked-text summary; expected to be a `<SummaryChip />`
   * but any inline content works. */
  summary?: ReactNode;
  /** Default open state. Owner-locked default = closed. */
  defaultOpen?: boolean;
  /** Fired the first time the user expands any drilldown in the page —
   * lets `BrowseDeeperRead` clear the first-time coach-mark hint. */
  onFirstExpand?: () => void;
  children: ReactNode;
};

export function BrowseDrilldown({
  label,
  summary,
  defaultOpen = false,
  onFirstExpand,
  children,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = useId();

  const handleToggle = () => {
    if (!open) {
      onFirstExpand?.();
    }
    setOpen((v) => !v);
  };

  return (
    <div className="border-t border-[var(--color-border-subtle)] first:border-t-0">
      <button
        type="button"
        onClick={handleToggle}
        aria-expanded={open}
        aria-controls={bodyId}
        className={cn(
          "group flex w-full items-baseline gap-3 py-3.5 px-3 -mx-3",
          "rounded-md transition-colors duration-150",
          "hover:bg-[var(--color-surface)]/40",
          "cursor-pointer text-left",
        )}
      >
        <Chevron open={open} />
        <span className="text-[14px] font-medium tracking-tight text-[var(--color-text)]">
          {label}
        </span>
        {summary && (
          <span className="ml-auto shrink-0 tabular-nums">{summary}</span>
        )}
      </button>
      {open && (
        <div
          id={bodyId}
          className="pl-[26px] mt-4 mb-3"
        >
          {children}
        </div>
      )}
    </div>
  );
}

// Custom 17px chevron — heavier stroke than the default `›` glyph so the
// affordance reads as unmistakably interactive. Idle = `text-muted`,
// hover/open = `text`. Open rotates 90° via Tailwind transform.
function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      aria-hidden="true"
      width="17"
      height="17"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn(
        "shrink-0 self-center transition-transform duration-200 ease-out",
        open
          ? "rotate-90 text-[var(--color-text)]"
          : "text-[var(--color-text-muted)] group-hover:text-[var(--color-text)]",
      )}
    >
      <polyline points="9 6 15 12 9 18" />
    </svg>
  );
}

// Surface 2 — naked-text "Editorial Eyebrow" summary chip. Eyebrow word in
// `text-faint`, figure in `text-muted`, both `text-[11px] uppercase
// tracking-[0.08em] tabular-nums`. No frame. Container queries on Section C
// collapse the long form to a shorter form on narrow bubbles (see
// browse-deeper-read.tsx for the @container wrapper). The collapsed form is
// passed in via the `compact` prop so each chip can pick its own collapse.
//
// Format conventions: compact `$1.31M`, middle dot `·` between metrics, en
// dash `–` for ranges. `tabular-nums` so digits column-align across rows.
export function SummaryChip({
  full,
  compact,
}: {
  full: ReactNode;
  /** Optional compact form rendered when the bubble is below ~480px. When
   * absent, the long form renders at all widths. */
  compact?: ReactNode;
}) {
  return (
    <span className="text-[11px] uppercase tracking-[0.08em] tabular-nums whitespace-nowrap">
      {compact ? (
        <>
          <span className="hidden @[480px]:inline">{full}</span>
          <span className="@[480px]:hidden">{compact}</span>
        </>
      ) : (
        full
      )}
    </span>
  );
}

// Helper components for the chip body — eyebrow and figure split by tone.
// Used inside `<SummaryChip full={...} compact={...} />` for consistency
// across all three Cycle 3 drilldowns.
export function ChipEyebrow({ children }: { children: ReactNode }) {
  return (
    <span className="text-[var(--color-text-faint)]">{children}</span>
  );
}

export function ChipFigure({ children }: { children: ReactNode }) {
  return (
    <span className="text-[var(--color-text-muted)]">{children}</span>
  );
}
