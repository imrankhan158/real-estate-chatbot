"use client";

import ReactMarkdown from "react-markdown";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
}

interface MessageBubbleProps {
  message: Message;
}

function UserAvatar() {
  return (
    <div className="w-8 h-8 rounded-full bg-[#c9a84c] flex items-center justify-center shrink-0">
      <span className="text-[#0f0f0f] font-bold text-sm">U</span>
    </div>
  );
}

function BotAvatar() {
  return (
    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#c9a84c] to-[#8b6914] flex items-center justify-center shrink-0">
      <span className="text-white text-xs font-bold">RE</span>
    </div>
  );
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={`flex gap-3 message-enter ${isUser ? "flex-row-reverse" : "flex-row"}`}
    >
      {isUser ? <UserAvatar /> : <BotAvatar />}

      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? "bg-[#c9a84c] text-[#0f0f0f] font-medium rounded-tr-sm"
            : "bg-[#1e1e1e] text-gray-200 border border-white/5 rounded-tl-sm"
        }`}
      >
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <div className="prose-chat">
            <ReactMarkdown>{message.content}</ReactMarkdown>
            {message.isStreaming && <span className="typing-cursor" />}
          </div>
        )}
      </div>
    </div>
  );
}
