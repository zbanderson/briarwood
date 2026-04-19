"use client";

import { cn } from "@/lib/cn";
import type { ModuleAttribution } from "@/lib/chat/events";

type Props = {
  modules: ModuleAttribution[];
};

export function ModuleBadges({ modules }: Props) {
  const substantive = modules.some((m) =>
    [
      "town_context",
      "comp_set",
      "cma",
      "value_thesis",
      "risk_profile",
      "strategy_fit",
      "rent_outlook",
      "projection_engine",
      "confidence",
      "town_research",
      "valuation_model",
    ].includes(m.module),
  );
  const visible = substantive
    ? modules.filter(
        (m) => !["listing_discovery", "geocoder", "visualizer"].includes(m.module),
      )
    : modules;
  if (visible.length === 0) return null;
  return (
    <div
      role="group"
      aria-label="Modules that contributed to this response"
      className="mt-3 flex flex-wrap items-center gap-1.5"
    >
      <span className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
        Modules
      </span>
      {visible.map((m) => (
        <span
          key={m.module}
          title={
            m.contributed_to.length
              ? `Contributed to: ${m.contributed_to.join(", ")}`
              : undefined
          }
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-2 py-0.5",
            "border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)]",
            "text-[11px] font-medium text-[var(--color-text-muted)]",
          )}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-sky-400/70" />
          {m.label}
        </span>
      ))}
    </div>
  );
}
