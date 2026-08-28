"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { tomorrowInTokyo } from "@/components/dashboard/RoutePlanPanel";
import type { RouteEconomicPolicy } from "@/lib/routeEconomicPolicy";
import type { RoutePlanBatchPreview, RoutePlanPreview } from "@/types";

// RouteBatchPlanPanel(月間営業スケジュール)はダッシュボードページの子として
// マウントされているため、ページ遷移でダッシュボードがアンマウントされると
// useState の中身(設計済みの月間計画)が消え、戻るたびに作り直しになってしまう。
// QuickAddPlanContext と同様にルートレイアウトへ状態を引き上げ、ページ遷移を
// またいでも設計結果を保持できるようにする。
// さらにブラウザの再読み込み(F5)でもJSのメモリ状態は消えるため、
// localStorage にも複製し、ユーザーが明示的に「月の設計を作り直す」を押す
// (= createMonthOutline が新しい結果で上書きする)までは復元し続ける。
// v1時代(容量超過時に保存済みキーごと削除してしまうバグがあった)に一部の週だけ
// 保存された壊れた状態がブラウザに残っている可能性があるため、キーをv2にして
// 古い保存内容を無視させる。
const STORAGE_KEY = "routeBatchPlan:v2";

type PersistedRouteBatchPlanState = {
  selectedMonth: string;
  policy: RouteEconomicPolicy;
  maxVisits: number;
  travelMode: RoutePlanPreview["travel_mode"];
  batch: RoutePlanBatchPreview | null;
  weekBatches: Record<number, RoutePlanBatchPreview>;
  decisions: Record<number, "approved" | "rejected">;
};

function loadPersistedState(): PersistedRouteBatchPlanState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PersistedRouteBatchPlanState;
  } catch {
    return null;
  }
}

type RouteBatchPlanContextValue = PersistedRouteBatchPlanState & {
  setSelectedMonth: (value: string) => void;
  setPolicy: (value: RouteEconomicPolicy) => void;
  setMaxVisits: (value: number) => void;
  setTravelMode: (value: RoutePlanPreview["travel_mode"]) => void;
  setBatch: (value: RoutePlanBatchPreview | null) => void;
  setWeekBatches: (
    updater: Record<number, RoutePlanBatchPreview> | ((current: Record<number, RoutePlanBatchPreview>) => Record<number, RoutePlanBatchPreview>),
  ) => void;
  setDecisions: (
    updater:
      | Record<number, "approved" | "rejected">
      | ((current: Record<number, "approved" | "rejected">) => Record<number, "approved" | "rejected">),
  ) => void;
};

const RouteBatchPlanContext = createContext<RouteBatchPlanContextValue | null>(null);

export function RouteBatchPlanProvider({ children }: { children: React.ReactNode }) {
  const persistedRef = useRef<PersistedRouteBatchPlanState | null | undefined>(undefined);
  if (persistedRef.current === undefined) {
    persistedRef.current = loadPersistedState();
  }
  const persisted = persistedRef.current;

  const [selectedMonth, setSelectedMonth] = useState(
    () => persisted?.selectedMonth ?? tomorrowInTokyo().slice(0, 7),
  );
  const [policy, setPolicy] = useState<RouteEconomicPolicy>(() => persisted?.policy ?? "balanced");
  const [maxVisits, setMaxVisits] = useState(() => persisted?.maxVisits ?? 4);
  const [travelMode, setTravelMode] = useState<RoutePlanPreview["travel_mode"]>(
    () => persisted?.travelMode ?? "driving",
  );
  const [batch, setBatch] = useState<RoutePlanBatchPreview | null>(() => persisted?.batch ?? null);
  const [weekBatches, setWeekBatches] = useState<Record<number, RoutePlanBatchPreview>>(
    () => persisted?.weekBatches ?? {},
  );
  const [decisions, setDecisions] = useState<Record<number, "approved" | "rejected">>(
    () => persisted?.decisions ?? {},
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    // weekBatches の各要素は previewSalesRouteBatch のレスポンスをそのまま保持して
    // おり、月間batchと重複する選択顧客一覧などを含むため、週の数だけ保存すると
    // 容量が膨らみやすい。パネル側が実際に使うのは weeks[0] と warnings だけなので、
    // 永続化時はその2つだけに絞って保存する(メモリ上のweekBatchesはフル構造のまま、
    // UIの型はそのまま満たす)。batch(月アウトラインのみ、outline_only=trueで取得済み
    // でstops等の詳細を含まない)はそのまま保存してよい。
    const slimWeekBatches = Object.fromEntries(
      Object.entries(weekBatches).map(([weekNumber, weekBatch]) => [
        weekNumber,
        { weeks: weekBatch.weeks.slice(0, 1), warnings: weekBatch.warnings },
      ]),
    );
    const baseState = {
      selectedMonth,
      policy,
      maxVisits,
      travelMode,
      batch,
      decisions,
    };
    try {
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ ...baseState, weekBatches: slimWeekBatches }),
      );
    } catch (writeError) {
      // 保存に失敗する場合、原因は主に容量超過(stops/乗換案内などを含む
      // weekBatchesが大きい)と想定されるため、各週の日別詳細(days)を
      // 削って「第N週は計算済み」という事実とヘッダー数値だけを残した
      // 軽量版で再挑戦する。それでも失敗したら諦めて、直前まで保存できて
      // いた状態を消さないようにする(保存済みキーには触らない)。
      const headlineOnlyWeekBatches = Object.fromEntries(
        Object.entries(slimWeekBatches).map(([weekNumber, weekBatch]) => [
          weekNumber,
          {
            weeks: weekBatch.weeks.map((week) => ({ ...week, days: [] })),
            warnings: weekBatch.warnings,
          },
        ]),
      );
      try {
        window.localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({ ...baseState, weekBatches: headlineOnlyWeekBatches }),
        );
      } catch {
        console.warn(
          "月間営業スケジュールの状態をlocalStorageへ保存できませんでした。次回の再読み込みで計算結果が消える可能性があります。",
          writeError,
        );
      }
    }
  }, [selectedMonth, policy, maxVisits, travelMode, batch, weekBatches, decisions]);

  return (
    <RouteBatchPlanContext.Provider
      value={{
        selectedMonth,
        policy,
        maxVisits,
        travelMode,
        batch,
        weekBatches,
        decisions,
        setSelectedMonth,
        setPolicy,
        setMaxVisits,
        setTravelMode,
        setBatch,
        setWeekBatches,
        setDecisions,
      }}
    >
      {children}
    </RouteBatchPlanContext.Provider>
  );
}

export function useRouteBatchPlan(): RouteBatchPlanContextValue {
  const context = useContext(RouteBatchPlanContext);
  if (!context) {
    throw new Error("useRouteBatchPlan は RouteBatchPlanProvider の内側で使ってください");
  }
  return context;
}
