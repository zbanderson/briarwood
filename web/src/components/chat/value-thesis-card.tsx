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
  if (n == null || !Number.isFinite(n)) return null;
  const sign = n >= 0 ? "+" : "";
  return `${sign}${(n * 100).toFixed(1)}%`;
}

function dims(comp: { beds?: number | null; baths?: number | null }) {
  const parts: string[] = [];
  if (comp.beds != null) parts.push(`${comp.beds}bd`);
  if (comp.baths != null) parts.push(`${comp.baths}ba`);
  return parts.join(" · ");
}

export function ValueThesisCard({ thesis }: Props) {
  const location = [thesis.town, thesis.state].filter(Boolean).join(", ");
  const premium = pct(thesis.premium_discount_pct);
  const premiumTone =
    thesis.premium_discount_pct == null
      ? "text-[var(--color-text-faint)]"
      : thesis.premium_discount_pct > 0
        ? "text-rose-300"
        : "text-emerald-300";

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
            Value thesis
          </div>
          <div className="mt-0.5 text-base font-semibold text-[var(--color-text)]">
            {thesis.address ?? location ?? "—"}
          </div>
        </div>
        {thesis.pricing_view && (
          <span className="shrink-0 rounded-full border border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
            {thesis.pricing_view}
          </span>
        )}
      </div>

      <div className="mt-4 flex items-baseline gap-2 text-[15px]">
        <span className="font-semibold text-[var(--color-text)]">
          {money(thesis.ask_price)}
        </span>
        <span className="text-[var(--color-text-faint)]">vs fair</span>
        <span className="font-semibold text-[var(--color-text)]">
          {money(thesis.fair_value_base)}
        </span>
        {premium && (
          <span className={cn("text-[13px] font-medium", premiumTone)}>
            {premium}
          </span>
        )}
      </div>
      {thesis.primary_value_source && (
        <div className="mt-1 text-[11px] text-[var(--color-text-faint)]">
          Primary source: {thesis.primary_value_source}
        </div>
      )}

      {thesis.key_value_drivers.length > 0 && (
        <ListBlock label="Value drivers" items={thesis.key_value_drivers} />
      )}
      {thesis.what_must_be_true.length > 0 && (
        <ListBlock
          label="What must be true"
          items={thesis.what_must_be_true}
          tone="amber"
        />
      )}
      {thesis.comp_selection_summary && (
        <div className="mt-4 text-[12px] text-[var(--color-text-muted)]">
          <span className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
            Comp selection
          </span>
          <div className="mt-1">{thesis.comp_selection_summary}</div>
        </div>
      )}

      {thesis.comps.length > 0 && (
        <ul className="mt-3 divide-y divide-[var(--color-border-subtle)]">
          {thesis.comps.map((comp, i) => (
            <li
              key={comp.property_id ?? `vt-comp-${i}`}
              className="flex items-baseline justify-between gap-3 py-2 text-[13px]"
            >
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-[var(--color-text)]">
                  {comp.address ?? comp.property_id ?? "—"}
                </div>
                <div className="text-[11px] text-[var(--color-text-muted)]">
                  {dims(comp) || "—"}
                  {comp.blocks_to_beach != null &&
                    ` · ${comp.blocks_to_beach} blk to beach`}
                </div>
              </div>
              <div className="shrink-0 text-right font-medium text-[var(--color-text)]">
                {money(comp.ask_price)}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ListBlock({
  label,
  items,
  tone,
}: {
  label: string;
  items: string[];
  tone?: "amber";
}) {
  const dot = tone === "amber" ? "bg-amber-400/70" : "bg-sky-400/70";
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
