"use client";

import { cn } from "@/lib/cn";
import type { RiskProfileEvent } from "@/lib/chat/events";

type Props = {
  profile: RiskProfileEvent;
};

const TIER_TONE: Record<string, string> = {
  strong: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  moderate: "bg-amber-500/15 text-amber-200 border-amber-500/30",
  thin: "bg-rose-500/15 text-rose-300 border-rose-500/30",
};

function money(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${Math.round(n).toLocaleString()}`;
}

function pct(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(0)}%`;
}

function tierLabel(tier: string | null | undefined) {
  if (!tier) return "Unknown";
  return tier[0]!.toUpperCase() + tier.slice(1);
}

export function RiskProfileCard({ profile }: Props) {
  const tier = profile.confidence_tier ?? null;
  const tone = tier ? TIER_TONE[tier] : undefined;
  const location = [profile.town, profile.state].filter(Boolean).join(", ");

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
            Risk profile
          </div>
          <div className="mt-0.5 text-base font-semibold text-[var(--color-text)]">
            {profile.address ?? location ?? "—"}
          </div>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider",
            tone ??
              "bg-[var(--color-bg-sunken)] text-[var(--color-text-muted)] border-[var(--color-border-subtle)]",
          )}
        >
          {tierLabel(tier)} · penalty {pct(profile.total_penalty)}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-[13px] sm:grid-cols-3">
        <Stat label="Ask price" value={money(profile.ask_price)} />
        <Stat label="Bear value" value={money(profile.bear_value)} tone="rose" />
        <Stat label="Stress value" value={money(profile.stress_value)} tone="rose" />
      </div>

      {profile.risk_flags.length > 0 && (
        <FlagBlock label="Risk drivers" tone="rose" items={profile.risk_flags} />
      )}
      {profile.trust_flags.length > 0 && (
        <FlagBlock label="Trust flags" tone="amber" items={profile.trust_flags} />
      )}
      {profile.key_risks.length > 0 && (
        <FlagBlock label="Key risks" tone="rose" items={profile.key_risks} />
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "rose";
}) {
  const valueClass =
    tone === "rose" ? "text-rose-300" : "text-[var(--color-text)]";
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
        {label}
      </div>
      <div className={cn("mt-0.5 font-medium", valueClass)}>{value}</div>
    </div>
  );
}

function FlagBlock({
  label,
  tone,
  items,
}: {
  label: string;
  tone: "rose" | "amber";
  items: string[];
}) {
  const dot = tone === "rose" ? "bg-rose-400/70" : "bg-amber-400/70";
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
