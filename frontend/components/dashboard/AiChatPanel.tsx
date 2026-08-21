"use client";

import { useState } from "react";
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

function formatYen(amount: number): string {
  return `¥${amount.toLocaleString("ja-JP")}`;
}

// 本物のAI応答はまだ無いため、質問文に含まれるキーワードから、
// 今ダッシュボードに表示している実データを使って返答を組み立てている。
function buildMockAnswer(question: string, context: AiChatPanelProps): string {
  const { target, achievementRate, plans, affinities } = context;
  const topPlan = [...plans].sort((a, b) => a.priority - b.priority)[0];
  const topAffinity = [...affinities].sort((a, b) => b.affinity_score - a.affinity_score)[0];

  if (/達成|予算|目標/.test(question)) {
    return `今月の目標は${formatYen(target.target_amount)}です。現在の達成見込みは${achievementRate.toFixed(1)}%です。`;
  }
  if (/商品|商材/.test(question)) {
    return topPlan?.product_name
      ? `直近で優先度が最も高い計画は「${topPlan.product_name}」(${topPlan.customer_name}様向け)です。`
      : "現在、優先度の高い計画が見つかりませんでした。";
  }
  if (/顧客|優先|誰/.test(question)) {
    return topPlan
      ? `最優先の顧客は${topPlan.customer_name}様です。理由: ${topPlan.reasoning_text}`
      : "現在、優先度の高い計画が見つかりませんでした。";
  }
  if (/得意|強み/.test(question)) {
    return topAffinity
      ? `${topAffinity.industry_name}・${topAffinity.category_name}(${topAffinity.pattern_name})が最も得意な分野です。勝率${Math.round(topAffinity.win_rate * 100)}%・平均成約${formatYen(topAffinity.avg_won_amount)}です。`
      : "まだ十分な成約実績が無いため、得意分野を判定できませんでした。";
  }

  return "すみません、もう少し具体的に聞いていただけますか？(この回答は仮のものです。実際のAI応答は今後実装予定です)";
}

export function AiChatPanel({ target, achievementRate, plans, affinities }: AiChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "ai",
      text: "こんにちは。目標や活動計画について質問してください。(現在は仮の回答です)",
    },
  ]);
  const [input, setInput] = useState("");
  const [isThinking, setIsThinking] = useState(false);

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const question = input.trim();
    if (!question) return;

    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: "user", text: question }]);
    setInput("");
    setIsThinking(true);

    window.setTimeout(() => {
      const answer = buildMockAnswer(question, { target, achievementRate, plans, affinities });
      setMessages((prev) => [...prev, { id: `a-${Date.now()}`, role: "ai", text: answer }]);
      setIsThinking(false);
    }, 500);
  }

  return (
    <section className="panel ai-chat">
      <h2>AIに質問する</h2>
      <div className="ai-chat__messages">
        {messages.map((message) => (
          <div key={message.id} className={`ai-chat__message ai-chat__message--${message.role}`}>
            {message.text}
          </div>
        ))}
        {isThinking && (
          <div className="ai-chat__message ai-chat__message--ai ai-chat__message--thinking">…</div>
        )}
      </div>
      <form className="ai-chat__form" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="例: 今月の達成見込みは？"
        />
        <button type="submit" className="regenerate-button" disabled={!input.trim()}>
          送信
        </button>
      </form>
    </section>
  );
}
