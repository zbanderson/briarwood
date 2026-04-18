"use client";

import "mapbox-gl/dist/mapbox-gl.css";

import { useEffect, useRef } from "react";
import {
  Map as MapboxMap,
  Marker,
  NavigationControl,
  type MapRef,
} from "react-map-gl/mapbox";
import { MapPin as MapPinIcon } from "lucide-react";
import { cn } from "@/lib/cn";
import type { Listing, MapPin } from "@/lib/chat/events";

type Props = {
  center: [number, number]; // [lng, lat]
  pins: MapPin[];
  listings?: Listing[];
  activeId?: string | null;
  onHover?: (pinId: string | null) => void;
  onSelect?: (pinId: string) => void;
};

const TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

// Mapbox dark style — themed cleanly to match our background.
const MAP_STYLE = "mapbox://styles/mapbox/dark-v11";

export function InlineMap({
  center,
  pins,
  listings,
  activeId,
  onHover,
  onSelect,
}: Props) {
  const mapRef = useRef<MapRef>(null);

  // Fit bounds whenever the pin set changes.
  useEffect(() => {
    if (!TOKEN) return;
    const map = mapRef.current;
    if (!map || pins.length === 0) return;

    const lngs = pins.map((p) => p.lng);
    const lats = pins.map((p) => p.lat);
    const sw: [number, number] = [Math.min(...lngs), Math.min(...lats)];
    const ne: [number, number] = [Math.max(...lngs), Math.max(...lats)];

    if (pins.length === 1) {
      map.flyTo({ center: [pins[0].lng, pins[0].lat], zoom: 14, duration: 600 });
    } else {
      map.fitBounds([sw, ne], {
        padding: { top: 40, bottom: 40, left: 40, right: 40 },
        duration: 600,
        maxZoom: 14,
      });
    }
  }, [pins]);

  // Pan to the active pin when the user hovers a card off-screen.
  useEffect(() => {
    if (!TOKEN || !activeId) return;
    const pin = pins.find((p) => p.id === activeId);
    if (!pin) return;
    mapRef.current?.panTo([pin.lng, pin.lat], { duration: 300 });
  }, [activeId, pins]);

  if (!TOKEN) {
    return <MissingTokenFallback pinCount={pins.length} />;
  }

  return (
    <div className="relative mt-3 h-[280px] w-full overflow-hidden rounded-xl border border-[var(--color-border-subtle)]">
      <MapboxMap
        ref={mapRef}
        mapboxAccessToken={TOKEN}
        initialViewState={{
          longitude: center[0],
          latitude: center[1],
          zoom: 12,
        }}
        mapStyle={MAP_STYLE}
        attributionControl={false}
        // Subtle interaction defaults — no rotation, no pitch.
        dragRotate={false}
        touchPitch={false}
        cooperativeGestures
      >
        <NavigationControl
          position="top-right"
          showCompass={false}
          visualizePitch={false}
        />

        {pins.map((p) => (
          <Marker
            key={p.id}
            longitude={p.lng}
            latitude={p.lat}
            anchor="bottom"
            onClick={(e) => {
              e.originalEvent.stopPropagation();
              onSelect?.(p.id);
            }}
          >
            <PinMarker
              label={p.label ?? ""}
              active={activeId === p.id}
              onMouseEnter={() => onHover?.(p.id)}
              onMouseLeave={() => onHover?.(null)}
            />
          </Marker>
        ))}
      </MapboxMap>

      {listings && listings.length > 0 && (
        <div
          aria-hidden
          className="pointer-events-none absolute bottom-2 left-2 rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)]/85 px-2 py-1 text-[11px] text-[var(--color-text-faint)] backdrop-blur"
        >
          {listings.length} {listings.length === 1 ? "listing" : "listings"}
        </div>
      )}
    </div>
  );
}

function PinMarker({
  label,
  active,
  onMouseEnter,
  onMouseLeave,
}: {
  label: string;
  active?: boolean;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}) {
  return (
    <div
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className={cn(
        "relative flex translate-y-1 cursor-pointer items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold shadow-md transition-all",
        active
          ? "z-10 scale-110 border-[var(--color-accent)] bg-[var(--color-accent)] text-[var(--color-accent-fg)]"
          : "border-[var(--color-border)] bg-[var(--color-bg-elevated)] text-[var(--color-text)] hover:border-[var(--color-text-faint)]",
      )}
    >
      <span>{label}</span>
      <span
        className={cn(
          "absolute -bottom-1 left-1/2 -translate-x-1/2 h-2 w-2 rotate-45 border-r border-b",
          active
            ? "bg-[var(--color-accent)] border-[var(--color-accent)]"
            : "bg-[var(--color-bg-elevated)] border-[var(--color-border)]",
        )}
      />
    </div>
  );
}

function MissingTokenFallback({ pinCount }: { pinCount: number }) {
  return (
    <div
      role="note"
      className="mt-3 flex h-[120px] w-full flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] px-4 text-center"
    >
      <MapPinIcon className="h-4 w-4 text-[var(--color-text-faint)]" aria-hidden />
      <p className="text-xs text-[var(--color-text-muted)]">
        Map needs a Mapbox token.{" "}
        <code className="rounded bg-[var(--color-surface)] px-1 py-0.5 text-[10px] text-[var(--color-text)]">
          NEXT_PUBLIC_MAPBOX_TOKEN
        </code>{" "}
        in <code className="text-[var(--color-text)]">web/.env.local</code>
      </p>
      <p className="text-[11px] text-[var(--color-text-faint)]">
        ({pinCount} {pinCount === 1 ? "pin" : "pins"} ready to render)
      </p>
    </div>
  );
}
