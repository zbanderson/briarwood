"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Plus, MessageSquare } from "lucide-react";
import { cn } from "@/lib/cn";
import type { ConversationSummary } from "@/lib/api";

type Props = {
  initialConversations: ConversationSummary[];
};

export function Sidebar({ initialConversations }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const [conversations, setConversations] = useState(initialConversations);

  useEffect(() => {
    // Refresh the list whenever the route changes — picks up newly created chats.
    let cancelled = false;
    fetch("/api/conversations", { cache: "no-store" })
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled) setConversations(data as ConversationSummary[]);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  const activeId = pathname?.startsWith("/c/") ? pathname.slice(3) : null;

  return (
    <aside
      aria-label="Conversations"
      className="hidden md:flex w-64 shrink-0 flex-col border-r border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)]"
    >
      <div className="px-3 py-4">
        <button
          type="button"
          onClick={() => router.push("/")}
          className={cn(
            "group flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm",
            "border border-[var(--color-border-subtle)] bg-[var(--color-surface)]",
            "hover:bg-[var(--color-surface-hover)] transition-colors",
          )}
        >
          <Plus className="h-4 w-4 text-[var(--color-text-muted)] group-hover:text-[var(--color-text)]" aria-hidden />
          <span className="font-medium">New chat</span>
        </button>
      </div>

      <nav
        aria-label="Past conversations"
        className="flex-1 overflow-y-auto px-2 pb-4"
      >
        {conversations.length === 0 ? (
          <p className="px-3 py-2 text-xs text-[var(--color-text-faint)]">
            No conversations yet.
          </p>
        ) : (
          <ul className="space-y-0.5">
            {conversations.map((c) => {
              const active = c.id === activeId;
              return (
                <li key={c.id}>
                  <Link
                    href={`/c/${c.id}`}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm",
                      "text-[var(--color-text-muted)]",
                      "hover:bg-[var(--color-surface)] hover:text-[var(--color-text)]",
                      active && "bg-[var(--color-surface)] text-[var(--color-text)]",
                    )}
                  >
                    <MessageSquare className="h-3.5 w-3.5 shrink-0" aria-hidden />
                    <span className="truncate">{c.title}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </nav>

      <div className="border-t border-[var(--color-border-subtle)] px-4 py-3 text-xs text-[var(--color-text-faint)]">
        Briarwood · prototype
      </div>
    </aside>
  );
}
