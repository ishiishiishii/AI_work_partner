"use client";

import { createContext, useContext, useState } from "react";
import { tomorrowInTokyo } from "@/components/dashboard/RoutePlanPanel";
import type { RouteEconomicPolicy } from "@/lib/routeEconomicPolicy";
import type { RoutePlanBatchPreview, RoutePlanPreview } from "@/types";

// RouteBatchPlanPanel(月間営業スケジュール)はダッシュボードページの子として
// マウントされているため、ページ遷移でダッシュボードがアンマウントされると
// useState の中身(設計済みの月間計画)が消え、戻るたびに作り直しになってしまう。
// QuickAddPlanContext と同様にルートレイアウトへ状態を引き上げ、ページ遷移を
// またいでも設計結果を保持できるようにする。
type RouteBatchPlanState = {
  selectedMonth: string;
  policy: RouteEconomicPolicy;
  maxVisits: number;
  travelMode: RoutePlanPreview["travel_mode"];
  batch: RoutePlanBatchPreview | null;
  weekBatches: Record<number, RoutePlanBatchPreview>;
  decisions: Record<number, "approved" | "rejected">;
};

type RouteBatchPlanContextValue = RouteBatchPlanState & {
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
  const [selectedMonth, setSelectedMonth] = useState(() => tomorrowInTokyo().slice(0, 7));
  const [policy, setPolicy] = useState<RouteEconomicPolicy>("balanced");
  const [maxVisits, setMaxVisits] = useState(4);
  const [travelMode, setTravelMode] = useState<RoutePlanPreview["travel_mode"]>("driving");
  const [batch, setBatch] = useState<RoutePlanBatchPreview | null>(null);
  const [weekBatches, setWeekBatches] = useState<Record<number, RoutePlanBatchPreview>>({});
  const [decisions, setDecisions] = useState<Record<number, "approved" | "rejected">>({});

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
