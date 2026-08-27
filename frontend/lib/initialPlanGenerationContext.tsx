"use client";

import { createContext, useContext, useState } from "react";

// 初回のAI活動計画生成(useDashboardData の generateInitialPlan)は数分かかることがあり、
// 生成中に「活動計画」ページから他ページへ遷移するとページ専属の useState が破棄されて
// しまい、戻ってきたときに「目標を保存すると、AIが今月の活動計画を作成します。」という
// 最初の状態に巻き戻って見えていた(実際の生成はバックエンドで裏側で継続している)。
// さらにその状態で目標を再保存すると、生成が二重に走ってしまう問題もあった。
// RouteBatchPlanProvider と同様にルートレイアウトへ引き上げ、ページ遷移をまたいでも
// 「今、生成中かどうか」を覚えておくようにする。
type InitialPlanGenerationContextValue = {
  isGenerating: (key: string) => boolean;
  setGenerating: (key: string, value: boolean) => void;
};

const InitialPlanGenerationContext = createContext<InitialPlanGenerationContextValue | null>(null);

export function InitialPlanGenerationProvider({ children }: { children: React.ReactNode }) {
  const [generatingKeys, setGeneratingKeys] = useState<Record<string, boolean>>({});

  function isGenerating(key: string): boolean {
    return generatingKeys[key] === true;
  }

  function setGenerating(key: string, value: boolean) {
    setGeneratingKeys((prev) => {
      if (value) return { ...prev, [key]: true };
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  return (
    <InitialPlanGenerationContext.Provider value={{ isGenerating, setGenerating }}>
      {children}
    </InitialPlanGenerationContext.Provider>
  );
}

export function useInitialPlanGeneration(): InitialPlanGenerationContextValue {
  const context = useContext(InitialPlanGenerationContext);
  if (!context) {
    throw new Error("useInitialPlanGeneration は InitialPlanGenerationProvider の内側で使ってください");
  }
  return context;
}
