"use client";

import { cn } from "@/lib/cn";
import type { StrategyPathEvent } from "@/lib/chat/events";

type Props = {
  strategy: StrategyPathEvent;
};

function money(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(Math.round(n)).toLocaleString()}`;
}

function pct(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function score(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toFixed(2);
}

export function StrategyPathCard({ strategy }: Props) {
  const location = [strategy.town, strategy.state].filter(Boolean).join(", ");
  const cashFlowTone =
    strategy.monthly_cash_flow != null && strategy.monthly_cash_flow < 0
      ? "rose"
      : "emerald";

  return (
    <div
      className={cn(
        "mt-4 rounded-2xl border border-[var(--color-border-subtle)]",
        "bg-[var(--color-surface)] p-4",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
            Best path
          </div>
          <div className="mt-0.5 text-base font-semibold text-[var(--color-text)]">
            {strategy.address ?? location ?? "—"}
          </div>
        </div>
        {strategy.best_path && (
          <span className="shrink-0 rounded-full border border-sky-500/30 bg-sky-500/15 px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider text-sky-300">
            {strategy.best_path}
          </span>
        )}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-[13px] sm:grid-cols-4">
        <Stat
          label="Cash flow / mo"
          value={money(strategy.monthly_cash_flow)}
          tone={cashFlowTone}
        />
        <Stat label="Cash-on-cash" value={pct(strategy.cash_on_cash_return)} />
        <Stat label="Annual NOI" value={money(strategy.annual_noi)} />
        <Stat
          label="Rental ease"
          value={
            strategy.rental_ease_label
              ? `${strategy.rental_ease_label} (${score(strategy.rental_ease_score)})`
              : score(strategy.rental_ease_score)
          }
        />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-4 text-[13px]">
        <Stat label="Rent support" value={score(strategy.rent_support_score)} />
        <Stat label="Liquidity" value={score(strategy.liquidity_score)} />
      </div>

      {strategy.recommendation && (
        <div className="mt-4 rounded-xl bg-[var(--color-bg-sunken)] px-3 py-2.5 text-[13px] text-[var(--color-text-muted)]">
          <span className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
            Recommendation
          </span>
          <div className="mt-1 text-[var(--color-text)]">
            {strategy.recommendation}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "rose" | "emerald";
}) {
  const valueClass =
    tone === "rose"
      ? "text-rose-300"
      : tone === "emerald"
        ? "text-emerald-300"
        : "text-[var(--color-text)]";
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
        {label}
      </div>
      <div className={cn("mt-0.5 font-medium", valueClass)}>{value}</div>
    </div>
  );
}
