import { Sidebar } from "@/components/chat/sidebar";
import { ChatView } from "@/components/chat/chat-view";
import { listConversations, type ConversationSummary } from "@/lib/api";

export default async function HomePage() {
  const conversations: ConversationSummary[] = await listConversations().catch(() => []);

  return (
    <div className="flex h-full">
      <Sidebar initialConversations={conversations} />
      <main className="flex-1 min-w-0">
        <ChatView navigateOnCreate />
      </main>
    </div>
  );
}
