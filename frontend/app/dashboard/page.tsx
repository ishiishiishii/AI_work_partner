"use client";

import { ActivityPlanList } from "@/components/dashboard/ActivityPlanList";
import { AiReasoningPanel } from "@/components/dashboard/AiReasoningPanel";
import { GoalCard } from "@/components/dashboard/GoalCard";
import { ReplanBanner } from "@/components/dashboard/ReplanBanner";
import { RouteBatchPlanPanel } from "@/components/dashboard/RouteBatchPlanPanel";
import { useDashboardData } from "@/lib/useDashboardData";
import { useRep } from "@/lib/repContext";
import type { RoutePlanBatchPreview } from "@/types";
import { useEffect, useState } from "react";

export default function DashboardPage() {
  const { selectedRep, isAuthLoading } = useRep();
  const REP_ID = selectedRep?.rep_id ?? null;
  const [aiMonthPlan, setAiMonthPlan] = useState<RoutePlanBatchPreview | null>(null);
  const {
    isLoading,
    loadError,
    target,
    plans,
    dailyTasks,
    deals,
    replan,
    altNotice,
    altPreview,
    needsInitialPlan,
    isGeneratingInitialPlan,
    routeRefreshRevision,
    handleTargetSave,
    handleRouteApproved,
    handleResultChange,
    handlePostpone,
    handleEditPlan,
    handleAddPlan,
    handleConfirmPlan,
    handleUpdateProgress,
    handleCommitProgress,
    handleRequestAlternative,
    confirmAlternative,
    cancelAlternativePreview,
  } = useDashboardData(REP_ID);

  useEffect(() => {
    setAiMonthPlan(null);
  }, [REP_ID]);

  const probabilityPercent = (value: number): number =>
    value <= 1 ? value * 100 : value;
  const aiForecastAmount = aiMonthPlan
    ? Number(aiMonthPlan.achieved_amount) +
      Number(aiMonthPlan.existing_plan_expected_sales) +
      Number(aiMonthPlan.portfolio_expected_sales)
    : 0;
  const aiForecastProfitAmount = aiMonthPlan
    ? Number(aiMonthPlan.achieved_gross_profit) +
      Number(aiMonthPlan.existing_plan_expected_gross_profit) +
      Number(aiMonthPlan.totals.expected_gross_profit ?? 0)
    : 0;
  const aiActualAmount = aiMonthPlan ? Number(aiMonthPlan.achieved_amount) : 0;
  const aiActualRate =
    aiMonthPlan?.monthly_target_amount && Number(aiMonthPlan.monthly_target_amount) > 0
      ? (aiActualAmount / Number(aiMonthPlan.monthly_target_amount)) * 100
      : 0;

  if (isAuthLoading || (selectedRep && isLoading)) {
    return (
      <main>
        <h1>営業ダッシュボード</h1>
        <p>読み込み中...</p>
      </main>
    );
  }

  if (!selectedRep) {
    return (
      <main>
        <h1>営業ダッシュボード</h1>
        <p className="activity-plan-list__empty">
          ログイン情報または担当者情報を確認できません。ログイン画面からやり直してください。
        </p>
      </main>
    );
  }

  if (loadError || !target) {
    return (
      <main>
        <h1>営業ダッシュボード</h1>
        <p className="activity-plan-list__empty">
          データの取得に失敗しました{loadError ? `(${loadError})` : ""}
          。バックエンド(API・Supabase)が起動しているか確認してください。
        </p>
      </main>
    );
  }

  return (
    <main className="dashboard-main">
      <h1>営業ダッシュボード</h1>
      <div className="dashboard-layout">
        <div className="dashboard-layout__primary">
          <GoalCard
            rep={selectedRep}
            target={target}
            forecastAmount={aiForecastAmount}
            forecastProfitAmount={aiForecastProfitAmount}
            actualAchievedAmount={aiActualAmount}
            actualAchievementRate={aiActualRate}
            salesAchievementProbability={
              aiMonthPlan ? probabilityPercent(aiMonthPlan.sales_achievement_probability) : 0
            }
            profitAchievementProbability={
              aiMonthPlan
                ? aiMonthPlan.profit_achievement_probability === null
                  ? null
                  : probabilityPercent(aiMonthPlan.profit_achievement_probability)
                : 0
            }
            jointAchievementProbability={
              aiMonthPlan ? probabilityPercent(aiMonthPlan.joint_achievement_probability) : 0
            }
            onSave={handleTargetSave}
            willGeneratePlan={needsInitialPlan}
          />
          <RouteBatchPlanPanel
            onApproved={handleRouteApproved}
            onPlanCalculated={(calculated) => {
              setAiMonthPlan(
                calculated?.start_date.slice(0, 7) === target.target_month ? calculated : null,
              );
            }}
            refreshSignal={routeRefreshRevision}
            existingPlans={plans}
          />
          {replan && <ReplanBanner info={replan} />}
          {altNotice && <p className="activity-plan-list__empty">{altNotice}</p>}
          {needsInitialPlan && (
            <p className="activity-plan-list__empty">
              {isGeneratingInitialPlan
                ? "AIが今月の活動計画を作成しています(数分かかる場合があります)..."
                : "目標を保存すると、AIが今月の活動計画を作成します。"}
            </p>
          )}
          <ActivityPlanList
            repId={selectedRep.rep_id}
            plans={plans}
            dailyTasks={dailyTasks}
            deals={deals}
            onResultChange={handleResultChange}
            onPostpone={handlePostpone}
            onRequestAlternative={handleRequestAlternative}
            altPreview={altPreview ? { planId: altPreview.planId, label: altPreview.label } : null}
            onConfirmAlternative={confirmAlternative}
            onCancelAlternative={cancelAlternativePreview}
            onEditPlan={handleEditPlan}
            onAddPlan={handleAddPlan}
            onConfirmPlan={handleConfirmPlan}
            onUpdateProgress={handleUpdateProgress}
            onCommitProgress={handleCommitProgress}
          />
        </div>
        <div className="dashboard-layout__sidebar">
          <AiReasoningPanel plans={plans} />
        </div>
      </div>
    </main>
  );
}
