"use client";

import { cn } from "@/lib/cn";
import type { CompsPreviewEvent } from "@/lib/chat/events";

type Props = {
  preview: CompsPreviewEvent;
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

function dims(row: {
  beds?: number | null;
  baths?: number | null;
  sqft?: number | null;
}) {
  const parts: string[] = [];
  if (row.beds != null) parts.push(`${row.beds}bd`);
  if (row.baths != null) parts.push(`${row.baths}ba`);
  if (row.sqft != null) parts.push(`${row.sqft.toLocaleString()} sqft`);
  return parts.join(" · ");
}

export function CompsPreviewCard({ preview }: Props) {
  const rows = preview.comps ?? [];
  if (rows.length === 0) return null;

  return (
    <div
      className={cn(
        "mt-4 rounded-2xl border border-[var(--color-border-subtle)]",
        "bg-[var(--color-surface)] p-4",
      )}
    >
      <div className="flex items-baseline justify-between">
        <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
          Comp set preview
        </div>
        <div className="text-[11px] text-[var(--color-text-faint)]">
          {preview.count} comps · median {money(preview.median_price)}
        </div>
      </div>

      <ul className="mt-3 divide-y divide-[var(--color-border-subtle)]">
        {rows.map((row, i) => {
          const premium = pct(row.premium_pct);
          const premiumTone =
            row.premium_pct == null
              ? "text-[var(--color-text-faint)]"
              : row.premium_pct > 0
                ? "text-rose-300"
                : "text-emerald-300";
          return (
            <li
              key={row.property_id ?? `comp-${i}`}
              className="flex items-baseline justify-between gap-3 py-2"
            >
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] font-medium text-[var(--color-text)]">
                  {row.address ?? row.property_id ?? "—"}
                </div>
                <div className="text-[11px] text-[var(--color-text-muted)]">
                  {dims(row) || "—"}
                </div>
              </div>
              <div className="shrink-0 text-right">
                <div className="text-[13px] font-medium text-[var(--color-text)]">
                  {money(row.price)}
                </div>
                {premium && (
                  <div className={cn("text-[11px]", premiumTone)}>
                    {premium} vs subject
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
