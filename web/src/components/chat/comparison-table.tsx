"use client";

import { cn } from "@/lib/cn";
import type { ComparisonRow, ComparisonTableEvent } from "@/lib/chat/events";

type Props = {
  table: ComparisonTableEvent;
};

const STANCE_TONE: Record<string, string> = {
  buy: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  buy_if_price_improves:
    "bg-amber-500/15 text-amber-200 border-amber-500/30",
  pass_unless_changes: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  pass: "bg-rose-500/15 text-rose-300 border-rose-500/30",
};

function stanceLabel(s: string | null | undefined) {
  if (!s) return "—";
  return s
    .split("_")
    .map((w) => w[0]?.toUpperCase() + w.slice(1))
    .join(" ");
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

function premiumTone(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "text-[var(--color-text-faint)]";
  // Negative premium = ask < fair value = a relative bargain.
  if (n < -0.02) return "text-emerald-300";
  if (n > 0.05) return "text-rose-300";
  return "text-amber-300";
}

export function ComparisonTable({ table }: Props) {
  const properties = table.properties ?? [];
  if (properties.length === 0) return null;

  return (
    <div
      className={cn(
        "mt-4 rounded-2xl border border-[var(--color-border-subtle)]",
        "bg-[var(--color-surface)] p-4",
      )}
    >
      <div className="text-base font-semibold text-[var(--color-text)]">
        Side-by-side
      </div>
      <div
        className={cn(
          "mt-3 grid gap-px overflow-hidden rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-border-subtle)]",
          properties.length === 2 ? "grid-cols-2" : "grid-cols-1",
        )}
      >
        {properties.map((p) => (
          <PropertyColumn key={p.property_id} property={p} />
        ))}
      </div>
    </div>
  );
}

function PropertyColumn({ property }: { property: ComparisonRow }) {
  if (property.error) {
    return (
      <div className="flex flex-col gap-2 bg-[var(--color-bg-elevated)] p-3">
        <div className="text-[12px] text-[var(--color-text-muted)]">
          {property.address ?? property.property_id}
        </div>
        <div className="text-[12px] text-rose-300">{property.error}</div>
      </div>
    );
  }

  const tone = property.stance ? STANCE_TONE[property.stance] : undefined;
  const subjectLine = property.address ?? property.property_id;
  const subTitle = [property.town, property.state].filter(Boolean).join(", ");
  const facts: string[] = [];
  if (property.beds != null) facts.push(`${property.beds}bd`);
  if (property.baths != null) facts.push(`${property.baths}ba`);
  if (property.sqft != null) facts.push(`${property.sqft.toLocaleString()} sqft`);

  return (
    <div className="flex flex-col gap-3 bg-[var(--color-bg-elevated)] p-3">
      <div>
        <div className="text-[13px] font-medium text-[var(--color-text)] line-clamp-2">
          {subjectLine}
        </div>
        {subTitle && (
          <div className="mt-0.5 text-[11px] text-[var(--color-text-faint)]">
            {subTitle}
          </div>
        )}
      </div>

      <span
        className={cn(
          "self-start rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider",
          tone ??
            "bg-[var(--color-bg-sunken)] text-[var(--color-text-muted)] border-[var(--color-border-subtle)]",
        )}
      >
        {stanceLabel(property.stance)}
      </span>

      <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[12px]">
        <Stat label="Ask" value={money(property.ask_price)} />
        <Stat label="Fair value" value={money(property.fair_value_base)} />
        <Stat
          label="Premium"
          value={pct(property.premium_pct)}
          valueClassName={premiumTone(property.premium_pct)}
        />
        <Stat label="Source" value={property.primary_value_source ?? "—"} />
      </dl>

      {facts.length > 0 && (
        <div className="text-[11px] text-[var(--color-text-faint)]">
          {facts.join(" · ")}
        </div>
      )}

      {(property.trust_flags ?? []).length > 0 && (
        <div className="flex flex-wrap gap-1">
          {(property.trust_flags ?? []).map((f) => (
            <span
              key={f}
              className="rounded-md border border-amber-500/20 bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-200/90"
            >
              {f}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  valueClassName,
}: {
  label: string;
  value: string;
  valueClassName?: string;
}) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wider text-[var(--color-text-faint)]">
        {label}
      </dt>
      <dd
        className={cn(
          "mt-0.5 font-medium tabular-nums text-[var(--color-text)]",
          valueClassName,
        )}
      >
        {value}
      </dd>
    </div>
  );
}
