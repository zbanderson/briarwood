"use client";

import dynamic from "next/dynamic";
import { useEffect, type ReactNode } from "react";
import { ExternalLink, MapPin, X } from "lucide-react";
import { cn } from "@/lib/cn";
import type { Listing, MapPin as ChatMapPin, TownSignalItem } from "@/lib/chat/events";

const InlineMap = dynamic(
  () => import("./inline-map").then((m) => m.InlineMap),
  { ssr: false },
);

type Props = {
  signal: TownSignalItem | null;
  subjectListing?: Listing | null;
  onClose: () => void;
};

const BUCKET_TONE: Record<TownSignalItem["bucket"], string> = {
  bullish: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  bearish: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  watch: "bg-amber-500/15 text-amber-200 border-amber-500/30",
};

export function TownSignalPanel({ signal, subjectListing, onClose }: Props) {
  useEffect(() => {
    if (!signal) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const isMobile = window.matchMedia("(max-width: 767px)").matches;
    const prevOverflow = document.body.style.overflow;
    if (isMobile) document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [signal, onClose]);

  if (!signal) return null;

  const pins: ChatMapPin[] = [];
  if (
    subjectListing?.lat != null &&
    subjectListing?.lng != null
  ) {
    pins.push({
      id: `${subjectListing.id}-subject`,
      lat: subjectListing.lat,
      lng: subjectListing.lng,
      label: "Home",
    });
  }
  if (
    signal.development_lat != null &&
    signal.development_lng != null
  ) {
    pins.push({
      id: `${signal.id}-development`,
      lat: signal.development_lat,
      lng: signal.development_lng,
      label: "Site",
    });
  }
  const center =
    pins.length > 0
      ? [
          pins.reduce((sum, pin) => sum + pin.lng, 0) / pins.length,
          pins.reduce((sum, pin) => sum + pin.lat, 0) / pins.length,
        ] as [number, number]
      : null;

  return (
    <>
      <button
        type="button"
        aria-label="Close town signal details"
        onClick={onClose}
        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm md:hidden"
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`Details for ${signal.title}`}
        className={cn(
          "fixed inset-0 z-50 flex flex-col bg-[var(--color-bg)]",
          "md:static md:z-auto md:w-[460px] lg:w-[520px] md:shrink-0",
          "md:border-l md:border-[var(--color-border-subtle)]",
        )}
      >
        <header
          className={cn(
            "shrink-0 flex items-start justify-between gap-3 px-5 py-4",
            "border-b border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)]/80 backdrop-blur",
          )}
        >
          <div className="min-w-0">
            <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
              Town signal
            </div>
            <h2 className="mt-1 text-base font-semibold text-[var(--color-text)]">
              {signal.title}
            </h2>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span
                className={cn(
                  "rounded-full border px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider",
                  BUCKET_TONE[signal.bucket],
                )}
              >
                {signal.bucket}
              </span>
              <span className="rounded-full border border-[var(--color-border-subtle)] px-2.5 py-1 text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
                {signal.status.replaceAll("_", " ")}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close details"
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-md",
              "text-[var(--color-text-muted)] hover:bg-[var(--color-surface)] hover:text-[var(--color-text)]",
              "transition-colors",
            )}
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          <Section title="Project summary">
            <p className="text-sm leading-6 text-[var(--color-text-muted)]">
              {signal.project_summary}
            </p>
          </Section>

          <Section title="Location and context">
            <div className="space-y-2 text-sm text-[var(--color-text-muted)]">
              {signal.location_label && (
                <div className="flex items-start gap-2">
                  <MapPin className="mt-0.5 h-4 w-4 text-[var(--color-text-faint)]" aria-hidden />
                  <span>{signal.location_label}</span>
                </div>
              )}
              <div>
                Confidence: {formatConfidence(signal.confidence)}
              </div>
              {subjectListing && (
                <div>
                  Subject property: {subjectListing.address_line}
                </div>
              )}
            </div>
          </Section>

          {center && pins.length > 0 && (
            <Section title="Map">
              <InlineMap center={center} pins={pins} />
            </Section>
          )}

          {signal.facts.length > 0 && (
            <Section title="Structured facts">
              <ul className="space-y-2 text-sm leading-6 text-[var(--color-text-muted)]">
                {signal.facts.map((fact, index) => (
                  <li key={index} className="flex gap-2">
                    <span className="mt-2 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-text-faint)]" />
                    <span>{fact}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {signal.inference && (
            <Section title="Briarwood interpretation">
              <p className="text-sm leading-6 text-[var(--color-text-muted)]">
                {signal.inference}
              </p>
            </Section>
          )}

          <Section title="Source">
            <div className="space-y-2 text-sm text-[var(--color-text-muted)]">
              <div>{signal.source_title ?? "Source document"}</div>
              <div className="capitalize">{signal.source_type.replaceAll("_", " ")}</div>
              {signal.source_date && <div>{signal.source_date}</div>}
              {signal.source_url && (
                <a
                  href={signal.source_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm",
                    "border border-[var(--color-border-subtle)] bg-[var(--color-surface)]",
                    "text-[var(--color-text-muted)] hover:text-[var(--color-text)]",
                    "hover:border-[var(--color-border)] transition-colors",
                  )}
                >
                  <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                  Open source document
                </a>
              )}
            </div>
          </Section>

          <Section title="Evidence excerpt">
            <p className="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] px-3 py-2 text-sm leading-6 text-[var(--color-text-muted)]">
              {signal.evidence_excerpt}
            </p>
          </Section>
        </div>
      </aside>
    </>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="mt-5 first:mt-0">
      <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-faint)]">
        {title}
      </div>
      <div className="mt-2">{children}</div>
    </section>
  );
}

function formatConfidence(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "Unknown";
  return `${Math.round(value * 100)}%`;
}
