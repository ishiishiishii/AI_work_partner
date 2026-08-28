"use client";

import dynamic from "next/dynamic";
import { ActivityPlanList } from "@/components/dashboard/ActivityPlanList";
import { AiChatPanel } from "@/components/dashboard/AiChatPanel";
import { AiReasoningPanel } from "@/components/dashboard/AiReasoningPanel";
import { ReplanBanner } from "@/components/dashboard/ReplanBanner";
import { TARGET_MONTH, useDashboardData } from "@/lib/useDashboardData";
import { useRep } from "@/lib/repContext";

// leafletはブラウザのwindow/documentに直接依存しておりSSR不可なため、
// Next.jsのサーバー描画パスに乗らないよう動的import(ssr:false)にする。
const MapPanel = dynamic(() => import("@/components/dashboard/MapPanel").then((m) => m.MapPanel), {
  ssr: false,
});

export default function ActivityPage() {
  const { selectedRep, isAuthLoading } = useRep();
  const REP_ID = selectedRep?.rep_id ?? null;
  const {
    isLoading,
    loadError,
    target,
    plans,
    dailyTasks,
    deals,
    customers,
    territory,
    affinities,
    replan,
    altNotice,
    achievementRate,
    altPreview,
    needsInitialPlan,
    isGeneratingInitialPlan,
    handleResultChange,
    handlePostpone,
    handleRequestAlternative,
    confirmAlternative,
    cancelAlternativePreview,
    handleEditPlan,
    handleAddPlan,
    handleConfirmPlan,
    handleUpdateProgress,
    handleCommitProgress,
  } = useDashboardData(REP_ID);

  if (isAuthLoading || (selectedRep && isLoading)) {
    return (
      <main>
        <h1>活動計画</h1>
        <p>読み込み中...</p>
      </main>
    );
  }

  if (!selectedRep) {
    return (
      <main>
        <h1>活動計画</h1>
        <p className="activity-plan-list__empty">
          ログイン情報または担当者情報を確認できません。ログイン画面からやり直してください。
        </p>
      </main>
    );
  }

  if (loadError || !target) {
    return (
      <main>
        <h1>活動計画</h1>
        <p className="activity-plan-list__empty">
          データの取得に失敗しました{loadError ? `(${loadError})` : ""}
          。バックエンド(API・Supabase)が起動しているか確認してください。
        </p>
      </main>
    );
  }

  return (
    <main className="dashboard-main">
      <h1>活動計画</h1>
      <div className="dashboard-layout">
        <div className="dashboard-layout__primary">
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
          <AiChatPanel target={target} achievementRate={achievementRate} plans={plans} affinities={affinities} />
          <MapPanel customers={customers} territory={territory} plans={plans} targetMonth={TARGET_MONTH} />
          <AiReasoningPanel plans={plans} />
        </div>
      </div>
    </main>
  );
}
