/**
 * Lightweight SSE stream parser.
 * Reads a ReadableStream and calls onToken / onError / onDone callbacks.
 */

interface SSEHandlers {
  onToken: (token: string) => void;
  onError: (error: string) => void;
  onDone: () => void;
}

export async function parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  handlers: SSEHandlers,
): Promise<void> {
  const decoder = new TextDecoder();

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const lines = decoder.decode(value, { stream: true }).split("\n");
      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        const data = line.slice(5).trim();
        if (data === "[DONE]") {
          handlers.onDone();
          return;
        }
        try {
          const parsed = JSON.parse(data);
          if (parsed.token) handlers.onToken(parsed.token);
          if (parsed.error) handlers.onError(parsed.error);
        } catch {
          // ignore malformed chunks
        }
      }
    }
  } finally {
    handlers.onDone();
  }
}
