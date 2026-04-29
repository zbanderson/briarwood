"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import type { ChatMessage } from "@/lib/chat/use-chat";
import type { Listing, TownSignalItem } from "@/lib/chat/events";
import { PropertyCarousel } from "./property-carousel";
import { VerdictCard } from "./verdict-card";
import { ChartFrame } from "./chart-frame";
import { ScenarioTable } from "./scenario-table";
import { ComparisonTable } from "./comparison-table";
import { TownSummaryCard } from "./town-summary-card";
import { CompsPreviewCard } from "./comps-preview-card";
import { RiskProfileCard } from "./risk-profile-card";
import { ValueThesisCard } from "./value-thesis-card";
import { CompsTableCard } from "./cma-table-card";
import { StrategyPathCard } from "./strategy-path-card";
import { RentOutlookCard } from "./rent-outlook-card";
import { TrustSummaryCard } from "./trust-summary-card";
import { ResearchUpdateCard } from "./research-update-card";
import { ModuleBadges } from "./module-badges";
import { GroundedText } from "./grounded-text";
import { EntryPointCard } from "./entry-point-card";
import { ScoutFinds } from "./scout-finds";
import { BrowseRead } from "./browse-read";
import { BrowseScout } from "./browse-scout";
import { BrowseDeeperRead } from "./browse-deeper-read";
import { InlinePrompt } from "./inline-prompt";

// Lazy-load Google Maps so the client-only browser API stays out of SSR.
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
  onSelectTownSignal?: (signal: TownSignalItem, subjectListing: Listing | null) => void;
  onPrompt?: (prompt: string) => void;
};

export function MessageList({
  messages,
  onSelectListing,
  onSelectTownSignal,
  onPrompt,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastMessageContent = messages[messages.length - 1]?.content;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, lastMessageContent]);

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
            onSelectTownSignal={onSelectTownSignal}
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
  onSelectTownSignal,
  onPrompt,
}: {
  message: ChatMessage;
  onSelectListing?: (listing: Listing) => void;
  onSelectTownSignal?: (signal: TownSignalItem, subjectListing: Listing | null) => void;
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
  const valuationComps = message.valuationComps;
  const marketSupportComps = message.marketSupportComps;
  const strategyPath = message.strategyPath;
  const rentOutlook = message.rentOutlook;
  const trustSummary = message.trustSummary;
  const researchUpdate = message.researchUpdate;
  const scoutInsights = message.scoutInsights ?? [];
  const modulesRan = message.modulesRan ?? [];
  const anchors = message.groundingAnchors ?? [];
  const muted = message.ungroundedDeclaration === true;
  const partialWarnings = message.partialDataWarnings ?? [];
  const verifierReport = message.verifierReport;
  const showCompPreview = Boolean(
    compsPreview && !valueThesis && !valuationComps && !marketSupportComps,
  );
  const subjectListing = listings[0] ?? null;
  // Phase 4c Cycle 1 — tier-aware render gate. BROWSE turns flow through
  // the new three-section layout (BrowseRead / BrowseScout /
  // BrowseDeeperRead); every other tier keeps the existing card stack.
  const isBrowse = message.answerType === "browse";

  return (
    <div className="flex">
      <div className="w-full text-[15px] leading-7 text-[var(--color-text)]">
        {partialWarnings.length > 0 && (
          <PartialDataBanner warnings={partialWarnings} />
        )}

        {/* Phase 4c Cycle 1 — BROWSE three-section newspaper layout.
            Section A renders fully in Cycle 1 (stance pill + headline +
            market_trend masthead + prose). Section B is a Cycle-1 stub
            (returns null) that fills in Cycle 2. Section C is a
            placeholder until Cycles 3-4 land the drilldowns. */}
        {isBrowse && (
          <>
            <BrowseRead
              verdict={verdict}
              valueThesis={valueThesis}
              charts={charts}
              proseContent={message.content}
              isStreaming={showDots}
              anchors={anchors}
              ungroundedDeclaration={muted}
            />
            <BrowseScout insights={scoutInsights} onPrompt={onPrompt} />
            <BrowseDeeperRead
              valueThesis={valueThesis}
              valuationComps={valuationComps ?? undefined}
              marketSupportComps={marketSupportComps ?? undefined}
              scenarioTable={scenarioTable ?? undefined}
              charts={charts}
              onPrompt={onPrompt}
            />
          </>
        )}

        {!isBrowse && verdict && <VerdictCard verdict={verdict} />}

        {!isBrowse &&
          (showDots ? (
            <StreamingIndicator />
          ) : (
            message.content && (
              <GroundedText
                content={message.content}
                anchors={anchors}
                muted={muted}
              />
            )
          ))}

        {/* Phase 4b Cycle 3 — Scout Finds renders under the synthesizer
            prose and above the existing card stack on non-BROWSE tiers.
            On BROWSE the Scout surface migrates inside Section B
            (BrowseScout) — see Phase 4c Cycle 2 in
            BROWSE_REBUILD_HANDOFF_PLAN.md. */}
        {!isBrowse && (
          <ScoutFinds insights={scoutInsights} onPrompt={onPrompt} />
        )}

        {/* Phase 4c Cycle 1 — non-BROWSE card stack. BROWSE turns short-
            circuit through the three-section layout above; every other
            tier renders the existing card stack unchanged. Cycles 2-4
            move scout / value thesis / comps / projection / rent /
            town / risk / confidence / strategy into Section C
            drilldowns; until those land, nothing in this block is
            shared with the BROWSE branch. */}
        {!isBrowse && (
          <>
            {strategyPath && <StrategyPathCard strategy={strategyPath} />}
            {strategyPath && onPrompt && (
              <InlinePrompt
                prompt="Walk me through the recommended path"
                label="Drill into strategy"
                onPick={onPrompt}
              />
            )}

            {valueThesis && <EntryPointCard thesis={valueThesis} />}

            {valueThesis && (
              <ValueThesisCard
                thesis={valueThesis}
                hideCompStory={Boolean(valuationComps || marketSupportComps)}
              />
            )}
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

            {valuationComps && (
              <CompsTableCard table={valuationComps} variant="valuation" />
            )}
            {valuationComps && onPrompt && (
              <InlinePrompt
                prompt="Which comps actually fed fair value?"
                label="Drill into fair-value comps"
                onPick={onPrompt}
              />
            )}

            {marketSupportComps && (
              <CompsTableCard
                table={marketSupportComps}
                variant="market_support"
              />
            )}
            {marketSupportComps && onPrompt && (
              <InlinePrompt
                prompt="How does the live market look around here?"
                label="Drill into market support"
                onPick={onPrompt}
              />
            )}

            {showCompPreview && compsPreview && (
              <CompsPreviewCard preview={compsPreview} />
            )}
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

            {townSummary && (
              <TownSummaryCard
                summary={townSummary}
                onSelectSignal={
                  onSelectTownSignal
                    ? (signal) => onSelectTownSignal(signal, subjectListing)
                    : undefined
                }
              />
            )}
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
              <ChartFrame
                key={`${c.kind ?? "chart"}-${c.url ?? "native"}-${i}`}
                chart={c}
              />
            ))}
          </>
        )}

        {researchUpdate && (
          <ResearchUpdateCard
            research={researchUpdate}
            onSelectSignal={
              onSelectTownSignal
                ? (signal) => onSelectTownSignal(signal, subjectListing)
                : undefined
            }
          />
        )}

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

        {verifierReport && <VerifierReasoningPanel report={verifierReport} />}

        {!message.isStreaming && message.id && !message.id.startsWith("a-") && (
          <FeedbackBar
            messageId={message.id}
            initialRating={message.userRating ?? null}
          />
        )}

        {message.critic && (
          <CriticPanel critic={message.critic} shipped={message.content} />
        )}
      </div>
    </div>
  );
}

function FeedbackBar({
  messageId,
  initialRating,
}: {
  messageId: string;
  initialRating: "up" | "down" | null;
}) {
  // Each AssistantMessage is keyed on message.id by the parent, so a
  // navigation to a different conversation remounts this component and
  // reads initialRating fresh. Within a single session the prop is
  // stable; the local state owns optimistic updates.
  const [rating, setRating] = useState<"up" | "down" | null>(initialRating);
  const [pending, setPending] = useState<"up" | "down" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async (next: "up" | "down") => {
    if (pending !== null) return;
    const previous = rating;
    setRating(next);
    setPending(next);
    setError(null);
    try {
      const res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message_id: messageId, rating: next }),
      });
      if (!res.ok) {
        throw new Error(`Couldn't save (${res.status})`);
      }
    } catch (err) {
      setRating(previous);
      setError((err as Error).message);
    } finally {
      setPending(null);
    }
  };

  const baseClass = cn(
    "inline-flex items-center justify-center h-7 w-7 rounded-md",
    "border border-transparent text-[var(--color-text-faint)]",
    "hover:text-[var(--color-text)] hover:bg-[var(--color-surface)]",
    "transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
  );
  const activeClass = "border-[var(--color-border)] text-[var(--color-text)] bg-[var(--color-surface)]";

  return (
    <div className="mt-3 flex items-center gap-1 text-xs">
      <button
        type="button"
        aria-label="This response was helpful"
        aria-pressed={rating === "up"}
        disabled={pending !== null}
        onClick={() => submit("up")}
        className={cn(baseClass, rating === "up" && activeClass)}
      >
        <ThumbIcon direction="up" filled={rating === "up"} />
      </button>
      <button
        type="button"
        aria-label="This response was not helpful"
        aria-pressed={rating === "down"}
        disabled={pending !== null}
        onClick={() => submit("down")}
        className={cn(baseClass, rating === "down" && activeClass)}
      >
        <ThumbIcon direction="down" filled={rating === "down"} />
      </button>
      {error && (
        <span
          role="alert"
          className="ml-2 text-[var(--color-text-faint)]"
        >
          {error}
        </span>
      )}
    </div>
  );
}

function ThumbIcon({
  direction,
  filled,
}: {
  direction: "up" | "down";
  filled: boolean;
}) {
  // Inline SVG so we don't pull in an icon library for two glyphs. The
  // up/down variant is a single rotation of the same path.
  const transform = direction === "down" ? "rotate(180 12 12)" : undefined;
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinejoin="round"
    >
      <g transform={transform}>
        <path d="M7 10v10H4V10h3z" />
        <path d="M7 10l4-7c1.4 0 2.4 1 2.2 2.4L13 9h5.5c1.1 0 1.9 1 1.7 2.1l-1.4 7c-.2 1.1-1.1 1.9-2.2 1.9H9c-1.1 0-2-.9-2-2V10z" />
      </g>
    </svg>
  );
}

function PartialDataBanner({
  warnings,
}: {
  warnings: NonNullable<ChatMessage["partialDataWarnings"]>;
}) {
  const [open, setOpen] = useState(false);
  const allReliable = warnings.every((w) => w.verdict_reliable);
  const tone = allReliable
    ? "border-amber-500/30 bg-amber-500/10 text-amber-100"
    : "border-rose-500/30 bg-rose-500/10 text-rose-100";
  const summary = allReliable
    ? `Some context couldn't load (${warnings.length}) — core verdict still reliable.`
    : `Some data couldn't load (${warnings.length}) — verdict may be affected.`;
  return (
    <div
      className={cn(
        "mt-3 rounded-lg border px-3 py-2 text-[12px]",
        tone,
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 text-left"
        aria-expanded={open}
      >
        <span>{summary}</span>
        <span aria-hidden className="text-[11px] opacity-70">
          {open ? "Hide" : "Details"}
        </span>
      </button>
      {open && (
        <ul className="mt-2 space-y-1 text-[12px] opacity-90">
          {warnings.map((w, i) => (
            <li key={i} className="flex gap-2">
              <span className="font-mono uppercase tracking-wider opacity-70">
                {w.section}
              </span>
              <span>— {w.reason}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function VerifierReasoningPanel({
  report,
}: {
  report: NonNullable<ChatMessage["verifierReport"]>;
}) {
  const hasViolations = report.violations.length > 0;
  return (
    <details className="mt-3 rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] p-2 text-xs text-[var(--color-text-muted)]">
      <summary className="cursor-pointer select-none font-mono">
        verifier: {report.sentences_with_violations}/{report.sentences_total} flagged
        {report.ungrounded_declaration ? " · ungrounded" : ""}
        {report.anchor_count > 0 ? ` · ${report.anchor_count} anchors` : ""}
        {report.tier ? ` · ${report.tier}` : ""}
      </summary>
      <div className="mt-2 space-y-2 font-mono">
        {hasViolations ? (
          <ul className="space-y-1">
            {report.violations.map((v, i) => (
              <li key={i}>
                <div className="text-[var(--color-text-faint)]">
                  {v.kind} · {v.value}
                </div>
                <div>{v.reason}</div>
                {v.sentence && (
                  <div className="opacity-75">“{v.sentence}”</div>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-[var(--color-text-faint)]">no violations.</div>
        )}
        {report.anchors && report.anchors.length > 0 && (
          <div>
            <div className="text-[var(--color-text-faint)]">anchors</div>
            <ul className="space-y-0.5">
              {report.anchors.map((a, i) => (
                <li key={i}>
                  {a.module}.{a.field} = {a.value}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </details>
  );
}

function CriticPanel({
  critic,
  shipped,
}: {
  critic: NonNullable<ChatMessage["critic"]>;
  shipped: string;
}) {
  const a = critic.original_draft ?? "(no draft captured)";
  const b = shipped;
  const diverged = Boolean(critic.rewritten_text) && critic.rewritten_text !== a;
  return (
    <details className="mt-3 rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] p-2 text-xs text-[var(--color-text-muted)]">
      <summary className="cursor-pointer select-none font-mono">
        critic: {critic.mode} · ran={String(critic.ran)}
        {critic.verdict ? ` · ${critic.verdict}` : ""}
        {critic.applied_rewrite ? " · applied" : ""}
        {diverged ? " · diverged" : ""}
      </summary>
      <div className="mt-2 space-y-2 font-mono">
        {critic.notes && (
          <div>
            <div className="text-[var(--color-text-faint)]">notes</div>
            <div>{critic.notes}</div>
          </div>
        )}
        {critic.numeric_check && (
          <div>
            <div className="text-[var(--color-text-faint)]">numeric_check</div>
            <div>
              ok={String(critic.numeric_check.ok)}
              {critic.numeric_check.missing.length > 0
                ? ` · missing=[${critic.numeric_check.missing.join(", ")}]`
                : ""}
            </div>
          </div>
        )}
        <div>
          <div className="text-[var(--color-text-faint)]">a) draft (without critic)</div>
          <pre className="whitespace-pre-wrap">{a}</pre>
        </div>
        <div>
          <div className="text-[var(--color-text-faint)]">
            b) shipped {critic.applied_rewrite ? "(critic rewrite)" : "(draft)"}
          </div>
          <pre className="whitespace-pre-wrap">{b}</pre>
        </div>
        {critic.rewritten_text && !critic.applied_rewrite && (
          <div>
            <div className="text-[var(--color-text-faint)]">proposed rewrite (not applied)</div>
            <pre className="whitespace-pre-wrap">{critic.rewritten_text}</pre>
          </div>
        )}
      </div>
    </details>
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
