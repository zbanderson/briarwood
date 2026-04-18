"use client";

import { cn } from "@/lib/cn";
import type { TownSummaryEvent } from "@/lib/chat/events";

type Props = {
  summary: TownSummaryEvent;
};

const TIER_TONE: Record<string, string> = {
  strong: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  moderate: "bg-amber-500/15 text-amber-200 border-amber-500/30",
  thin: "bg-rose-500/15 text-rose-300 border-rose-500/30",
};

function money(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${Math.round(n).toLocaleString()}`;
}

function ppsf(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${Math.round(n)}/sqft`;
}

function tierLabel(tier: string | null | undefined) {
  if (!tier) return "Unknown";
  return tier[0]!.toUpperCase() + tier.slice(1);
}

export function TownSummaryCard({ summary }: Props) {
  const tier = summary.confidence_tier ?? null;
  const tone = tier ? TIER_TONE[tier] : undefined;
  const conf = summary.confidence_raw;
  const confPct = conf != null ? `${Math.round(conf * 100)}%` : "—";
  const location = [summary.town, summary.state].filter(Boolean).join(", ");

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
            Town context
          </div>
          <div className="mt-0.5 text-base font-semibold text-[var(--color-text)]">
            {location}
          </div>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider",
            tone ??
              "bg-[var(--color-bg-sunken)] text-[var(--color-text-muted)] border-[var(--color-border-subtle)]",
          )}
        >
          {tierLabel(tier)} · {confPct}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-[13px] sm:grid-cols-4">
        <Stat label="Median price" value={money(summary.median_price)} />
        <Stat label="Median PPSF" value={ppsf(summary.median_ppsf)} />
        <Stat
          label="Sold (recent)"
          value={
            summary.sold_count != null
              ? summary.sold_count.toLocaleString()
              : "—"
          }
        />
        <Stat
          label="Docs seeded"
          value={summary.doc_count != null ? `${summary.doc_count}` : "—"}
        />
      </div>

      {summary.bullish_signals.length > 0 && (
        <SignalBlock
          label="Bullish signals"
          tone="emerald"
          items={summary.bullish_signals}
        />
      )}
      {summary.bearish_signals.length > 0 && (
        <SignalBlock
          label="Bearish signals"
          tone="rose"
          items={summary.bearish_signals}
        />
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
        {label}
      </div>
      <div className="mt-0.5 font-medium text-[var(--color-text)]">{value}</div>
    </div>
  );
}

function SignalBlock({
  label,
  tone,
  items,
}: {
  label: string;
  tone: "emerald" | "rose";
  items: string[];
}) {
  const dot =
    tone === "emerald" ? "bg-emerald-400/70" : "bg-rose-400/70";
  return (
    <div className="mt-4">
      <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
        {label}
      </div>
      <ul className="mt-1.5 space-y-1 text-[13px] text-[var(--color-text-muted)]">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2">
            <span
              className={cn(
                "mt-2 inline-block h-1.5 w-1.5 shrink-0 rounded-full",
                dot,
              )}
            />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
