"use client";

import { useEffect, useRef, useState, type MutableRefObject } from "react";
import { MapPin as MapPinIcon } from "lucide-react";
import type { Listing, MapPin } from "@/lib/chat/events";

type Props = {
  center: [number, number]; // [lng, lat]
  pins: MapPin[];
  listings?: Listing[];
  activeId?: string | null;
  onHover?: (pinId: string | null) => void;
  onSelect?: (pinId: string) => void;
};

type GoogleMapsNamespace = {
  Map: new (element: HTMLElement, options: GoogleMapOptions) => GoogleMapInstance;
  Marker: new (options: GoogleMarkerOptions) => GoogleMarkerInstance;
  LatLngBounds: new () => GoogleLatLngBounds;
  Size: new (width: number, height: number) => GoogleSize;
  Point: new (x: number, y: number) => GooglePoint;
};

type GoogleWindow = Window & {
  google?: {
    maps?: GoogleMapsNamespace;
  };
  __briarwoodGoogleMapsPromise?: Promise<GoogleMapsNamespace>;
};

type GoogleMapOptions = {
  center: GoogleLatLngLiteral;
  zoom: number;
  disableDefaultUI?: boolean;
  zoomControl?: boolean;
  mapTypeControl?: boolean;
  streetViewControl?: boolean;
  fullscreenControl?: boolean;
  clickableIcons?: boolean;
  gestureHandling?: "cooperative" | "greedy" | "none" | "auto";
  styles?: GoogleMapStyle[];
};

type GoogleMapStyle = {
  elementType?: string;
  featureType?: string;
  stylers: Array<Record<string, string | number>>;
};

type GoogleLatLngLiteral = {
  lat: number;
  lng: number;
};

type GoogleSize = object;
type GooglePoint = object;

type GoogleMapInstance = {
  fitBounds: (bounds: GoogleLatLngBounds, padding?: number | GooglePadding) => void;
  panTo: (latLng: GoogleLatLngLiteral) => void;
  setCenter: (latLng: GoogleLatLngLiteral) => void;
  setZoom: (zoom: number) => void;
};

type GooglePadding = {
  top: number;
  right: number;
  bottom: number;
  left: number;
};

type GoogleLatLngBounds = {
  extend: (latLng: GoogleLatLngLiteral) => void;
};

type GoogleMarkerOptions = {
  map: GoogleMapInstance;
  position: GoogleLatLngLiteral;
  title?: string;
  optimized?: boolean;
  zIndex?: number;
  icon?: GoogleMarkerIcon;
};

type GoogleMarkerIcon = {
  url: string;
  scaledSize: GoogleSize;
  anchor: GooglePoint;
  labelOrigin: GooglePoint;
};

type GoogleMapsEventHandle = {
  remove?: () => void;
};

type GoogleMarkerInstance = {
  addListener: (eventName: string, handler: () => void) => GoogleMapsEventHandle;
  setIcon: (icon: GoogleMarkerIcon) => void;
  setMap: (map: GoogleMapInstance | null) => void;
  setPosition: (position: GoogleLatLngLiteral) => void;
  setTitle: (title: string) => void;
  setZIndex: (zIndex: number) => void;
};

type RenderedMarker = {
  pinId: string;
  marker: GoogleMarkerInstance;
  listeners: GoogleMapsEventHandle[];
};

const API_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
const GOOGLE_MAPS_API_SRC = "https://maps.googleapis.com/maps/api/js";

const GOOGLE_MAP_STYLE: GoogleMapStyle[] = [
  { elementType: "geometry", stylers: [{ color: "#1f1e1d" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#b8b2a4" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#1f1e1d" }] },
  { featureType: "administrative", elementType: "geometry", stylers: [{ color: "#3a3835" }] },
  { featureType: "poi", elementType: "geometry", stylers: [{ color: "#262524" }] },
  { featureType: "poi.park", elementType: "geometry", stylers: [{ color: "#232522" }] },
  { featureType: "road", elementType: "geometry", stylers: [{ color: "#34322f" }] },
  { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#4a423a" }] },
  { featureType: "transit", elementType: "geometry", stylers: [{ color: "#2f2d2b" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#18232e" }] },
];

export function InlineMap({
  center,
  pins,
  listings,
  activeId,
  onHover,
  onSelect,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<GoogleMapInstance | null>(null);
  const markersRef = useRef<RenderedMarker[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const keyState = getGoogleMapsApiKeyState(API_KEY);

  useEffect(() => {
    if (!keyState.ok) return;
    if (!containerRef.current) return;

    let disposed = false;

    loadGoogleMaps(API_KEY)
      .then((maps) => {
        if (disposed || !containerRef.current) return;
        setLoadError(null);
        if (!mapRef.current) {
          mapRef.current = new maps.Map(containerRef.current, {
            center: { lng: center[0], lat: center[1] },
            zoom: pins.length <= 1 ? 14 : 12,
            disableDefaultUI: true,
            zoomControl: true,
            mapTypeControl: false,
            streetViewControl: false,
            fullscreenControl: false,
            clickableIcons: false,
            gestureHandling: "cooperative",
            styles: GOOGLE_MAP_STYLE,
          });
        }
        renderMarkers({
          maps,
          map: mapRef.current,
          markersRef,
          pins,
          activeId: null,
          onHover,
          onSelect,
        });
        fitPins(maps, mapRef.current, pins, center);
      })
      .catch(() => {
        if (!disposed) {
          setLoadError("Google Maps could not load in the browser.");
        }
      });

    return () => {
      disposed = true;
    };
  }, [center, keyState.ok, onHover, onSelect, pins]);

  useEffect(() => {
    if (!keyState.ok || !mapRef.current) return;
    const maps = (window as GoogleWindow).google?.maps;
    if (!maps) return;
    renderMarkers({
      maps,
      map: mapRef.current,
      markersRef,
      pins,
      activeId,
      onHover,
      onSelect,
    });
    if (!activeId) return;
    const pin = pins.find((candidate) => candidate.id === activeId);
    if (!pin) return;
    mapRef.current.panTo({ lat: pin.lat, lng: pin.lng });
  }, [activeId, keyState.ok, onHover, onSelect, pins]);

  useEffect(() => {
    return () => {
      clearMarkers(markersRef.current);
      markersRef.current = [];
      mapRef.current = null;
    };
  }, []);

  if (!keyState.ok) {
    return <MissingApiKeyFallback pinCount={pins.length} reason={keyState.reason} />;
  }
  if (loadError) {
    return <MissingApiKeyFallback pinCount={pins.length} reason={loadError} />;
  }

  return (
    <div className="relative mt-3 h-[220px] w-full overflow-hidden rounded-xl border border-[var(--color-border-subtle)]">
      <div ref={containerRef} className="h-full w-full" />

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

function renderMarkers({
  maps,
  map,
  markersRef,
  pins,
  activeId,
  onHover,
  onSelect,
}: {
  maps: GoogleMapsNamespace;
  map: GoogleMapInstance;
  markersRef: MutableRefObject<RenderedMarker[]>;
  pins: MapPin[];
  activeId?: string | null;
  onHover?: (pinId: string | null) => void;
  onSelect?: (pinId: string) => void;
}) {
  const nextById = new Map(pins.map((pin) => [pin.id, pin]));
  const existingById = new Map(markersRef.current.map((entry) => [entry.pinId, entry]));

  for (const entry of markersRef.current) {
    if (nextById.has(entry.pinId)) continue;
    detachMarker(entry);
    existingById.delete(entry.pinId);
  }

  const nextRendered: RenderedMarker[] = [];
  for (const pin of pins) {
    const existing = existingById.get(pin.id);
    const isActive = activeId === pin.id;
    if (existing) {
      existing.marker.setPosition({ lat: pin.lat, lng: pin.lng });
      existing.marker.setTitle(pin.label ?? "Property");
      existing.marker.setZIndex(isActive ? 2 : 1);
      existing.marker.setIcon(buildMarkerIcon(maps, pin.label ?? "", isActive));
      nextRendered.push(existing);
      continue;
    }

    const marker = new maps.Marker({
      map,
      position: { lat: pin.lat, lng: pin.lng },
      title: pin.label ?? "Property",
      optimized: false,
      zIndex: isActive ? 2 : 1,
      icon: buildMarkerIcon(maps, pin.label ?? "", isActive),
    });

    const listeners = [
      marker.addListener("click", () => onSelect?.(pin.id)),
      marker.addListener("mouseover", () => onHover?.(pin.id)),
      marker.addListener("mouseout", () => onHover?.(null)),
    ];

    nextRendered.push({ pinId: pin.id, marker, listeners });
  }

  markersRef.current = nextRendered;
}

function fitPins(
  maps: GoogleMapsNamespace,
  map: GoogleMapInstance,
  pins: MapPin[],
  center: [number, number],
) {
  if (pins.length === 0) {
    map.setCenter({ lng: center[0], lat: center[1] });
    map.setZoom(12);
    return;
  }
  if (pins.length === 1) {
    map.setCenter({ lng: pins[0].lng, lat: pins[0].lat });
    map.setZoom(14);
    return;
  }

  const bounds = new maps.LatLngBounds();
  for (const pin of pins) {
    bounds.extend({ lat: pin.lat, lng: pin.lng });
  }
  map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
}

function clearMarkers(markers: RenderedMarker[]) {
  for (const entry of markers) {
    detachMarker(entry);
  }
}

function detachMarker(entry: RenderedMarker) {
  for (const listener of entry.listeners) {
    listener.remove?.();
  }
  entry.marker.setMap(null);
}

function buildMarkerIcon(
  maps: GoogleMapsNamespace,
  label: string,
  active: boolean,
): GoogleMarkerIcon {
  const visibleLabel = label.trim() || "Home";
  const sanitizedLabel = escapeSvgText(visibleLabel);
  const width = Math.max(64, Math.min(160, 20 + visibleLabel.length * 8));
  const height = 42;
  const pillFill = active ? "#c96442" : "#262524";
  const pillStroke = active ? "#c96442" : "#3a3835";
  const textFill = active ? "#fff8f3" : "#f3efe6";
  const pointerFill = active ? "#c96442" : "#262524";
  const pointerStroke = active ? "#c96442" : "#3a3835";

  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
      <rect x="1" y="1" rx="16" ry="16" width="${width - 2}" height="28" fill="${pillFill}" stroke="${pillStroke}" stroke-width="2" />
      <path d="M ${width / 2 - 6} 25 L ${width / 2} 35 L ${width / 2 + 6} 25 Z" fill="${pointerFill}" stroke="${pointerStroke}" stroke-width="2" stroke-linejoin="round" />
      <text x="50%" y="18" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" font-weight="700" fill="${textFill}">${sanitizedLabel}</text>
    </svg>
  `.trim();

  return {
    url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
    scaledSize: new maps.Size(width, height),
    anchor: new maps.Point(width / 2, height),
    labelOrigin: new maps.Point(width / 2, 16),
  };
}

function escapeSvgText(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function getGoogleMapsApiKeyState(apiKey: string | undefined) {
  const normalized = apiKey?.trim() ?? "";
  if (!normalized) {
    return {
      ok: false,
      reason:
        "Map needs a browser-safe Google Maps key in web/.env.local as NEXT_PUBLIC_GOOGLE_MAPS_API_KEY.",
    };
  }
  if (normalized.includes("YOUR_") || normalized.includes("your_")) {
    return {
      ok: false,
      reason:
        "Replace the placeholder Google Maps key in web/.env.local with a real browser key.",
    };
  }
  return { ok: true, reason: "" };
}

function loadGoogleMaps(apiKey: string | undefined): Promise<GoogleMapsNamespace> {
  const normalized = apiKey?.trim();
  if (!normalized) {
    return Promise.reject(new Error("Missing Google Maps API key"));
  }

  const win = window as GoogleWindow;
  if (win.google?.maps) {
    return Promise.resolve(win.google.maps);
  }
  if (win.__briarwoodGoogleMapsPromise) {
    return win.__briarwoodGoogleMapsPromise;
  }

  win.__briarwoodGoogleMapsPromise = new Promise<GoogleMapsNamespace>((resolve, reject) => {
    const callbackName = "__briarwoodGoogleMapsInit";
    const existingScript = document.querySelector<HTMLScriptElement>(
      `script[data-google-maps-loader="briarwood"]`,
    );

    (win as GoogleWindow & Record<string, unknown>)[callbackName] = () => {
      const maps = (window as GoogleWindow).google?.maps;
      if (!maps) {
        reject(new Error("Google Maps loaded without maps namespace"));
        return;
      }
      resolve(maps);
    };

    if (existingScript) {
      existingScript.addEventListener("error", () => {
        reject(new Error("Google Maps script failed to load"));
      });
      return;
    }

    const script = document.createElement("script");
    script.src = `${GOOGLE_MAPS_API_SRC}?key=${encodeURIComponent(normalized)}&loading=async&callback=${callbackName}`;
    script.async = true;
    script.defer = true;
    script.dataset.googleMapsLoader = "briarwood";
    script.onerror = () => {
      reject(new Error("Google Maps script failed to load"));
    };
    document.head.appendChild(script);
  }).catch((error) => {
    win.__briarwoodGoogleMapsPromise = undefined;
    throw error;
  });

  return win.__briarwoodGoogleMapsPromise;
}

function MissingApiKeyFallback({
  pinCount,
  reason,
}: {
  pinCount: number;
  reason: string;
}) {
  return (
    <div
      role="note"
      className="mt-3 flex h-[120px] w-full flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] px-4 text-center"
    >
      <MapPinIcon className="h-4 w-4 text-[var(--color-text-faint)]" aria-hidden />
      <p className="text-xs text-[var(--color-text-muted)]">
        {reason}{" "}
        <code className="rounded bg-[var(--color-surface)] px-1 py-0.5 text-[10px] text-[var(--color-text)]">
          NEXT_PUBLIC_GOOGLE_MAPS_API_KEY
        </code>{" "}
        in <code className="text-[var(--color-text)]">web/.env.local</code>
      </p>
      <p className="text-[11px] text-[var(--color-text-faint)]">
        ({pinCount} {pinCount === 1 ? "pin" : "pins"} ready to render)
      </p>
    </div>
  );
}
