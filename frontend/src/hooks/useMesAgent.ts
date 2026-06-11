import { useRef, useState } from "react";
import { API_BASE } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

export function useMesAgent() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const sessionIdRef = useRef<string>("");
  const readerRef = useRef<ReadableStreamDefaultReader | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  async function send(text: string) {
    if (!text.trim() || isStreaming) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setIsStreaming(true);

    // Placeholder for assistant
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", streaming: true },
    ]);

    abortRef.current = new AbortController();

    try {
      const res = await fetch(`${API_BASE}/agent/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionIdRef.current }),
        signal: abortRef.current.signal,
      });

      if (!res.ok) {
        if (res.status === 429) throw new Error("RATE_LIMITED");
        throw new Error(`HTTP ${res.status}`);
      }

      if (!sessionIdRef.current) {
        sessionIdRef.current = res.headers.get("X-Session-Id") ?? "";
      }

      if (!res.body) throw new Error("No response body");
      const reader = res.body.getReader();
      readerRef.current = reader;
      const decoder = new TextDecoder();
      let buffer = "";
      let done_ = false;

      while (!done_) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const payload = JSON.parse(line.slice(6));
            if (payload.delta) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last.role === "assistant") {
                  updated[updated.length - 1] = {
                    ...last,
                    content: last.content + payload.delta,
                  };
                }
                return updated;
              });
            }
            if (payload.done) {
              done_ = true;
              break;
            }
          } catch {
            // ignore
          }
        }
      }
    } catch (err) {
      const isAbort = err instanceof DOMException && err.name === "AbortError";
      const isRateLimit = err instanceof Error && err.message === "RATE_LIMITED";
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last.role === "assistant") {
          if (isAbort) {
            // 사용자가 Stop을 누른 경우 — 받은 부분 응답을 보존
            updated[updated.length - 1] = { ...last, content: last.content + "\n\n[중단됨]" };
          } else if (isRateLimit) {
            updated[updated.length - 1] = {
              ...last,
              content: last.content + "\n\n[요청이 너무 많습니다. 잠시 후 다시 시도하세요.]",
            };
          } else {
            updated[updated.length - 1] = {
              ...last,
              content: last.content + "\n\n[오류가 발생했습니다.]",
            };
          }
        }
        return updated;
      });
    } finally {
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last.role === "assistant") {
          updated[updated.length - 1] = { ...last, streaming: false };
        }
        return updated;
      });
      setIsStreaming(false);
    }
  }

  function stop() {
    abortRef.current?.abort();
    readerRef.current?.cancel();
    setIsStreaming(false);
  }

  function clear() {
    setMessages([]);
    sessionIdRef.current = "";
  }

  return { messages, isStreaming, send, stop, clear };
}
