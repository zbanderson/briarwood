"use client";

import { useCallback, useState } from "react";
import type {
  ChartEvent,
  ChatEvent,
  ComparisonTableEvent,
  CompsPreviewEvent,
  CriticTelemetry,
  GroundingAnchor,
  Listing,
  ListingsEvent,
  MapEvent,
  ModuleAttribution,
  PartialDataWarningEvent,
  ValuationCompsEvent,
  MarketSupportCompsEvent,
  RentOutlookEvent,
  ResearchUpdateEvent,
  RiskProfileEvent,
  ScenarioTableEvent,
  ScoutInsightItem,
  StrategyPathEvent,
  TrustSummaryEvent,
  TownSummaryEvent,
  ValueThesisEvent,
  VerdictEvent,
  VerifierReportEvent,
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
  valuationComps?: ValuationCompsEvent;
  marketSupportComps?: MarketSupportCompsEvent;
  strategyPath?: StrategyPathEvent;
  rentOutlook?: RentOutlookEvent;
  trustSummary?: TrustSummaryEvent;
  researchUpdate?: ResearchUpdateEvent;
  // Phase 4b Cycle 3 — Scout-surfaced angles for the dedicated drilldown
  // surface. Empty / no-fire turns leave this undefined.
  scoutInsights?: ScoutInsightItem[];
  modulesRan?: ModuleAttribution[];
  groundingAnchors?: GroundingAnchor[];
  ungroundedDeclaration?: boolean;
  critic?: CriticTelemetry;
  // F10: keep the full verifier report so the UI can show a reasoning toggle.
  verifierReport?: VerifierReportEvent;
  // F7: degradation notices emitted when a non-core enrichment fails.
  partialDataWarnings?: PartialDataWarningEvent[];
  isStreaming?: boolean;
  // Stage 2 feedback loop: rehydrated from the feedback table on page
  // load (api/store.py::get_conversation LEFT JOIN). The FeedbackBar
  // owns its own optimistic state; this field is the persisted truth.
  userRating?: "up" | "down" | null;
  // Phase 4c Cycle 1: routed answer type (e.g. "browse", "decision",
  // "edge"). Captured from the `message` SSE event when the server
  // assigns the assistant message id. Drives tier-specific render
  // trees — BROWSE turns render the three-section newspaper layout;
  // every other tier renders the existing card stack.
  answerType?: string | null;
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
  const [conversationId, setConversationId] = useState<string | undefined>(
    initialConversationId,
  );
  const [abortController, setAbortController] = useState<AbortController | null>(
    null,
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
        case "valuation_comps":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, valuationComps: event } : m,
            ),
          );
          break;
        case "market_support_comps":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, marketSupportComps: event } : m,
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
        case "trust_summary":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, trustSummary: event } : m,
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
        case "scout_insights":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, scoutInsights: event.items } : m,
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
          setConversationId(event.id);
          onConversationCreated?.(event.id, event.title);
          break;
        case "message":
          // Server-assigned id — replace temp id on the matching role.
          // Phase 4c Cycle 1: capture the optional `answer_type` so the
          // assistant render tree can pick a tier-specific layout.
          if (event.role === "assistant") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId
                  ? { ...m, id: event.id, answerType: event.answer_type ?? null }
                  : m,
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
        case "verifier_report": {
          const reportPayload = event;
          const criticPayload = event.critic;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    verifierReport: reportPayload,
                    ...(criticPayload ? { critic: criticPayload } : {}),
                  }
                : m,
            ),
          );
          break;
        }
        case "partial_data_warning": {
          const warning = event;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    partialDataWarnings: [
                      ...(m.partialDataWarnings ?? []),
                      warning,
                    ],
                  }
                : m,
            ),
          );
          break;
        }
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
      setAbortController(controller);

      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: historyForRequest,
            conversation_id: conversationId ?? null,
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
        setAbortController(null);
      }
    },
    [applyEvent, conversationId, isStreaming, messages],
  );

  const stop = useCallback(() => {
    abortController?.abort();
  }, [abortController]);

  return {
    messages,
    suggestions,
    isStreaming,
    error,
    send,
    stop,
    setMessages,
    conversationId,
  };
}
