"use client";

import { cn } from "@/lib/cn";
import type { RentOutlookEvent } from "@/lib/chat/events";

type Props = {
  outlook: RentOutlookEvent;
  /** Phase 4c Cycle 4 — Section C drilldowns embed this card with no extra
   * border (parent drilldown body is the frame). `framed=false` drops the
   * outer rounded-2xl wrapper + bg + padding; default `true` preserves the
   * non-BROWSE rendering. */
  framed?: boolean;
};

function money(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${Math.round(n).toLocaleString()}`;
}

function score(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return null;
  return n.toFixed(2);
}

export function RentOutlookCard({ outlook, framed = true }: Props) {
  const location = [outlook.town, outlook.state].filter(Boolean).join(", ");
  const easeScore = score(outlook.rental_ease_score);
  const futureRange =
    outlook.future_rent_low != null || outlook.future_rent_high != null;

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
        <Stat label="Entry basis" value={money(outlook.entry_basis)} />
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
        <Stat
          label="Carry offset"
          value={
            outlook.carry_offset_ratio != null
              ? `${outlook.carry_offset_ratio.toFixed(2)}x`
              : "—"
          }
        />
        <Stat label="Break-even rent" value={money(outlook.break_even_rent)} />
        <Stat
          label="Break-even probability"
          value={
            outlook.break_even_probability != null
              ? `${Math.round(outlook.break_even_probability * 100)}%`
              : "—"
          }
        />
        <Stat
          label="Adjusted rent confidence"
          value={
            outlook.adjusted_rent_confidence != null
              ? `${Math.round(outlook.adjusted_rent_confidence * 100)}%`
              : "—"
          }
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

      {outlook.market_context_note && (
        <div className="mt-3 rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] px-3 py-2 text-[12px] text-[var(--color-text-muted)]">
          {outlook.market_context_note}
        </div>
      )}
      {outlook.rent_haircut_pct != null && outlook.rent_haircut_pct > 0 && (
        <div className="mt-3 rounded-xl border border-amber-400/20 bg-amber-400/10 px-3 py-2 text-[12px] text-[var(--color-text-muted)]">
          Briarwood is haircutting rent confidence by{" "}
          {Math.round(outlook.rent_haircut_pct * 100)}% because the income story
          is legally or operationally fragile.
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
