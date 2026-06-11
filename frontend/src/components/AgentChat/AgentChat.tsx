import { useState, useRef, useEffect } from "react";
import { Send, Square, Trash2, Bot, User } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { useMesAgent } from "@/hooks/useMesAgent";

const QUICK_PROMPTS = [
  "현재 코팅 라인 이상 원인 분석해줘",
  "지난 24시간 이상 이력 요약해줘",
  "가장 위험한 설비 순위 알려줘",
  "점도와 두께 상관관계 분석해줘",
  "Line 1 교대 보고서 작성해줘",
];

export function AgentChat() {
  const { messages, isStreaming, send, stop, clear } = useMesAgent();
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim()) return;
    send(input);
    setInput("");
  }

  return (
    <div className="flex flex-col h-full glass-card overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1c2740]">
        <div className="flex items-center gap-2">
          <Bot size={18} className="text-[#38bdf8]" />
          <span className="font-semibold text-sm">공정 AI 에이전트</span>
          <span className="text-xs text-[#6b7280]">실시간 공정 데이터 분석</span>
        </div>
        <button onClick={clear} className="text-[#6b7280] hover:text-white transition-colors">
          <Trash2 size={14} />
        </button>
      </div>

      {/* Quick prompts */}
      {messages.length === 0 && (
        <div className="p-4 space-y-2">
          <div className="text-xs text-[#6b7280] mb-3">빠른 질문</div>
          {QUICK_PROMPTS.map((p) => (
            <button
              key={p}
              onClick={() => send(p)}
              className="w-full text-left text-xs px-3 py-2 rounded-lg bg-[#1c2740]/70 hover:bg-[#233252] text-[#7c8db5] border border-transparent hover:border-[#38bdf8]/30 hover:text-white transition-colors"
            >
              {p}
            </button>
          ))}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
            <div
              className={`w-7 h-7 rounded-full shrink-0 flex items-center justify-center ${
                msg.role === "user" ? "bg-gradient-to-br from-[#38bdf8] to-[#6366f1]" : "bg-[#1c2740]"
              }`}
            >
              {msg.role === "user" ? (
                <User size={14} className="text-white" />
              ) : (
                <Bot size={14} className="text-[#38bdf8]" />
              )}
            </div>
            <div
              className={`max-w-[80%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-gradient-to-br from-[#2563eb] to-[#4f46e5] text-white whitespace-pre-wrap"
                  : "bg-[#16203a]/80 border border-[#1c2740] text-[#e2e8f0] markdown-body"
              }`}
            >
              {msg.role === "user" ? (
                msg.content
              ) : (
                <ReactMarkdown>{msg.content}</ReactMarkdown>
              )}
              {msg.streaming && (
                <span className="inline-block w-1.5 h-4 bg-[#38bdf8] ml-1 animate-pulse" />
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-3 border-t border-[#1c2740] flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="공정 데이터에 대해 질문하세요…"
          className="flex-1 bg-[#0d1322] border border-[#1c2740] rounded-lg px-3 py-2 text-sm text-white placeholder-[#64748b] outline-none focus:border-[#38bdf8]/50 focus:ring-1 focus:ring-[#38bdf8]/30 transition-colors"
          disabled={isStreaming}
        />
        {isStreaming ? (
          <button
            type="button"
            onClick={stop}
            className="px-3 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white transition-colors"
          >
            <Square size={14} />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!input.trim()}
            className="px-3 py-2 rounded-lg bg-gradient-to-br from-[#38bdf8] to-[#6366f1] hover:opacity-90 disabled:opacity-40 text-white transition-opacity"
          >
            <Send size={14} />
          </button>
        )}
      </form>
    </div>
  );
}
