import type {
  ChartEvent,
  ChartSpec,
  CmaPositioningChartSpec,
  RentBurnChartSpec,
  RentRampChartSpec,
  RiskBarChartSpec,
  ScenarioFanChartSpec,
  ValueOpportunityChartSpec,
} from "./events";

type ChartSurface = {
  title?: string;
  summary?: string | null;
  companion?: string | null;
  shouldRender: boolean;
};

function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function money(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return null;
  return `$${Math.round(n).toLocaleString()}`;
}

function pct(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return null;
  const sign = n >= 0 ? "+" : "";
  return `${sign}${(n * 100).toFixed(1)}%`;
}

function chartTitle(chart: ChartEvent) {
  if (chart.title) return chart.title;
  if (chart.kind) {
    return chart.kind
      .split("_")
      .map((w) => w[0]?.toUpperCase() + w.slice(1))
      .join(" ");
  }
  return "Chart";
}

function valueSurface(spec: ValueOpportunityChartSpec): ChartSurface {
  const ask = spec.ask_price ?? null;
  const fair = spec.fair_value_base ?? null;
  const premium = spec.premium_discount_pct ?? null;
  const shouldRender = isNumber(ask) && isNumber(fair);
  if (!shouldRender) return { shouldRender: false };

  let summary: string | null = null;
  if (isNumber(premium)) {
    if (premium > 0.01) {
      summary = `The current ask is running ${pct(premium)} above Briarwood's fair value read.`;
    } else if (premium < -0.01) {
      summary = `The current ask is landing ${pct(premium)} below Briarwood's fair value read.`;
    } else {
      summary = "The current ask is broadly in line with Briarwood's fair value read.";
    }
  }

  return {
    title: "Ask vs fair value",
    summary,
    companion: "Pair this with the comp set and CMA to see what is actually supporting the valuation.",
    shouldRender,
  };
}

function scenarioSurface(spec: ScenarioFanChartSpec): ChartSurface {
  const values = [
    spec.bull_case_value,
    spec.base_case_value,
    spec.bear_case_value,
    spec.stress_case_value,
  ].filter(isNumber);
  const shouldRender = isNumber(spec.ask_price) && values.length >= 2;
  if (!shouldRender) return { shouldRender: false };

  const baseDelta =
    isNumber(spec.ask_price) && isNumber(spec.base_case_value) && spec.ask_price !== 0
      ? (spec.base_case_value - spec.ask_price) / spec.ask_price
      : null;
  const bullBearSpread =
    isNumber(spec.bull_case_value) && isNumber(spec.bear_case_value)
      ? spec.bull_case_value - spec.bear_case_value
      : null;

  return {
    title: "5-year value range",
    summary:
      baseDelta != null
        ? `The base case points to ${pct(baseDelta)} versus today's basis over five years.`
        : null,
    companion:
      bullBearSpread != null
        ? `Use the scenario table to compare the full spread: ${money(bullBearSpread)} between bull and bear.`
        : "Use the scenario table to compare bull, base, bear, and stress assumptions.",
    shouldRender,
  };
}

function cmaSurface(spec: CmaPositioningChartSpec): ChartSurface {
  const priced = spec.comps.filter((comp) => isNumber(comp.ask_price));
  if (priced.length === 0) return { shouldRender: false };
  const inModel = priced.filter((comp) => comp.feeds_fair_value).length;
  return {
    title: "Where the comps sit",
    summary: `This shows where the chosen comps land relative to the ask and Briarwood's fair value range.`,
    companion:
      inModel > 0
        ? `${inModel} comp${inModel === 1 ? "" : "s"} are currently feeding fair value; use the CMA table to see why each one is in or out.`
        : "Use the CMA table to see which comps are supporting the read and which ones are only contextual.",
    shouldRender: true,
  };
}

function riskSurface(spec: RiskBarChartSpec): ChartSurface {
  const items = spec.items.filter((item) => isNumber(item.value) && item.value > 0);
  if (items.length === 0) return { shouldRender: false };
  const top = [...items].sort((a, b) => b.value - a.value)[0];
  return {
    title: "Risk drivers",
    summary: top ? `${top.label} is the biggest factor pushing this setup away from a clean green light.` : null,
    companion: "Use this with the trust card to separate true downside from thin or missing inputs.",
    shouldRender: true,
  };
}

function rentBurnSurface(spec: RentBurnChartSpec): ChartSurface {
  const points = spec.points.filter((point) => isNumber(point.year));
  const hasObligation = points.some((point) => isNumber(point.monthly_obligation));
  const hasRent = points.some((point) => isNumber(point.rent_base));
  if (points.length < 2 || !hasRent || !hasObligation) return { shouldRender: false };

  const last = points[points.length - 1];
  const gap =
    isNumber(last.monthly_obligation) && isNumber(last.rent_base)
      ? last.rent_base - last.monthly_obligation
      : null;

  return {
    title: "Rent vs monthly cost",
    summary:
      gap != null
        ? gap >= 0
          ? `By the end of this horizon, modeled rent covers monthly cost by about ${money(gap)}.`
          : `By the end of this horizon, modeled rent is still short of monthly cost by about ${money(Math.abs(gap))}.`
        : null,
    companion: "Read this next to the rent card to see whether the carry burden is realistic for the rental story.",
    shouldRender: true,
  };
}

function rentRampSurface(spec: RentRampChartSpec): ChartSurface {
  const points = spec.points.filter((point) => isNumber(point.year));
  if (points.length < 2 || !isNumber(spec.current_rent) || !isNumber(spec.monthly_obligation)) {
    return { shouldRender: false };
  }
  const breakEvenYear = spec.break_even_years?.["3"];
  return {
    title: "Can rent catch up?",
    summary:
      breakEvenYear == null
        ? "On the current assumptions, rent does not catch monthly cost inside the modeled hold period."
        : breakEvenYear === 0
          ? "On the current assumptions, the deal works on day one."
          : `On the current assumptions, rent catches monthly cost around year ${breakEvenYear}.`,
    companion: "This is the hold-period reality check: if there is no break-even, the carry burden has to be justified elsewhere.",
    shouldRender: true,
  };
}

function resolveSurface(spec: ChartSpec): ChartSurface {
  switch (spec.kind) {
    case "value_opportunity":
      return valueSurface(spec);
    case "scenario_fan":
      return scenarioSurface(spec);
    case "cma_positioning":
      return cmaSurface(spec);
    case "risk_bar":
      return riskSurface(spec);
    case "rent_burn":
      return rentBurnSurface(spec);
    case "rent_ramp":
      return rentRampSurface(spec);
    default:
      return { shouldRender: true };
  }
}

export function getChartSurface(chart: ChartEvent): ChartSurface {
  const advisor = chart.advisor ?? null;
  if (!chart.spec) {
    return {
      title: advisor?.title ?? chartTitle(chart),
      summary: advisor?.summary ?? null,
      companion: advisor?.companion ?? null,
      shouldRender: Boolean(chart.url),
    };
  }
  const surface = resolveSurface(chart.spec);
  return {
    ...surface,
    title: surface.title ?? chartTitle(chart),
    summary: surface.summary ?? advisor?.summary ?? null,
    companion: surface.companion ?? advisor?.companion ?? null,
  };
}
