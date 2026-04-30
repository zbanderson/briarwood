// Chart-renderer migration substrate (Cycle 1).
//
// Resolves the production chart-token CSS vars declared in `globals.css`
// (`--chart-base`, `--chart-bull`, `--chart-bear`, `--chart-stress`,
// `--chart-neutral`, `--chart-grid`, `--chart-text-faint`, plus the
// `--color-bg-sunken` / `--color-surface` / `--color-text` /
// `--color-text-muted` / `--color-border-subtle` neighbors the chart chrome
// reads) to concrete hex values that ECharts can drop into its `option`
// object. ECharts cannot resolve `var(--…)` natively at render time.
//
// Reads `getComputedStyle(document.documentElement)` once at first call
// and caches. Falls back to the static `globals.css` hex values during SSR
// or before mount so the option object is never partially populated.
// Theme switching (light/dark) is not in scope for v1; if it lands the
// helper grows a `useSyncExternalStore` subscription to
// `prefers-color-scheme` and resets the cache.

const FALLBACK = {
  base: "#79b8ff",
  bull: "#75d38f",
  bear: "#f28b82",
  stress: "#d7b38a",
  neutral: "#b8b2a4",
  grid: "#2f2d2b",
  textFaint: "#8a847a",
  bgSunken: "#1a1918",
  surface: "#2b2a28",
  text: "#f3efe6",
  textMuted: "#b8b2a4",
  borderSubtle: "#2f2d2b",
} as const;

export type ChartTokens = typeof FALLBACK;

let cache: ChartTokens | null = null;

const VAR_NAMES: Record<keyof ChartTokens, string> = {
  base: "--chart-base",
  bull: "--chart-bull",
  bear: "--chart-bear",
  stress: "--chart-stress",
  neutral: "--chart-neutral",
  grid: "--chart-grid",
  textFaint: "--chart-text-faint",
  bgSunken: "--color-bg-sunken",
  surface: "--color-surface",
  text: "--color-text",
  textMuted: "--color-text-muted",
  borderSubtle: "--color-border-subtle",
};

export function getChartTokens(): ChartTokens {
  if (cache) return cache;
  if (typeof window === "undefined" || typeof document === "undefined") {
    return FALLBACK;
  }
  const styles = window.getComputedStyle(document.documentElement);
  const resolved = {} as Record<keyof ChartTokens, string>;
  for (const key of Object.keys(VAR_NAMES) as Array<keyof ChartTokens>) {
    const raw = styles.getPropertyValue(VAR_NAMES[key]).trim();
    resolved[key] = raw.length > 0 ? raw : FALLBACK[key];
  }
  cache = resolved as ChartTokens;
  return cache;
}
