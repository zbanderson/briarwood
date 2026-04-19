"use client";

import { cn } from "@/lib/cn";
import type { ValueThesisEvent } from "@/lib/chat/events";

type Props = {
  thesis: ValueThesisEvent;
};

function money(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${Math.round(n).toLocaleString()}`;
}

function pct(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

export function EntryPointCard({ thesis }: Props) {
  const ask = thesis.ask_price ?? null;
  const fair = thesis.fair_value_base ?? null;
  const riskAdjusted = thesis.risk_adjusted_fair_value ?? null;
  const anchor = riskAdjusted ?? fair;
  const requiredDiscount = thesis.required_discount ?? null;
  const hasSignal =
    (ask != null && Number.isFinite(ask)) ||
    (fair != null && Number.isFinite(fair)) ||
    (riskAdjusted != null && Number.isFinite(riskAdjusted));

  if (!hasSignal) return null;

  let takeaway = "This gets more interesting closer to Briarwood's value read.";
  if (ask != null && Number.isFinite(ask) && anchor != null && Number.isFinite(anchor)) {
    takeaway =
      ask > anchor
        ? `This gets more interesting closer to ${money(anchor)} than today's ${money(ask)} ask.`
        : `Today's ask is already close to Briarwood's working entry level around ${money(anchor)}.`;
  }

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
            Good entry point
          </div>
          <div className="mt-0.5 text-base font-semibold text-[var(--color-text)]">
            {money(anchor)}
          </div>
        </div>
        {requiredDiscount != null && Number.isFinite(requiredDiscount) && (
          <span className="shrink-0 rounded-full border border-amber-500/30 bg-amber-500/15 px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider text-amber-200">
            {pct(requiredDiscount)} discount
          </span>
        )}
      </div>

      <div className="mt-3 text-[13px] text-[var(--color-text-muted)]">{takeaway}</div>

      <div className="mt-4 grid grid-cols-2 gap-3 text-[12px]">
        <MiniStat label="Ask" value={money(ask)} />
        <MiniStat label="Fair value" value={money(fair)} />
        <MiniStat label="Risk-adjusted" value={money(riskAdjusted)} />
        <MiniStat label="Required discount" value={pct(requiredDiscount)} />
      </div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
        {label}
      </div>
      <div className="mt-0.5 font-medium text-[var(--color-text)]">{value}</div>
    </div>
  );
}
