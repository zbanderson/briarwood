"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";
import type { ChartEvent } from "@/lib/chat/events";

type Props = {
  chart: ChartEvent;
};

function chartTitle(c: ChartEvent) {
  if (c.title) return c.title;
  if (c.kind) {
    return c.kind
      .split("_")
      .map((w) => w[0]?.toUpperCase() + w.slice(1))
      .join(" ");
  }
  return "Chart";
}

export function ChartFrame({ chart }: Props) {
  const [loaded, setLoaded] = useState(false);

  return (
    <figure
      className={cn(
        "mt-4 overflow-hidden rounded-2xl border border-[var(--color-border-subtle)]",
        "bg-[var(--color-surface)]",
      )}
    >
      <figcaption className="border-b border-[var(--color-border-subtle)] px-4 py-2 text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
        {chartTitle(chart)}
      </figcaption>
      <div className="relative">
        {!loaded && (
          <div
            aria-hidden
            className="absolute inset-0 animate-pulse bg-[var(--color-bg-sunken)]"
          />
        )}
        <iframe
          src={chart.url}
          title={chartTitle(chart)}
          loading="lazy"
          sandbox="allow-scripts allow-same-origin"
          onLoad={() => setLoaded(true)}
          className="block h-[420px] w-full border-0 bg-white"
        />
      </div>
    </figure>
  );
}
