"use client";

import { useState } from "react";
import { askAiQuestion, type AiChatHistoryMessage } from "@/lib/api";
import type { ActivityPlan, RepAffinity, SalesTarget } from "@/types";

type ChatMessage = {
  id: string;
  role: "user" | "ai";
  text: string;
};

type AiChatPanelProps = {
  target: SalesTarget;
  achievementRate: number;
  plans: ActivityPlan[];
  affinities: RepAffinity[];
};

export function AiChatPanel({ target, achievementRate, plans, affinities }: AiChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "ai",
      text: "こんにちは。目標や活動計画について質問してください。",
    },
  ]);
  const [input, setInput] = useState("");
  const [isThinking, setIsThinking] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const question = input.trim();
    if (!question || isThinking) return;

    const history: AiChatHistoryMessage[] = messages
      .filter((message) => message.id !== "welcome")
      .map((message) => ({
        role: message.role === "ai" ? "assistant" : "user",
        content: message.text,
      }));

    setMessages((prev) => [
      ...prev,
      { id: "u-" + Date.now(), role: "user", text: question },
    ]);
    setInput("");
    setIsThinking(true);

    try {
      const answer = await askAiQuestion(question, history, {
        target,
        achievementRate,
        plans,
        affinities,
      });
      setMessages((prev) => [
        ...prev,
        { id: "a-" + Date.now(), role: "ai", text: answer },
      ]);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Qwenから回答を取得できませんでした。";
      setMessages((prev) => [
        ...prev,
        {
          id: "e-" + Date.now(),
          role: "ai",
          text: "エラー: " + message,
        },
      ]);
    } finally {
      setIsThinking(false);
    }
  }

  return (
    <section className="panel ai-chat">
      <h2>AIに質問する</h2>
      <div className="ai-chat__messages" aria-live="polite">
        {messages.map((message) => (
          <div
            key={message.id}
            className={"ai-chat__message ai-chat__message--" + message.role}
          >
            {message.text}
          </div>
        ))}
        {isThinking && (
          <div className="ai-chat__message ai-chat__message--ai ai-chat__message--thinking">
            Qwenが回答を作成しています…
          </div>
        )}
      </div>
      <form className="ai-chat__form" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="例: 今月の達成見込みは？"
          maxLength={2000}
          disabled={isThinking}
        />
        <button
          type="submit"
          className="regenerate-button"
          disabled={!input.trim() || isThinking}
        >
          送信
        </button>
      </form>
    </section>
  );
}
