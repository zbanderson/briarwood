"use client";

import { cn } from "@/lib/cn";

// Phase 4c Cycle 3 — extracted from messages.tsx so BROWSE Section C
// drilldowns and the legacy non-BROWSE card stack share one drill-in
// affordance. Behavior unchanged: pill button that emits a follow-up
// prompt via `onPick`.

type Props = {
  label: string;
  prompt: string;
  onPick: (prompt: string) => void;
};

export function InlinePrompt({ label, prompt, onPick }: Props) {
  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => onPick(prompt)}
        className={cn(
          "rounded-full border border-[var(--color-border-subtle)] px-3 py-1.5 text-xs",
          "text-[var(--color-text-muted)] hover:text-[var(--color-text)]",
          "hover:border-[var(--color-border)] hover:bg-[var(--color-surface)]",
          "transition-colors",
        )}
      >
        {label}
      </button>
    </div>
  );
}
