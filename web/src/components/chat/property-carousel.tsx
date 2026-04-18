"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import type { Listing } from "@/lib/chat/events";
import { PropertyCard } from "./property-card";

type Props = {
  listings: Listing[];
  activeId?: string | null;
  onSelect?: (listing: Listing) => void;
  onHover?: (listing: Listing | null) => void;
};

export function PropertyCarousel({ listings, activeId, onSelect, onHover }: Props) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [canPrev, setCanPrev] = useState(false);
  const [canNext, setCanNext] = useState(false);

  const refresh = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    setCanPrev(el.scrollLeft > 4);
    setCanNext(el.scrollLeft + el.clientWidth < el.scrollWidth - 4);
  }, []);

  useEffect(() => {
    refresh();
  }, [listings.length, refresh]);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    el.addEventListener("scroll", refresh, { passive: true });
    const ro = new ResizeObserver(refresh);
    ro.observe(el);
    return () => {
      el.removeEventListener("scroll", refresh);
      ro.disconnect();
    };
  }, [refresh]);

  const nudge = (dir: 1 | -1) => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollBy({ left: dir * (el.clientWidth * 0.85), behavior: "smooth" });
  };

  if (listings.length === 0) return null;

  return (
    <div className="relative -mx-4 mt-3">
      <div
        ref={scrollerRef}
        className={cn(
          "flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-2",
          // Hide scrollbar — caret nav buttons are the primary affordance.
          "[scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
        )}
        role="list"
        aria-label="Matching listings"
      >
        {listings.map((l) => (
          <div role="listitem" key={l.id}>
            <PropertyCard
              listing={l}
              active={activeId === l.id}
              onSelect={onSelect}
              onHover={onHover}
            />
          </div>
        ))}
      </div>

      {(canPrev || canNext) && (
        <>
          <CaretButton
            direction="prev"
            disabled={!canPrev}
            onClick={() => nudge(-1)}
          />
          <CaretButton
            direction="next"
            disabled={!canNext}
            onClick={() => nudge(1)}
          />
        </>
      )}
    </div>
  );
}

function CaretButton({
  direction,
  disabled,
  onClick,
}: {
  direction: "prev" | "next";
  disabled: boolean;
  onClick: () => void;
}) {
  const Icon = direction === "prev" ? ChevronLeft : ChevronRight;
  return (
    <button
      type="button"
      aria-label={direction === "prev" ? "Previous listings" : "Next listings"}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "absolute top-1/2 hidden h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full",
        "border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)]/95 backdrop-blur",
        "text-[var(--color-text-muted)] transition-all",
        "hover:border-[var(--color-border)] hover:text-[var(--color-text)]",
        "disabled:opacity-0 disabled:pointer-events-none",
        "md:flex",
        direction === "prev" ? "left-1" : "right-1",
      )}
    >
      <Icon className="h-4 w-4" aria-hidden />
    </button>
  );
}
