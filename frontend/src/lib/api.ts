/**
 * API client – thin wrapper over fetch for all backend calls.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

export interface Stats {
  total: number;
  darglobal: number;
  wasalt: number;
}

export interface ChatHistoryItem {
  role: "user" | "assistant";
  content: string;
}

export async function fetchStats(): Promise<Stats> {
  const res = await fetch(`${BASE_URL}/api/stats`);
  if (!res.ok) throw new Error(`Stats request failed: ${res.status}`);
  return res.json();
}

export function streamChat(
  message: string,
  history: ChatHistoryItem[],
  signal: AbortSignal,
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  return fetch(`${BASE_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
    signal,
  }).then((res) => {
    if (!res.ok) throw new Error(`Chat request failed: ${res.status}`);
    return res.body!.getReader();
  });
}
