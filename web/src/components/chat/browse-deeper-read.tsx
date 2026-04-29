"use client";

import { useCallback, useSyncExternalStore } from "react";
import { cn } from "@/lib/cn";
import type {
  ChartEvent,
  CmaPositioningChartSpec,
  MarketSupportCompsEvent,
  ScenarioTableEvent,
  ValuationCompsEvent,
  ValueThesisEvent,
} from "@/lib/chat/events";
import { BrowseSection } from "./browse-section";
import {
  BrowseDrilldown,
  ChipEyebrow,
  ChipFigure,
  SummaryChip,
} from "./browse-drilldown";
import { ChartFrame, formatCompSetChip } from "./chart-frame";
import { CompsTableCard } from "./cma-table-card";
import { InlinePrompt } from "./inline-prompt";
import { ScenarioTable } from "./scenario-table";
import { ValueThesisDrilldownBody } from "./value-thesis-drilldown-body";

// Phase 4c Cycle 3 — Section C ("THE DEEPER READ") fully filled. Three
// drilldowns (Comps, Value thesis, Projection) sit on chevron-list rows
// over 1px rules. Each drilldown row has a SummaryChip on the right that
// previews the underlying evidence in one glance ("5 SOLD · 3 ACTIVE",
// "FAIR $1.31M · 5.3% APE", "5Y $1.18M – $1.65M"). Independent open state
// per row; embedded charts and structured cards inside open bodies render
// borderless via the `framed={false}` prop wired in this cycle.
//
// Cycle 4 will add Rent / Town / Risk / Confidence / Recommended-path
// drilldowns inside the same `BrowseDrilldown` primitive.

const HINT_STORAGE_KEY = "briarwood:section-c-hint-seen";

// Phase 4c Cycle 3 — `useSyncExternalStore`-backed hint state.
//
// The first-time coach-mark reads its visibility from `localStorage`. The
// straightforward `useEffect(() => { setShowHint(...) }, [])` pattern was
// flagged by the repo's `react-hooks/set-state-in-effect` ESLint rule (the
// Cycle 2 closeout records the same lint-driven rewrite on FeedbackBar);
// the canonical alternative for "render derives from a browser-only
// store" is `useSyncExternalStore`. Listeners are also notified manually
// from `markHintSeen()` because `localStorage` only fires the `storage`
// event in *other* windows.
const hintListeners = new Set<() => void>();

function readHintShouldShow(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return !window.localStorage.getItem(HINT_STORAGE_KEY);
  } catch {
    return false;
  }
}

function readHintShouldShowServer(): boolean {
  // SSR snapshot — never show the hint on the server. Hydrating client
  // re-reads after mount and pops the hint in if appropriate.
  return false;
}

function subscribeHint(callback: () => void): () => void {
  hintListeners.add(callback);
  if (typeof window !== "undefined") {
    window.addEventListener("storage", callback);
  }
  return () => {
    hintListeners.delete(callback);
    if (typeof window !== "undefined") {
      window.removeEventListener("storage", callback);
    }
  };
}

function markHintSeen() {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(HINT_STORAGE_KEY, "1");
  } catch {
    // localStorage may be unavailable; the hint will keep showing for the
    // session, which is acceptable for the one-shot demo.
  }
  // localStorage's `storage` event only fires in *other* windows. Manually
  // notify subscribers in the same window so the hint dismiss is reactive.
  hintListeners.forEach((listener) => listener());
}

type Props = {
  valueThesis?: ValueThesisEvent;
  valuationComps?: ValuationCompsEvent;
  marketSupportComps?: MarketSupportCompsEvent;
  scenarioTable?: ScenarioTableEvent;
  charts: ChartEvent[];
  onPrompt?: (prompt: string) => void;
};

function compactMoney(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const v = Math.abs(n);
  if (v >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000) return `$${Math.round(n / 1_000)}K`;
  return `$${Math.round(n).toLocaleString()}`;
}

function findChart<K extends ChartEvent["kind"]>(
  charts: ChartEvent[],
  kind: K,
): ChartEvent | null {
  return charts.find((c) => c.kind === kind) ?? null;
}

function isCmaSpec(
  spec: ChartEvent["spec"] | null | undefined,
): spec is CmaPositioningChartSpec {
  return spec != null && spec.kind === "cma_positioning";
}

export function BrowseDeeperRead({
  valueThesis,
  valuationComps,
  marketSupportComps,
  scenarioTable,
  charts,
  onPrompt,
}: Props) {
  const showHint = useSyncExternalStore(
    subscribeHint,
    readHintShouldShow,
    readHintShouldShowServer,
  );
  const dismissHint = useCallback(() => {
    markHintSeen();
  }, []);

  // Comps drilldown — chip counts derive from the cma_positioning chart's
  // spec.comps (same source-of-truth as the chart's MetricChip "Comp set"
  // chip in chart-frame.tsx; cf. formatCompSetChip).
  const cmaChart = findChart(charts, "cma_positioning");
  const cmaSpec = isCmaSpec(cmaChart?.spec) ? cmaChart.spec : null;
  const compsChip = (() => {
    if (!cmaSpec) return null;
    const sold = cmaSpec.comps.filter((c) => c.listing_status === "sold").length;
    const active = cmaSpec.comps.filter(
      (c) => c.listing_status === "active",
    ).length;
    const crossTown = cmaSpec.comps.filter(
      (c) => c.listing_status === "sold" && Boolean(c.is_cross_town),
    ).length;
    const fullText = formatCompSetChip({
      sold,
      active,
      crossTown,
      total: cmaSpec.comps.length,
    });
    const compactText = `${cmaSpec.comps.length} COMPS`;
    return (
      <SummaryChip
        full={<ChipFigure>{fullText}</ChipFigure>}
        compact={<ChipFigure>{compactText}</ChipFigure>}
      />
    );
  })();

  // Value thesis chip — "FAIR $1.31M · 5.3% APE" full / "$1.31M · 5.3%"
  // compact (compress to keep both numbers per owner pick #5).
  const fairValue = valueThesis?.fair_value_base ?? null;
  const premium = valueThesis?.premium_discount_pct ?? null;
  const apePct =
    premium != null && Number.isFinite(premium)
      ? Math.abs(premium * 100)
      : null;
  const valueThesisChip = (() => {
    if (fairValue == null && apePct == null) return null;
    const fairStr = compactMoney(fairValue);
    const apeStr = apePct != null ? `${apePct.toFixed(1)}%` : null;
    const fullParts: React.ReactNode[] = [];
    if (fairValue != null) {
      fullParts.push(<ChipEyebrow key="fair-eyebrow">{"FAIR "}</ChipEyebrow>);
      fullParts.push(<ChipFigure key="fair-fig">{fairStr}</ChipFigure>);
    }
    if (apeStr) {
      if (fullParts.length > 0) {
        fullParts.push(
          <ChipFigure key="dot">{" · "}</ChipFigure>,
        );
      }
      fullParts.push(<ChipFigure key="ape-fig">{apeStr}</ChipFigure>);
      fullParts.push(<ChipEyebrow key="ape-eyebrow">{" APE"}</ChipEyebrow>);
    }
    const compactParts: React.ReactNode[] = [];
    if (fairValue != null) {
      compactParts.push(<ChipFigure key="c-fair">{fairStr}</ChipFigure>);
    }
    if (apeStr) {
      if (compactParts.length > 0) {
        compactParts.push(
          <ChipFigure key="c-dot">{" · "}</ChipFigure>,
        );
      }
      compactParts.push(<ChipFigure key="c-ape">{apeStr}</ChipFigure>);
    }
    return (
      <SummaryChip full={<>{fullParts}</>} compact={<>{compactParts}</>} />
    );
  })();

  // Projection chip — "5Y $1.18M – $1.65M" — bull/bear from scenarioTable.
  const projectionChip = (() => {
    if (!scenarioTable || !scenarioTable.rows || scenarioTable.rows.length === 0) {
      return null;
    }
    const bull = scenarioTable.rows.find((r) => r.scenario === "Bull");
    const bear = scenarioTable.rows.find((r) => r.scenario === "Bear");
    if (
      !bull ||
      !bear ||
      !Number.isFinite(bull.value) ||
      !Number.isFinite(bear.value)
    ) {
      return null;
    }
    const range = `${compactMoney(bear.value)} – ${compactMoney(bull.value)}`;
    return (
      <SummaryChip
        full={
          <>
            <ChipEyebrow>5Y</ChipEyebrow>
            <ChipFigure>{" "}{range}</ChipFigure>
          </>
        }
      />
    );
  })();

  const valueOpportunityChart = findChart(charts, "value_opportunity");
  const scenarioFanChart = findChart(charts, "scenario_fan");

  const hasComps =
    Boolean(cmaSpec) || Boolean(valuationComps) || Boolean(marketSupportComps);
  const hasValueThesis = Boolean(valueThesis);
  const hasProjection = Boolean(scenarioTable);

  // If we have nothing to render in any drilldown, the section still renders
  // its sub-head + a one-line italic note so the user knows where the
  // deeper-read area is. Loud absence is honest UI.
  const anyDrilldownContent = hasComps || hasValueThesis || hasProjection;

  return (
    <BrowseSection label="The Deeper Read" ariaLabel="The Deeper Read">
      <div className="@container">
        {!anyDrilldownContent ? (
          <div className="text-[13px] italic leading-snug text-[var(--color-text-faint)]">
            Drilldowns will fill in once the underlying evidence finishes
            loading.
          </div>
        ) : (
          <>
            {hasComps && (
              <BrowseDrilldown
                label="Comps"
                summary={compsChip}
                onFirstExpand={dismissHint}
              >
                {cmaChart && <ChartFrame chart={cmaChart} framed={false} />}
                {valuationComps && (
                  <CompsTableCard
                    table={valuationComps}
                    variant="valuation"
                    framed={false}
                  />
                )}
                {marketSupportComps && (
                  <CompsTableCard
                    table={marketSupportComps}
                    variant="market_support"
                    framed={false}
                  />
                )}
                {onPrompt && (
                  <InlinePrompt
                    prompt="Why were these comps chosen?"
                    label="Drill into comps"
                    onPick={onPrompt}
                  />
                )}
              </BrowseDrilldown>
            )}
            {hasValueThesis && valueThesis && (
              <BrowseDrilldown
                label="Value thesis"
                summary={valueThesisChip}
                onFirstExpand={dismissHint}
              >
                <ValueThesisDrilldownBody thesis={valueThesis} />
                {valueOpportunityChart && (
                  <ChartFrame chart={valueOpportunityChart} framed={false} />
                )}
                {onPrompt && (
                  <InlinePrompt
                    prompt="What would change your value view?"
                    label="Drill into value thesis"
                    onPick={onPrompt}
                  />
                )}
              </BrowseDrilldown>
            )}
            {hasProjection && scenarioTable && (
              <BrowseDrilldown
                label="Projection"
                summary={projectionChip}
                onFirstExpand={dismissHint}
              >
                <ScenarioTable table={scenarioTable} framed={false} />
                {scenarioFanChart && (
                  <ChartFrame chart={scenarioFanChart} framed={false} />
                )}
                {onPrompt && (
                  <InlinePrompt
                    prompt="Show me the downside case in more detail"
                    label="Drill into scenarios"
                    onPick={onPrompt}
                  />
                )}
              </BrowseDrilldown>
            )}
          </>
        )}
        {showHint && anyDrilldownContent && (
          <CoachMark onDismiss={dismissHint} />
        )}
      </div>
    </BrowseSection>
  );
}

// Surface 3 (Variant Q) — coach-mark tooltip rendered below the first
// drilldown row. Arrow points UP at the first chevron's x-position. The
// arrow is composed of two stacked CSS triangles so it inherits the
// tooltip's 1px subtle border without rendering a horizontal line at the
// tooltip's top edge.
//
// Position: the parent `<div className="@container">` wraps the drilldown
// stack. The first BrowseDrilldown row's chevron sits at `pl-3` inside a
// `-mx-3` button, so the chevron's center is at the wrapper's left edge +
// ~8.5px (chevron half-width). The tooltip's CSS arrow `left` is set so the
// arrow tip aligns with that position.
function CoachMark({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "relative mt-2 mb-1",
        "rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-surface)]",
        "px-3 py-2 pr-8 text-[12px] text-[var(--color-text-muted)] shadow-sm",
        "section-c-hint-fade-in",
      )}
    >
      {/* Outer triangle — uses border-bottom color trick to render the
          arrow tip's slanted edges in the tooltip's border tone. */}
      <span
        aria-hidden
        className={cn(
          "absolute -top-[6px] left-[3px]",
          "h-0 w-0",
          "border-l-[6px] border-r-[6px] border-b-[6px]",
          "border-l-transparent border-r-transparent border-b-[var(--color-border-subtle)]",
        )}
      />
      {/* Inner triangle — 1px smaller, surface-colored, stacked on top so
          the tooltip's top edge "becomes" the arrow's base without leaving
          a 1px horizontal line through the arrow. */}
      <span
        aria-hidden
        className={cn(
          "absolute -top-[5px] left-[4px]",
          "h-0 w-0",
          "border-l-[5px] border-r-[5px] border-b-[5px]",
          "border-l-transparent border-r-transparent border-b-[var(--color-surface)]",
        )}
      />
      Tap any row to see the evidence.
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss tip"
        className={cn(
          "absolute right-2 top-1/2 -translate-y-1/2",
          "text-[var(--color-text-faint)] hover:text-[var(--color-text)]",
          "text-[14px] leading-none transition-colors",
        )}
      >
        ×
      </button>
    </div>
  );
}
