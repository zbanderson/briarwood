"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import type { ChatMessage } from "@/lib/chat/use-chat";
import type { Listing } from "@/lib/chat/events";
import { PropertyCarousel } from "./property-carousel";
import { VerdictCard } from "./verdict-card";
import { ChartFrame } from "./chart-frame";
import { ScenarioTable } from "./scenario-table";
import { ComparisonTable } from "./comparison-table";
import { TownSummaryCard } from "./town-summary-card";
import { CompsPreviewCard } from "./comps-preview-card";
import { RiskProfileCard } from "./risk-profile-card";
import { ValueThesisCard } from "./value-thesis-card";
import { CmaTableCard } from "./cma-table-card";
import { StrategyPathCard } from "./strategy-path-card";
import { RentOutlookCard } from "./rent-outlook-card";
import { TrustSummaryCard } from "./trust-summary-card";
import { ResearchUpdateCard } from "./research-update-card";
import { ModuleBadges } from "./module-badges";
import { GroundedText } from "./grounded-text";
import { EntryPointCard } from "./entry-point-card";

// Lazy-load Mapbox — keeps it out of the main bundle and avoids SSR errors
// from window-only globals in mapbox-gl.
const InlineMap = dynamic(
  () => import("./inline-map").then((m) => m.InlineMap),
  { ssr: false, loading: () => <MapSkeleton /> },
);

function MapSkeleton() {
  return (
    <div
      aria-hidden
      className="mt-3 h-[220px] w-full animate-pulse rounded-xl bg-[var(--color-bg-sunken)] border border-[var(--color-border-subtle)]"
    />
  );
}

type MessageListProps = {
  messages: ChatMessage[];
  onSelectListing?: (listing: Listing) => void;
  onPrompt?: (prompt: string) => void;
};

export function MessageList({
  messages,
  onSelectListing,
  onPrompt,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, messages[messages.length - 1]?.content]);

  return (
    <div className="flex flex-col gap-6">
      {messages.map((m) =>
        m.role === "user" ? (
          <UserMessage key={m.id} content={m.content} />
        ) : (
          <AssistantMessage
            key={m.id}
            message={m}
            onSelectListing={onSelectListing}
            onPrompt={onPrompt}
          />
        ),
      )}
      <div ref={bottomRef} aria-hidden />
    </div>
  );
}

function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div
        className={cn(
          "max-w-[80%] rounded-2xl px-4 py-2.5 text-[15px] leading-6",
          "bg-[var(--color-user-bubble)] text-[var(--color-text)]",
          "whitespace-pre-wrap break-words",
        )}
      >
        {content}
      </div>
    </div>
  );
}

function AssistantMessage({
  message,
  onSelectListing,
  onPrompt,
}: {
  message: ChatMessage;
  onSelectListing?: (listing: Listing) => void;
  onPrompt?: (prompt: string) => void;
}) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const showDots = message.isStreaming && message.content.length === 0;
  const listings = message.listings ?? [];
  const map = message.map;
  const charts = message.charts ?? [];
  const verdict = message.verdict;
  const scenarioTable = message.scenarioTable;
  const comparisonTable = message.comparisonTable;
  const townSummary = message.townSummary;
  const compsPreview = message.compsPreview;
  const riskProfile = message.riskProfile;
  const valueThesis = message.valueThesis;
  const cmaTable = message.cmaTable;
  const strategyPath = message.strategyPath;
  const rentOutlook = message.rentOutlook;
  const trustSummary = message.trustSummary;
  const researchUpdate = message.researchUpdate;
  const modulesRan = message.modulesRan ?? [];
  const anchors = message.groundingAnchors ?? [];
  const muted = message.ungroundedDeclaration === true;
  const showCompPreview = Boolean(compsPreview && !valueThesis && !cmaTable);

  return (
    <div className="flex">
      <div className="w-full text-[15px] leading-7 text-[var(--color-text)]">
        {verdict && <VerdictCard verdict={verdict} />}

        {showDots ? (
          <StreamingIndicator />
        ) : (
          message.content && (
            <GroundedText
              content={message.content}
              anchors={anchors}
              muted={muted}
            />
          )
        )}

        {strategyPath && <StrategyPathCard strategy={strategyPath} />}
        {strategyPath && onPrompt && (
          <InlinePrompt
            prompt="Walk me through the recommended path"
            label="Drill into strategy"
            onPick={onPrompt}
          />
        )}

        {valueThesis && <EntryPointCard thesis={valueThesis} />}

        {valueThesis && <ValueThesisCard thesis={valueThesis} hideCompStory={Boolean(cmaTable)} />}
        {valueThesis && onPrompt && (
          <InlinePrompt
            prompt="What would change your value view?"
            label="Drill into value thesis"
            onPick={onPrompt}
          />
        )}

        {rentOutlook && <RentOutlookCard outlook={rentOutlook} />}
        {rentOutlook && onPrompt && (
          <InlinePrompt
            prompt="What rent would make this deal work?"
            label="Drill into rent"
            onPick={onPrompt}
          />
        )}

        {trustSummary && <TrustSummaryCard summary={trustSummary} />}
        {trustSummary && onPrompt && (
          <InlinePrompt
            prompt="What data is missing or estimated?"
            label="Drill into confidence"
            onPick={onPrompt}
          />
        )}

        {riskProfile && <RiskProfileCard profile={riskProfile} />}
        {riskProfile && onPrompt && (
          <InlinePrompt
            prompt="What's the biggest risk here?"
            label="Drill into risk"
            onPick={onPrompt}
          />
        )}

        {cmaTable && <CmaTableCard table={cmaTable} />}
        {cmaTable && onPrompt && (
          <InlinePrompt
            prompt="Which comps actually fed fair value?"
            label="Drill into the CMA"
            onPick={onPrompt}
          />
        )}

        {showCompPreview && compsPreview && <CompsPreviewCard preview={compsPreview} />}
        {showCompPreview && compsPreview && onPrompt && (
          <InlinePrompt
            prompt={
              compsPreview.count > compsPreview.comps.length
                ? "Show me the full comp set"
                : "Why were these comps chosen?"
            }
            label="Drill into comps"
            onPick={onPrompt}
          />
        )}

        {townSummary && <TownSummaryCard summary={townSummary} />}
        {townSummary && onPrompt && (
          <InlinePrompt
            prompt="What's driving the town outlook?"
            label="Drill into town context"
            onPick={onPrompt}
          />
        )}

        {scenarioTable && <ScenarioTable table={scenarioTable} />}
        {scenarioTable && onPrompt && (
          <InlinePrompt
            prompt="Show me the downside case in more detail"
            label="Drill into scenarios"
            onPick={onPrompt}
          />
        )}

        {charts.map((c, i) => (
          <ChartFrame key={`${c.kind ?? "chart"}-${c.url ?? "native"}-${i}`} chart={c} />
        ))}

        {researchUpdate && <ResearchUpdateCard research={researchUpdate} />}

        {comparisonTable && <ComparisonTable table={comparisonTable} />}

        {map && map.pins.length > 0 && (
          <InlineMap
            center={map.center}
            pins={map.pins}
            listings={listings}
            activeId={hoveredId}
            onHover={setHoveredId}
            onSelect={(id) => {
              const l = listings.find((x) => x.id === id);
              if (l) onSelectListing?.(l);
            }}
          />
        )}

        {listings.length > 0 && (
          <PropertyCarousel
            listings={listings}
            activeId={hoveredId}
            onHover={(l) => setHoveredId(l?.id ?? null)}
            onSelect={onSelectListing}
          />
        )}

        {modulesRan.length > 0 && <ModuleBadges modules={modulesRan} />}
      </div>
    </div>
  );
}

function InlinePrompt({
  label,
  prompt,
  onPick,
}: {
  label: string;
  prompt: string;
  onPick: (prompt: string) => void;
}) {
  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => onPick(prompt)}
        className={cn(
          "rounded-full border border-[var(--color-border-subtle)] px-3 py-1.5 text-xs",
          "text-[var(--color-text-muted)] hover:text-[var(--color-text)]",
          "hover:border-[var(--color-border)] hover:bg-[var(--color-surface)]",
          "transition-colors",
        )}
      >
        {label}
      </button>
    </div>
  );
}

export function StreamingIndicator() {
  return (
    <span
      className="dot-pulse inline-flex items-center gap-1 text-[var(--color-text-faint)]"
      aria-label="Assistant is typing"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
    </span>
  );
}

export function SuggestionChips({
  items,
  onPick,
  disabled,
}: {
  items: string[];
  onPick: (s: string) => void;
  disabled?: boolean;
}) {
  if (items.length === 0) return null;
  return (
    <div
      role="group"
      aria-label="Suggested follow-ups"
      className="mt-4 flex flex-wrap gap-2"
    >
      {items.map((s) => (
        <button
          key={s}
          type="button"
          onClick={() => onPick(s)}
          disabled={disabled}
          className={cn(
            "rounded-full border border-[var(--color-border-subtle)] px-3 py-1.5 text-xs",
            "text-[var(--color-text-muted)] hover:text-[var(--color-text)]",
            "hover:border-[var(--color-border)] hover:bg-[var(--color-surface)]",
            "transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
          )}
        >
          {s}
        </button>
      ))}
    </div>
  );
}
