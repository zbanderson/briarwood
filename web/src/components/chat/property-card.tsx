"use client";

import { Bath, BedDouble, ExternalLink, Maximize2 } from "lucide-react";
import { cn } from "@/lib/cn";
import type { Listing, ListingStatus } from "@/lib/chat/events";

type Props = {
  listing: Listing;
  /** Highlighted state — driven by the inline map (Phase 3.4). */
  active?: boolean;
  onSelect?: (listing: Listing) => void;
  onHover?: (listing: Listing | null) => void;
  className?: string;
};

const STATUS_LABEL: Record<ListingStatus, string> = {
  active: "Active",
  pending: "Pending",
  contingent: "Contingent",
  sold: "Sold",
};

const STATUS_TONE: Record<ListingStatus, string> = {
  active: "bg-emerald-500/15 text-emerald-300/90 border-emerald-500/20",
  pending: "bg-amber-500/15 text-amber-200/90 border-amber-500/20",
  contingent: "bg-amber-500/15 text-amber-200/90 border-amber-500/20",
  sold: "bg-zinc-500/15 text-zinc-300/80 border-zinc-500/20",
};

function formatPrice(p: number) {
  if (p >= 1_000_000) {
    const m = p / 1_000_000;
    return `$${m % 1 === 0 ? m.toFixed(0) : m.toFixed(2)}M`;
  }
  return `$${(p / 1000).toFixed(0)}k`;
}

function formatSqft(s: number) {
  return s.toLocaleString();
}

export function PropertyCard({
  listing,
  active,
  onSelect,
  onHover,
  className,
}: Props) {
  const tone = STATUS_TONE[listing.status];
  const previewImage = listing.photo_url ?? listing.streetViewImageUrl;
  const photoStyle = previewImage
    ? { backgroundImage: `url(${previewImage})` }
    : {
        backgroundImage: `linear-gradient(135deg,
          oklch(0.42 0.07 ${listing.hue ?? 30}) 0%,
          oklch(0.28 0.05 ${(listing.hue ?? 30) + 30}) 100%)`,
      };

  const viewDetails = () => onSelect?.(listing);

  return (
    <article
      onMouseEnter={() => onHover?.(listing)}
      onMouseLeave={() => onHover?.(null)}
      className={cn(
        "group flex w-[280px] shrink-0 snap-start flex-col overflow-hidden rounded-xl",
        "border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)]",
        "transition-all duration-150 hover:border-[var(--color-border)]",
        active && "border-[var(--color-accent)] shadow-[0_0_0_1px_var(--color-accent)]",
        className,
      )}
    >
      <button
        type="button"
        onClick={viewDetails}
        aria-label={`View details for ${listing.address_line}`}
        className="relative block h-40 w-full overflow-hidden bg-cover bg-center"
        style={photoStyle}
      >
        <span
          className={cn(
            "absolute left-3 top-3 inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium",
            tone,
          )}
        >
          {STATUS_LABEL[listing.status]}
        </span>
        {!listing.photo_url && listing.streetViewImageUrl && (
          <span className="absolute bottom-3 left-3 rounded-full border border-black/10 bg-black/55 px-2 py-0.5 text-[10px] uppercase tracking-wider text-white/90">
            Street View
          </span>
        )}
      </button>

      <div className="flex flex-1 flex-col gap-2 p-3.5">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-lg font-semibold tracking-tight text-[var(--color-text)]">
            {formatPrice(listing.price)}
          </span>
          <span className="text-xs text-[var(--color-text-faint)]">
            ${Math.round(listing.price / listing.sqft)}/sqft
          </span>
        </div>

        <p className="text-sm text-[var(--color-text-muted)] leading-snug">
          <span className="text-[var(--color-text)]">{listing.address_line}</span>
          <br />
          {listing.city}, {listing.state}
          {listing.zip ? ` ${listing.zip}` : ""}
        </p>

        <ul className="mt-1 flex items-center gap-3 text-xs text-[var(--color-text-muted)]">
          <li className="flex items-center gap-1">
            <BedDouble className="h-3.5 w-3.5" aria-hidden />
            <span>{listing.beds} bd</span>
          </li>
          <li className="flex items-center gap-1">
            <Bath className="h-3.5 w-3.5" aria-hidden />
            <span>{listing.baths} ba</span>
          </li>
          <li className="flex items-center gap-1">
            <Maximize2 className="h-3.5 w-3.5" aria-hidden />
            <span>{formatSqft(listing.sqft)} sqft</span>
          </li>
        </ul>

        <div className="mt-2 flex items-center justify-between">
          <button
            type="button"
            onClick={viewDetails}
            className={cn(
              "rounded-md px-2.5 py-1 text-xs font-medium",
              "bg-[var(--color-surface)] text-[var(--color-text)]",
              "hover:bg-[var(--color-surface-hover)] transition-colors",
            )}
          >
            View details
          </button>
          {listing.source_url && (
            <a
              href={listing.source_url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1 text-xs text-[var(--color-text-faint)] hover:text-[var(--color-text-muted)]"
              aria-label="Open original listing"
            >
              <ExternalLink className="h-3 w-3" aria-hidden />
              Source
            </a>
          )}
        </div>
      </div>
    </article>
  );
}
