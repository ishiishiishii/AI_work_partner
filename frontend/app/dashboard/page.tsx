"use client";

import { useState } from "react";
import { ActivityPlanList } from "@/components/dashboard/ActivityPlanList";
import { AiReasoningPanel } from "@/components/dashboard/AiReasoningPanel";
import { GoalCard } from "@/components/dashboard/GoalCard";
import { ReplanBanner } from "@/components/dashboard/ReplanBanner";
import { updateSalesTarget } from "@/lib/api";
import {
  mockActivityPlans,
  mockRepAffinities,
  mockReplacementCandidates,
  mockSalesRep,
  mockSalesTarget,
} from "@/lib/mockData";
import type { ActivityPlan, DealResultStatus, ReplanInfo, SalesTarget } from "@/types";

function calcForecastAmount(plans: ActivityPlan[]): number {
  return plans.reduce((sum, plan) => {
    if (plan.result_status === "won") return sum + plan.expected_amount;
    if (plan.result_status === "lost") return sum;
    return sum + plan.expected_amount * (plan.expected_probability / 100);
  }, 0);
}

function calcAchievementRate(plans: ActivityPlan[], targetAmount: number): number {
  if (targetAmount <= 0) return 0;
  return (calcForecastAmount(plans) / targetAmount) * 100;
}

export default function DashboardPage() {
  const [target, setTarget] = useState<SalesTarget>(mockSalesTarget);
  const [plans, setPlans] = useState<ActivityPlan[]>(mockActivityPlans);
  const [candidates, setCandidates] = useState<ActivityPlan[]>(mockReplacementCandidates);
  const [replan, setReplan] = useState<ReplanInfo | null>(null);
  // 再計画で「どの計画の結果をきっかけに、どの計画を追加したか」を覚えておく（取り消し用）
  const [replanLinks, setReplanLinks] = useState<Record<number, number>>({});

  const forecastAmount = calcForecastAmount(plans);
  const achievementRate = calcAchievementRate(plans, target.target_amount);

  async function handleTargetSave(input: { target_amount: number; target_deal_count: number }) {
    const updated = await updateSalesTarget(mockSalesRep.rep_id, target.target_month, input);
    setTarget(updated);
  }

  function handleResultChange(planId: number, status: DealResultStatus) {
    const changedPlan = plans.find((plan) => plan.plan_id === planId);
    if (!changedPlan) return;

    // 同じ結果をもう一度押したら取り消し
    if (changedPlan.result_status === status) {
      undoResult(planId);
      return;
    }

    const nextPlans = plans.map((plan) =>
      plan.plan_id === planId ? { ...plan, result_status: status } : plan,
    );

    const alreadyReplanned = Boolean(replanLinks[planId]);
    if (
      (status === "lost" || status === "postponed") &&
      !alreadyReplanned &&
      candidates.length > 0
    ) {
      const [candidate, ...restCandidates] = candidates;
      const before = calcAchievementRate(nextPlans, target.target_amount);
      const withCandidate = [...nextPlans, candidate];
      const after = calcAchievementRate(withCandidate, target.target_amount);

      setCandidates(restCandidates);
      setReplanLinks((prev) => ({ ...prev, [planId]: candidate.plan_id }));
      setReplan({
        before_achievement_rate: before,
        after_achievement_rate: after,
        reason: `${changedPlan.customer_name}の${status === "lost" ? "失注" : "延期"}により、代わりに${candidate.customer_name}への提案を追加しました`,
      });
      setPlans(withCandidate);
      return;
    }

    setPlans(nextPlans);
  }

  function undoResult(planId: number) {
    const linkedCandidateId = replanLinks[planId];
    const resetPlans = plans.map((plan) =>
      plan.plan_id === planId ? { ...plan, result_status: "pending" as const } : plan,
    );

    if (!linkedCandidateId) {
      setPlans(resetPlans);
      return;
    }

    // 再計画で追加された計画がまだ未入力なら、一緒に取り消して候補に戻す。
    // すでに結果が入力されていたら、それは実際の計画として残す。
    const linkedPlan = resetPlans.find((plan) => plan.plan_id === linkedCandidateId);
    const shouldRemoveLinkedPlan = linkedPlan?.result_status === "pending";

    setPlans(
      shouldRemoveLinkedPlan
        ? resetPlans.filter((plan) => plan.plan_id !== linkedCandidateId)
        : resetPlans,
    );
    if (shouldRemoveLinkedPlan && linkedPlan) {
      setCandidates((prev) => [linkedPlan, ...prev]);
    }
    setReplanLinks((prev) => {
      const next = { ...prev };
      delete next[planId];
      return next;
    });
    setReplan(null);
  }

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
      <ActivityPlanList plans={plans} onResultChange={handleResultChange} />
      <AiReasoningPanel plans={plans} affinities={mockRepAffinities} />
    </main>
  );
}
