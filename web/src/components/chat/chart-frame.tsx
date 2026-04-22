"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";
import { getChartSurface } from "@/lib/chat/chart-surface";
import type {
  ChartEvent,
  CmaPositioningChartSpec,
  ChartSpec,
  HorizontalBarWithRangesChartSpec,
  RentBurnChartSpec,
  RentRampChartSpec,
  RiskBarChartSpec,
  ScenarioFanChartSpec,
  ValueOpportunityChartSpec,
} from "@/lib/chat/events";

type Props = {
  chart: ChartEvent;
};

const SVG_W = 640;
const SVG_H = 300;

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

function linePath(
  values: Array<number | null | undefined>,
  xForIndex: (index: number) => number,
  yForValue: (value: number) => number,
) {
  let path = "";
  values.forEach((value, index) => {
    if (!isNumber(value)) return;
    const cmd = path ? "L" : "M";
    path += `${cmd}${xForIndex(index)} ${yForValue(value)} `;
  });
  return path.trim();
}

function areaPath(
  upper: Array<number | null | undefined>,
  lower: Array<number | null | undefined>,
  xForIndex: (index: number) => number,
  yForValue: (value: number) => number,
) {
  const upperPoints = upper
    .map((value, index) =>
      isNumber(value) ? `${xForIndex(index)} ${yForValue(value)}` : null,
    )
    .filter(Boolean) as string[];
  const lowerPoints = lower
    .map((value, index) =>
      isNumber(value) ? `${xForIndex(index)} ${yForValue(value)}` : null,
    )
    .filter(Boolean)
    .reverse() as string[];
  if (upperPoints.length === 0 || lowerPoints.length === 0) return null;
  return `M${upperPoints.join(" L")} L${lowerPoints.join(" L")} Z`;
}

function chartBounds(values: Array<number | null | undefined>) {
  const numeric = values.filter(isNumber);
  if (numeric.length === 0) {
    return { min: 0, max: 1 };
  }
  const min = Math.min(...numeric);
  const max = Math.max(...numeric);
  const span = Math.max(max - min, max * 0.08, 1);
  return { min: min - span * 0.18, max: max + span * 0.18 };
}

function NativeChart({ spec, title }: { spec: ChartSpec; title: string }) {
  if (spec.kind === "scenario_fan") {
    return <ScenarioFanChart spec={spec} title={title} />;
  }
  if (spec.kind === "cma_positioning") {
    return <CmaPositioningChart spec={spec} title={title} />;
  }
  if (spec.kind === "risk_bar") {
    return <RiskBarChart spec={spec} title={title} />;
  }
  if (spec.kind === "rent_burn") {
    return <RentBurnChart spec={spec} title={title} />;
  }
  if (spec.kind === "rent_ramp") {
    return <RentRampChart spec={spec} title={title} />;
  }
  if (spec.kind === "value_opportunity") {
    return <ValueOpportunityChart spec={spec} title={title} />;
  }
  if (spec.kind === "horizontal_bar_with_ranges") {
    return <HorizontalBarWithRangesChart spec={spec} title={title} />;
  }
  return null;
}

export function ChartFrame({ chart }: Props) {
  const [loaded, setLoaded] = useState(false);
  const surface = getChartSurface(chart);
  const title = surface.title ?? chartTitle(chart);

  if (!surface.shouldRender) return null;

  if (chart.spec) {
    const body = <NativeChart spec={chart.spec} title={title} />;
    if (!body) return null;
    return (
      <figure
        className={cn(
          "mt-4 overflow-hidden rounded-2xl border border-[var(--color-border-subtle)]",
          "bg-[var(--color-surface)]",
        )}
      >
        <figcaption className="border-b border-[var(--color-border-subtle)] px-4 py-2 text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
          {title}
        </figcaption>
        <div className="px-3 py-3">
          {chart.provenance && chart.provenance.length > 0 && (
            <ProvenanceChips items={chart.provenance} />
          )}
          {surface.summary && (
            <div className="mb-3 text-[13px] text-[var(--color-text-muted)]">
              {surface.summary}
            </div>
          )}
          {body}
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
    <figure
      className={cn(
        "mt-4 overflow-hidden rounded-2xl border border-[var(--color-border-subtle)]",
        "bg-[var(--color-surface)]",
      )}
    >
      <figcaption className="border-b border-[var(--color-border-subtle)] px-4 py-2 text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
        {title}
      </figcaption>
      <div className="relative">
        {chart.provenance && chart.provenance.length > 0 && (
          <div className="border-b border-[var(--color-border-subtle)] px-4 py-3">
            <ProvenanceChips items={chart.provenance} />
          </div>
        )}
        {surface.summary && (
          <div className="border-b border-[var(--color-border-subtle)] px-4 py-3 text-[13px] text-[var(--color-text-muted)]">
            {surface.summary}
          </div>
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
      {surface.companion && (
        <div className="border-t border-[var(--color-border-subtle)] px-4 py-3 text-[12px] text-[var(--color-text-faint)]">
          {surface.companion}
        </div>
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
  title,
}: {
  spec: ScenarioFanChartSpec;
  title: string;
}) {
  const years = [0, 1, 2, 3, 4, 5];
  const ask = spec.ask_price ?? null;
  const basisLabel = (spec.basis_label ?? "ask").replace(/_/g, " ");
  const bull = spec.bull_case_value ?? ask;
  const base = spec.base_case_value ?? ask;
  const bear = spec.bear_case_value ?? ask;
  const stress = spec.stress_case_value ?? null;
  const pathFor = (target: number | null | undefined) =>
    years.map((year) => {
      if (!isNumber(ask) || !isNumber(target)) return null;
      return ask + (target - ask) * (year / 5);
    });
  const bullPath = pathFor(bull);
  const basePath = pathFor(base);
  const bearPath = pathFor(bear);
  const stressPath = pathFor(stress);
  const bounds = chartBounds([
    ask,
    spec.bull_case_value,
    spec.base_case_value,
    spec.bear_case_value,
    spec.stress_case_value,
  ]);
  const xForIndex = (index: number) => 72 + index * 104;
  const yForValue = (value: number) =>
    230 - ((value - bounds.min) / (bounds.max - bounds.min || 1)) * 170;
  const band = areaPath(bullPath, bearPath, xForIndex, yForValue);
  const endpointX = xForIndex(years.length - 1);
  const annotate = (
    label: string,
    tone: string,
    value: number | null | undefined,
    dy: number,
  ) =>
    isNumber(value) ? (
      <g key={label}>
        <circle cx={endpointX} cy={yForValue(value)} r="4.5" fill={tone} />
        <text
          x={Math.min(endpointX + 10, SVG_W - 12)}
          y={yForValue(value) + dy}
          fontSize="10"
          fill="var(--color-text)"
        >
          {label}
        </text>
      </g>
    ) : null;

  return (
    <div>
      <svg viewBox={`0 0 ${SVG_W} ${SVG_H}`} className="w-full">
        <rect
          x="0"
          y="0"
          width={SVG_W}
          height={SVG_H}
          rx="18"
          fill="var(--color-bg-sunken)"
        />
        {[0, 1, 2, 3].map((row) => {
          const y = 52 + row * 46;
          return (
            <line
              key={row}
              x1="64"
              y1={y}
              x2="592"
              y2={y}
              stroke="var(--color-border-subtle)"
              strokeDasharray="4 6"
            />
          );
        })}
        {band && (
          <path d={band} fill="rgba(103, 167, 255, 0.16)" stroke="none" />
        )}
        {isNumber(ask) && (
          <line
            x1="64"
            y1={yForValue(ask)}
            x2="592"
            y2={yForValue(ask)}
            stroke="rgba(243,239,230,0.4)"
            strokeDasharray="6 6"
          />
        )}
        <path
          d={linePath(bullPath, xForIndex, yForValue)}
          fill="none"
          stroke="#75d38f"
          strokeWidth="3"
          strokeDasharray="5 6"
        />
        <path
          d={linePath(basePath, xForIndex, yForValue)}
          fill="none"
          stroke="#79b8ff"
          strokeWidth="4"
        />
        <path
          d={linePath(bearPath, xForIndex, yForValue)}
          fill="none"
          stroke="#f28b82"
          strokeWidth="3"
          strokeDasharray="5 6"
        />
        {stressPath.some(isNumber) && (
          <path
            d={linePath(stressPath, xForIndex, yForValue)}
            fill="none"
            stroke="#d7b38a"
            strokeWidth="2"
            strokeDasharray="2 6"
          />
        )}
        {years.map((year, index) => (
          <g key={year}>
            <text
              x={xForIndex(index)}
              y="262"
              textAnchor="middle"
              fontSize="11"
              fill="var(--color-text-faint)"
            >
              {year === 0 ? "Today" : `Y${year}`}
            </text>
          </g>
        ))}
        <text x="72" y="26" fontSize="13" fill="var(--color-text)">
          {title}
        </text>
        {annotate("Upside", "#75d38f", spec.bull_case_value, -8)}
        {annotate("Base", "#79b8ff", spec.base_case_value, 4)}
        {annotate("Downside", "#f28b82", spec.bear_case_value, 16)}
        {!isNumber(spec.bear_case_value) &&
          annotate("Floor", "#d7b38a", spec.stress_case_value, 16)}
        {isNumber(spec.stress_case_value) &&
          annotate("Floor", "#d7b38a", spec.stress_case_value, 28)}
      </svg>
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
  title,
}: {
  spec: CmaPositioningChartSpec;
  title: string;
}) {
  const compValues = spec.comps
    .map((comp) => comp.ask_price)
    .filter(isNumber);
  const explicitChosen = spec.comps.filter((comp) => comp.feeds_fair_value != null);
  const chosenCount = explicitChosen.filter((comp) => comp.feeds_fair_value).length;
  const values = [
    spec.subject_ask,
    spec.fair_value_base,
    spec.value_low,
    spec.value_high,
    ...compValues,
  ];
  const bounds = chartBounds(values);
  const xForValue = (value: number) =>
    72 + ((value - bounds.min) / (bounds.max - bounds.min || 1)) * 500;
  const rowY = (index: number) => 64 + index * 28;
  return (
    <div>
      <svg
        viewBox={`0 0 ${SVG_W} ${Math.max(180, 120 + spec.comps.length * 28)}`}
        className="w-full"
      >
        <rect
          x="0"
          y="0"
          width={SVG_W}
          height={Math.max(180, 120 + spec.comps.length * 28)}
          rx="18"
          fill="var(--color-bg-sunken)"
        />
        {isNumber(spec.value_low) && isNumber(spec.value_high) && (
          <rect
            x={xForValue(spec.value_low)}
            y="28"
            width={Math.max(xForValue(spec.value_high) - xForValue(spec.value_low), 6)}
            height="18"
            rx="9"
            fill="rgba(121, 184, 255, 0.18)"
          />
        )}
        {isNumber(spec.fair_value_base) && (
          <line
            x1={xForValue(spec.fair_value_base)}
            y1="24"
            x2={xForValue(spec.fair_value_base)}
            y2={Math.max(150, 86 + spec.comps.length * 28)}
            stroke="#79b8ff"
            strokeDasharray="6 6"
          />
        )}
        {isNumber(spec.subject_ask) && (
          <line
            x1={xForValue(spec.subject_ask)}
            y1="24"
            x2={xForValue(spec.subject_ask)}
            y2={Math.max(150, 86 + spec.comps.length * 28)}
            stroke="#f28b82"
            strokeDasharray="3 5"
          />
        )}
        <text x="72" y="18" fontSize="13" fill="var(--color-text)">
          {title}
        </text>
        {isNumber(spec.fair_value_base) && (
          <text x={xForValue(spec.fair_value_base)} y="58" textAnchor="middle" fontSize="10" fill="#79b8ff">
            Fair value
          </text>
        )}
        {isNumber(spec.subject_ask) && (
          <text x={xForValue(spec.subject_ask)} y="72" textAnchor="middle" fontSize="10" fill="#f28b82">
            Ask
          </text>
        )}
        {spec.comps.map((comp, index) => {
          if (!isNumber(comp.ask_price)) return null;
          const y = rowY(index);
          const tone = comp.feeds_fair_value ? "#75d38f" : "#b8b2a4";
          return (
            <g key={`${comp.address ?? "comp"}-${index}`}>
              <text x="28" y={y + 4} fontSize="10" fill="var(--color-text-muted)">
                {comp.address?.slice(0, 18) ?? `Comp ${index + 1}`}
              </text>
              <circle cx={xForValue(comp.ask_price)} cy={y} r="6" fill={tone} />
              <text x={xForValue(comp.ask_price) + 10} y={y + 4} fontSize="10" fill="var(--color-text)">
                {money(comp.ask_price)}
              </text>
            </g>
          );
        })}
      </svg>
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
        <MetricChip
          label="Chosen comps"
          value={explicitChosen.length > 0 ? `${chosenCount} in model` : "Context only"}
          tone="emerald"
        />
      </div>
    </div>
  );
}

function RiskBarChart({
  spec,
  title,
}: {
  spec: RiskBarChartSpec;
  title: string;
}) {
  const max = Math.max(...spec.items.map((item) => item.value), 0.1);
  return (
    <div>
      <div className="rounded-2xl bg-[var(--color-bg-sunken)] p-4">
        <div className="text-[13px] font-medium text-[var(--color-text)]">
          {title}
        </div>
        <div className="mt-1 text-[12px] text-[var(--color-text-faint)]">
          Bear {money(spec.bear_value)} · Stress {money(spec.stress_value)}
        </div>
        <div className="mt-4 space-y-3">
          {spec.items.map((item) => (
            <div key={`${item.tone}-${item.label}`}>
              <div className="mb-1 flex items-center justify-between gap-3 text-[12px]">
                <span className="text-[var(--color-text-muted)]">{item.label}</span>
                <span className="text-[var(--color-text-faint)]">
                  {(item.value * 100).toFixed(0)} pts
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-[var(--color-surface)]">
                <div
                  className={cn(
                    "h-full rounded-full",
                    item.tone === "risk" ? "bg-rose-400/80" : "bg-amber-300/80",
                  )}
                  style={{ width: `${Math.max((item.value / max) * 100, 8)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function RentBurnChart({
  spec,
  title,
}: {
  spec: RentBurnChartSpec;
  title: string;
}) {
  const years = spec.points.map((point) => point.year);
  const values = spec.points.flatMap((point) => [
    point.rent_base,
    point.rent_bull,
    point.rent_bear,
    point.monthly_obligation,
  ]);
  const bounds = chartBounds(values);
  const xForIndex = (index: number) => {
    const step = years.length > 1 ? 520 / (years.length - 1) : 0;
    return 72 + index * step;
  };
  const yForValue = (value: number) =>
    230 - ((value - bounds.min) / (bounds.max - bounds.min || 1)) * 170;
  const basePath = spec.points.map((point) => point.rent_base);
  const bullPath = spec.points.map((point) => point.rent_bull);
  const bearPath = spec.points.map((point) => point.rent_bear);
  const obligationPath = spec.points.map((point) => point.monthly_obligation);
  const marketPath =
    isNumber(spec.market_rent) && spec.points.length > 0
      ? spec.points.map(() => spec.market_rent)
      : [];
  const marketLowPath =
    isNumber(spec.market_rent_low) && spec.points.length > 0
      ? spec.points.map(() => spec.market_rent_low)
      : [];
  const marketHighPath =
    isNumber(spec.market_rent_high) && spec.points.length > 0
      ? spec.points.map(() => spec.market_rent_high)
      : [];
  const band = areaPath(bullPath, bearPath, xForIndex, yForValue);
  const marketBand =
    marketLowPath.length > 0 && marketHighPath.length > 0
      ? areaPath(marketHighPath, marketLowPath, xForIndex, yForValue)
      : null;

  return (
    <div>
      <svg viewBox={`0 0 ${SVG_W} ${SVG_H}`} className="w-full">
        <rect
          x="0"
          y="0"
          width={SVG_W}
          height={SVG_H}
          rx="18"
          fill="var(--color-bg-sunken)"
        />
        {[0, 1, 2, 3].map((row) => {
          const y = 52 + row * 46;
          return (
            <line
              key={row}
              x1="64"
              y1={y}
              x2="592"
              y2={y}
              stroke="var(--color-border-subtle)"
              strokeDasharray="4 6"
            />
          );
        })}
        {band && (
          <path d={band} fill="rgba(103, 167, 255, 0.16)" stroke="none" />
        )}
        {marketBand && (
          <path d={marketBand} fill="rgba(214, 168, 92, 0.12)" stroke="none" />
        )}
        <path
          d={linePath(basePath, xForIndex, yForValue)}
          fill="none"
          stroke="#79b8ff"
          strokeWidth="4"
        />
        {marketPath.some(isNumber) && (
          <path
            d={linePath(marketPath, xForIndex, yForValue)}
            fill="none"
            stroke="#d6a85c"
            strokeWidth="2.5"
            strokeDasharray="5 6"
          />
        )}
        <path
          d={linePath(obligationPath, xForIndex, yForValue)}
          fill="none"
          stroke="#f28b82"
          strokeWidth="3"
          strokeDasharray="6 6"
        />
        <text x="72" y="26" fontSize="13" fill="var(--color-text)">
          {title}
        </text>
        {years.map((year, index) => (
          <text
            key={year}
            x={xForIndex(index)}
            y="262"
            textAnchor="middle"
            fontSize="11"
            fill="var(--color-text-faint)"
          >
            Y{year}
          </text>
        ))}
      </svg>
      <div className="mt-3 grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-3">
        <MetricChip
          label={spec.working_label ?? "Base rent"}
          value={money(spec.points[spec.points.length - 1]?.rent_base)}
          tone="sky"
        />
        <MetricChip
          label="Bull / Bear"
          value={`${money(spec.points[spec.points.length - 1]?.rent_bull)} / ${money(spec.points[spec.points.length - 1]?.rent_bear)}`}
        />
        <MetricChip
          label="Obligation"
          value={money(spec.points[spec.points.length - 1]?.monthly_obligation)}
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
  title,
}: {
  spec: RentRampChartSpec;
  title: string;
}) {
  const years = spec.points.map((point) => point.year);
  const values = spec.points.flatMap((point) => [
    point.net_0,
    point.net_3,
    point.net_5,
  ]);
  const bounds = chartBounds(values);
  const xForIndex = (index: number) => {
    const step = years.length > 1 ? 520 / (years.length - 1) : 0;
    return 72 + index * step;
  };
  const yForValue = (value: number) =>
    230 - ((value - bounds.min) / (bounds.max - bounds.min || 1)) * 170;
  const zeroPath = spec.points.map((point) => point.net_0);
  const basePath = spec.points.map((point) => point.net_3);
  const upsidePath = spec.points.map((point) => point.net_5);

  return (
    <div>
      <svg viewBox={`0 0 ${SVG_W} ${SVG_H}`} className="w-full">
        <rect
          x="0"
          y="0"
          width={SVG_W}
          height={SVG_H}
          rx="18"
          fill="var(--color-bg-sunken)"
        />
        {[0, 1, 2, 3].map((row) => {
          const y = 52 + row * 46;
          return (
            <line
              key={row}
              x1="64"
              y1={y}
              x2="592"
              y2={y}
              stroke="var(--color-border-subtle)"
              strokeDasharray="4 6"
            />
          );
        })}
        <line
          x1="64"
          y1={yForValue(0)}
          x2="592"
          y2={yForValue(0)}
          stroke="rgba(243,239,230,0.45)"
          strokeDasharray="6 6"
        />
        <path
          d={linePath(zeroPath, xForIndex, yForValue)}
          fill="none"
          stroke="rgba(184,178,164,0.85)"
          strokeWidth="2.5"
        />
        <path
          d={linePath(basePath, xForIndex, yForValue)}
          fill="none"
          stroke="#79b8ff"
          strokeWidth="4"
        />
        <path
          d={linePath(upsidePath, xForIndex, yForValue)}
          fill="none"
          stroke="#75d38f"
          strokeWidth="3"
          strokeDasharray="5 6"
        />
        <text x="72" y="26" fontSize="13" fill="var(--color-text)">
          {title}
        </text>
        {years.map((year, index) => (
          <text
            key={year}
            x={xForIndex(index)}
            y="262"
            textAnchor="middle"
            fontSize="11"
            fill="var(--color-text-faint)"
          >
            Y{year}
          </text>
        ))}
      </svg>
      <div className="mt-3 grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-4">
        <MetricChip label="Today rent" value={money(spec.current_rent)} tone="sky" />
        <MetricChip label="Monthly cost" value={money(spec.monthly_obligation)} />
        <MetricChip label="Today cash flow" value={money(spec.today_cash_flow)} tone={spec.today_cash_flow != null && spec.today_cash_flow < 0 ? "rose" : "emerald"} />
        <MetricChip
          label="Break-even"
          value={
            breakEvenLabel(spec.break_even_years?.["3"])
          }
        />
      </div>
    </div>
  );
}

function ValueOpportunityChart({
  spec,
  title,
}: {
  spec: ValueOpportunityChartSpec;
  title: string;
}) {
  const ask = spec.ask_price ?? null;
  const fair = spec.fair_value_base ?? null;
  const premium = spec.premium_discount_pct ?? null;
  const values = [ask, fair];
  const bounds = chartBounds(values);
  const xForValue = (value: number) =>
    56 + ((value - bounds.min) / (bounds.max - bounds.min || 1)) * 528;
  return (
    <div className="rounded-2xl bg-[var(--color-bg-sunken)] p-4">
      <div className="text-[13px] font-medium text-[var(--color-text)]">
        {title}
      </div>
      <div className="mt-1 text-[12px] text-[var(--color-text-faint)]">
        Ask {money(ask)} vs fair value {money(fair)} · {pct(premium)}
      </div>
      <svg viewBox={`0 0 ${SVG_W} 120`} className="mt-4 w-full">
        <line
          x1="56"
          y1="64"
          x2="584"
          y2="64"
          stroke="var(--color-border)"
          strokeWidth="10"
          strokeLinecap="round"
        />
        {isNumber(fair) && (
          <g>
            <circle cx={xForValue(fair)} cy="64" r="10" fill="#79b8ff" />
            <text
              x={xForValue(fair)}
              y="38"
              textAnchor="middle"
              fontSize="11"
              fill="var(--color-text)"
            >
              Fair
            </text>
          </g>
        )}
        {isNumber(ask) && (
          <g>
            <circle cx={xForValue(ask)} cy="64" r="10" fill="#f28b82" />
            <text
              x={xForValue(ask)}
              y="98"
              textAnchor="middle"
              fontSize="11"
              fill="var(--color-text)"
            >
              Ask
            </text>
          </g>
        )}
      </svg>
      {spec.value_drivers && spec.value_drivers.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
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
  title,
}: {
  spec: HorizontalBarWithRangesChartSpec;
  title: string;
}) {
  const scenarios = spec.scenarios.filter(
    (s) => isNumber(s.low) && isNumber(s.high) && isNumber(s.median),
  );
  if (scenarios.length === 0) return null;

  const unit = spec.unit ?? "";
  const rowHeight = 44;
  const topPad = 48;
  const bottomPad = 28;
  const leftPad = 140;
  const rightPad = 32;
  const chartWidth = SVG_W - leftPad - rightPad;
  const viewH = topPad + scenarios.length * rowHeight + bottomPad;

  const allValues = scenarios.flatMap((s) => [s.low, s.high, s.median]);
  const bounds = chartBounds(allValues);
  const xForValue = (value: number) =>
    leftPad + ((value - bounds.min) / (bounds.max - bounds.min || 1)) * chartWidth;
  const rowY = (index: number) => topPad + index * rowHeight + rowHeight / 2;

  const formatValue = (n: number) => {
    if (!isNumber(n)) return "—";
    const rounded = Math.round(n);
    return unit ? `${rounded}` : `$${rounded.toLocaleString()}`;
  };

  const emphasisId = spec.emphasis_scenario_id ?? null;

  return (
    <div>
      <svg viewBox={`0 0 ${SVG_W} ${viewH}`} className="w-full">
        <rect
          x="0"
          y="0"
          width={SVG_W}
          height={viewH}
          rx="18"
          fill="var(--color-bg-sunken)"
        />
        <text x={leftPad} y="22" fontSize="13" fill="var(--color-text)">
          {title}
        </text>
        {unit && (
          <text
            x={SVG_W - rightPad}
            y="22"
            textAnchor="end"
            fontSize="11"
            fill="var(--color-text-faint)"
          >
            {unit}
          </text>
        )}
        {scenarios.map((scenario, index) => {
          const isEmphasized = emphasisId != null && scenario.id === emphasisId;
          const isSubject = scenario.is_subject === true;
          const y = rowY(index);
          const x1 = xForValue(scenario.low);
          const x2 = xForValue(scenario.high);
          const xMed = xForValue(scenario.median);
          const barWidth = Math.max(x2 - x1, 6);

          const fillColor = isEmphasized
            ? "rgba(245, 197, 66, 0.35)"
            : isSubject
              ? "rgba(242, 139, 130, 0.22)"
              : "rgba(121, 184, 255, 0.20)";
          const strokeColor = isEmphasized
            ? "#f5c542"
            : isSubject
              ? "#f28b82"
              : "#79b8ff";
          const labelWeight = isEmphasized ? 600 : 500;

          return (
            <g key={scenario.id}>
              <text
                x={leftPad - 12}
                y={y + 4}
                textAnchor="end"
                fontSize="11"
                fontWeight={labelWeight}
                fill="var(--color-text)"
              >
                {scenario.label.slice(0, 22)}
              </text>
              <rect
                x={x1}
                y={y - 10}
                width={barWidth}
                height={20}
                rx="6"
                fill={fillColor}
                stroke={strokeColor}
                strokeWidth={isEmphasized ? 2 : 1}
              />
              <line
                x1={xMed}
                y1={y - 12}
                x2={xMed}
                y2={y + 12}
                stroke={strokeColor}
                strokeWidth="2"
              />
              <text
                x={x2 + 8}
                y={y + 4}
                fontSize="10"
                fill="var(--color-text-muted)"
              >
                {formatValue(scenario.median)}
                {isNumber(scenario.sample_size)
                  ? ` · n=${scenario.sample_size}`
                  : ""}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-[var(--color-text-faint)]">
        {scenarios.map((scenario) => {
          const isEmphasized = emphasisId != null && scenario.id === emphasisId;
          return (
            <span
              key={scenario.id}
              className={cn(
                "rounded-full border px-2 py-0.5",
                isEmphasized
                  ? "border-[#f5c542] text-[var(--color-text)]"
                  : "border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)]",
              )}
            >
              {scenario.label}: {formatValue(scenario.low)}–{formatValue(scenario.high)}
            </span>
          );
        })}
      </div>
    </div>
  );
}
