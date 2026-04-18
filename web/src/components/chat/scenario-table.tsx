"use client";

import { cn } from "@/lib/cn";
import type { ScenarioRow, ScenarioTableEvent } from "@/lib/chat/events";

type Props = {
  table: ScenarioTableEvent;
};

const SCENARIO_TONE: Record<string, string> = {
  Bull: "text-emerald-300",
  Base: "text-[var(--color-text)]",
  Bear: "text-amber-300",
  Stress: "text-rose-300",
};

function money(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${Math.round(n).toLocaleString()}`;
}

function pct(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${(n * 100).toFixed(1)}%`;
}

function deltaTone(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "text-[var(--color-text-faint)]";
  if (n > 0.01) return "text-emerald-300";
  if (n < -0.01) return "text-rose-300";
  return "text-[var(--color-text-muted)]";
}

export function ScenarioTable({ table }: Props) {
  const { rows, address, ask_price, spread } = table;
  if (!rows || rows.length === 0) return null;

  return (
    <div
      className={cn(
        "mt-4 rounded-2xl border border-[var(--color-border-subtle)]",
        "bg-[var(--color-surface)] p-4",
      )}
    >
      <div className="flex items-baseline justify-between gap-3">
        <div>
          {address && (
            <div className="text-[13px] text-[var(--color-text-muted)]">
              {address}
            </div>
          )}
          <div className="mt-0.5 text-base font-semibold text-[var(--color-text)]">
            5-year scenarios
          </div>
        </div>
        {ask_price != null && (
          <div className="text-right text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
            Ask
            <div className="mt-0.5 text-[13px] font-medium text-[var(--color-text)] normal-case tracking-normal">
              {money(ask_price)}
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 overflow-hidden rounded-lg border border-[var(--color-border-subtle)]">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--color-bg-sunken)]">
            <tr className="text-left text-[10px] uppercase tracking-wider text-[var(--color-text-faint)]">
              <th className="px-3 py-2 font-medium">Scenario</th>
              <th className="px-3 py-2 font-medium text-right">Value</th>
              <th className="px-3 py-2 font-medium text-right">vs ask</th>
              <th className="px-3 py-2 font-medium text-right">Growth</th>
              <th className="px-3 py-2 font-medium text-right">Adj.</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border-subtle)]">
            {rows.map((r) => (
              <ScenarioRowView key={r.scenario} row={r} />
            ))}
          </tbody>
        </table>
      </div>

      {spread != null && Number.isFinite(spread) && (
        <div className="mt-3 text-[11px] text-[var(--color-text-faint)]">
          Bull–bear spread: {money(spread)}
        </div>
      )}
    </div>
  );
}

function ScenarioRowView({ row }: { row: ScenarioRow }) {
  const tone = SCENARIO_TONE[row.scenario] ?? "text-[var(--color-text)]";
  return (
    <tr className="bg-[var(--color-surface)]">
      <td className={cn("px-3 py-2 font-medium", tone)}>{row.scenario}</td>
      <td className="px-3 py-2 text-right tabular-nums text-[var(--color-text)]">
        {money(row.value)}
      </td>
      <td className={cn("px-3 py-2 text-right tabular-nums", deltaTone(row.delta_pct))}>
        {pct(row.delta_pct)}
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-[var(--color-text-muted)]">
        {pct(row.growth_rate)}
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-[var(--color-text-muted)]">
        {pct(row.adjustment_pct)}
      </td>
    </tr>
  );
}
