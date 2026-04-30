"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { cn } from "@/lib/cn";
import { getChartSurface } from "@/lib/chat/chart-surface";
import type {
  ChartEvent,
  ChartLegendItem,
  ChartValueFormat,
  CmaPositioningChartSpec,
  ChartSpec,
  HorizontalBarWithRangesChartSpec,
  MarketTrendChartSpec,
  RentBurnChartSpec,
  RentRampChartSpec,
  RiskBarChartSpec,
  ScenarioFanChartSpec,
  ValueOpportunityChartSpec,
} from "@/lib/chat/events";

type Props = {
  chart: ChartEvent;
  /** Phase 4c Cycle 3 — Section C drilldowns embed charts inline with no
   * extra border around them (constraint: "no nested boxed cards"). When
   * `framed=false`, drop the outer `<figure>` rounded-2xl border + bg, drop
   * inner border-b dividers, drop horizontal padding (parent provides it),
   * and reduce the title weight so the chart's title doesn't compete with
   * the drilldown row's label. Default `true` preserves non-BROWSE
   * rendering. */
  framed?: boolean;
};

// Chart-renderer migration — all eight `ChartSpec` kinds render through
// a single Apache ECharts module loaded with `ssr: false` so the ECharts
// chunk arrives after the page is interactive. Non-chart routes carry
// zero ECharts cost in their first-load chunks. Suspense fallback is a
// solid shimmer matching the chart's outer rounded rectangle (320px
// default height; per-kind wrappers adjust when the underlying chart is
// shorter, e.g. `value_opportunity`).
const LazyChartECharts = dynamic(() => import("./chart-echarts"), {
  ssr: false,
  loading: () => (
    <div
      aria-hidden
      className="h-[320px] w-full animate-pulse rounded-2xl bg-[var(--color-bg-sunken)]"
    />
  ),
});

type ChartChrome = {
  xAxisLabel?: string | null;
  yAxisLabel?: string | null;
  valueFormat?: ChartValueFormat | null;
};

function chartTitle(c: ChartEvent) {
  if (c.title) return c.title;
  if (c.kind) {
    return c.kind
      .split("_")
      .map((w) => w[0]?.toUpperCase() + w.slice(1))
      .join(" ");
  }
  return "Chart";
}

function money(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${Math.round(n).toLocaleString()}`;
}

function pct(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${(n * 100).toFixed(1)}%`;
}

function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

// Phase 4c Cycle 3 (§3.4.1) — shared formatter for the `Comp set` chip on
// `cma_positioning` and the "Comps" drilldown SummaryChip in
// `browse-deeper-read.tsx`. Both consume the same `CmaPositioningChartSpec`
// payload so the chart-prose alignment that §3.4.1 demands is structural.
//
// Format: "5 SOLD · 3 ACTIVE", or "5 SOLD (2 CROSS-TOWN) · 3 ACTIVE" when
// a SOLD subset is cross-town. When everything is null (legacy cached
// payloads with no provenance), falls back to total comp count.
export function formatCompSetChip(counts: {
  sold: number;
  active: number;
  crossTown: number;
  total: number;
}): string {
  const { sold, active, crossTown, total } = counts;
  const parts: string[] = [];
  if (sold > 0) {
    parts.push(
      crossTown > 0
        ? `${sold} SOLD (${crossTown} CROSS-TOWN)`
        : `${sold} SOLD`,
    );
  }
  if (active > 0) parts.push(`${active} ACTIVE`);
  if (parts.length === 0) {
    return total > 0 ? `${total} COMPS` : "—";
  }
  return parts.join(" · ");
}

function strokeDashFor(style: ChartLegendItem["style"]): string | undefined {
  if (style === "dashed") return "5 6";
  if (style === "dotted") return "2 5";
  return undefined;
}

function LegendRow({ items }: { items: ChartLegendItem[] }) {
  if (items.length === 0) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-[var(--color-text-muted)]">
      {items.map((item, idx) => {
        const dash = strokeDashFor(item.style);
        const color = item.color || "var(--chart-base)";
        return (
          <span key={`${item.label}-${idx}`} className="flex items-center gap-1.5">
            <svg width="20" height="8" aria-hidden>
              <line
                x1="0"
                y1="4"
                x2="20"
                y2="4"
                stroke={color}
                strokeWidth="2.5"
                strokeDasharray={dash}
                strokeLinecap="round"
              />
            </svg>
            <span>{item.label}</span>
          </span>
        );
      })}
    </div>
  );
}

function ChartBody({ spec, chrome }: { spec: ChartSpec; chrome: ChartChrome }) {
  if (spec.kind === "scenario_fan") {
    return <ScenarioFanChart spec={spec} chrome={chrome} />;
  }
  if (spec.kind === "cma_positioning") {
    return <CmaPositioningChart spec={spec} chrome={chrome} />;
  }
  if (spec.kind === "risk_bar") {
    return <RiskBarChart spec={spec} chrome={chrome} />;
  }
  if (spec.kind === "rent_burn") {
    return <RentBurnChart spec={spec} chrome={chrome} />;
  }
  if (spec.kind === "rent_ramp") {
    return <RentRampChart spec={spec} chrome={chrome} />;
  }
  if (spec.kind === "value_opportunity") {
    return <ValueOpportunityChart spec={spec} chrome={chrome} />;
  }
  if (spec.kind === "horizontal_bar_with_ranges") {
    return <HorizontalBarWithRangesChart spec={spec} chrome={chrome} />;
  }
  if (spec.kind === "market_trend") {
    return <MarketTrendChart spec={spec} chrome={chrome} />;
  }
  return null;
}

export function ChartFrame({ chart, framed = true }: Props) {
  const [loaded, setLoaded] = useState(false);
  const surface = getChartSurface(chart);
  const title = surface.title ?? chartTitle(chart);
  const subtitle = chart.subtitle ?? null;
  const legend = chart.legend ?? null;
  const chrome: ChartChrome = {
    xAxisLabel: chart.x_axis_label,
    yAxisLabel: chart.y_axis_label,
    valueFormat: chart.value_format,
  };

  if (!surface.shouldRender) return null;

  // Phase 4c Cycle 3 — `framed=false` drops the outer rounded-2xl border, the
  // inner section-divider border-b lines, and the horizontal padding (parent
  // drilldown body provides indent). Title weight reduces so it doesn't
  // compete with the drilldown row's label.
  const outerClass = framed
    ? cn(
        "mt-4 overflow-hidden rounded-2xl border border-[var(--color-border-subtle)]",
        "bg-[var(--color-surface)]",
      )
    : "mt-2";
  const headerClass = framed
    ? "border-b border-[var(--color-border-subtle)] px-4 pt-4 pb-3"
    : "pb-2";
  const titleClass = framed
    ? "text-[18px] font-bold leading-tight tracking-tight text-[var(--color-text)]"
    : "text-[14px] font-semibold leading-tight tracking-tight text-[var(--color-text)]";
  const bodyClass = framed ? "px-3 pt-3 pb-3" : "";
  const provenanceWrapperClass = framed ? "" : "mb-2";
  const summaryWrapperClass = framed
    ? "border-b border-[var(--color-border-subtle)] px-4 py-3 text-[13px] text-[var(--color-text-muted)]"
    : "mb-3 text-[13px] text-[var(--color-text-muted)]";
  const legendWrapperClass = framed ? "px-4 pb-2" : "mt-3";
  const companionWrapperClass = framed
    ? "border-t border-[var(--color-border-subtle)] px-4 py-3 text-[12px] text-[var(--color-text-faint)]"
    : "mt-3 text-[12px] text-[var(--color-text-faint)]";

  if (chart.spec) {
    const body = <ChartBody spec={chart.spec} chrome={chrome} />;
    if (!body) return null;
    return (
      <figure className={outerClass}>
        <div className={headerClass}>
          <h3 className={titleClass}>{title}</h3>
          {subtitle && (
            <p className="mt-1 text-[13px] leading-snug text-[var(--color-text-muted)]">
              {subtitle}
            </p>
          )}
        </div>
        <div className={bodyClass}>
          {chart.provenance && chart.provenance.length > 0 && (
            <ProvenanceChips items={chart.provenance} />
          )}
          {/* Phase 3 Cycle C: the Representation Agent's per-chart claim
              leads the figure when present. Falls back to the visual_advisor
              summary when the agent didn't produce a claim. */}
          {chart.why_this_chart ? (
            <div className="mb-3 border-l-2 border-[var(--color-border-subtle)] pl-3 text-[13px] italic leading-snug text-[var(--color-text-muted)]">
              {chart.why_this_chart}
            </div>
          ) : (
            surface.summary && (
              <div className="mb-3 text-[13px] text-[var(--color-text-muted)]">
                {surface.summary}
              </div>
            )
          )}
          {body}
          {legend && legend.length > 0 && <LegendRow items={legend} />}
          {surface.companion && (
            <div className="mt-3 text-[12px] text-[var(--color-text-faint)]">
              {surface.companion}
            </div>
          )}
        </div>
      </figure>
    );
  }

  if (!chart.url) return null;

  return (
    <figure className={outerClass}>
      <div className={headerClass}>
        <h3 className={titleClass}>{title}</h3>
        {subtitle && (
          <p className="mt-1 text-[13px] leading-snug text-[var(--color-text-muted)]">
            {subtitle}
          </p>
        )}
      </div>
      <div className="relative">
        {chart.provenance && chart.provenance.length > 0 && (
          <div
            className={cn(
              framed
                ? "border-b border-[var(--color-border-subtle)] px-4 py-3"
                : provenanceWrapperClass,
            )}
          >
            <ProvenanceChips items={chart.provenance} />
          </div>
        )}
        {surface.summary && (
          <div className={summaryWrapperClass}>{surface.summary}</div>
        )}
        {!loaded && (
          <div
            aria-hidden
            className="absolute inset-0 animate-pulse bg-[var(--color-bg-sunken)]"
          />
        )}
        <iframe
          src={chart.url}
          title={title}
          loading="lazy"
          sandbox="allow-scripts allow-same-origin"
          onLoad={() => setLoaded(true)}
          className="block h-[420px] w-full border-0 bg-white"
        />
      </div>
      {legend && legend.length > 0 && (
        <div className={legendWrapperClass}>
          <LegendRow items={legend} />
        </div>
      )}
      {surface.companion && (
        <div className={companionWrapperClass}>{surface.companion}</div>
      )}
    </figure>
  );
}

function ProvenanceChips({ items }: { items: string[] }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-faint)]">
        Driven by
      </span>
      {items.map((item) => (
        <span
          key={item}
          className="rounded-full border border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] px-2 py-0.5 text-[10px] text-[var(--color-text-muted)]"
        >
          {item}
        </span>
      ))}
    </div>
  );
}

function ScenarioFanChart({
  spec,
  chrome,
}: {
  spec: ScenarioFanChartSpec;
  chrome: ChartChrome;
}) {
  const basisLabel = (spec.basis_label ?? "ask").replace(/_/g, " ");
  return (
    <div>
      <LazyChartECharts spec={spec} chrome={chrome} />
      <div className="mt-3 grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-4">
        <MetricChip label={basisLabel} value={money(spec.ask_price)} />
        <MetricChip label="Base" value={money(spec.base_case_value)} tone="sky" />
        <MetricChip label="Bull" value={money(spec.bull_case_value)} tone="emerald" />
        <MetricChip label="Bear" value={money(spec.bear_case_value)} tone="rose" />
      </div>
    </div>
  );
}

function CmaPositioningChart({
  spec,
  chrome,
}: {
  spec: CmaPositioningChartSpec;
  chrome: ChartChrome;
}) {
  // Cycle 3 (§3.4.1) — `feeds_fair_value` is retired. The "Comp set" chip
  // is computed from `listing_status` against the same `spec.comps` the
  // chart renders, so chart-prose alignment with the BROWSE Section C
  // "Comps" drilldown SummaryChip in browse-deeper-read.tsx is structural.
  const soldCount = spec.comps.filter((c) => c.listing_status === "sold").length;
  const activeCount = spec.comps.filter(
    (c) => c.listing_status === "active",
  ).length;
  const crossTownCount = spec.comps.filter(
    (c) => c.listing_status === "sold" && Boolean(c.is_cross_town),
  ).length;
  const compSetSummary = formatCompSetChip({
    sold: soldCount,
    active: activeCount,
    crossTown: crossTownCount,
    total: spec.comps.length,
  });
  return (
    <div>
      <LazyChartECharts spec={spec} chrome={chrome} />
      <div className="mt-3 grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-4">
        <MetricChip label="Ask" value={money(spec.subject_ask)} tone="rose" />
        <MetricChip label="Fair value" value={money(spec.fair_value_base)} tone="sky" />
        <MetricChip
          label="Range"
          value={
            isNumber(spec.value_low) || isNumber(spec.value_high)
              ? `${money(spec.value_low)} – ${money(spec.value_high)}`
              : "—"
          }
        />
        <MetricChip label="Comp set" value={compSetSummary} tone="emerald" />
      </div>
    </div>
  );
}

function RiskBarChart({
  spec,
  chrome,
}: {
  spec: RiskBarChartSpec;
  chrome: ChartChrome;
}) {
  return (
    <div>
      <div className="mb-2 text-[12px] text-[var(--color-text-faint)]">
        Bear {money(spec.bear_value)} · Stress {money(spec.stress_value)}
      </div>
      <LazyChartECharts spec={spec} chrome={chrome} />
    </div>
  );
}

function RentBurnChart({
  spec,
  chrome,
}: {
  spec: RentBurnChartSpec;
  chrome: ChartChrome;
}) {
  const last = spec.points[spec.points.length - 1];
  return (
    <div>
      <LazyChartECharts spec={spec} chrome={chrome} />
      <div className="mt-3 grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-3">
        <MetricChip
          label={spec.working_label ?? "Base rent"}
          value={money(last?.rent_base)}
          tone="sky"
        />
        <MetricChip
          label="Bull / Bear"
          value={`${money(last?.rent_bull)} / ${money(last?.rent_bear)}`}
        />
        <MetricChip
          label="Obligation"
          value={money(last?.monthly_obligation)}
          tone="rose"
        />
        {isNumber(spec.market_rent) && (
          <MetricChip
            label={spec.market_label ?? "Market regime"}
            value={money(spec.market_rent)}
          />
        )}
      </div>
      {spec.market_context_note && (
        <div className="mt-3 text-[12px] text-[var(--color-text-faint)]">
          {spec.market_context_note}
        </div>
      )}
    </div>
  );
}

function RentRampChart({
  spec,
  chrome,
}: {
  spec: RentRampChartSpec;
  chrome: ChartChrome;
}) {
  return (
    <div>
      <LazyChartECharts spec={spec} chrome={chrome} />
      <div className="mt-3 grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-4">
        <MetricChip label="Today rent" value={money(spec.current_rent)} tone="sky" />
        <MetricChip label="Monthly cost" value={money(spec.monthly_obligation)} />
        <MetricChip
          label="Today cash flow"
          value={money(spec.today_cash_flow)}
          tone={
            spec.today_cash_flow != null && spec.today_cash_flow < 0
              ? "rose"
              : "emerald"
          }
        />
        <MetricChip
          label="Break-even"
          value={breakEvenLabel(spec.break_even_years?.["3"])}
        />
      </div>
    </div>
  );
}

function ValueOpportunityChart({
  spec,
  chrome,
}: {
  spec: ValueOpportunityChartSpec;
  chrome: ChartChrome;
}) {
  const ask = spec.ask_price ?? null;
  const fair = spec.fair_value_base ?? null;
  const premium = spec.premium_discount_pct ?? null;
  return (
    <div>
      <div className="mb-2 text-[12px] text-[var(--color-text-faint)]">
        Ask {money(ask)} vs fair value {money(fair)} · {pct(premium)}
      </div>
      <LazyChartECharts spec={spec} chrome={chrome} />
      {spec.value_drivers && spec.value_drivers.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {spec.value_drivers.slice(0, 4).map((driver) => (
            <span
              key={driver}
              className="rounded-full border border-sky-500/20 bg-sky-500/10 px-2.5 py-1 text-[11px] text-sky-200"
            >
              {driver}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function MetricChip({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "rose" | "emerald" | "sky";
}) {
  const valueClass =
    tone === "rose"
      ? "text-rose-300"
      : tone === "emerald"
        ? "text-emerald-300"
        : tone === "sky"
          ? "text-sky-300"
          : "text-[var(--color-text)]";
  return (
    <div className="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] px-3 py-2">
      <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
        {label}
      </div>
      <div className={cn("mt-0.5 text-[13px] font-medium", valueClass)}>
        {value}
      </div>
    </div>
  );
}

function breakEvenLabel(year: number | null | undefined) {
  if (year == null) return "No break-even";
  if (year === 0) return "Works today";
  return `Year ${year}`;
}

function HorizontalBarWithRangesChart({
  spec,
  chrome,
}: {
  spec: HorizontalBarWithRangesChartSpec;
  chrome: ChartChrome;
}) {
  const scenarios = spec.scenarios.filter(
    (s) => isNumber(s.low) && isNumber(s.high) && isNumber(s.median),
  );
  if (scenarios.length === 0) return null;

  const unit = spec.unit ?? "";
  const emphasisId = spec.emphasis_scenario_id ?? null;
  const formatValue = (n: number) => {
    const rounded = Math.round(n);
    return unit ? `${rounded}` : `$${rounded.toLocaleString()}`;
  };

  return (
    <div>
      <LazyChartECharts spec={spec} chrome={chrome} />
      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-[var(--color-text-faint)]">
        {scenarios.map((scenario) => {
          const isEmphasized =
            emphasisId != null && scenario.id === emphasisId;
          return (
            <span
              key={scenario.id}
              className={cn(
                "rounded-full border px-2 py-0.5",
                isEmphasized
                  ? "border-[var(--chart-stress)] text-[var(--color-text)]"
                  : "border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)]",
              )}
            >
              {scenario.label}: {formatValue(scenario.low)}–
              {formatValue(scenario.high)}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function MarketTrendChart({
  spec,
  chrome,
}: {
  spec: MarketTrendChartSpec;
  chrome: ChartChrome;
}) {
  const points = spec.points ?? [];
  if (points.length === 0) return null;

  const oneYearChange = spec.one_year_change_pct;
  const threeYearChange = spec.three_year_change_pct;

  return (
    <div>
      <LazyChartECharts spec={spec} chrome={chrome} />
      <div className="mt-3 grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-4">
        <MetricChip
          label={spec.geography_name ? `${spec.geography_name} now` : "Now"}
          value={money(spec.current_value)}
          tone="sky"
        />
        <MetricChip
          label="1-year change"
          value={pct(oneYearChange)}
          tone={
            isNumber(oneYearChange) && oneYearChange < 0 ? "rose" : "emerald"
          }
        />
        <MetricChip
          label="3-year change"
          value={pct(threeYearChange)}
          tone={
            isNumber(threeYearChange) && threeYearChange < 0
              ? "rose"
              : "emerald"
          }
        />
        <MetricChip
          label="Geography"
          value={spec.geography_type ? `${spec.geography_type}-level` : "—"}
        />
      </div>
    </div>
  );
}
