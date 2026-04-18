"use client";

import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef } from "react";
import { cn } from "@/lib/cn";

type Props = {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onStop?: () => void;
  isStreaming?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
};

export function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  isStreaming,
  placeholder = "Ask about a property, town, or market…",
  autoFocus,
}: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "0px";
    ta.style.height = Math.min(ta.scrollHeight, 240) + "px";
  }, [value]);

  const canSend = value.trim().length > 0 && !isStreaming;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSend) onSubmit();
      }}
      className={cn(
        "flex items-end gap-2 rounded-2xl border border-[var(--color-border)]",
        "bg-[var(--color-bg-elevated)] px-4 py-3",
        "shadow-[0_1px_0_0_rgba(0,0,0,0.2)] focus-within:border-[var(--color-text-faint)]",
        "transition-colors",
      )}
    >
      <textarea
        ref={textareaRef}
        value={value}
        autoFocus={autoFocus}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (canSend) onSubmit();
          }
        }}
        rows={1}
        placeholder={placeholder}
        aria-label="Message"
        className={cn(
          "min-h-[24px] max-h-[240px] flex-1 resize-none bg-transparent",
          "text-[15px] leading-6 text-[var(--color-text)]",
          "placeholder:text-[var(--color-text-faint)] outline-none",
        )}
      />
      {isStreaming ? (
        <button
          type="button"
          aria-label="Stop generating"
          onClick={onStop}
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
            "bg-[var(--color-surface)] text-[var(--color-text)]",
            "hover:bg-[var(--color-surface-hover)] transition-colors",
          )}
        >
          <Square className="h-3.5 w-3.5 fill-current" aria-hidden />
        </button>
      ) : (
        <button
          type="submit"
          aria-label="Send message"
          disabled={!canSend}
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors",
            canSend
              ? "bg-[var(--color-accent)] text-[var(--color-accent-fg)] hover:bg-[var(--color-accent-hover)]"
              : "bg-[var(--color-surface)] text-[var(--color-text-faint)] cursor-not-allowed",
          )}
        >
          <ArrowUp className="h-4 w-4" aria-hidden />
        </button>
      )}
    </form>
  );
}
