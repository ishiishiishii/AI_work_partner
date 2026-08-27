"use client";

import { ActivityPlanList } from "@/components/dashboard/ActivityPlanList";
import { AiReasoningPanel } from "@/components/dashboard/AiReasoningPanel";
import { GoalCard } from "@/components/dashboard/GoalCard";
import { ReplanBanner } from "@/components/dashboard/ReplanBanner";
import { RoutePlanPanel } from "@/components/dashboard/RoutePlanPanel";
import { useDashboardData } from "@/lib/useDashboardData";
import { useRep } from "@/lib/repContext";

export default function DashboardPage() {
  const { selectedRep, isAuthLoading } = useRep();
  const REP_ID = selectedRep?.rep_id ?? null;
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
    isRegenerating,
    needsInitialPlan,
    isGeneratingInitialPlan,
    forecastAmount,
    forecastProfitAmount,
    actualAchievedAmount,
    actualAchievementRate,
    handleTargetSave,
    handleRouteApproved,
    handleRegenerate,
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
            forecastAmount={forecastAmount}
            forecastProfitAmount={forecastProfitAmount}
            actualAchievedAmount={actualAchievedAmount}
            actualAchievementRate={actualAchievementRate}
            onSave={handleTargetSave}
            willGeneratePlan={needsInitialPlan}
          />
          {replan && <ReplanBanner info={replan} />}
          {altNotice && <p className="activity-plan-list__empty">{altNotice}</p>}
          {needsInitialPlan ? (
            <p className="activity-plan-list__empty">
              {isGeneratingInitialPlan
                ? "AIが今月の活動計画を作成しています(数分かかる場合があります)..."
                : "目標を保存すると、AIが今月の活動計画を作成します。"}
            </p>
          ) : (
            <div className="regenerate-bar">
              <button
                type="button"
                className="regenerate-button"
                onClick={handleRegenerate}
                disabled={isRegenerating}
              >
                {isRegenerating ? "生成中..." : "AIに計画を作り直してもらう"}
              </button>
            </div>
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
          <RoutePlanPanel onSaved={handleRouteApproved} />
          <AiReasoningPanel plans={plans} />
        </div>
      </div>
    </main>
  );
}
