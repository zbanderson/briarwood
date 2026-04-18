"use client";

import dynamic from "next/dynamic";
import { useEffect } from "react";
import { ExternalLink, Sparkles, X } from "lucide-react";
import { cn } from "@/lib/cn";
import type { Listing } from "@/lib/chat/events";

const InlineMap = dynamic(
  () => import("./inline-map").then((m) => m.InlineMap),
  { ssr: false },
);

type Props = {
  listing: Listing | null;
  onClose: () => void;
  /** Escalation hook: pins the listing as turn context and kicks off
   * an analysis turn in the chat. */
  onRunAnalysis?: (listing: Listing) => void;
};

const STATUS_LABEL: Record<Listing["status"], string> = {
  active: "Active",
  pending: "Pending",
  contingent: "Contingent",
  sold: "Sold",
};

function formatPrice(p: number) {
  if (p >= 1_000_000) {
    const m = p / 1_000_000;
    return `$${m % 1 === 0 ? m.toFixed(0) : m.toFixed(2)}M`;
  }
  return `$${p.toLocaleString()}`;
}

export function DetailPanel({ listing, onClose, onRunAnalysis }: Props) {
  // Escape closes; body scroll-lock only on small viewports (when panel is full-screen).
  useEffect(() => {
    if (!listing) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const isMobile = window.matchMedia("(max-width: 767px)").matches;
    const prevOverflow = document.body.style.overflow;
    if (isMobile) document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [listing, onClose]);

  if (!listing) return null;

  const photoStyle = listing.photo_url
    ? { backgroundImage: `url(${listing.photo_url})` }
    : {
        backgroundImage: `linear-gradient(135deg,
          oklch(0.42 0.07 ${listing.hue ?? 30}) 0%,
          oklch(0.28 0.05 ${(listing.hue ?? 30) + 30}) 100%)`,
      };

  return (
    <>
      {/* Mobile backdrop */}
      <button
        type="button"
        aria-label="Close details"
        onClick={onClose}
        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm md:hidden"
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`Details for ${listing.address_line}`}
        className={cn(
          "fixed inset-0 z-50 flex flex-col bg-[var(--color-bg)]",
          // Desktop: not fixed, just a sized column inside the chat layout flex.
          "md:static md:z-auto md:w-[460px] lg:w-[520px] md:shrink-0",
          "md:border-l md:border-[var(--color-border-subtle)]",
        )}
      >
        <DetailHeader listing={listing} onClose={onClose} />

        <div className="flex-1 overflow-y-auto">
          <div
            aria-hidden
            className="relative h-56 w-full bg-cover bg-center"
            style={photoStyle}
          >
            <div className="absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-[var(--color-bg)] to-transparent" />
          </div>

          <div className="px-5 py-4">
            <PriceBlock listing={listing} />
            <StatGrid listing={listing} className="mt-4" />

            {listing.lat != null && listing.lng != null && (
              <Section title="Location">
                <InlineMap
                  center={[listing.lng, listing.lat]}
                  pins={[
                    {
                      id: listing.id,
                      lat: listing.lat,
                      lng: listing.lng,
                      label: formatPrice(listing.price),
                    },
                  ]}
                />
              </Section>
            )}

            <Section title="About this property">
              <p className="text-sm text-[var(--color-text-muted)] leading-6">
                {listing.beds}-bed, {listing.baths}-bath{" "}
                {listing.year_built ? `built in ${listing.year_built}` : "home"} on a{" "}
                {listing.lot_sqft
                  ? `${listing.lot_sqft.toLocaleString()} sqft lot`
                  : "lot"}
                {" in "}
                {listing.city}, {listing.state}.
              </p>
              <p className="mt-2 text-xs text-[var(--color-text-faint)]">
                Comp analysis, scenarios, and decision summary will render here
                once the orchestrator bridge is wired in.
              </p>
            </Section>

            {listing.source_url && (
              <Section title="Source">
                <a
                  href={listing.source_url}
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
                  Open original listing
                </a>
              </Section>
            )}
          </div>
        </div>

        {onRunAnalysis && (
          <DetailFooter
            listing={listing}
            onRunAnalysis={onRunAnalysis}
          />
        )}
      </aside>
    </>
  );
}

function DetailFooter({
  listing,
  onRunAnalysis,
}: {
  listing: Listing;
  onRunAnalysis: (listing: Listing) => void;
}) {
  return (
    <footer
      className={cn(
        "shrink-0 border-t border-[var(--color-border-subtle)]",
        "bg-[var(--color-bg-elevated)]/95 backdrop-blur px-5 py-3.5",
      )}
    >
      <button
        type="button"
        onClick={() => onRunAnalysis(listing)}
        className={cn(
          "group flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium",
          "bg-[var(--color-accent)] text-[var(--color-accent-fg)]",
          "hover:brightness-110 active:brightness-95 transition",
          "shadow-sm",
        )}
      >
        <Sparkles className="h-4 w-4" aria-hidden />
        Run analysis
      </button>
      <p className="mt-2 text-center text-[11px] text-[var(--color-text-faint)]">
        Brings the chat up to speed on this property — comps, scenarios,
        decision summary.
      </p>
    </footer>
  );
}

function DetailHeader({
  listing,
  onClose,
}: {
  listing: Listing;
  onClose: () => void;
}) {
  return (
    <header
      className={cn(
        "shrink-0 flex items-center justify-between gap-3 px-5 py-3.5",
        "border-b border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)]/80 backdrop-blur",
      )}
    >
      <div className="min-w-0">
        <h2 className="truncate text-sm font-semibold text-[var(--color-text)]">
          {listing.address_line}
        </h2>
        <p className="truncate text-xs text-[var(--color-text-faint)]">
          {listing.city}, {listing.state}
          {listing.zip ? ` ${listing.zip}` : ""}
        </p>
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
  );
}

function PriceBlock({ listing }: { listing: Listing }) {
  const ppsf = Math.round(listing.price / listing.sqft);
  return (
    <div className="flex items-end justify-between gap-2">
      <div>
        <p className="text-3xl font-semibold tracking-tight text-[var(--color-text)]">
          {formatPrice(listing.price)}
        </p>
        <p className="mt-0.5 text-xs text-[var(--color-text-faint)]">
          ${ppsf}/sqft
        </p>
      </div>
      <span
        className={cn(
          "rounded-full border px-2 py-0.5 text-[11px] font-medium",
          listing.status === "active" &&
            "bg-emerald-500/15 text-emerald-300/90 border-emerald-500/20",
          listing.status === "pending" &&
            "bg-amber-500/15 text-amber-200/90 border-amber-500/20",
          listing.status === "contingent" &&
            "bg-amber-500/15 text-amber-200/90 border-amber-500/20",
          listing.status === "sold" &&
            "bg-zinc-500/15 text-zinc-300/80 border-zinc-500/20",
        )}
      >
        {STATUS_LABEL[listing.status]}
      </span>
    </div>
  );
}

function StatGrid({
  listing,
  className,
}: {
  listing: Listing;
  className?: string;
}) {
  const stats: Array<[string, string]> = [
    ["Beds", String(listing.beds)],
    ["Baths", String(listing.baths)],
    ["Interior", `${listing.sqft.toLocaleString()} sqft`],
  ];
  if (listing.lot_sqft) stats.push(["Lot", `${listing.lot_sqft.toLocaleString()} sqft`]);
  if (listing.year_built) stats.push(["Built", String(listing.year_built)]);

  return (
    <dl
      className={cn(
        "grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-border-subtle)]",
        className,
      )}
    >
      {stats.map(([label, value]) => (
        <div
          key={label}
          className="flex flex-col gap-0.5 bg-[var(--color-bg-elevated)] px-3 py-2.5"
        >
          <dt className="text-[10px] uppercase tracking-wide text-[var(--color-text-faint)]">
            {label}
          </dt>
          <dd className="text-sm font-medium text-[var(--color-text)]">
            {value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h3 className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-faint)]">
        {title}
      </h3>
      <div className="mt-2">{children}</div>
    </section>
  );
}
