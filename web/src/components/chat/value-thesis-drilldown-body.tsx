"use client";

import { cn } from "@/lib/cn";
import type { HiddenUpsideItem, ValueThesisEvent } from "@/lib/chat/events";

// Phase 4c Cycle 3 — fresh body for the Value-thesis drilldown.
//
// Merges the content of `EntryPointCard` (good-entry-point anchor + ask /
// fair / risk-adjusted / required-discount mini-stats) and `ValueThesisCard`
// (drivers, what must be true, why this stance, what changes my view, hidden
// upside, blocked thesis warnings) into a single borderless body so the
// drilldown reads as section content rather than a card-in-a-card. The
// existing `EntryPointCard` and `ValueThesisCard` stay untouched on
// non-BROWSE tiers.
//
// Constraints honored: no outer rounded-2xl border / bg / padding wrapper —
// this is rendered inside `BrowseDrilldown`'s already-indented open body.
// `tabular-nums` everywhere a number appears.

type Props = {
  thesis: ValueThesisEvent;
};

function money(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${Math.round(n).toLocaleString()}`;
}

function pct(n: number | null | undefined): string | null {
  if (n == null || !Number.isFinite(n)) return null;
  const sign = n >= 0 ? "+" : "";
  return `${sign}${(n * 100).toFixed(1)}%`;
}

function dims(comp: { beds?: number | null; baths?: number | null }): string {
  const parts: string[] = [];
  if (comp.beds != null) parts.push(`${comp.beds}bd`);
  if (comp.baths != null) parts.push(`${comp.baths}ba`);
  return parts.join(" · ");
}

export function ValueThesisDrilldownBody({ thesis }: Props) {
  const ask = thesis.ask_price ?? null;
  const fair = thesis.fair_value_base ?? null;
  const riskAdjusted = thesis.risk_adjusted_fair_value ?? null;
  const requiredDiscount = thesis.required_discount ?? null;
  const anchor = riskAdjusted ?? fair;
  const premium = pct(thesis.premium_discount_pct);
  const premiumTone =
    thesis.premium_discount_pct == null
      ? "text-[var(--color-text-faint)]"
      : thesis.premium_discount_pct > 0
        ? "text-rose-300"
        : "text-emerald-300";

  let takeaway = "This gets more interesting closer to Briarwood's value read.";
  if (
    ask != null &&
    Number.isFinite(ask) &&
    anchor != null &&
    Number.isFinite(anchor)
  ) {
    takeaway =
      ask > anchor
        ? `This gets more interesting closer to ${money(anchor)} than today's ${money(ask)} ask.`
        : `Today's ask is already close to Briarwood's working entry level around ${money(anchor)}.`;
  }

  return (
    <div className="space-y-4">
      <div>
        <Eyebrow>Good entry point</Eyebrow>
        <div className="mt-0.5 text-base font-semibold tabular-nums text-[var(--color-text)]">
          {money(anchor)}
        </div>
        <p className="mt-2 text-[13px] leading-snug text-[var(--color-text-muted)]">
          {takeaway}
        </p>
      </div>

      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[13px] tabular-nums">
        <span className="font-medium text-[var(--color-text)]">{money(ask)}</span>
        <span className="text-[var(--color-text-faint)]">vs fair</span>
        <span className="font-medium text-[var(--color-text)]">{money(fair)}</span>
        {premium && (
          <span className={cn("text-[12px] font-medium", premiumTone)}>
            {premium}
          </span>
        )}
      </div>

      {(riskAdjusted != null || requiredDiscount != null) && (
        <div className="grid grid-cols-2 gap-3 text-[12px]">
          <MiniStat label="Risk-adjusted" value={money(riskAdjusted)} />
          <MiniStat
            label="Required discount"
            value={pct(requiredDiscount) ?? "—"}
          />
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
      {thesis.why_this_stance && thesis.why_this_stance.length > 0 && (
        <ListBlock label="Why this stance" items={thesis.why_this_stance} />
      )}
      {thesis.what_changes_my_view && thesis.what_changes_my_view.length > 0 && (
        <ListBlock
          label="What changes my view"
          items={thesis.what_changes_my_view}
          tone="amber"
        />
      )}
      {thesis.optionality_signal &&
        thesis.optionality_signal.hidden_upside_items.length > 0 && (
          <HiddenUpsideBlock signal={thesis.optionality_signal} />
        )}
      {thesis.blocked_thesis_warnings &&
        thesis.blocked_thesis_warnings.length > 0 && (
          <ListBlock
            label="Blocked thesis warnings"
            items={thesis.blocked_thesis_warnings}
            tone="amber"
          />
        )}

      {thesis.comp_selection_summary && (
        <div className="text-[12px] text-[var(--color-text-muted)]">
          <Eyebrow>Comps behind fair value</Eyebrow>
          <div className="mt-1">{thesis.comp_selection_summary}</div>
        </div>
      )}

      {thesis.comps.length > 0 && (
        <ul className="divide-y divide-[var(--color-border-subtle)]">
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
                {(comp.source_label || comp.source_summary) && (
                  <div className="mt-1 flex items-center gap-2 text-[10px] uppercase tracking-wider text-[var(--color-text-faint)]">
                    {comp.source_label && (
                      <span className="rounded-full border border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] px-2 py-0.5">
                        {comp.source_label}
                      </span>
                    )}
                    {comp.source_summary && (
                      <span className="truncate normal-case tracking-normal">
                        {comp.source_summary}
                      </span>
                    )}
                  </div>
                )}
              </div>
              <div className="shrink-0 text-right font-medium tabular-nums text-[var(--color-text)]">
                {money(comp.ask_price)}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
      {children}
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
        {label}
      </div>
      <div className="mt-0.5 font-medium tabular-nums text-[var(--color-text)]">
        {value}
      </div>
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
    <div>
      <Eyebrow>{label}</Eyebrow>
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

function HiddenUpsideBlock({
  signal,
}: {
  signal: { hidden_upside_items: HiddenUpsideItem[]; summary?: string | null };
}) {
  return (
    <div>
      <Eyebrow>Hidden upside</Eyebrow>
      {signal.summary && (
        <div className="mt-1 text-[12px] text-[var(--color-text-muted)]">
          {signal.summary}
        </div>
      )}
      <ul className="mt-2 space-y-2">
        {signal.hidden_upside_items.map((item, i) => {
          const magUsd = money(item.magnitude_usd);
          const magPct = pct(item.magnitude_pct);
          const hasUsd =
            item.magnitude_usd != null && Number.isFinite(item.magnitude_usd);
          const magnitude = [hasUsd ? magUsd : null, magPct]
            .filter(Boolean)
            .join(" · ");
          return (
            <li
              key={`${item.kind}-${i}`}
              className="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] p-2.5 text-[13px]"
            >
              <div className="flex items-baseline justify-between gap-3">
                <span className="font-medium text-[var(--color-text)]">
                  {item.label}
                </span>
                {magnitude && (
                  <span className="shrink-0 text-[12px] font-medium tabular-nums text-emerald-300">
                    {magnitude}
                  </span>
                )}
              </div>
              {item.rationale && (
                <div className="mt-1 text-[12px] text-[var(--color-text-muted)]">
                  {item.rationale}
                </div>
              )}
              <div className="mt-1 text-[10px] uppercase tracking-wider text-[var(--color-text-faint)]">
                {item.source_module.replace(/_/g, " ")}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
