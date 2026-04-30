"use client";

import { cn } from "@/lib/cn";
import type { StrategyPathEvent } from "@/lib/chat/events";

type Props = {
  strategy: StrategyPathEvent;
  /** Phase 4c Cycle 4 — Section C drilldowns embed this card with no extra
   * border (parent drilldown body is the frame). `framed=false` drops the
   * outer rounded-2xl wrapper + bg + padding; default `true` preserves the
   * non-BROWSE rendering. */
  framed?: boolean;
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

export function StrategyPathCard({ strategy, framed = true }: Props) {
  const location = [strategy.town, strategy.state].filter(Boolean).join(", ");
  const badge =
    strategy.best_path?.replace(/_/g, " ") ??
    strategy.pricing_view?.replace(/_/g, " ") ??
    null;
  const headline =
    strategy.recommendation ??
    strategy.best_path?.replace(/_/g, " ") ??
    "No recommendation yet";
  const cashFlowTone =
    strategy.monthly_cash_flow != null && strategy.monthly_cash_flow < 0
      ? "rose"
      : "emerald";

  return (
    <div
      className={cn(
        framed
          ? "mt-4 rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-surface)] p-4"
          : "",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
            Recommendation
          </div>
          <div className="mt-0.5 text-base font-semibold text-[var(--color-text)]">
            {headline}
          </div>
          <div className="mt-1 text-[12px] text-[var(--color-text-faint)]">
            {strategy.address ?? location ?? "—"}
          </div>
        </div>
        {badge && (
          <span className="shrink-0 rounded-full border border-sky-500/30 bg-sky-500/15 px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider text-sky-300">
            {badge}
          </span>
        )}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-[13px] sm:grid-cols-4">
        <Stat
          label="Monthly carry gap"
          value={money(strategy.monthly_cash_flow)}
          tone={cashFlowTone}
        />
        <Stat label="Annual NOI" value={money(strategy.annual_noi)} />
        <Stat
          label="Rental ease"
          value={
            strategy.rental_ease_label
              ? `${strategy.rental_ease_label} (${score(strategy.rental_ease_score)})`
              : score(strategy.rental_ease_score)
          }
        />
        <Stat label="Liquidity" value={score(strategy.liquidity_score)} />
      </div>

      {(strategy.best_path || strategy.rent_support_score != null || strategy.cash_on_cash_return != null) && (
        <div className="mt-4 rounded-xl bg-[var(--color-bg-sunken)] px-3 py-2.5 text-[13px] text-[var(--color-text-muted)]">
          <span className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
            Why this path
          </span>
          <div className="mt-1 text-[var(--color-text)]">
            {strategy.best_path
              ? strategy.best_path.replace(/_/g, " ")
              : "Current economics still need to clear a higher bar."}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-3 text-[12px]">
            <Stat label="Rent support" value={score(strategy.rent_support_score)} />
            <Stat label="Cash-on-cash" value={pct(strategy.cash_on_cash_return)} />
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
