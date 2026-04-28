"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

// Phase 4c Cycle 1 — shared Section primitive for the BROWSE three-section
// layout. Provides the newspaper-front-page hierarchy: small-caps section
// label, optional 1px top rule, optional subtitle, content slot. No nested
// boxed-card border around the section itself — that's the visual
// difference between "designed by a newspaper editor" and "designed by an
// LLM."
//
// Used by BrowseRead (Section A — `showRule={false}` since it's first),
// BrowseScout (Section B — conditional null when scout returned empty),
// and BrowseDeeperRead (Section C — drilldown list).

type Props = {
  /** Uppercase section label (e.g. "THE READ", "WHAT YOU'D MISS"). */
  label?: string;
  /** Optional small subtitle next to the label (e.g. Scout's
   * "Angles you didn't ask about"). */
  subtitle?: string;
  /** When false, suppresses the 1px top rule. Set on the first
   * section in the bubble so the rebuild doesn't double up against
   * the bubble's own top edge. Defaults to true. */
  showRule?: boolean;
  /** Optional override on the section's aria-label. Defaults to `label`
   * when present. */
  ariaLabel?: string;
  children: ReactNode;
};

export function BrowseSection({
  label,
  subtitle,
  showRule = true,
  ariaLabel,
  children,
}: Props) {
  return (
    <section
      aria-label={ariaLabel ?? label}
      className={cn(
        "mt-6 pt-6",
        showRule && "border-t border-[var(--color-border-subtle)]",
      )}
    >
      {label && (
        <div className="flex items-baseline justify-between gap-3">
          <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--color-text-faint)]">
            {label}
          </div>
          {subtitle && (
            <div className="text-[11px] text-[var(--color-text-faint)]">
              {subtitle}
            </div>
          )}
        </div>
      )}
      <div className={cn(label && "mt-3")}>{children}</div>
    </section>
  );
}
