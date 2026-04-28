// Server-side API client for the FastAPI bridge.
// Used from React Server Components and Route Handlers.

const API_BASE =
  process.env.BRIARWOOD_API_URL ?? "http://127.0.0.1:8000";

export type ConversationSummary = {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
};

export type StoredMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  events: Array<Record<string, unknown>>;
  created_at: number;
  // LEFT JOIN'd from the feedback table on hydration. Always null for
  // user-role messages and for assistant messages that haven't been
  // rated yet. See api/store.py::get_conversation.
  user_rating: "up" | "down" | null;
};

export type ConversationDetail = ConversationSummary & {
  messages: StoredMessage[];
};

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

export function listConversations() {
  return fetchJson<ConversationSummary[]>("/api/conversations");
}

export function getConversation(id: string) {
  return fetchJson<ConversationDetail>(`/api/conversations/${id}`);
}

export const apiBaseUrl = API_BASE;
