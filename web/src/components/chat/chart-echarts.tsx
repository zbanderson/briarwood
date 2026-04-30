"use client";

// Apache ECharts renderer for all eight `ChartSpec` kinds. Loaded via
// `next/dynamic({ ssr: false })` from `chart-frame.tsx` so the ECharts
// chunk arrives after the page is interactive — non-chart routes carry
// zero ECharts cost in their first-load chunks.
//
// One module-level option-builder per chart kind. The default-exported
// `ChartECharts` router switches on `spec.kind` and renders a single
// `<ReactECharts>` with the resolved `EChartsOption`. Colors resolve
// through `getChartTokens()` so chart palettes match the production
// CSS-var palette without per-chart hex duplication.
//
// `cma_positioning` additionally accepts `hoveredAddress` /
// `onHoverAddress` props for the eval-prototype hover-sync pattern; the
// chart self-highlights when a hovered address is set, and pushes
// hovered-marker addresses back up. The other seven chart kinds do not
// expose hover-sync (no production call sites consume it).

import { useEffect, useMemo, useRef } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import type {
  ChartSpec,
  ChartValueFormat,
  CmaPositioningChartSpec,
  HorizontalBarWithRangesChartSpec,
  MarketTrendChartSpec,
  RentBurnChartSpec,
  RentRampChartSpec,
  RiskBarChartSpec,
  ScenarioFanChartSpec,
  ValueOpportunityChartSpec,
} from "@/lib/chat/events";
import { getChartTokens, type ChartTokens } from "@/lib/chat/chart-tokens";

const DEFAULT_HEIGHT = 320;
const VALUE_OPPORTUNITY_HEIGHT = 200;

type Chrome = {
  xAxisLabel?: string | null;
  yAxisLabel?: string | null;
  valueFormat?: ChartValueFormat | null;
};

function isNumber(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

function tickMoney(n: number): string {
  if (!Number.isFinite(n)) return "";
  const abs = Math.abs(n);
  if (abs >= 1_000_000) {
    return `$${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
  }
  if (abs >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${Math.round(n).toLocaleString()}`;
}

function formatTick(value: number, format: ChartValueFormat | null | undefined) {
  if (!Number.isFinite(value)) return "";
  if (format === "percent") {
    const pctValue = value * 100;
    return `${Math.abs(pctValue) >= 10 ? pctValue.toFixed(0) : pctValue.toFixed(1)}%`;
  }
  if (format === "count") return Math.round(value).toLocaleString();
  return tickMoney(value);
}

// ---------------------------------------------------------------------
// cma_positioning
// ---------------------------------------------------------------------

type PricedComp = CmaPositioningChartSpec["comps"][number] & { ask_price: number };

function buildCmaOption(
  spec: CmaPositioningChartSpec,
  chrome: Chrome,
  tokens: ChartTokens,
  priced: PricedComp[],
): EChartsOption {
  const addresses = priced.map((c) => c.address ?? "—").slice().reverse();
  const rowsByStatus = (
    matchActive: boolean,
    matchCrossTown: boolean,
  ): Array<[number, string]> =>
    priced
      .filter((c) => {
        const isActive = c.listing_status === "active";
        if (matchActive) return isActive;
        const isCrossTown = !isActive && Boolean(c.is_cross_town);
        if (matchCrossTown) return !isActive && isCrossTown;
        return !isActive && !isCrossTown;
      })
      .map((c) => [c.ask_price, c.address ?? "—"]);

  const option: EChartsOption = {
    backgroundColor: tokens.bgSunken,
    grid: { left: 100, right: 24, top: 36, bottom: 44 },
    tooltip: {
      trigger: "item",
      backgroundColor: tokens.surface,
      borderColor: tokens.borderSubtle,
      textStyle: { color: tokens.text, fontSize: 11 },
      formatter: (raw) => {
        const arr = raw as unknown as { value: [number, string] };
        const [ask, addr] = arr.value;
        return `<div style="font-weight:500">${addr}</div><div style="color:${tokens.textMuted}">${tickMoney(ask)}</div>`;
      },
    },
    xAxis: {
      type: "value",
      name: chrome.xAxisLabel ?? "Ask price",
      nameLocation: "middle",
      nameGap: 26,
      nameTextStyle: { color: tokens.textFaint, fontSize: 10 },
      axisLabel: {
        color: tokens.textFaint,
        fontSize: 10,
        formatter: (v: number) => tickMoney(v),
      },
      splitLine: { lineStyle: { color: tokens.grid, type: [4, 6] } },
      axisLine: { show: false },
    },
    yAxis: {
      type: "category",
      data: addresses,
      name: chrome.yAxisLabel ?? "Comp",
      nameLocation: "middle",
      nameGap: 84,
      nameRotate: 90,
      nameTextStyle: { color: tokens.textFaint, fontSize: 10 },
      axisLabel: {
        color: tokens.textMuted,
        fontSize: 10,
        formatter: (v: string) => v.slice(0, 16),
      },
      axisTick: { show: false },
      axisLine: { show: false },
    },
    series: [
      {
        name: "SOLD",
        type: "scatter",
        data: rowsByStatus(false, false),
        symbol: "circle",
        symbolSize: 12,
        itemStyle: { color: tokens.bull },
        emphasis: {
          itemStyle: {
            color: tokens.bull,
            borderColor: tokens.text,
            borderWidth: 2,
          },
        },
        markLine: {
          symbol: "none",
          silent: true,
          lineStyle: { color: tokens.base, type: [6, 6] },
          label: {
            position: "end",
            color: tokens.base,
            fontSize: 10,
            formatter: "Fair value",
          },
          data:
            typeof spec.fair_value_base === "number"
              ? [{ xAxis: spec.fair_value_base }]
              : [],
        },
        markArea:
          typeof spec.value_low === "number" &&
          typeof spec.value_high === "number"
            ? {
                silent: true,
                itemStyle: { color: tokens.base, opacity: 0.12 },
                data: [
                  [{ xAxis: spec.value_low }, { xAxis: spec.value_high }],
                ],
              }
            : undefined,
      },
      {
        name: "Cross-town SOLD",
        type: "scatter",
        data: rowsByStatus(false, true),
        symbol: "circle",
        symbolSize: 12,
        itemStyle: {
          color: tokens.bull,
          borderColor: tokens.base,
          borderType: [2, 2],
          borderWidth: 1.5,
        },
      },
      {
        name: "ACTIVE",
        type: "scatter",
        data: rowsByStatus(true, false),
        symbol: "triangle",
        symbolSize: 12,
        itemStyle: {
          color: "transparent",
          borderColor: tokens.neutral,
          borderWidth: 1.5,
        },
        emphasis: { itemStyle: { borderWidth: 2.5 } },
        markLine:
          typeof spec.subject_ask === "number"
            ? {
                symbol: "none",
                silent: true,
                lineStyle: { color: tokens.bear, type: [3, 5] },
                label: {
                  position: "end",
                  color: tokens.bear,
                  fontSize: 10,
                  formatter: "Ask",
                },
                data: [{ xAxis: spec.subject_ask }],
              }
            : undefined,
      },
    ],
  };

  return option;
}

// ---------------------------------------------------------------------
// scenario_fan — bull/base/bear/stress fan over years 0..5 with a
// shaded band between bull and bear. ECharts fills "between two
// lines" via a stack pair: the lower bound (bear) renders with a
// transparent area, the upper-minus-lower delta stacks on top with a
// translucent fill, producing the visual band without a custom series.
// ---------------------------------------------------------------------

function buildScenarioFanOption(
  spec: ScenarioFanChartSpec,
  chrome: Chrome,
  tokens: ChartTokens,
): EChartsOption {
  const years = [0, 1, 2, 3, 4, 5];
  const labels = years.map((y) => (y === 0 ? "Today" : `Y${y}`));
  const ask = spec.ask_price ?? null;
  const project = (target: number | null | undefined): Array<number | null> =>
    years.map((y) => {
      if (!isNumber(ask) || !isNumber(target)) return null;
      return ask + (target - ask) * (y / 5);
    });
  const bull = project(spec.bull_case_value);
  const base = project(spec.base_case_value);
  const bear = project(spec.bear_case_value);
  const stress = project(spec.stress_case_value);
  const bullBearDelta = bull.map((b, i) => {
    const bb = bear[i];
    if (b == null || bb == null) return null;
    return b - bb;
  });

  const series: EChartsOption["series"] = [
    {
      name: "_band_lower",
      type: "line",
      data: bear,
      stack: "fan",
      lineStyle: { opacity: 0 },
      areaStyle: { color: "transparent" },
      symbol: "none",
      silent: true,
      tooltip: { show: false },
      z: 1,
    },
    {
      name: "_band_fill",
      type: "line",
      data: bullBearDelta,
      stack: "fan",
      lineStyle: { opacity: 0 },
      areaStyle: { color: tokens.base, opacity: 0.16 },
      symbol: "none",
      silent: true,
      tooltip: { show: false },
      z: 1,
    },
    {
      name: "Bull",
      type: "line",
      data: bull,
      smooth: false,
      symbol: "circle",
      symbolSize: 6,
      lineStyle: { color: tokens.bull, width: 3, type: [5, 6] },
      itemStyle: { color: tokens.bull },
      z: 3,
      endLabel: isNumber(spec.bull_case_value)
        ? {
            show: true,
            formatter: "Upside",
            color: tokens.text,
            fontSize: 10,
          }
        : undefined,
    },
    {
      name: "Base",
      type: "line",
      data: base,
      smooth: false,
      symbol: "circle",
      symbolSize: 6,
      lineStyle: { color: tokens.base, width: 4 },
      itemStyle: { color: tokens.base },
      z: 4,
      endLabel: isNumber(spec.base_case_value)
        ? {
            show: true,
            formatter: "Base",
            color: tokens.text,
            fontSize: 10,
          }
        : undefined,
    },
    {
      name: "Bear",
      type: "line",
      data: bear,
      smooth: false,
      symbol: "circle",
      symbolSize: 6,
      lineStyle: { color: tokens.bear, width: 3, type: [5, 6] },
      itemStyle: { color: tokens.bear },
      z: 3,
      endLabel: isNumber(spec.bear_case_value)
        ? {
            show: true,
            formatter: "Downside",
            color: tokens.text,
            fontSize: 10,
          }
        : undefined,
    },
  ];
  if (stress.some(isNumber)) {
    series.push({
      name: "Stress",
      type: "line",
      data: stress,
      smooth: false,
      symbol: "circle",
      symbolSize: 5,
      lineStyle: { color: tokens.stress, width: 2, type: [2, 6] },
      itemStyle: { color: tokens.stress },
      z: 2,
      endLabel: isNumber(spec.stress_case_value)
        ? {
            show: true,
            formatter: "Floor",
            color: tokens.text,
            fontSize: 10,
          }
        : undefined,
    });
  }

  return {
    backgroundColor: tokens.bgSunken,
    grid: { left: 64, right: 80, top: 24, bottom: 44 },
    tooltip: {
      trigger: "axis",
      backgroundColor: tokens.surface,
      borderColor: tokens.borderSubtle,
      textStyle: { color: tokens.text, fontSize: 11 },
      valueFormatter: (v) =>
        isNumber(v) ? formatTick(v, chrome.valueFormat) : "—",
    },
    xAxis: {
      type: "category",
      data: labels,
      boundaryGap: false,
      name: chrome.xAxisLabel ?? undefined,
      nameLocation: "middle",
      nameGap: 26,
      nameTextStyle: { color: tokens.textFaint, fontSize: 10 },
      axisLabel: { color: tokens.textFaint, fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      name: chrome.yAxisLabel ?? undefined,
      nameLocation: "middle",
      nameGap: 56,
      nameRotate: 90,
      nameTextStyle: { color: tokens.textFaint, fontSize: 10 },
      axisLabel: {
        color: tokens.textFaint,
        fontSize: 9,
        formatter: (v: number) => formatTick(v, chrome.valueFormat),
      },
      splitLine: { lineStyle: { color: tokens.grid, type: [4, 6] } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series,
  };
}

// ---------------------------------------------------------------------
// market_trend — single line + three anchor markers (Now / 1y / 3y)
// ---------------------------------------------------------------------

function buildMarketTrendOption(
  spec: MarketTrendChartSpec,
  chrome: Chrome,
  tokens: ChartTokens,
): EChartsOption {
  const points = spec.points ?? [];
  const data = points.map((p) => p.value);
  const labels = points.map((p) => (p.date ?? "").slice(0, 7));

  const lastIdx = points.length - 1;
  const oneYearIdx = points.length > 12 ? lastIdx - 12 : 0;
  const threeYearIdx = points.length > 36 ? lastIdx - 36 : 0;

  const yearLabel = (date: string | undefined) =>
    typeof date === "string" && date.length >= 4 ? date.slice(0, 4) : "";

  const markPointData: Array<{
    coord: [number, number];
    name: string;
    itemStyle: { color: string };
    label: { color: string; formatter: string };
  }> = [];
  const pushMark = (idx: number, name: string, color: string) => {
    if (idx < 0 || idx > lastIdx) return;
    const v = points[idx]?.value;
    if (!isNumber(v)) return;
    markPointData.push({
      coord: [idx, v],
      name,
      itemStyle: { color },
      label: { color, formatter: name },
    });
  };
  pushMark(threeYearIdx, "3y", tokens.neutral);
  pushMark(oneYearIdx, "1y", tokens.stress);
  pushMark(lastIdx, "Now", tokens.bull);

  const tickStride = Math.max(1, Math.floor(points.length / 5));

  return {
    backgroundColor: tokens.bgSunken,
    grid: { left: 64, right: 32, top: 24, bottom: 44 },
    tooltip: {
      trigger: "axis",
      backgroundColor: tokens.surface,
      borderColor: tokens.borderSubtle,
      textStyle: { color: tokens.text, fontSize: 11 },
      valueFormatter: (v) =>
        isNumber(v) ? formatTick(v, chrome.valueFormat) : "—",
    },
    xAxis: {
      type: "category",
      data: labels,
      boundaryGap: false,
      name: chrome.xAxisLabel ?? undefined,
      nameLocation: "middle",
      nameGap: 26,
      nameTextStyle: { color: tokens.textFaint, fontSize: 10 },
      axisLabel: {
        color: tokens.textFaint,
        fontSize: 11,
        interval: tickStride - 1,
        formatter: (v: string) => yearLabel(v),
      },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      name: chrome.yAxisLabel ?? undefined,
      nameLocation: "middle",
      nameGap: 56,
      nameRotate: 90,
      nameTextStyle: { color: tokens.textFaint, fontSize: 10 },
      axisLabel: {
        color: tokens.textFaint,
        fontSize: 9,
        formatter: (v: number) => formatTick(v, chrome.valueFormat),
      },
      splitLine: { lineStyle: { color: tokens.grid, type: [4, 6] } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: "line",
        data,
        smooth: false,
        showSymbol: false,
        lineStyle: { color: tokens.base, width: 3 },
        itemStyle: { color: tokens.base },
        markPoint: {
          symbol: "circle",
          symbolSize: 9,
          data: markPointData,
          label: {
            show: true,
            position: "top",
            distance: 6,
            fontSize: 10,
          },
        },
      },
    ],
  };
}

// ---------------------------------------------------------------------
// risk_bar — horizontal bars; `tone` keys color (risk → rose, trust →
// amber). Values are penalty shares in [0, 1].
// ---------------------------------------------------------------------

const ROSE = "rgba(244, 113, 113, 0.85)";
const AMBER = "rgba(252, 211, 77, 0.85)";

function buildRiskBarOption(
  spec: RiskBarChartSpec,
  _chrome: Chrome,
  tokens: ChartTokens,
): EChartsOption {
  const items = [...spec.items].reverse();
  const labels = items.map((i) => i.label);
  const data = items.map((i) => ({
    value: i.value,
    itemStyle: { color: i.tone === "risk" ? ROSE : AMBER, borderRadius: 4 },
  }));

  return {
    backgroundColor: tokens.bgSunken,
    grid: { left: 140, right: 64, top: 16, bottom: 32 },
    tooltip: {
      trigger: "item",
      backgroundColor: tokens.surface,
      borderColor: tokens.borderSubtle,
      textStyle: { color: tokens.text, fontSize: 11 },
      formatter: (raw) => {
        const r = raw as unknown as { name: string; value: number };
        return `<div style="font-weight:500">${r.name}</div><div style="color:${tokens.textMuted}">${(r.value * 100).toFixed(0)} pts</div>`;
      },
    },
    xAxis: {
      type: "value",
      max: 1,
      axisLabel: {
        color: tokens.textFaint,
        fontSize: 9,
        formatter: (v: number) => `${(v * 100).toFixed(0)}%`,
      },
      splitLine: { lineStyle: { color: tokens.grid, type: [4, 6] } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: "category",
      data: labels,
      axisLabel: { color: tokens.textMuted, fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: "bar",
        data,
        barWidth: 12,
        label: {
          show: true,
          position: "right",
          color: tokens.textFaint,
          fontSize: 10,
          formatter: (p) => {
            const v = (p as unknown as { value: number }).value;
            return `${(v * 100).toFixed(0)} pts`;
          },
        },
      },
    ],
  };
}

// ---------------------------------------------------------------------
// rent_burn — base rent + bull/bear band + market band + monthly
// obligation overlay across years.
// ---------------------------------------------------------------------

function buildRentBurnOption(
  spec: RentBurnChartSpec,
  chrome: Chrome,
  tokens: ChartTokens,
): EChartsOption {
  const points = spec.points ?? [];
  const labels = points.map((p) => `Y${p.year}`);
  const base = points.map((p) => p.rent_base ?? null);
  const bull = points.map((p) => p.rent_bull ?? null);
  const bear = points.map((p) => p.rent_bear ?? null);
  const obligation = points.map((p) => p.monthly_obligation ?? null);
  const market = isNumber(spec.market_rent)
    ? points.map(() => spec.market_rent ?? null)
    : null;

  const bullBearDelta = bull.map((b, i) => {
    const bb = bear[i];
    if (b == null || bb == null) return null;
    return b - bb;
  });

  const series: EChartsOption["series"] = [
    {
      name: "_band_lower",
      type: "line",
      data: bear,
      stack: "scenario_band",
      lineStyle: { opacity: 0 },
      areaStyle: { color: "transparent" },
      symbol: "none",
      silent: true,
      tooltip: { show: false },
      z: 1,
    },
    {
      name: "_band_fill",
      type: "line",
      data: bullBearDelta,
      stack: "scenario_band",
      lineStyle: { opacity: 0 },
      areaStyle: { color: tokens.base, opacity: 0.16 },
      symbol: "none",
      silent: true,
      tooltip: { show: false },
      z: 1,
    },
    {
      name: spec.working_label ?? "Base rent",
      type: "line",
      data: base,
      smooth: false,
      symbol: "none",
      lineStyle: { color: tokens.base, width: 4 },
      z: 4,
    },
    {
      name: "Obligation",
      type: "line",
      data: obligation,
      smooth: false,
      symbol: "none",
      lineStyle: { color: tokens.bear, width: 3, type: [6, 6] },
      z: 3,
    },
  ];
  if (market) {
    series.push({
      name: spec.market_label ?? "Market",
      type: "line",
      data: market,
      smooth: false,
      symbol: "none",
      lineStyle: { color: tokens.stress, width: 2.5, type: [5, 6] },
      z: 2,
    });
    if (
      isNumber(spec.market_rent_low) &&
      isNumber(spec.market_rent_high) &&
      points.length > 0
    ) {
      const lowConst = points.map(() => spec.market_rent_low ?? null);
      const deltaConst = points.map(() =>
        isNumber(spec.market_rent_low) && isNumber(spec.market_rent_high)
          ? spec.market_rent_high - spec.market_rent_low
          : null,
      );
      series.unshift(
        {
          name: "_market_low",
          type: "line",
          data: lowConst,
          stack: "market_band",
          lineStyle: { opacity: 0 },
          areaStyle: { color: "transparent" },
          symbol: "none",
          silent: true,
          tooltip: { show: false },
          z: 1,
        },
        {
          name: "_market_fill",
          type: "line",
          data: deltaConst,
          stack: "market_band",
          lineStyle: { opacity: 0 },
          areaStyle: { color: tokens.stress, opacity: 0.12 },
          symbol: "none",
          silent: true,
          tooltip: { show: false },
          z: 1,
        },
      );
    }
  }

  return {
    backgroundColor: tokens.bgSunken,
    grid: { left: 64, right: 32, top: 24, bottom: 44 },
    tooltip: {
      trigger: "axis",
      backgroundColor: tokens.surface,
      borderColor: tokens.borderSubtle,
      textStyle: { color: tokens.text, fontSize: 11 },
      valueFormatter: (v) =>
        isNumber(v) ? formatTick(v, chrome.valueFormat) : "—",
    },
    xAxis: {
      type: "category",
      data: labels,
      boundaryGap: false,
      name: chrome.xAxisLabel ?? undefined,
      nameLocation: "middle",
      nameGap: 26,
      nameTextStyle: { color: tokens.textFaint, fontSize: 10 },
      axisLabel: { color: tokens.textFaint, fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      name: chrome.yAxisLabel ?? undefined,
      nameLocation: "middle",
      nameGap: 56,
      nameRotate: 90,
      nameTextStyle: { color: tokens.textFaint, fontSize: 10 },
      axisLabel: {
        color: tokens.textFaint,
        fontSize: 9,
        formatter: (v: number) => formatTick(v, chrome.valueFormat),
      },
      splitLine: { lineStyle: { color: tokens.grid, type: [4, 6] } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series,
  };
}

// ---------------------------------------------------------------------
// rent_ramp — three lines (0% / 3% / 5% rent escalation) + zero-line
// reference for break-even visibility.
// ---------------------------------------------------------------------

function buildRentRampOption(
  spec: RentRampChartSpec,
  chrome: Chrome,
  tokens: ChartTokens,
): EChartsOption {
  const points = spec.points ?? [];
  const labels = points.map((p) => `Y${p.year}`);
  const zero = points.map((p) => p.net_0 ?? null);
  const base = points.map((p) => p.net_3 ?? null);
  const upside = points.map((p) => p.net_5 ?? null);

  return {
    backgroundColor: tokens.bgSunken,
    grid: { left: 64, right: 32, top: 24, bottom: 44 },
    tooltip: {
      trigger: "axis",
      backgroundColor: tokens.surface,
      borderColor: tokens.borderSubtle,
      textStyle: { color: tokens.text, fontSize: 11 },
      valueFormatter: (v) =>
        isNumber(v) ? formatTick(v, chrome.valueFormat) : "—",
    },
    xAxis: {
      type: "category",
      data: labels,
      boundaryGap: false,
      name: chrome.xAxisLabel ?? undefined,
      nameLocation: "middle",
      nameGap: 26,
      nameTextStyle: { color: tokens.textFaint, fontSize: 10 },
      axisLabel: { color: tokens.textFaint, fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      name: chrome.yAxisLabel ?? undefined,
      nameLocation: "middle",
      nameGap: 56,
      nameRotate: 90,
      nameTextStyle: { color: tokens.textFaint, fontSize: 10 },
      axisLabel: {
        color: tokens.textFaint,
        fontSize: 9,
        formatter: (v: number) => formatTick(v, chrome.valueFormat),
      },
      splitLine: { lineStyle: { color: tokens.grid, type: [4, 6] } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        name: "0% rent escalation",
        type: "line",
        data: zero,
        smooth: false,
        symbol: "none",
        lineStyle: { color: tokens.neutral, width: 2.5 },
        markLine: {
          symbol: "none",
          silent: true,
          lineStyle: { color: tokens.text, opacity: 0.4, type: [6, 6] },
          data: [{ yAxis: 0 }],
          label: { show: false },
        },
      },
      {
        name: "3% rent escalation",
        type: "line",
        data: base,
        smooth: false,
        symbol: "none",
        lineStyle: { color: tokens.base, width: 4 },
      },
      {
        name: "5% rent escalation",
        type: "line",
        data: upside,
        smooth: false,
        symbol: "none",
        lineStyle: { color: tokens.bull, width: 3, type: [5, 6] },
      },
    ],
  };
}

// ---------------------------------------------------------------------
// value_opportunity — single horizontal axis with two annotated dots
// (Fair value, Ask). Closes §3.4.2 — the y-axis label rotation that
// caused vertical-character stacks in the native renderer is replaced
// by ECharts' declarative `nameRotate` (we don't expose a y-axis label
// at all here; the chart is a number line, and the orphaned y axis is
// suppressed).
// ---------------------------------------------------------------------

function buildValueOpportunityOption(
  spec: ValueOpportunityChartSpec,
  chrome: Chrome,
  tokens: ChartTokens,
): EChartsOption {
  const ask = spec.ask_price ?? null;
  const fair = spec.fair_value_base ?? null;

  const data: Array<{
    value: [number, string];
    label: { color: string; formatter: string };
    itemStyle: { color: string };
  }> = [];
  if (isNumber(fair)) {
    data.push({
      value: [fair, "row"],
      label: { color: tokens.base, formatter: "Fair" },
      itemStyle: { color: tokens.base },
    });
  }
  if (isNumber(ask)) {
    data.push({
      value: [ask, "row"],
      label: { color: tokens.bear, formatter: "Ask" },
      itemStyle: { color: tokens.bear },
    });
  }

  return {
    backgroundColor: tokens.bgSunken,
    grid: { left: 32, right: 32, top: 56, bottom: 64 },
    tooltip: {
      trigger: "item",
      backgroundColor: tokens.surface,
      borderColor: tokens.borderSubtle,
      textStyle: { color: tokens.text, fontSize: 11 },
      formatter: (raw) => {
        const r = raw as unknown as {
          value: [number, string];
          label: { formatter: string };
        };
        return `<div style="font-weight:500">${r.label.formatter}</div><div style="color:${tokens.textMuted}">${formatTick(r.value[0], chrome.valueFormat)}</div>`;
      },
    },
    xAxis: {
      type: "value",
      name: chrome.xAxisLabel ?? undefined,
      nameLocation: "middle",
      nameGap: 26,
      nameTextStyle: { color: tokens.textFaint, fontSize: 10 },
      axisLabel: {
        color: tokens.textFaint,
        fontSize: 10,
        formatter: (v: number) => formatTick(v, chrome.valueFormat),
      },
      splitLine: { lineStyle: { color: tokens.grid, type: [4, 6] } },
      axisLine: { lineStyle: { color: tokens.grid } },
    },
    yAxis: {
      type: "category",
      data: ["row"],
      show: false,
    },
    series: [
      {
        type: "scatter",
        data,
        symbol: "circle",
        symbolSize: 22,
        emphasis: {
          itemStyle: { borderColor: tokens.text, borderWidth: 2 },
        },
        label: {
          show: true,
          position: "top",
          distance: 12,
          fontSize: 12,
          fontWeight: 500,
          formatter: (p) => {
            const r = p as unknown as { data: { label: { formatter: string } } };
            return r.data.label.formatter;
          },
        },
      },
    ],
  };
}

// ---------------------------------------------------------------------
// horizontal_bar_with_ranges — one row per scenario; each row is a
// translucent bar from low→high with a median tick. Subject scenarios
// render in `bear` tone, emphasized scenarios in `stress` tone, others
// in `base`. Marker class = "tick on a range bar" handled declaratively
// via two stacked bar series + a custom medianline series.
// ---------------------------------------------------------------------

function buildHorizontalBarWithRangesOption(
  spec: HorizontalBarWithRangesChartSpec,
  chrome: Chrome,
  tokens: ChartTokens,
): EChartsOption {
  const scenarios = spec.scenarios.filter(
    (s) => isNumber(s.low) && isNumber(s.high) && isNumber(s.median),
  );
  const reversed = [...scenarios].reverse();
  const labels = reversed.map((s) => s.label.slice(0, 22));
  const emphasisId = spec.emphasis_scenario_id ?? null;

  const colorFor = (s: HorizontalBarWithRangesChartSpec["scenarios"][number]) => {
    if (emphasisId != null && s.id === emphasisId) return tokens.stress;
    if (s.is_subject === true) return tokens.bear;
    return tokens.base;
  };
  const fillFor = (s: HorizontalBarWithRangesChartSpec["scenarios"][number]) => {
    const stroke = colorFor(s);
    return { color: stroke, opacity: 0.22 };
  };

  const lowOffset = reversed.map((s) => s.low);
  const ranges = reversed.map((s) => ({
    value: s.high - s.low,
    itemStyle: {
      color: fillFor(s).color,
      opacity: fillFor(s).opacity,
      borderColor: colorFor(s),
      borderWidth: emphasisId != null && s.id === emphasisId ? 2 : 1,
    },
  }));
  const medianMarkData = reversed.flatMap((s, i) => {
    const stroke = colorFor(s);
    return [
      [
        { coord: [s.median, i], lineStyle: { color: stroke, width: 2 } },
        { coord: [s.median, i], lineStyle: { color: stroke, width: 2 } },
      ],
    ];
  });
  // Median line markers are rendered via a thin scatter with a vertical
  // bar symbol so each row has a tick at its median.
  const medianTicks = reversed.map((s) => ({
    value: [s.median, s.label.slice(0, 22)] as [number, string],
    itemStyle: { color: colorFor(s) },
  }));

  const unit = spec.unit ?? "";
  const formatVal = (v: number) =>
    unit ? `${Math.round(v)}` : `$${Math.round(v).toLocaleString()}`;

  return {
    backgroundColor: tokens.bgSunken,
    grid: { left: 140, right: 80, top: 32, bottom: 44 },
    tooltip: {
      trigger: "item",
      backgroundColor: tokens.surface,
      borderColor: tokens.borderSubtle,
      textStyle: { color: tokens.text, fontSize: 11 },
      formatter: (raw) => {
        const r = raw as unknown as { name: string; value: number | unknown[] };
        const value = Array.isArray(r.value) ? (r.value[0] as number) : r.value;
        const orig = reversed.find((s) => s.label.slice(0, 22) === r.name);
        if (!orig) return `${r.name}: ${formatVal(value)}`;
        const sample = isNumber(orig.sample_size) ? ` · n=${orig.sample_size}` : "";
        return `<div style="font-weight:500">${orig.label}</div><div style="color:${tokens.textMuted}">${formatVal(orig.low)}–${formatVal(orig.high)} · median ${formatVal(orig.median)}${sample}</div>`;
      },
    },
    xAxis: {
      type: "value",
      name: chrome.xAxisLabel ?? undefined,
      nameLocation: "middle",
      nameGap: 26,
      nameTextStyle: { color: tokens.textFaint, fontSize: 10 },
      axisLabel: {
        color: tokens.textFaint,
        fontSize: 9,
        formatter: (v: number) => formatVal(v),
      },
      splitLine: { lineStyle: { color: tokens.grid, type: [4, 6] } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: "category",
      data: labels,
      axisLabel: { color: tokens.textMuted, fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        name: "_offset",
        type: "bar",
        stack: "range",
        data: lowOffset,
        itemStyle: { color: "transparent" },
        silent: true,
        tooltip: { show: false },
        barWidth: 18,
        z: 1,
      },
      {
        name: "Range",
        type: "bar",
        stack: "range",
        data: ranges,
        barWidth: 18,
        z: 2,
        markLine: {
          symbol: "none",
          silent: true,
          lineStyle: { width: 0 },
          data: medianMarkData as unknown as never,
        },
        label: {
          show: true,
          position: "right",
          color: tokens.textMuted,
          fontSize: 10,
          formatter: (p) => {
            const r = p as unknown as { name: string };
            const orig = reversed.find((s) => s.label.slice(0, 22) === r.name);
            if (!orig) return "";
            const sample = isNumber(orig.sample_size) ? ` · n=${orig.sample_size}` : "";
            return `${formatVal(orig.median)}${sample}`;
          },
        },
      },
      {
        name: "Median",
        type: "scatter",
        data: medianTicks,
        symbol: "rect",
        symbolSize: [3, 22],
        z: 3,
        tooltip: { show: false },
      },
    ],
  };
}

// ---------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------

type RouterProps = {
  spec: ChartSpec;
  chrome: Chrome;
  hoveredAddress?: string | null;
  onHoverAddress?: (address: string | null) => void;
};

export default function ChartECharts({
  spec,
  chrome,
  hoveredAddress = null,
  onHoverAddress,
}: RouterProps) {
  const ref = useRef<ReactECharts>(null);
  const tokens = getChartTokens();

  // `priced` is the source of truth for hover-sync indexing on
  // `cma_positioning`. Memoize so the useEffect deps don't churn each
  // render — the array identity stays stable until `spec.comps` changes.
  const priced = useMemo<PricedComp[]>(() => {
    if (spec.kind !== "cma_positioning") return [];
    return spec.comps.filter(
      (c): c is PricedComp =>
        typeof c.ask_price === "number" && Number.isFinite(c.ask_price),
    );
  }, [spec]);

  let option: EChartsOption | null = null;
  let height = DEFAULT_HEIGHT;

  if (spec.kind === "cma_positioning") {
    option = buildCmaOption(spec, chrome, tokens, priced);
  } else if (spec.kind === "scenario_fan") {
    option = buildScenarioFanOption(spec, chrome, tokens);
  } else if (spec.kind === "market_trend") {
    option = buildMarketTrendOption(spec, chrome, tokens);
  } else if (spec.kind === "risk_bar") {
    option = buildRiskBarOption(spec, chrome, tokens);
  } else if (spec.kind === "rent_burn") {
    option = buildRentBurnOption(spec, chrome, tokens);
  } else if (spec.kind === "rent_ramp") {
    option = buildRentRampOption(spec, chrome, tokens);
  } else if (spec.kind === "value_opportunity") {
    option = buildValueOpportunityOption(spec, chrome, tokens);
    height = VALUE_OPPORTUNITY_HEIGHT;
  } else if (spec.kind === "horizontal_bar_with_ranges") {
    option = buildHorizontalBarWithRangesOption(spec, chrome, tokens);
    const rows = spec.scenarios.filter(
      (s) => isNumber(s.low) && isNumber(s.high) && isNumber(s.median),
    ).length;
    height = Math.max(180, 56 + rows * 36);
  }

  // CMA hover-sync wiring (eval-prototype pattern). Other chart kinds
  // ignore `hoveredAddress` and never wire `onHoverAddress`.
  useEffect(() => {
    const inst = ref.current?.getEchartsInstance();
    if (!inst) return;
    if (spec.kind !== "cma_positioning") return;
    inst.dispatchAction({ type: "downplay" });
    if (hoveredAddress == null) return;
    const idx = priced.findIndex((c) => c.address === hoveredAddress);
    if (idx < 0) return;
    inst.dispatchAction({
      type: "highlight",
      seriesIndex: 0,
      dataIndex: idx,
    });
  }, [hoveredAddress, priced, spec.kind]);

  const onEvents =
    spec.kind === "cma_positioning" && onHoverAddress
      ? {
          mouseover: (p: { value?: unknown }) => {
            const v = p.value as [number, string] | undefined;
            if (Array.isArray(v) && typeof v[1] === "string") {
              onHoverAddress(v[1]);
            }
          },
          mouseout: () => onHoverAddress(null),
        }
      : undefined;

  if (!option) return null;

  return (
    <div
      className="rounded-2xl"
      style={{ background: tokens.bgSunken, height }}
    >
      <ReactECharts
        ref={ref}
        option={option}
        style={{ height: "100%", width: "100%" }}
        opts={{ renderer: "svg" }}
        onEvents={onEvents}
        notMerge
      />
    </div>
  );
}
