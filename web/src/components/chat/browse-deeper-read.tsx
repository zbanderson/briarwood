"use client";

import { BrowseSection } from "./browse-section";

// Phase 4c Cycle 1 — Section C ("THE DEEPER READ") placeholder.
//
// Cycle 1 renders the section sub-head + a one-line placeholder so the
// gate is visible end-to-end and the layout target is recognizable from
// the first browser smoke. Cycles 2-4 replace the placeholder with the
// chevron-list drilldown stack:
//
// - Cycle 3: Comps / Value thesis / Projection drilldowns
// - Cycle 4: Rent / Town / Risk / Confidence / Recommended path drilldowns
//
// The drilldown primitive (chevron + label + summary chip on a 1px rule;
// independent open state per row) lands in Cycle 3.

export function BrowseDeeperRead() {
  return (
    <BrowseSection label="The Deeper Read" ariaLabel="The Deeper Read">
      <div className="text-[13px] italic leading-snug text-[var(--color-text-faint)]">
        Drilldowns coming in Cycles 2&ndash;4.
      </div>
    </BrowseSection>
  );
}
