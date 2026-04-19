import { notFound } from "next/navigation";
import { Sidebar } from "@/components/chat/sidebar";
import { ChatView } from "@/components/chat/chat-view";
import { getConversation, listConversations } from "@/lib/api";
import type { ChatMessage } from "@/lib/chat/use-chat";
import type {
  ChartEvent,
  ComparisonTableEvent,
  CompsPreviewEvent,
  GroundingAnchor,
  Listing,
  MapPin,
  ModuleAttribution,
  RentOutlookEvent,
  ResearchUpdateEvent,
  RiskProfileEvent,
  ScenarioTableEvent,
  StrategyPathEvent,
  TownSummaryEvent,
  ValueThesisEvent,
  VerdictEvent,
} from "@/lib/chat/events";

export default async function ConversationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const [conversations, conv] = await Promise.all([
    listConversations().catch(() => []),
    getConversation(id).catch(() => null),
  ]);

  if (!conv) notFound();

  const initialMessages: ChatMessage[] = conv.messages.map((m) => {
    const msg: ChatMessage = {
      id: m.id,
      role: m.role,
      content: m.content,
    };
    // Rehydrate every structured event the SSE reducer in use-chat.ts knows
    // about, so a page refresh on /c/[id] restores cards + badges that came
    // through during the live stream. Keep this in sync with applyEvent there.
    const charts: ChartEvent[] = [];
    for (const ev of m.events ?? []) {
      const type = (ev as { type?: string }).type;
      if (type === "listings" && Array.isArray((ev as { items?: unknown }).items)) {
        msg.listings = (ev as { items: Listing[] }).items;
      } else if (type === "map") {
        const e = ev as { center: [number, number]; pins: MapPin[] };
        msg.map = { center: e.center, pins: e.pins };
      } else if (type === "chart") {
        charts.push(ev as ChartEvent);
      } else if (type === "verdict") {
        msg.verdict = ev as VerdictEvent;
      } else if (type === "scenario_table") {
        msg.scenarioTable = ev as ScenarioTableEvent;
      } else if (type === "comparison_table") {
        msg.comparisonTable = ev as ComparisonTableEvent;
      } else if (type === "town_summary") {
        msg.townSummary = ev as TownSummaryEvent;
      } else if (type === "comps_preview") {
        msg.compsPreview = ev as CompsPreviewEvent;
      } else if (type === "risk_profile") {
        msg.riskProfile = ev as RiskProfileEvent;
      } else if (type === "value_thesis") {
        msg.valueThesis = ev as ValueThesisEvent;
      } else if (type === "strategy_path") {
        msg.strategyPath = ev as StrategyPathEvent;
      } else if (type === "rent_outlook") {
        msg.rentOutlook = ev as RentOutlookEvent;
      } else if (type === "research_update") {
        msg.researchUpdate = ev as ResearchUpdateEvent;
      } else if (type === "modules_ran") {
        const items = (ev as { items?: ModuleAttribution[] }).items;
        if (Array.isArray(items)) msg.modulesRan = items;
      } else if (type === "grounding_annotations") {
        const e = ev as {
          anchors?: GroundingAnchor[];
          ungrounded_declaration?: boolean;
        };
        if (Array.isArray(e.anchors)) msg.groundingAnchors = e.anchors;
        if (typeof e.ungrounded_declaration === "boolean") {
          msg.ungroundedDeclaration = e.ungrounded_declaration;
        }
      }
    }
    if (charts.length > 0) msg.charts = charts;
    return msg;
  });

  return (
    <div className="flex h-full">
      <Sidebar initialConversations={conversations} />
      <main className="flex-1 min-w-0">
        <ChatView conversationId={id} initialMessages={initialMessages} />
      </main>
    </div>
  );
}
