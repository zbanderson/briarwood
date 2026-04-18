"use client";

import { cn } from "@/lib/cn";

const SUGGESTED_PROMPTS = [
  "Find me a starter home in Denver",
  "Compare Austin vs. Raleigh for remote workers",
  "What's happening in the Seattle market?",
  "3BR homes under $900k in Belmar NJ with no HOA",
];

type Props = {
  onPick: (prompt: string) => void;
};

export function EmptyState({ onPick }: Props) {
  return (
    <div className="flex flex-col items-center text-center px-4 pt-12 pb-6">
      <h1 className="text-3xl font-semibold tracking-tight text-[var(--color-text)]">
        Where are you looking?
      </h1>
      <p className="mt-2 text-[var(--color-text-muted)]">
        Ask Briarwood about a property, town, or market trend.
      </p>

      <ul
        aria-label="Suggested prompts"
        className="mt-10 grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2"
      >
        {SUGGESTED_PROMPTS.map((p) => (
          <li key={p}>
            <button
              type="button"
              onClick={() => onPick(p)}
              className={cn(
                "group w-full rounded-xl border border-[var(--color-border-subtle)]",
                "bg-[var(--color-bg-elevated)] px-4 py-3 text-left text-sm",
                "text-[var(--color-text-muted)] hover:text-[var(--color-text)]",
                "hover:border-[var(--color-border)] hover:bg-[var(--color-surface)]",
                "transition-colors",
              )}
            >
              {p}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
