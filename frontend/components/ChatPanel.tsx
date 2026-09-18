"use client";

import { useEffect, useRef, useState } from "react";
import { sendChatMessage } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";

interface Props {
  cadastralId: string | null;
  onHide?: () => void;
}

// Not a chatbot-UI-quality concern — a real, if minimal, requirement:
// M3.3 asks for conversation memory "within a session", and the backend's
// session_id is entirely client-supplied (no auth in this project). A
// per-tab-lifetime id kept in localStorage is the simplest thing that
// actually satisfies "within a session" across page reloads, without
// inventing an auth concept the brief explicitly excludes.
function getOrCreateSessionId(): string {
  const key = "alix-chat-session-id";
  const existing = window.localStorage.getItem(key);
  if (existing) return existing;
  const created = crypto.randomUUID();
  window.localStorage.setItem(key, created);
  return created;
}

export default function ChatPanel({ cadastralId, onHide }: Props) {
  // Lazy initializer, not an effect — this component is only ever mounted
  // client-side (dynamic-imported with ssr:false in page.tsx, the same
  // pattern MapView uses for its own window/document access), so reading
  // localStorage here directly is safe and avoids an extra render pass.
  const [sessionId] = useState<string>(() => getOrCreateSessionId());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || !sessionId || sending) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setSending(true);
    setError(null);
    try {
      const response = await sendChatMessage(sessionId, text, cadastralId);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: response.answer, citations: response.citations },
      ]);
    } catch {
      setError("The chat request failed — is the backend running?");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-2 border-b border-zinc-200 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-zinc-900">Ask about this parcel</h2>
          <p className="mt-1 text-xs text-zinc-500">
            {cadastralId
              ? `Scoped to ${cadastralId} + national legislation.`
              : "No parcel selected — general questions only."}
          </p>
        </div>
        {onHide && (
          <button
            type="button"
            onClick={onHide}
            aria-label="Hide chat panel"
            title="Hide chat panel"
            className="shrink-0 rounded p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700"
          >
            ✕
          </button>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {messages.length === 0 && (
          <p className="text-xs text-zinc-400">
            e.g. &ldquo;Can I build a third storey here?&rdquo; or &ldquo;Quelle autorité est
            compétente pour les établissements de classe 1 ?&rdquo;
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <div
              className={
                "inline-block max-w-full rounded-lg px-3 py-2 text-sm whitespace-pre-wrap " +
                (m.role === "user" ? "bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-900")
              }
            >
              {m.content}
            </div>
            {m.citations && m.citations.length > 0 && (
              <ul className="mt-1 space-y-0.5 text-left text-xs text-zinc-500">
                {m.citations.map((c) => (
                  <li key={c.ref_id}>
                    [{c.ref_id}]{" "}
                    <a
                      href={c.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="underline hover:text-zinc-700"
                    >
                      {c.document_title}
                      {c.article_ref ? `, ${c.article_ref}` : ""}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
        {sending && <p className="text-xs text-zinc-400">Thinking…</p>}
        {error && <p className="text-xs text-red-600">{error}</p>}
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2 border-t border-zinc-200 p-3">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question…"
          className="flex-1 rounded border border-zinc-300 px-2 py-1.5 text-sm text-zinc-900 placeholder:text-zinc-400"
          disabled={!sessionId || sending}
        />
        <button
          type="submit"
          disabled={!sessionId || sending || !input.trim()}
          className="rounded bg-zinc-900 px-3 py-1.5 text-sm text-white disabled:opacity-40"
        >
          Send
        </button>
      </form>
    </div>
  );
}
