"use client";

import { cn } from "@/lib/cn";
import type { ResearchUpdateEvent } from "@/lib/chat/events";

type Props = {
  research: ResearchUpdateEvent;
};

const CONFIDENCE_TONE: Record<string, string> = {
  strong: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  moderate: "bg-amber-500/15 text-amber-200 border-amber-500/30",
  thin: "bg-rose-500/15 text-rose-300 border-rose-500/30",
};

function confidenceClass(label: string | null | undefined) {
  if (!label) return undefined;
  const key = label.toLowerCase();
  return CONFIDENCE_TONE[key];
}

export function ResearchUpdateCard({ research }: Props) {
  const tone = confidenceClass(research.confidence_label);
  const location = [research.town, research.state].filter(Boolean).join(", ");

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
            Town research
          </div>
          <div className="mt-0.5 text-base font-semibold text-[var(--color-text)]">
            {location || "—"}
          </div>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider",
            tone ??
              "bg-[var(--color-bg-sunken)] text-[var(--color-text-muted)] border-[var(--color-border-subtle)]",
          )}
        >
          {research.confidence_label ?? "Unknown"}
          {research.document_count != null && ` · ${research.document_count} docs`}
        </span>
      </div>

      {research.narrative_summary && (
        <p className="mt-3 text-[13px] leading-6 text-[var(--color-text-muted)]">
          {research.narrative_summary}
        </p>
      )}

      {research.bullish_signals.length > 0 && (
        <SignalBlock
          label="Bullish signals"
          tone="emerald"
          items={research.bullish_signals}
        />
      )}
      {research.bearish_signals.length > 0 && (
        <SignalBlock
          label="Bearish signals"
          tone="rose"
          items={research.bearish_signals}
        />
      )}
      {research.watch_items.length > 0 && (
        <SignalBlock
          label="Watch items"
          tone="amber"
          items={research.watch_items}
        />
      )}
      {research.warnings.length > 0 && (
        <SignalBlock
          label="Warnings"
          tone="rose"
          items={research.warnings}
        />
      )}
    </div>
  );
}

function SignalBlock({
  label,
  tone,
  items,
}: {
  label: string;
  tone: "emerald" | "rose" | "amber";
  items: string[];
}) {
  const dot =
    tone === "emerald"
      ? "bg-emerald-400/70"
      : tone === "amber"
        ? "bg-amber-400/70"
        : "bg-rose-400/70";
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
