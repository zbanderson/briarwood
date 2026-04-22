"use client";

import { cn } from "@/lib/cn";
import type {
  MarketSupportCompsEvent,
  ValuationCompsEvent,
} from "@/lib/chat/events";

type CompsTableEvent = ValuationCompsEvent | MarketSupportCompsEvent;

type Variant = "valuation" | "market_support";

type Props = {
  table: CompsTableEvent;
  variant: Variant;
};

function money(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${Math.round(n).toLocaleString()}`;
}

const HEADINGS: Record<Variant, { eyebrow: string; blurb: string }> = {
  valuation: {
    eyebrow: "Comps that fed fair value",
    blurb: "Sourced from the valuation module's selected comp set.",
  },
  market_support: {
    eyebrow: "Market support comps",
    blurb: "Live market context — not evidence behind Briarwood's fair value.",
  },
};

export function CompsTableCard({ table, variant }: Props) {
  if (table.rows.length === 0) return null;
  const heading = HEADINGS[variant];
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
            {heading.eyebrow}
          </div>
          <div className="mt-0.5 text-base font-semibold text-[var(--color-text)]">
            {(table.address ?? [table.town, table.state].filter(Boolean).join(", ")) || "Comp table"}
          </div>
          <div className="mt-1 text-[12px] text-[var(--color-text-faint)]">
            {heading.blurb}
          </div>
        </div>
      </div>
      {table.summary && (
        <div className="mt-2 text-[12px] text-[var(--color-text-muted)]">
          {table.summary}
        </div>
      )}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[620px] text-left text-[12px]">
          <thead className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
            <tr>
              <th className="pb-2 font-medium">Comp</th>
              <th className="pb-2 font-medium">Dims</th>
              <th className="pb-2 font-medium">Price</th>
              <th className="pb-2 font-medium">Origin</th>
              {variant === "valuation" ? (
                <th className="pb-2 font-medium">In fair value</th>
              ) : null}
              <th className="pb-2 font-medium">Why it is here</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border-subtle)] text-[var(--color-text-muted)]">
            {table.rows.map((row, index) => (
              <tr key={row.property_id ?? row.address ?? `${variant}-row-${index}`}>
                <td className="py-2 pr-3 font-medium text-[var(--color-text)]">
                  {row.address ?? row.property_id ?? "—"}
                </td>
                <td className="py-2 pr-3">
                  {[row.beds != null ? `${row.beds}bd` : null, row.baths != null ? `${row.baths}ba` : null]
                    .filter(Boolean)
                    .join(" · ") || "—"}
                </td>
                <td className="py-2 pr-3">{money(row.ask_price)}</td>
                <td className="py-2 pr-3">
                  {[row.source_label, row.selected_by].filter(Boolean).join(" · ") || "—"}
                </td>
                {variant === "valuation" ? (
                  <td className="py-2 pr-3">
                    {row.feeds_fair_value == null ? "—" : row.feeds_fair_value ? "Yes" : "No"}
                  </td>
                ) : null}
                <td className="py-2">{row.inclusion_reason ?? row.source_summary ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
