"use client";

import { cn } from "@/lib/cn";
import type { RentOutlookEvent } from "@/lib/chat/events";

type Props = {
  outlook: RentOutlookEvent;
};

function money(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${Math.round(n).toLocaleString()}`;
}

function score(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return null;
  return n.toFixed(2);
}

export function RentOutlookCard({ outlook }: Props) {
  const location = [outlook.town, outlook.state].filter(Boolean).join(", ");
  const easeScore = score(outlook.rental_ease_score);
  const futureRange =
    outlook.future_rent_low != null || outlook.future_rent_high != null;

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
            Rent outlook
          </div>
          <div className="mt-0.5 text-base font-semibold text-[var(--color-text)]">
            {outlook.address ?? location ?? "—"}
          </div>
        </div>
        {outlook.rental_ease_label && (
          <span className="shrink-0 rounded-full border border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
            {outlook.rental_ease_label}
            {easeScore && ` · ${easeScore}`}
          </span>
        )}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-[13px] sm:grid-cols-4">
        <Stat label="Monthly rent" value={money(outlook.monthly_rent)} />
        <Stat
          label="Effective monthly"
          value={money(outlook.effective_monthly_rent)}
        />
        <Stat label="Annual NOI" value={money(outlook.annual_noi)} />
        <Stat
          label="Source"
          value={outlook.rent_source_type ?? "—"}
        />
      </div>

      {(outlook.zillow_market_rent != null ||
        outlook.zillow_rental_comp_count != null) && (
        <div className="mt-3 rounded-xl bg-[var(--color-bg-sunken)] px-3 py-2 text-[12px] text-[var(--color-text-muted)]">
          <span className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
            Zillow market
          </span>
          <span className="ml-2 text-[var(--color-text)]">
            {money(outlook.zillow_market_rent)}
          </span>
          {outlook.zillow_rental_comp_count != null && (
            <span className="ml-2">
              · {outlook.zillow_rental_comp_count} comps
            </span>
          )}
        </div>
      )}

      {futureRange && (
        <div className="mt-4">
          <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
            {outlook.horizon_years
              ? `${outlook.horizon_years}-year forward range`
              : "Forward range"}
          </div>
          <div className="mt-1 flex items-baseline gap-2 text-[13px]">
            <span className="text-[var(--color-text-muted)]">
              {money(outlook.future_rent_low)}
            </span>
            <span className="text-[var(--color-text-faint)]">→</span>
            <span className="font-semibold text-[var(--color-text)]">
              {money(outlook.future_rent_mid)}
            </span>
            <span className="text-[var(--color-text-faint)]">→</span>
            <span className="text-[var(--color-text-muted)]">
              {money(outlook.future_rent_high)}
            </span>
          </div>
        </div>
      )}

      {outlook.basis_to_rent_framing && (
        <div className="mt-4 text-[12px] text-[var(--color-text-muted)]">
          <span className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
            Basis-to-rent
          </span>
          <div className="mt-1">{outlook.basis_to_rent_framing}</div>
        </div>
      )}
      {outlook.owner_occupy_then_rent && (
        <div className="mt-3 text-[12px] text-[var(--color-text-muted)]">
          <span className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
            Owner-occupy → rent
          </span>
          <div className="mt-1">{outlook.owner_occupy_then_rent}</div>
        </div>
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
