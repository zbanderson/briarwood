import { notFound } from "next/navigation";
import { Sidebar } from "@/components/chat/sidebar";
import { ChatView } from "@/components/chat/chat-view";
import { getConversation, listConversations } from "@/lib/api";
import type { ChatMessage } from "@/lib/chat/use-chat";
import type { Listing, MapPin } from "@/lib/chat/events";

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
    for (const ev of m.events ?? []) {
      const type = (ev as { type?: string }).type;
      if (type === "listings" && Array.isArray((ev as { items?: unknown }).items)) {
        msg.listings = (ev as { items: Listing[] }).items;
      } else if (type === "map") {
        const e = ev as { center: [number, number]; pins: MapPin[] };
        msg.map = { center: e.center, pins: e.pins };
      }
    }
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
