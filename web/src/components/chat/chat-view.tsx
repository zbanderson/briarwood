"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { MapPin, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { Composer } from "./composer";
import { DetailPanel } from "./detail-panel";
import { EmptyState } from "./empty-state";
import { MessageList, SuggestionChips } from "./messages";
import { TownSignalPanel } from "./town-signal-panel";
import { useChat, type ChatMessage } from "@/lib/chat/use-chat";
import type { Listing, TownSignalItem } from "@/lib/chat/events";

type Props = {
  conversationId?: string;
  initialMessages?: ChatMessage[];
  /** When true, navigate to /c/[id] as soon as the server assigns an id. */
  navigateOnCreate?: boolean;
};

export function ChatView({
  conversationId,
  initialMessages = [],
  navigateOnCreate = false,
}: Props) {
  const router = useRouter();
  const [draft, setDraft] = useState("");
  const [selectedListing, setSelectedListing] = useState<Listing | null>(null);
  const [selectedTownSignal, setSelectedTownSignal] = useState<{
    signal: TownSignalItem;
    subjectListing: Listing | null;
  } | null>(null);
  const pendingNavigationIdRef = useRef<string | null>(null);
  // Separate from selectedListing: the panel can close while the pin persists,
  // and the pin carries across subsequent typed turns until the user dismisses.
  const [pinnedListing, setPinnedListing] = useState<Listing | null>(null);

  const { messages, suggestions, isStreaming, error, send, stop } = useChat({
    initialMessages,
    conversationId,
    onConversationCreated: (id) => {
      pendingNavigationIdRef.current = id;
    },
    onDone: () => {
      if (!navigateOnCreate || conversationId) return;
      const targetId = pendingNavigationIdRef.current;
      if (!targetId) return;
      pendingNavigationIdRef.current = null;
      // Wait until the assistant message has been persisted before changing
      // routes, or the new /c/[id] page can rehydrate with an empty turn.
      router.replace(`/c/${targetId}`);
    },
  });

  const submitDraft = () => {
    const content = draft.trim();
    if (!content) return;
    setDraft("");
    void send({ content, pinnedListing });
  };

  const submitImmediate = (content: string) => {
    setDraft("");
    void send({ content, pinnedListing });
  };

  const runAnalysis = (listing: Listing) => {
    setPinnedListing(listing);
    setSelectedListing(null);
    void send({
      content: `Analyze ${listing.address_line}, ${listing.city}, ${listing.state}`,
      pinnedListing: listing,
    });
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full min-h-0">
      <div className="flex h-full min-w-0 flex-1 flex-col">
        <div className="flex-1 min-h-0 overflow-y-auto">
          <div className="mx-auto w-full max-w-3xl px-4 pb-6">
            {isEmpty ? (
              <EmptyState onPick={submitImmediate} />
            ) : (
              <div className="pt-8">
                <MessageList
                  messages={messages}
                  onSelectListing={(listing) => {
                    setSelectedTownSignal(null);
                    setSelectedListing(listing);
                  }}
                  onSelectTownSignal={(signal, subjectListing) => {
                    setSelectedListing(null);
                    setSelectedTownSignal({ signal, subjectListing });
                  }}
                  onPrompt={submitImmediate}
                />
                {!isStreaming && (
                  <SuggestionChips
                    items={suggestions}
                    onPick={submitImmediate}
                    disabled={isStreaming}
                  />
                )}
                {error && (
                  <p
                    role="alert"
                    className="mt-4 text-sm text-red-400/90"
                  >
                    {error}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="shrink-0 border-t border-[var(--color-border-subtle)] bg-[var(--color-bg)]">
          <div className="mx-auto w-full max-w-3xl px-4 py-4">
            {pinnedListing && (
              <PinnedContextChip
                listing={pinnedListing}
                onClear={() => setPinnedListing(null)}
              />
            )}
            <Composer
              value={draft}
              onChange={setDraft}
              onSubmit={submitDraft}
              onStop={stop}
              isStreaming={isStreaming}
              autoFocus={isEmpty}
            />
            <p className="mt-2 text-center text-[11px] text-[var(--color-text-faint)]">
              Briarwood can be wrong. Verify property details before acting.
            </p>
          </div>
        </div>
      </div>

      <DetailPanel
        listing={selectedListing}
        onClose={() => setSelectedListing(null)}
        onRunAnalysis={runAnalysis}
      />
      <TownSignalPanel
        signal={selectedTownSignal?.signal ?? null}
        subjectListing={selectedTownSignal?.subjectListing ?? null}
        onClose={() => setSelectedTownSignal(null)}
      />
    </div>
  );
}

function PinnedContextChip({
  listing,
  onClear,
}: {
  listing: Listing;
  onClear: () => void;
}) {
  return (
    <div
      role="status"
      aria-label="Pinned property context"
      className={cn(
        "mb-2 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs",
        "border-[var(--color-accent)]/40 bg-[var(--color-accent)]/10 text-[var(--color-text)]",
      )}
    >
      <MapPin className="h-3 w-3 text-[var(--color-accent)]" aria-hidden />
      <span className="truncate max-w-[320px]">
        <span className="text-[var(--color-text-faint)]">Pinned: </span>
        {listing.address_line}, {listing.city}
      </span>
      <button
        type="button"
        onClick={onClear}
        aria-label="Clear pinned property"
        className={cn(
          "flex h-4 w-4 items-center justify-center rounded-full",
          "text-[var(--color-text-muted)] hover:text-[var(--color-text)]",
          "hover:bg-[var(--color-surface)] transition-colors",
        )}
      >
        <X className="h-3 w-3" aria-hidden />
      </button>
    </div>
  );
}
