"use client";

import { createContext, useCallback, useContext, useState } from "react";

// ダッシュボードのカレンダー(ActivityPlanList)には、予定の作成・編集を1つの
// パネルで行う元々の詳細フォーム(時間帯・内容・商品・成約確率・メモ等)がある。
// QuickAddFab(全ページ共通の右下＋)は「予定」を選んだとき、ダッシュボード上では
// この簡略版を出さずに元の詳細フォームへ委譲したい。ダッシュボードとAppNavは
// レイアウト上の兄弟(親子ではない)なので、その橋渡しにこのContextを使う。
// ActivityPlanListがマウントされている間だけ関数が登録され、それ以外のページ
// (登録先が無い)ではnullのままなので、QuickAddFabは自前の簡易フォームを使う。
type QuickAddPlanContextValue = {
  openRichPlanCreator: (() => void) | null;
  setOpenRichPlanCreator: (fn: (() => void) | null) => void;
};

const QuickAddPlanContext = createContext<QuickAddPlanContextValue | null>(null);

export function QuickAddPlanProvider({ children }: { children: React.ReactNode }) {
  const [openRichPlanCreator, setOpenRichPlanCreatorState] = useState<(() => void) | null>(null);

  const setOpenRichPlanCreator = useCallback((fn: (() => void) | null) => {
    setOpenRichPlanCreatorState(() => fn);
  }, []);

  return (
    <QuickAddPlanContext.Provider value={{ openRichPlanCreator, setOpenRichPlanCreator }}>
      {children}
    </QuickAddPlanContext.Provider>
  );
}

export function useQuickAddPlan(): QuickAddPlanContextValue {
  const context = useContext(QuickAddPlanContext);
  if (!context) {
    throw new Error("useQuickAddPlan は QuickAddPlanProvider の内側で使ってください");
  }
  return context;
}
