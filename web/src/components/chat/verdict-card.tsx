"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";
import type { VerdictEvent } from "@/lib/chat/events";

type Props = {
  verdict: VerdictEvent;
};

const STANCE_TONE: Record<string, string> = {
  buy: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  buy_if_price_improves:
    "bg-amber-500/15 text-amber-200 border-amber-500/30",
  pass_unless_changes: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  pass: "bg-rose-500/15 text-rose-300 border-rose-500/30",
};

function stanceLabel(s: string | null | undefined) {
  if (!s) return "Undecided";
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

export function VerdictCard({ verdict }: Props) {
  const stance = verdict.stance ?? null;
  const tone = stance ? STANCE_TONE[stance] : undefined;
  const evidenceItems = verdict.evidence_items ?? [];

  const ask = verdict.ask_price ?? null;
  const fair = verdict.fair_value_base ?? null;
  const low = verdict.value_low ?? null;
  const high = verdict.value_high ?? null;

  // Position the ask price marker within the value range bar.
  let askPos: number | null = null;
  if (ask != null && low != null && high != null && high > low) {
    const clamped = Math.max(low, Math.min(high, ask));
    askPos = ((clamped - low) / (high - low)) * 100;
  }

  const subjectLine = [verdict.address, verdict.town, verdict.state]
    .filter(Boolean)
    .join(", ");

  return (
    <div
      className={cn(
        "mt-4 rounded-2xl border border-[var(--color-border-subtle)]",
        "bg-[var(--color-surface)] p-4",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          {subjectLine && (
            <div className="text-[13px] text-[var(--color-text-muted)]">
              {subjectLine}
            </div>
          )}
          <div className="mt-0.5 text-base font-semibold text-[var(--color-text)]">
            Decision
          </div>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider",
            tone ??
              "bg-[var(--color-bg-sunken)] text-[var(--color-text-muted)] border-[var(--color-border-subtle)]",
          )}
        >
          {stanceLabel(stance)}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-[13px] sm:grid-cols-4">
        <Stat label="Ask" value={money(ask)} />
        <Stat label="Fair value" value={money(fair)} />
        <Stat label="Ask vs fair" value={pct(verdict.ask_premium_pct)} />
        <Stat label="Basis vs fair" value={pct(verdict.basis_premium_pct)} />
      </div>

      {verdict.lead_reason && (
        <div className="mt-4 text-[13px] leading-6 text-[var(--color-text)]">
          {verdict.lead_reason}
        </div>
      )}

      {evidenceItems.length > 0 && (
        <ListBlock label="What Briarwood is seeing" items={evidenceItems} />
      )}

      {low != null && high != null && (
        <div className="mt-4">
          <div className="flex items-center justify-between text-[11px] text-[var(--color-text-faint)]">
            <span>{money(low)}</span>
            <span className="uppercase tracking-wider">Value range</span>
            <span>{money(high)}</span>
          </div>
          <div className="relative mt-1.5 h-2 overflow-hidden rounded-full bg-[var(--color-bg-sunken)]">
            <div className="absolute inset-y-0 left-0 right-0 bg-gradient-to-r from-emerald-500/30 via-amber-500/30 to-rose-500/30" />
            {askPos != null && (
              <div
                className="absolute top-1/2 h-3 w-[2px] -translate-y-1/2 bg-[var(--color-text)]"
                style={{ left: `${askPos}%` }}
                aria-label={`Ask: ${money(ask)}`}
              />
            )}
          </div>
        </div>
      )}

      {verdict.next_step_teaser && (
        <div className="mt-4 rounded-xl border border-sky-500/20 bg-sky-500/10 px-3 py-2 text-[12px] text-sky-100/90">
          {verdict.next_step_teaser}
        </div>
      )}

      {verdict.trust_flags.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {verdict.trust_flags.map((f) => (
            <span
              key={f}
              className="rounded-md border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-200/90"
            >
              {f}
            </span>
          ))}
        </div>
      )}

      {verdict.why_this_stance && verdict.why_this_stance.length > 0 && (
        <ListBlock label="Why this stance" items={verdict.why_this_stance} />
      )}

      {verdict.what_must_be_true.length > 0 && (
        <ListBlock label="What must be true" items={verdict.what_must_be_true} />
      )}
      {verdict.key_risks.length > 0 && (
        <ListBlock label="Key risks" items={verdict.key_risks} />
      )}

      <VerdictDetails verdict={verdict} />
    </div>
  );
}

function VerdictDetails({ verdict }: { verdict: VerdictEvent }) {
  const [open, setOpen] = useState(false);

  const whatChanges = verdict.what_changes_my_view ?? [];
  const blocked = verdict.blocked_thesis_warnings ?? [];
  const contradictions = verdict.contradiction_count ?? null;
  const trust = verdict.trust_summary ?? null;

  const hasContent =
    whatChanges.length > 0 ||
    blocked.length > 0 ||
    (contradictions != null && contradictions > 0) ||
    (trust != null &&
      (trust.confidence != null ||
        trust.band != null ||
        trust.field_completeness != null ||
        trust.estimated_reliance != null));

  if (!hasContent) return null;

  return (
    <div className="mt-4 border-t border-[var(--color-border-subtle)] pt-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-[11px] uppercase tracking-wider text-[var(--color-text-faint)] hover:text-[var(--color-text-muted)]"
        aria-expanded={open}
      >
        <span>{open ? "Hide details" : "Show more"}</span>
        <span aria-hidden>{open ? "−" : "+"}</span>
      </button>

      {open && (
        <div className="mt-3 space-y-3">
          {trust && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[12px] sm:grid-cols-4">
              {trust.confidence != null && (
                <Stat
                  label="Confidence"
                  value={`${Math.round(trust.confidence * 100)}%`}
                />
              )}
              {trust.band && <Stat label="Band" value={trust.band} />}
              {trust.field_completeness != null && (
                <Stat
                  label="Completeness"
                  value={`${Math.round(trust.field_completeness * 100)}%`}
                />
              )}
              {trust.estimated_reliance != null && (
                <Stat
                  label="Reliance"
                  value={`${Math.round(trust.estimated_reliance * 100)}%`}
                />
              )}
            </div>
          )}

          {contradictions != null && contradictions > 0 && (
            <div className="text-[12px] text-amber-200/90">
              {contradictions} contradiction{contradictions === 1 ? "" : "s"} across
              modules — see verifier report for details.
            </div>
          )}

          {whatChanges.length > 0 && (
            <ListBlock label="What changes my view" items={whatChanges} />
          )}

          {blocked.length > 0 && (
            <div>
              <div className="text-[11px] uppercase tracking-wider text-rose-300/80">
                Blocked thesis warnings
              </div>
              <ul className="mt-1.5 space-y-1 text-[12px] text-rose-200/90">
                {blocked.map((w, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="mt-2 inline-block h-1 w-1 shrink-0 rounded-full bg-rose-400/70" />
                    <span>{w}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
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

function ListBlock({ label, items }: { label: string; items: string[] }) {
  return (
    <div className="mt-4">
      <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
        {label}
      </div>
      <ul className="mt-1.5 space-y-1 text-[13px] text-[var(--color-text-muted)]">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2">
            <span className="mt-2 inline-block h-1 w-1 shrink-0 rounded-full bg-[var(--color-text-faint)]" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
