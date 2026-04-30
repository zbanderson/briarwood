"use client";

import { cn } from "@/lib/cn";
import type { TrustSummaryEvent } from "@/lib/chat/events";

type Props = {
  summary: TrustSummaryEvent;
  /** Phase 4c Cycle 4 — Section C drilldowns embed this card with no extra
   * border (parent drilldown body is the frame). `framed=false` drops the
   * outer rounded-2xl wrapper + bg + padding; default `true` preserves the
   * non-BROWSE rendering. */
  framed?: boolean;
};

function pct(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

export function TrustSummaryCard({ summary, framed = true }: Props) {
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
            Trust
          </div>
          <div className="mt-0.5 text-base font-semibold text-[var(--color-text)]">
            {summary.band ?? "Trust summary"}
          </div>
        </div>
        {summary.confidence != null && (
          <div className="text-right">
            <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
              Confidence
            </div>
            <div className="mt-0.5 font-semibold text-[var(--color-text)]">
              {pct(summary.confidence)}
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 text-[13px] sm:grid-cols-3">
        <Stat label="Field completeness" value={pct(summary.field_completeness)} />
        <Stat label="Estimated reliance" value={pct(summary.estimated_reliance)} />
        <Stat
          label="Contradictions"
          value={summary.contradiction_count != null ? String(summary.contradiction_count) : "—"}
        />
      </div>

      {summary.trust_flags.length > 0 && (
        <ListBlock label="What is limiting trust" items={summary.trust_flags} />
      )}
      {summary.blocked_thesis_warnings.length > 0 && (
        <ListBlock
          label="Blocked thesis warnings"
          items={summary.blocked_thesis_warnings}
          tone="amber"
        />
      )}
      {summary.why_this_stance && summary.why_this_stance.length > 0 && (
        <ListBlock label="Why this stance" items={summary.why_this_stance} />
      )}
      {summary.what_changes_my_view && summary.what_changes_my_view.length > 0 && (
        <ListBlock
          label="What changes my view"
          items={summary.what_changes_my_view}
          tone="amber"
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
