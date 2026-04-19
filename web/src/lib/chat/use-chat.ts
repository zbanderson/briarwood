"use client";

import { useCallback, useRef, useState } from "react";
import type {
  ChartEvent,
  ChatEvent,
  ComparisonTableEvent,
  CompsPreviewEvent,
  GroundingAnchor,
  Listing,
  ListingsEvent,
  MapEvent,
  ModuleAttribution,
  RentOutlookEvent,
  ResearchUpdateEvent,
  RiskProfileEvent,
  ScenarioTableEvent,
  StrategyPathEvent,
  TownSummaryEvent,
  ValueThesisEvent,
  VerdictEvent,
} from "./events";

export type ChatRole = "user" | "assistant";

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  // Structured payloads collected as the assistant streams. Rendered inline
  // by the assistant message component (cards, maps, charts, verdicts, etc.).
  listings?: ListingsEvent["items"];
  map?: { center: MapEvent["center"]; pins: MapEvent["pins"] };
  charts?: ChartEvent[];
  verdict?: VerdictEvent;
  scenarioTable?: ScenarioTableEvent;
  comparisonTable?: ComparisonTableEvent;
  townSummary?: TownSummaryEvent;
  compsPreview?: CompsPreviewEvent;
  riskProfile?: RiskProfileEvent;
  valueThesis?: ValueThesisEvent;
  strategyPath?: StrategyPathEvent;
  rentOutlook?: RentOutlookEvent;
  researchUpdate?: ResearchUpdateEvent;
  modulesRan?: ModuleAttribution[];
  groundingAnchors?: GroundingAnchor[];
  ungroundedDeclaration?: boolean;
  isStreaming?: boolean;
};

export type UseChatOptions = {
  initialMessages?: ChatMessage[];
  conversationId?: string;
  onConversationCreated?: (id: string, title: string) => void;
  onDone?: () => void;
};

type SendOptions = {
  content: string;
  /** When set, the backend receives the listing as subject-of-turn context
   * and emits listing-aware narration + suggestions. */
  pinnedListing?: Listing | null;
};

function tempId(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Custom SSE consumer for the Briarwood chat protocol.
 *
 * We deliberately don't use Vercel AI SDK's useChat here: our wire format is
 * structured (text deltas + listings + maps + suggestions interleaved), and
 * owning the parser keeps the data flow legible. If the protocol grows we can
 * still adopt useChat with a custom streamProtocol later.
 */
export function useChat({
  initialMessages = [],
  conversationId: initialConversationId,
  onConversationCreated,
  onDone,
}: UseChatOptions = {}) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const conversationIdRef = useRef<string | undefined>(initialConversationId);
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async ({ content, pinnedListing }: SendOptions) => {
      if (isStreaming || !content.trim()) return;
      setError(null);
      setSuggestions([]);

      const userMsg: ChatMessage = {
        id: tempId("u"),
        role: "user",
        content: content.trim(),
      };
      const assistantMsg: ChatMessage = {
        id: tempId("a"),
        role: "assistant",
        content: "",
        isStreaming: true,
      };

      // Snapshot history *before* this turn so the request body matches what
      // the model should see (excluding the in-flight assistant placeholder).
      const historyForRequest = [...messages, userMsg].map((m) => ({
        role: m.role,
        content: m.content,
      }));

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: historyForRequest,
            conversation_id: conversationIdRef.current ?? null,
            pinned_listing: pinnedListing ?? null,
          }),
          signal: controller.signal,
        });

        if (!res.ok || !res.body) {
          throw new Error(`Request failed (${res.status})`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // SSE frames are separated by a blank line.
          let sep: number;
          while ((sep = buffer.indexOf("\n\n")) !== -1) {
            const frame = buffer.slice(0, sep);
            buffer = buffer.slice(sep + 2);
            const dataLine = frame
              .split("\n")
              .find((l) => l.startsWith("data:"));
            if (!dataLine) continue;
            const payload = dataLine.slice(5).trim();
            if (!payload) continue;
            let event: ChatEvent;
            try {
              event = JSON.parse(payload) as ChatEvent;
            } catch {
              continue;
            }
            applyEvent(event, assistantMsg.id);
          }
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        setError((err as Error).message);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id ? { ...m, isStreaming: false } : m,
          ),
        );
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    // applyEvent is defined below and uses setters that are stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [isStreaming, messages],
  );

  const applyEvent = useCallback(
    (event: ChatEvent, assistantMsgId: string) => {
      switch (event.type) {
        case "text_delta":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? { ...m, content: m.content + event.content }
                : m,
            ),
          );
          break;
        case "listings":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, listings: event.items } : m,
            ),
          );
          break;
        case "map":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? { ...m, map: { center: event.center, pins: event.pins } }
                : m,
            ),
          );
          break;
        case "chart":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? { ...m, charts: [...(m.charts ?? []), event] }
                : m,
            ),
          );
          break;
        case "verdict":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, verdict: event } : m,
            ),
          );
          break;
        case "scenario_table":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, scenarioTable: event } : m,
            ),
          );
          break;
        case "comparison_table":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, comparisonTable: event } : m,
            ),
          );
          break;
        case "town_summary":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, townSummary: event } : m,
            ),
          );
          break;
        case "comps_preview":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, compsPreview: event } : m,
            ),
          );
          break;
        case "risk_profile":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, riskProfile: event } : m,
            ),
          );
          break;
        case "value_thesis":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, valueThesis: event } : m,
            ),
          );
          break;
        case "strategy_path":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, strategyPath: event } : m,
            ),
          );
          break;
        case "rent_outlook":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, rentOutlook: event } : m,
            ),
          );
          break;
        case "research_update":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, researchUpdate: event } : m,
            ),
          );
          break;
        case "modules_ran":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, modulesRan: event.items } : m,
            ),
          );
          break;
        case "suggestions":
          setSuggestions(event.items);
          break;
        case "conversation":
          conversationIdRef.current = event.id;
          onConversationCreated?.(event.id, event.title);
          break;
        case "message":
          // Server-assigned id — replace temp id on the matching role.
          if (event.role === "assistant") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, id: event.id } : m,
              ),
            );
          }
          break;
        case "done":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, isStreaming: false } : m,
            ),
          );
          onDone?.();
          break;
        case "error":
          setError(event.message);
          break;
        case "tool_call":
        case "tool_result":
          // Surface in a side-panel later (Phase 3.5). No-op for now.
          break;
        case "verifier_report":
          // Step 5 ships the verifier in advisory mode — payload is dev-side
          // only (visible via DevTools network tab) so we deliberately don't
          // surface it in the UI yet. Step 6+ may render counts inline.
          break;
        case "grounding_annotations":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    groundingAnchors: event.anchors,
                    ungroundedDeclaration: event.ungrounded_declaration,
                  }
                : m,
            ),
          );
          break;
      }
    },
    [onConversationCreated, onDone],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return {
    messages,
    suggestions,
    isStreaming,
    error,
    send,
    stop,
    setMessages,
    conversationId: conversationIdRef.current,
  };
}
