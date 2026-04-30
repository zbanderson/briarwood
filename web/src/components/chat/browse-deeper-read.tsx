"use client";

import { useCallback, useSyncExternalStore } from "react";
import { cn } from "@/lib/cn";
import type {
  ChartEvent,
  CmaPositioningChartSpec,
  MarketSupportCompsEvent,
  MarketTrendChartSpec,
  RentOutlookEvent,
  RiskProfileEvent,
  ScenarioTableEvent,
  StrategyPathEvent,
  TownSignalItem,
  TownSummaryEvent,
  TrustSummaryEvent,
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
import { RentOutlookCard } from "./rent-outlook-card";
import { RiskProfileCard } from "./risk-profile-card";
import { ScenarioTable } from "./scenario-table";
import { StrategyPathCard } from "./strategy-path-card";
import { TownSummaryCard } from "./town-summary-card";
import { TrustSummaryCard } from "./trust-summary-card";
import { ValueThesisDrilldownBody } from "./value-thesis-drilldown-body";

// Phase 4c Cycle 3 — Section C ("THE DEEPER READ") shipped three drilldowns
// (Comps, Value thesis, Projection) on the `BrowseDrilldown` "Civic Ledger"
// primitive. Each drilldown row had a SummaryChip on the right that previewed
// the underlying evidence in one glance ("8 SOLD", "FAIR $1.31M · 5.3% APE",
// "5Y $1.18M – $1.65M").
//
// Phase 4c Cycle 4 — Section C fills out completely:
//   * five new drilldowns added: Rent / Town / Risk / Confidence / Path
//   * cross-cutting teaser hooks: each closed row carries a one-line italic
//     explainer below the label, derived from real data (see
//     ROADMAP §3.5 Cycle 4 carry-over). Newspaper rhythm preserved — the
//     teaser is text inline with the row, NEVER a boxed card.
// The hint coach-mark, ChipEyebrow / ChipFigure surface-2 chip system, and
// the `framed={false}` borderless body convention are unchanged from Cycle 3.

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
  rentOutlook?: RentOutlookEvent;
  townSummary?: TownSummaryEvent;
  riskProfile?: RiskProfileEvent;
  trustSummary?: TrustSummaryEvent;
  strategyPath?: StrategyPathEvent;
  charts: ChartEvent[];
  onPrompt?: (prompt: string) => void;
  onSelectTownSignal?: (signal: TownSignalItem) => void;
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

function isMarketTrendSpec(
  spec: ChartEvent["spec"] | null | undefined,
): spec is MarketTrendChartSpec {
  return spec != null && spec.kind === "market_trend";
}

// Cycle 4 — short street-only address for inline teaser sentences. Strips a
// trailing town/state if a full address came through. Keeps "1209 16th Ave"
// out of the noise floor of "1209 16th Ave, Belmar, NJ 07719".
function shortAddress(addr: string | null | undefined): string | null {
  if (!addr) return null;
  const head = addr.split(",")[0]?.trim();
  return head && head.length > 0 ? head : null;
}

export function BrowseDeeperRead({
  valueThesis,
  valuationComps,
  marketSupportComps,
  scenarioTable,
  rentOutlook,
  townSummary,
  riskProfile,
  trustSummary,
  strategyPath,
  charts,
  onPrompt,
  onSelectTownSignal,
}: Props) {
  const showHint = useSyncExternalStore(
    subscribeHint,
    readHintShouldShow,
    readHintShouldShowServer,
  );
  const dismissHint = useCallback(() => {
    markHintSeen();
  }, []);

  // ------------------------------------------------------------------
  // Comps drilldown (Cycle 3) — chip + Cycle 4 teaser
  // ------------------------------------------------------------------
  // Chip counts derive from the cma_positioning chart's spec.comps (same
  // source-of-truth as the chart's MetricChip "Comp set" chip in
  // chart-frame.tsx; cf. formatCompSetChip).
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

  // Cycle 4 teaser — "Top sale: <addr> at <price> · <N> within ±10% of ask".
  // Uses the same `cmaSpec.comps` data the chart and chip already cite, so
  // the teaser can't drift from what's visible in the chart.
  const compsTeaser = (() => {
    if (!cmaSpec) return null;
    const sold = cmaSpec.comps.filter(
      (c) =>
        c.listing_status === "sold" &&
        typeof c.ask_price === "number" &&
        Number.isFinite(c.ask_price),
    );
    if (sold.length === 0) return null;
    const top = sold.reduce<typeof sold[number] | null>((acc, comp) => {
      if (!acc) return comp;
      const accPrice = acc.ask_price ?? -Infinity;
      const compPrice = comp.ask_price ?? -Infinity;
      return compPrice > accPrice ? comp : acc;
    }, null);
    const subjectAsk = cmaSpec.subject_ask;
    const withinBand =
      subjectAsk != null && Number.isFinite(subjectAsk)
        ? cmaSpec.comps.filter((c) => {
            if (c.ask_price == null || !Number.isFinite(c.ask_price)) {
              return false;
            }
            return Math.abs(c.ask_price - subjectAsk) / subjectAsk <= 0.1;
          }).length
        : null;
    const topAddr = shortAddress(top?.address);
    const topPrice =
      top?.ask_price != null && Number.isFinite(top.ask_price)
        ? compactMoney(top.ask_price)
        : null;
    if (!topAddr || !topPrice) return null;
    const tail =
      withinBand != null
        ? ` · ${withinBand} within ±10% of ask`
        : "";
    return `Top sale: ${topAddr} at ${topPrice}${tail}`;
  })();

  // ------------------------------------------------------------------
  // Value thesis drilldown (Cycle 3) — chip + Cycle 4 teaser
  // ------------------------------------------------------------------
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
          <ChipFigure key="dot">{" · "}</ChipFigure>,
        );
      }
      fullParts.push(<ChipFigure key="ape-fig">{apeStr}</ChipFigure>);
      fullParts.push(<ChipEyebrow key="ape-eyebrow">{" APE"}</ChipEyebrow>);
    }
    const compactParts: React.ReactNode[] = [];
    if (fairValue != null) {
      compactParts.push(<ChipFigure key="c-fair">{fairStr}</ChipFigure>);
    }
    if (apeStr) {
      if (compactParts.length > 0) {
        compactParts.push(
          <ChipFigure key="c-dot">{" · "}</ChipFigure>,
        );
      }
      compactParts.push(<ChipFigure key="c-ape">{apeStr}</ChipFigure>);
    }
    return (
      <SummaryChip full={<>{fullParts}</>} compact={<>{compactParts}</>} />
    );
  })();

  // Cycle 4 teaser — describes the SHAPE of the value gap and the lead
  // value driver. "Fair $1.31M sits 5.3% under ask · top driver: <text>".
  const valueThesisTeaser = (() => {
    if (!valueThesis) return null;
    const parts: string[] = [];
    if (fairValue != null && apePct != null) {
      const direction = (premium ?? 0) >= 0 ? "over" : "under";
      parts.push(
        `Fair ${compactMoney(fairValue)} sits ${apePct.toFixed(1)}% ${direction} ask`,
      );
    } else if (fairValue != null) {
      parts.push(`Fair ${compactMoney(fairValue)}`);
    }
    const drivers =
      valueThesis.key_value_drivers?.length
        ? valueThesis.key_value_drivers
        : valueThesis.value_drivers;
    const topDriver = drivers && drivers.length > 0 ? drivers[0] : null;
    if (topDriver) {
      parts.push(`top driver: ${topDriver.toLowerCase()}`);
    }
    if (parts.length === 0) return null;
    return parts.join(" · ");
  })();

  // ------------------------------------------------------------------
  // Projection drilldown (Cycle 3) — chip + Cycle 4 teaser
  // ------------------------------------------------------------------
  // Projection chip — "5Y $1.18M – $1.65M" — bull/bear from scenarioTable.
  const projectionRows = scenarioTable?.rows ?? [];
  const bull = projectionRows.find((r) => r.scenario === "Bull");
  const bear = projectionRows.find((r) => r.scenario === "Bear");
  const base = projectionRows.find((r) => r.scenario === "Base");
  const projectionChip = (() => {
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
            <ChipFigure>{" "}{range}</ChipFigure>
          </>
        }
      />
    );
  })();

  // Cycle 4 teaser — describes the SPREAD versus base, not the absolute
  // range. "+22% bull / -15% bear vs base $1.32M".
  const projectionTeaser = (() => {
    if (!bull || !bear || !base) return null;
    const bullV = bull.value;
    const bearV = bear.value;
    const baseV = base.value;
    if (
      bullV == null ||
      bearV == null ||
      baseV == null ||
      !Number.isFinite(bullV) ||
      !Number.isFinite(bearV) ||
      !Number.isFinite(baseV) ||
      baseV === 0
    ) {
      return null;
    }
    const bullPct = ((bullV - baseV) / baseV) * 100;
    const bearPct = ((bearV - baseV) / baseV) * 100;
    const bullStr = `${bullPct >= 0 ? "+" : ""}${bullPct.toFixed(0)}% bull`;
    const bearStr = `${bearPct >= 0 ? "+" : ""}${bearPct.toFixed(0)}% bear`;
    return `${bullStr} / ${bearStr} vs base ${compactMoney(baseV)}`;
  })();

  // ------------------------------------------------------------------
  // Cycle 4 — Rent drilldown
  // ------------------------------------------------------------------
  const rentChip = (() => {
    if (!rentOutlook) return null;
    const monthly = rentOutlook.monthly_rent ?? rentOutlook.effective_monthly_rent;
    if (monthly == null || !Number.isFinite(monthly)) return null;
    const monthlyStr = compactMoney(monthly);
    const ratio = rentOutlook.carry_offset_ratio;
    const ratioStr =
      ratio != null && Number.isFinite(ratio) ? `${ratio.toFixed(2)}x` : null;
    return (
      <SummaryChip
        full={
          <>
            <ChipFigure>{monthlyStr}</ChipFigure>
            {ratioStr && (
              <>
                <ChipFigure>{" · "}</ChipFigure>
                <ChipFigure>{ratioStr}</ChipFigure>
                <ChipEyebrow>{" CARRY"}</ChipEyebrow>
              </>
            )}
          </>
        }
        compact={<ChipFigure>{monthlyStr}/mo</ChipFigure>}
      />
    );
  })();

  // Rent teaser — lead with the rental ease label + carry-coverage. Falls
  // back to the basis-to-rent framing when ease isn't graded.
  const rentTeaser = (() => {
    if (!rentOutlook) return null;
    const parts: string[] = [];
    const monthly = rentOutlook.monthly_rent ?? rentOutlook.effective_monthly_rent;
    if (monthly != null && Number.isFinite(monthly)) {
      parts.push(`${compactMoney(monthly)}/mo`);
    }
    if (rentOutlook.rental_ease_label) {
      parts.push(`${rentOutlook.rental_ease_label.toLowerCase()} to rent`);
    }
    if (
      rentOutlook.carry_offset_ratio != null &&
      Number.isFinite(rentOutlook.carry_offset_ratio)
    ) {
      parts.push(`covers ${rentOutlook.carry_offset_ratio.toFixed(2)}× carry`);
    }
    if (parts.length === 0) return null;
    return parts.join(" · ");
  })();

  // ------------------------------------------------------------------
  // Cycle 4 — Town drilldown
  // ------------------------------------------------------------------
  // Chip pulls 3y change% from market_trend chart spec (per BROWSE plan:
  // "Summary chip: 3y change%"). Falls through to median price when the
  // chart didn't ship.
  const marketTrendChart = findChart(charts, "market_trend");
  const marketTrendSpec = isMarketTrendSpec(marketTrendChart?.spec)
    ? marketTrendChart.spec
    : null;
  const townChip = (() => {
    const threeY = marketTrendSpec?.three_year_change_pct;
    if (threeY != null && Number.isFinite(threeY)) {
      const sign = threeY >= 0 ? "+" : "";
      const txt = `${sign}${(threeY * 100).toFixed(1)}%`;
      return (
        <SummaryChip
          full={
            <>
              <ChipEyebrow>{"3Y "}</ChipEyebrow>
              <ChipFigure>{txt}</ChipFigure>
            </>
          }
        />
      );
    }
    if (
      townSummary?.median_price != null &&
      Number.isFinite(townSummary.median_price)
    ) {
      return (
        <SummaryChip
          full={
            <>
              <ChipEyebrow>{"MEDIAN "}</ChipEyebrow>
              <ChipFigure>{compactMoney(townSummary.median_price)}</ChipFigure>
            </>
          }
        />
      );
    }
    return null;
  })();

  // Town teaser — bullish / bearish signal balance gives the user an honest
  // read of which way the town is leaning before they expand.
  const townTeaser = (() => {
    if (!townSummary) return null;
    const bullCount = townSummary.bullish_signals?.length ?? 0;
    const bearCount = townSummary.bearish_signals?.length ?? 0;
    if (bullCount === 0 && bearCount === 0) return null;
    const parts: string[] = [];
    if (townSummary.median_price != null) {
      parts.push(`Median ${compactMoney(townSummary.median_price)}`);
    }
    parts.push(`${bullCount} bullish vs ${bearCount} bearish`);
    return parts.join(" · ");
  })();

  // ------------------------------------------------------------------
  // Cycle 4 — Risk drilldown
  // ------------------------------------------------------------------
  const riskBarChart = findChart(charts, "risk_bar");
  const riskFlagCount = riskProfile?.risk_flags?.length ?? 0;
  const riskChip = (() => {
    if (!riskProfile) return null;
    const tier = riskProfile.confidence_tier;
    const tierLabel =
      tier == null ? null : tier[0]!.toUpperCase() + tier.slice(1);
    if (riskFlagCount === 0 && !tierLabel) return null;
    const fullParts: React.ReactNode[] = [];
    if (riskFlagCount > 0) {
      fullParts.push(
        <ChipFigure key="rf">
          {riskFlagCount} {riskFlagCount === 1 ? "FLAG" : "FLAGS"}
        </ChipFigure>,
      );
    }
    if (tierLabel) {
      if (fullParts.length > 0) {
        fullParts.push(<ChipFigure key="rf-dot">{" · "}</ChipFigure>);
      }
      fullParts.push(<ChipEyebrow key="rf-tier">{tierLabel.toUpperCase()}</ChipEyebrow>);
    }
    const compactParts: React.ReactNode[] = [];
    if (riskFlagCount > 0) {
      compactParts.push(
        <ChipFigure key="rfc">
          {riskFlagCount} {riskFlagCount === 1 ? "FLAG" : "FLAGS"}
        </ChipFigure>,
      );
    } else if (tierLabel) {
      compactParts.push(<ChipEyebrow key="rfc-tier">{tierLabel.toUpperCase()}</ChipEyebrow>);
    }
    return <SummaryChip full={<>{fullParts}</>} compact={<>{compactParts}</>} />;
  })();

  // Risk teaser — lead with the dominant flag (first risk_flag), then total
  // counts. Honest UI: if there are zero risk flags, surface the trust-flag
  // count instead so the row isn't silent.
  const riskTeaser = (() => {
    if (!riskProfile) return null;
    const lead = riskProfile.risk_flags?.[0] ?? null;
    const trustCount = riskProfile.trust_flags?.length ?? 0;
    const parts: string[] = [];
    if (lead) {
      parts.push(`Lead: ${lead.toLowerCase()}`);
    } else if (trustCount > 0) {
      parts.push("No hard risk flags");
    } else {
      return null;
    }
    const tail: string[] = [];
    if (riskFlagCount > 0) tail.push(`${riskFlagCount} risk drivers`);
    if (trustCount > 0) tail.push(`${trustCount} trust flags`);
    if (tail.length > 0) parts.push(tail.join(", "));
    return parts.join(" · ");
  })();

  // ------------------------------------------------------------------
  // Cycle 4 — Confidence & data drilldown
  // ------------------------------------------------------------------
  const trustChip = (() => {
    if (!trustSummary) return null;
    const band = trustSummary.band ?? null;
    const conf = trustSummary.confidence;
    if (!band && conf == null) return null;
    const confStr =
      conf != null && Number.isFinite(conf) ? `${Math.round(conf * 100)}%` : null;
    const fullParts: React.ReactNode[] = [];
    if (band) {
      fullParts.push(<ChipEyebrow key="tb">{band.toUpperCase()}</ChipEyebrow>);
    }
    if (confStr) {
      if (fullParts.length > 0) {
        fullParts.push(<ChipFigure key="tb-dot">{" · "}</ChipFigure>);
      }
      fullParts.push(<ChipFigure key="tb-conf">{confStr}</ChipFigure>);
    }
    return <SummaryChip full={<>{fullParts}</>} />;
  })();

  // Confidence teaser — band + first trust flag (the lead constraint on
  // certainty) + contradiction count when present.
  const trustTeaser = (() => {
    if (!trustSummary) return null;
    const parts: string[] = [];
    if (trustSummary.band) {
      const conf =
        trustSummary.confidence != null && Number.isFinite(trustSummary.confidence)
          ? ` (${Math.round(trustSummary.confidence * 100)}%)`
          : "";
      parts.push(`${trustSummary.band}${conf}`);
    }
    const lead = trustSummary.trust_flags?.[0];
    if (lead) {
      parts.push(`limit: ${lead.toLowerCase()}`);
    }
    const contra = trustSummary.contradiction_count;
    if (contra != null && contra > 0) {
      parts.push(`${contra} contradiction${contra === 1 ? "" : "s"}`);
    }
    if (parts.length === 0) return null;
    return parts.join(" · ");
  })();

  // ------------------------------------------------------------------
  // Cycle 4 — Recommended path drilldown (StrategyPathCard absorbed)
  // ------------------------------------------------------------------
  const pathChip = (() => {
    if (!strategyPath) return null;
    const path = strategyPath.best_path?.replace(/_/g, " ") ?? null;
    if (!path) return null;
    return (
      <SummaryChip
        full={<ChipEyebrow>{path.toUpperCase()}</ChipEyebrow>}
      />
    );
  })();

  // Path teaser — short read on what the recommendation buys you. Lead
  // with the path label, then carry-flow + cash-on-cash so the reader has
  // the financial shape before opening the body.
  const pathTeaser = (() => {
    if (!strategyPath) return null;
    const parts: string[] = [];
    if (strategyPath.best_path) {
      parts.push(strategyPath.best_path.replace(/_/g, " "));
    } else if (strategyPath.recommendation) {
      const trimmed =
        strategyPath.recommendation.length > 80
          ? `${strategyPath.recommendation.slice(0, 77)}…`
          : strategyPath.recommendation;
      parts.push(trimmed);
    }
    const flow = strategyPath.monthly_cash_flow;
    if (flow != null && Number.isFinite(flow)) {
      const sign = flow < 0 ? "-" : "+";
      parts.push(`${sign}${compactMoney(Math.abs(flow))}/mo`);
    }
    const coc = strategyPath.cash_on_cash_return;
    if (coc != null && Number.isFinite(coc)) {
      parts.push(`${(coc * 100).toFixed(1)}% cash-on-cash`);
    }
    if (parts.length === 0) return null;
    return parts.join(" · ");
  })();

  const valueOpportunityChart = findChart(charts, "value_opportunity");
  const scenarioFanChart = findChart(charts, "scenario_fan");
  const rentBurnChart = findChart(charts, "rent_burn");
  const rentRampChart = findChart(charts, "rent_ramp");

  const hasComps =
    Boolean(cmaSpec) || Boolean(valuationComps) || Boolean(marketSupportComps);
  const hasValueThesis = Boolean(valueThesis);
  const hasProjection = Boolean(scenarioTable);
  const hasRent = Boolean(rentOutlook);
  const hasTown = Boolean(townSummary);
  const hasRisk = Boolean(riskProfile);
  const hasTrust = Boolean(trustSummary);
  const hasStrategy = Boolean(strategyPath);

  // If we have nothing to render in any drilldown, the section still renders
  // its sub-head + a one-line italic note so the user knows where the
  // deeper-read area is. Loud absence is honest UI.
  const anyDrilldownContent =
    hasComps ||
    hasValueThesis ||
    hasProjection ||
    hasRent ||
    hasTown ||
    hasRisk ||
    hasTrust ||
    hasStrategy;

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
                teaser={compsTeaser}
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
                teaser={valueThesisTeaser}
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
                teaser={projectionTeaser}
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
            {hasRent && rentOutlook && (
              <BrowseDrilldown
                label="Rent"
                summary={rentChip}
                teaser={rentTeaser}
                onFirstExpand={dismissHint}
              >
                <RentOutlookCard outlook={rentOutlook} framed={false} />
                {rentBurnChart && (
                  <ChartFrame chart={rentBurnChart} framed={false} />
                )}
                {rentRampChart && (
                  <ChartFrame chart={rentRampChart} framed={false} />
                )}
                {onPrompt && (
                  <InlinePrompt
                    prompt="What rent would make this deal work?"
                    label="Drill into rent"
                    onPick={onPrompt}
                  />
                )}
              </BrowseDrilldown>
            )}
            {hasTown && townSummary && (
              <BrowseDrilldown
                label="Town context"
                summary={townChip}
                teaser={townTeaser}
                onFirstExpand={dismissHint}
              >
                {/* market_trend chart deliberately stays in Section A
                    (BrowseRead masthead) — do not double-render here.
                    See BROWSE_REBUILD_HANDOFF_PLAN Cycle 4 scope. */}
                <TownSummaryCard
                  summary={townSummary}
                  onSelectSignal={onSelectTownSignal}
                  framed={false}
                />
                {onPrompt && (
                  <InlinePrompt
                    prompt="What's driving the town outlook?"
                    label="Drill into town context"
                    onPick={onPrompt}
                  />
                )}
              </BrowseDrilldown>
            )}
            {hasRisk && riskProfile && (
              <BrowseDrilldown
                label="Risk"
                summary={riskChip}
                teaser={riskTeaser}
                onFirstExpand={dismissHint}
              >
                <RiskProfileCard profile={riskProfile} framed={false} />
                {riskBarChart && (
                  <ChartFrame chart={riskBarChart} framed={false} />
                )}
                {onPrompt && (
                  <InlinePrompt
                    prompt="What's the biggest risk here?"
                    label="Drill into risk"
                    onPick={onPrompt}
                  />
                )}
              </BrowseDrilldown>
            )}
            {hasTrust && trustSummary && (
              <BrowseDrilldown
                label="Confidence & data"
                summary={trustChip}
                teaser={trustTeaser}
                onFirstExpand={dismissHint}
              >
                <TrustSummaryCard summary={trustSummary} framed={false} />
                {onPrompt && (
                  <InlinePrompt
                    prompt="What data is missing or estimated?"
                    label="Drill into confidence"
                    onPick={onPrompt}
                  />
                )}
              </BrowseDrilldown>
            )}
            {hasStrategy && strategyPath && (
              <BrowseDrilldown
                label="Recommended path"
                summary={pathChip}
                teaser={pathTeaser}
                onFirstExpand={dismissHint}
              >
                <StrategyPathCard strategy={strategyPath} framed={false} />
                {onPrompt && (
                  <InlinePrompt
                    prompt="Walk me through the recommended path"
                    label="Drill into strategy"
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
