"use client";

import { useEffect, useState } from "react";
import { ActivityPlanList } from "@/components/dashboard/ActivityPlanList";
import { AiReasoningPanel } from "@/components/dashboard/AiReasoningPanel";
import { GoalCard } from "@/components/dashboard/GoalCard";
import { ReplanBanner } from "@/components/dashboard/ReplanBanner";
import {
  fetchActivityPlans,
  fetchSalesTarget,
  generateActivityPlans,
  postActivityResult,
  replanActivityPlans,
  saveSalesTarget,
} from "@/lib/api";
import { calcAchievementRate, calcForecastAmount } from "@/lib/forecast";
import {
  mockAlternativeCandidates,
  mockDailyTasks,
  mockRepAffinities,
  mockSalesRep,
} from "@/lib/mockData";
import type { ActivityPlan, DealResultStatus, ReplanInfo, SalesTarget } from "@/types";

const REP_ID = mockSalesRep.rep_id;
const TARGET_MONTH = "2026-08";

export default function DashboardPage() {
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [target, setTarget] = useState<SalesTarget | null>(null);
  const [plans, setPlans] = useState<ActivityPlan[]>([]);
  const [replan, setReplan] = useState<ReplanInfo | null>(null);
  const [isRegenerating, setIsRegenerating] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setIsLoading(true);
        setLoadError(null);
        const [fetchedTarget, fetchedPlans] = await Promise.all([
          fetchSalesTarget(REP_ID, TARGET_MONTH),
          fetchActivityPlans(REP_ID),
        ]);
        if (cancelled) return;

        // 計画が1件も無ければ、初回だけAIに作ってもらう
        const resolvedPlans =
          fetchedPlans.length > 0 ? fetchedPlans : await generateActivityPlans(REP_ID, TARGET_MONTH);
        if (cancelled) return;

        setTarget(
          fetchedTarget ?? {
            rep_id: REP_ID,
            target_month: TARGET_MONTH,
            target_amount: 0,
            target_deal_count: 0,
          },
        );
        setPlans(resolvedPlans);
      } catch (error) {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : "読み込みに失敗しました");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleTargetSave(input: { target_amount: number; target_deal_count: number }) {
    const updated = await saveSalesTarget(REP_ID, TARGET_MONTH, input);
    setTarget(updated);
  }

  async function handleRegenerate() {
    setIsRegenerating(true);
    try {
      const fresh = await generateActivityPlans(REP_ID, TARGET_MONTH);
      setPlans(fresh);
      setReplan(null);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "計画生成に失敗しました");
    } finally {
      setIsRegenerating(false);
    }
  }

  async function handleResultChange(planId: string, status: DealResultStatus) {
    const changedPlan = plans.find((plan) => plan.plan_id === planId);
    if (!changedPlan || !target) return;

    // 同じ結果をもう一度押したら、表示だけ取り消し
    // （バックエンドに送信済みの記録は削除されません。取り消しAPIはまだ無いためです）
    if (changedPlan.result_status === status) {
      setPlans((prev) =>
        prev.map((plan) => (plan.plan_id === planId ? { ...plan, result_status: "pending" } : plan)),
      );
      return;
    }

    const updatedPlans = plans.map((plan) =>
      plan.plan_id === planId ? { ...plan, result_status: status } : plan,
    );
    setPlans(updatedPlans);

    // 「対応が難しい」で差し替えたローカル専用の計画には実在する deal_id が無いため、
    // バックエンドへは送信せず表示のみ更新する
    if (!changedPlan.deal_id) {
      return;
    }

    try {
      await postActivityResult(REP_ID, changedPlan, status as Exclude<DealResultStatus, "pending">);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "結果の登録に失敗しました");
      setPlans(plans); // ロールバック
      return;
    }

    if (status === "lost" || status === "postponed") {
      const before = calcAchievementRate(updatedPlans, target.target_amount);
      try {
        const freshPlans = await replanActivityPlans(REP_ID, TARGET_MONTH);
        const after = calcAchievementRate(freshPlans, target.target_amount);
        setPlans(freshPlans);
        setReplan({
          before_achievement_rate: before,
          after_achievement_rate: after,
          reason: "商談結果を反映し、AIが残り期間の計画を組み直しました",
        });
      } catch (error) {
        setLoadError(error instanceof Error ? error.message : "再計画に失敗しました");
      }
    }
  }

  function handleRequestAlternative(planId: string) {
    const changedPlan = plans.find((plan) => plan.plan_id === planId);
    if (!changedPlan || !target) return;

    const candidate = mockAlternativeCandidates.find(
      (item) => !plans.some((plan) => plan.plan_id === item.plan_id),
    );
    if (!candidate) return;

    const before = calcAchievementRate(plans, target.target_amount);
    const nextPlans = plans.filter((plan) => plan.plan_id !== planId).concat(candidate);
    const after = calcAchievementRate(nextPlans, target.target_amount);

    setPlans(nextPlans);
    setReplan({
      before_achievement_rate: before,
      after_achievement_rate: after,
      reason: `${changedPlan.customer_name}への対応が難しいとのことなので、AIが${candidate.customer_name}への提案に差し替えました`,
    });
  }

  if (isLoading) {
    return (
      <main>
        <h1>営業ダッシュボード</h1>
        <p>読み込み中...</p>
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

  const forecastAmount = calcForecastAmount(plans);
  const achievementRate = calcAchievementRate(plans, target.target_amount);

  return (
    <main>
      <h1>営業ダッシュボード</h1>
      <GoalCard
        rep={mockSalesRep}
        target={target}
        forecastAmount={forecastAmount}
        achievementRate={achievementRate}
        onSave={handleTargetSave}
      />
      {replan && <ReplanBanner info={replan} />}
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
      <ActivityPlanList
        plans={plans}
        dailyTasks={mockDailyTasks}
        onResultChange={handleResultChange}
        onRequestAlternative={handleRequestAlternative}
      />
      <AiReasoningPanel plans={plans} affinities={mockRepAffinities} />
    </main>
  );
}
