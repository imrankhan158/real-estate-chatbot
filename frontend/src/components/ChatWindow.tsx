"use client";

import { useEffect, useRef, useState } from "react";
import { Building2, RotateCcw, Send } from "lucide-react";

import { fetchStats, streamChat, type Stats } from "@/lib/api";
import { parseSSEStream } from "@/lib/sse";
import MessageBubble, { type Message } from "./MessageBubble";
import SuggestedPrompts from "./SuggestedPrompts";

let _idCounter = 0;
const uid = () => `msg_${++_idCounter}`;

export default function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Keep a ref so async callbacks always see the current loading state
  const isLoadingRef = useRef(false);

  useEffect(() => {
    fetchStats().then(setStats).catch(() => setStats(null));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || isLoadingRef.current) return;

    setError(null);
    setInput("");
    setIsLoading(true);
    isLoadingRef.current = true;

    const userMsg: Message = { id: uid(), role: "user", content: trimmed };
    const botId = uid();
    const botMsg: Message = { id: botId, role: "assistant", content: "", isStreaming: true };

    // Snapshot history from current messages before appending new ones
    const history = messages.map(({ role, content }) => ({ role, content }));
    setMessages((prev) => [...prev, userMsg, botMsg]);

    abortRef.current = new AbortController();

    try {
      const reader = await streamChat(trimmed, history, abortRef.current.signal);
      await parseSSEStream(reader, {
        onToken: (token) =>
          setMessages((m) =>
            m.map((msg) =>
              msg.id === botId ? { ...msg, content: msg.content + token } : msg,
            ),
          ),
        onError: (err) => {
          setError(err);
          setMessages((m) =>
            m.map((msg) =>
              msg.id === botId
                ? { ...msg, content: `Sorry, an error occurred: ${err}`, isStreaming: false }
                : msg,
            ),
          );
        },
        onDone: () =>
          setMessages((m) =>
            m.map((msg) => (msg.id === botId ? { ...msg, isStreaming: false } : msg)),
          ),
      });
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return;
      const msg = err instanceof Error ? err.message : "Connection error";
      setError(msg);
      setMessages((m) =>
        m.map((msg) =>
          msg.id === botId
            ? { ...msg, content: "Connection error. Please try again.", isStreaming: false }
            : msg,
        ),
      );
    } finally {
      setIsLoading(false);
      isLoadingRef.current = false;
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }

  function handleReset() {
    abortRef.current?.abort();
    setMessages([]);
    setError(null);
    setIsLoading(false);
    isLoadingRef.current = false;
  }

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-screen max-h-screen bg-[#0f0f0f]">
      {/* Header */}
      <header className="shrink-0 border-b border-white/5 bg-[#141414]">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#c9a84c] to-[#8b6914] flex items-center justify-center">
              <Building2 size={18} className="text-white" />
            </div>
            <div>
              <h1 className="font-semibold text-white text-base leading-tight">Real Estate AI</h1>
              <p className="text-xs text-gray-500">DarGlobal & Wasalt Listings</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {stats ? (
              <>
                <StatPill color="bg-[#c9a84c]" label="DarGlobal" count={stats.darglobal} />
                <StatPill color="bg-emerald-400" label="Wasalt" count={stats.wasalt} />
                <span className="inline-flex items-center gap-1.5 text-xs bg-[#c9a84c]/10 border border-[#c9a84c]/30 px-3 py-1.5 rounded-full text-[#c9a84c]">
                  {stats.total} properties
                </span>
              </>
            ) : (
              <span className="text-xs text-gray-600 animate-pulse">Loading...</span>
            )}
            {messages.length > 0 && (
              <button
                onClick={handleReset}
                title="Clear chat"
                className="p-2 rounded-lg hover:bg-white/5 text-gray-500 hover:text-gray-300 transition-colors"
              >
                <RotateCcw size={15} />
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-4 py-6 space-y-5">
          {isEmpty ? (
            <EmptyState onSelect={sendMessage} disabled={isLoading} />
          ) : (
            messages.map((msg) => <MessageBubble key={msg.id} message={msg} />)
          )}

          {error && !isLoading && (
            <p className="bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3 text-sm text-red-400">
              {error}
            </p>
          )}

          <div ref={bottomRef} />
        </div>
      </main>

      {/* Suggested prompts after first message */}
      {!isEmpty && !isLoading && (
        <div className="shrink-0 border-t border-white/5 bg-[#0f0f0f] px-4 pt-3">
          <div className="max-w-4xl mx-auto">
            <SuggestedPrompts onSelect={sendMessage} disabled={isLoading} />
          </div>
        </div>
      )}

      {/* Input */}
      <div className="shrink-0 border-t border-white/5 bg-[#141414] px-4 py-4">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-end gap-3 bg-[#1e1e1e] border border-white/10 rounded-2xl px-4 py-3 focus-within:border-[#c9a84c]/50 transition-colors">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about properties, prices, locations..."
              disabled={isLoading}
              rows={1}
              className="flex-1 bg-transparent text-sm text-gray-200 placeholder-gray-600 resize-none outline-none min-h-[24px] max-h-[160px] leading-6 disabled:opacity-50"
            />
            <button
              onClick={() => sendMessage(input)}
              disabled={isLoading || !input.trim()}
              className="shrink-0 w-9 h-9 rounded-xl bg-[#c9a84c] hover:bg-[#b8933d] disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-all active:scale-95"
            >
              {isLoading ? (
                <div className="w-4 h-4 border-2 border-[#0f0f0f]/30 border-t-[#0f0f0f] rounded-full animate-spin" />
              ) : (
                <Send size={15} className="text-[#0f0f0f]" />
              )}
            </button>
          </div>
          <p className="text-center text-xs text-gray-700 mt-2">
            Powered by{" "}
            <a
              href="https://openrouter.ai"
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-600 hover:text-gray-500"
            >
              OpenRouter
            </a>{" "}
            · Data from DarGlobal & Wasalt
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function StatPill({ color, label, count }: { color: string; label: string; count: number }) {
  return (
    <span className="hidden sm:inline-flex items-center gap-1.5 text-xs bg-[#1e1e1e] border border-white/10 px-3 py-1.5 rounded-full text-gray-400">
      <span className={`w-1.5 h-1.5 rounded-full ${color}`} />
      {label}: {count}
    </span>
  );
}

function EmptyState({
  onSelect,
  disabled,
}: {
  onSelect: (p: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] gap-8 text-center">
      <div>
        <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-[#c9a84c] to-[#8b6914] flex items-center justify-center">
          <Building2 size={32} className="text-white" />
        </div>
        <h2 className="text-2xl font-semibold text-white mb-2">Find Your Dream Property</h2>
        <p className="text-gray-500 max-w-md text-sm leading-relaxed">
          Ask about properties from{" "}
          <span className="text-[#c9a84c]">DarGlobal</span> (luxury international) and{" "}
          <span className="text-emerald-400">Wasalt</span> (Saudi Arabia).
        </p>
      </div>
      <SuggestedPrompts onSelect={onSelect} disabled={disabled} />
    </div>
  );
}
