"use client";

import { useEffect, useState } from "react";
import { ActivityPlanList, type PlanEditFields } from "@/components/dashboard/ActivityPlanList";
import { AiChatPanel } from "@/components/dashboard/AiChatPanel";
import { AiReasoningPanel } from "@/components/dashboard/AiReasoningPanel";
import { GoalCard } from "@/components/dashboard/GoalCard";
import { MapPanel } from "@/components/dashboard/MapPanel";
import { ReplanBanner } from "@/components/dashboard/ReplanBanner";
import {
  cancelPlan,
  createManualPlan,
  createPlan,
  deleteActivityResult,
  fetchActivityPlans,
  fetchDeals,
  fetchForecast,
  fetchRepAffinity,
  fetchSalesTarget,
  generateActivityPlans,
  postActivityResult,
  recalculateRepAffinity,
  replanActivityPlans,
  saveSalesTarget,
  updatePlan,
  updatePlanProgress,
} from "@/lib/api";
import { calcAchievementRate, calcForecastAmount } from "@/lib/forecast";
import { mockTaskSuggestions } from "@/lib/mockData";
import { useRep } from "@/lib/repContext";
import type {
  ActivityPlan,
  Deal,
  DealResultStatus,
  Forecast,
  RepAffinity,
  ReplanInfo,
  SalesTarget,
} from "@/types";

// 以前は "2026-08" にハードコードされており、実際の日付とズレていた
// (AIチャットにも「今日」を伝えていなかった。backend/app/services/qwen_chat.py 参照)。
function getCurrentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

const TARGET_MONTH = getCurrentMonth();

export default function DashboardPage() {
  const { selectedRep } = useRep();
  const REP_ID = selectedRep?.rep_id ?? null;
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [target, setTarget] = useState<SalesTarget | null>(null);
  const [plans, setPlans] = useState<ActivityPlan[]>([]);
  const [dailyTasks, setDailyTasks] = useState<ActivityPlan[]>([]);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [affinities, setAffinities] = useState<RepAffinity[]>([]);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [replan, setReplan] = useState<ReplanInfo | null>(null);
  const [altNotice, setAltNotice] = useState<string | null>(null);
  const [isRegenerating, setIsRegenerating] = useState(false);
  // plan_id -> バックエンドに登録済みの result_id（取り消し時にどれを消すか特定するため）
  const [resultIdByPlan, setResultIdByPlan] = useState<Record<number, number>>({});

  // 目標(sales_target)がまだ無い月は 404 になるため、その場合はクライアント側計算に
  // フォールバックする(forecastAmount/achievementRate の算出箇所を参照)
  async function refreshForecast(repId: number) {
    try {
      setForecast(await fetchForecast(repId, TARGET_MONTH));
    } catch {
      setForecast(null);
    }
  }

  useEffect(() => {
    if (REP_ID === null) return;
    const repId = REP_ID;
    let cancelled = false;

    async function load() {
      try {
        setIsLoading(true);
        setLoadError(null);
        const [fetchedTarget, fetchedPlans] = await Promise.all([
          fetchSalesTarget(repId, TARGET_MONTH),
          fetchActivityPlans(repId),
        ]);
        if (cancelled) return;

        // 訪問系の計画が1件も無ければ、初回だけAIに作ってもらう
        // (顧客に紐づかない日次タスクは generate の対象外なので、件数判定には含めない)
        const initialVisitPlans = fetchedPlans.filter((plan) => plan.category === "visit");
        const resolvedVisitPlans =
          initialVisitPlans.length > 0
            ? initialVisitPlans
            : await generateActivityPlans(repId, TARGET_MONTH);
        if (cancelled) return;

        // 得意分野スコアは計算済みのキャッシュなので、表示前に最新の結果を反映させておく
        await recalculateRepAffinity(repId);
        const [fetchedAffinities, fetchedDeals] = await Promise.all([
          fetchRepAffinity(repId),
          fetchDeals(repId),
        ]);
        if (cancelled) return;

        setTarget(
          fetchedTarget ?? {
            rep_id: repId,
            target_month: TARGET_MONTH,
            target_amount: 0,
            target_deal_count: 0,
          },
        );
        setPlans(resolvedVisitPlans);
        setDailyTasks(fetchedPlans.filter((plan) => plan.category === "task"));
        setAffinities(fetchedAffinities);
        setDeals(fetchedDeals);
        await refreshForecast(repId);
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
  }, [REP_ID]);

  async function handleTargetSave(input: { target_amount: number; target_deal_count: number }) {
    if (REP_ID === null) return;
    const updated = await saveSalesTarget(REP_ID, TARGET_MONTH, input);
    setTarget(updated);
    await refreshForecast(REP_ID);
  }

  async function handleRegenerate() {
    if (REP_ID === null) return;
    const repId = REP_ID;
    setIsRegenerating(true);
    try {
      const fresh = await generateActivityPlans(repId, TARGET_MONTH);
      setPlans(fresh);
      setReplan(null);
      await refreshForecast(repId);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "計画生成に失敗しました");
    } finally {
      setIsRegenerating(false);
    }
  }

  async function handleResultChange(planId: number, status: DealResultStatus, activityTypeName: string) {
    const changedPlan = plans.find((plan) => plan.plan_id === planId);
    if (!changedPlan || !target || REP_ID === null) return;

    // 同じ結果をもう一度押したら取り消し。バックエンドに送信済みの記録があれば、
    // そちらも削除して商談/計画のステータスを登録前に戻す。
    if (changedPlan.result_status === status) {
      const resultId = resultIdByPlan[planId];
      setPlans((prev) =>
        prev.map((plan) => (plan.plan_id === planId ? { ...plan, result_status: "pending" } : plan)),
      );

      // 「対応が難しい」の差し替え等、バックエンドに送信されていない結果は表示を戻すだけ
      if (resultId === undefined) return;

      setResultIdByPlan((prev) => {
        const next = { ...prev };
        delete next[planId];
        return next;
      });

      try {
        await deleteActivityResult(REP_ID, resultId);
        if (status === "won" || status === "lost") {
          // 成約/失注の取り消しは得意分野スコアにも影響するため、最新値を取り直す
          await recalculateRepAffinity(REP_ID);
          setAffinities(await fetchRepAffinity(REP_ID));
        }
        await refreshForecast(REP_ID);
      } catch (error) {
        setLoadError(error instanceof Error ? error.message : "結果の取り消しに失敗しました");
      }
      return;
    }

    const updatedPlans = plans.map((plan) =>
      plan.plan_id === planId
        ? { ...plan, result_status: status, activity_type_name: activityTypeName }
        : plan,
    );
    setPlans(updatedPlans);

    // 「対応が難しい」で差し替えたローカル専用の計画には実在する deal_id が無いため、
    // バックエンドへは送信せず表示のみ更新する
    if (!changedPlan.deal_id) {
      return;
    }

    try {
      const result = await postActivityResult(
        REP_ID,
        changedPlan,
        status as Exclude<DealResultStatus, "pending">,
        activityTypeName,
      );
      setResultIdByPlan((prev) => ({ ...prev, [planId]: result.result_id }));
      await refreshForecast(REP_ID);
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
        await refreshForecast(REP_ID);
      } catch (error) {
        setLoadError(error instanceof Error ? error.message : "再計画に失敗しました");
      }
    }
  }

  async function handleEditPlan(planId: number, updates: PlanEditFields) {
    if (REP_ID === null) return;
    const target = [...plans, ...dailyTasks].find((plan) => plan.plan_id === planId);
    if (!target) return;

    const previousPlans = plans;
    const previousTasks = dailyTasks;
    const updated: ActivityPlan = { ...target, ...updates };

    // 種別(訪問/事務作業)を切り替えた場合は、表示するリスト自体を跨いで移動させる
    const nextPlans = plans.filter((plan) => plan.plan_id !== planId);
    const nextTasks = dailyTasks.filter((task) => task.plan_id !== planId);
    if (updated.category === "visit") {
      setPlans([...nextPlans, updated]);
      setDailyTasks(nextTasks);
    } else {
      setDailyTasks([...nextTasks, updated]);
      setPlans(nextPlans);
    }

    try {
      await updatePlan(REP_ID, planId, updates);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "予定の更新に失敗しました");
      setPlans(previousPlans);
      setDailyTasks(previousTasks);
    }
  }

  async function handleAddPlan(newPlan: ActivityPlan) {
    if (REP_ID === null) return;
    try {
      const created = await createManualPlan(REP_ID, {
        plan_date: newPlan.plan_date,
        start_time: newPlan.start_time,
        end_time: newPlan.end_time,
        category: newPlan.category,
        activity_type_name: newPlan.activity_type_name,
        customer_name: newPlan.customer_name,
        customer_id: newPlan.customer_id,
        deal_id: newPlan.deal_id,
        priority: newPlan.priority,
      });
      if (created.category === "visit") {
        setPlans((prev) => [...prev, created]);
      } else {
        setDailyTasks((prev) => [...prev, created]);
      }
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "予定の追加に失敗しました");
    }
  }

  // 「確定する」はAI提案フラグだけを外す。提案理由(reasoning_text)はそのまま残す
  function handleConfirmPlan(planId: number) {
    setPlans((prev) =>
      prev.map((plan) => (plan.plan_id === planId ? { ...plan, is_ai_generated: false } : plan)),
    );
    setDailyTasks((prev) =>
      prev.map((task) => (task.plan_id === planId ? { ...task, is_ai_generated: false } : task)),
    );
  }

  // スライダー操作中は見た目だけ即時更新する(ドラッグ中に onChange が連発するため、
  // バックエンドへの保存はドラッグ完了時の handleCommitProgress にまとめる)。
  function handleUpdateProgress(planId: number, percent: number) {
    setPlans((prev) =>
      prev.map((plan) => (plan.plan_id === planId ? { ...plan, progress_percent: percent } : plan)),
    );
    setDailyTasks((prev) =>
      prev.map((task) => (task.plan_id === planId ? { ...task, progress_percent: percent } : task)),
    );
  }

  async function handleCommitProgress(planId: number, percent: number) {
    if (REP_ID === null) return;
    try {
      await updatePlanProgress(REP_ID, planId, percent);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "進捗の保存に失敗しました");
    }
  }

  async function handleRequestAlternative(planId: number) {
    const changedPlan = plans.find((plan) => plan.plan_id === planId) ?? dailyTasks.find((task) => task.plan_id === planId);
    if (!changedPlan || !target || REP_ID === null) return;
    const foundInPlans = plans.some((plan) => plan.plan_id === planId);
    setAltNotice(null);

    if (changedPlan.category === "task") {
      // 商談のような実データが無い事務作業は、固定の候補プールから未使用のものを提示する
      const usedTitles = new Set([...plans, ...dailyTasks].map((item) => item.customer_name));
      const candidateTask = mockTaskSuggestions.find((task) => !usedTitles.has(task.title));
      if (!candidateTask) {
        setAltNotice("現在、差し替えられる事務作業の候補がありません。");
        return;
      }

      try {
        // 商談側(下)と同じく、差し替え候補を実在の予定として登録し元の予定は取り消す
        // (どちらもバックエンドに反映。以前はローカル専用の plan_id しか持たず、
        // リロードすると消えていた)。
        const created = await createPlan(REP_ID, {
          plan_date: changedPlan.plan_date,
          category: "task",
          activity_type: candidateTask.activityTypeName,
          customer_id: null,
          deal_id: null,
          priority: changedPlan.priority,
          title: candidateTask.title,
          rationale: candidateTask.reasoningText,
        });
        await cancelPlan(REP_ID, planId);

        const candidate: ActivityPlan = {
          plan_id: created.plan_id,
          rep_id: changedPlan.rep_id,
          plan_date: changedPlan.plan_date,
          // 時間が(手動編集などで)設定済みならそのまま引き継ぐ
          start_time: changedPlan.start_time,
          end_time: changedPlan.end_time,
          category: "task",
          customer_id: null,
          customer_name: candidateTask.title,
          deal_id: null,
          product_name: null,
          activity_type_name: candidateTask.activityTypeName,
          priority: changedPlan.priority,
          expected_amount: 0,
          expected_probability: 0,
          is_ai_generated: true,
          reasoning_text: candidateTask.reasoningText,
          result_status: "pending",
          memo: null,
          progress_percent: 0,
        };

        if (foundInPlans) {
          setPlans((prev) => prev.filter((plan) => plan.plan_id !== planId).concat(candidate));
        } else {
          setDailyTasks((prev) => prev.filter((task) => task.plan_id !== planId).concat(candidate));
        }
        setReplan({
          before_achievement_rate: calcAchievementRate(plans, target.target_amount),
          after_achievement_rate: calcAchievementRate(plans, target.target_amount),
          reason: `${changedPlan.customer_name}への対応が難しいとのことなので、AIが「${candidate.customer_name}」に差し替えました`,
        });
      } catch (error) {
        setLoadError(error instanceof Error ? error.message : "予定の差し替えに失敗しました");
      }
      return;
    }

    // 現在計画に入っていない、進行中(未成約・未失注)の商談から候補を選ぶ
    const usedDealIds = new Set(plans.map((plan) => plan.deal_id).filter((id): id is number => id !== null));
    const candidateDeal = [...deals]
      .filter((deal) => deal.deal_result_status === "ongoing" && !usedDealIds.has(deal.deal_id))
      .sort((a, b) => b.estimated_amount * b.win_probability - a.estimated_amount * a.win_probability)[0];
    if (!candidateDeal) {
      setAltNotice("現在、差し替えられる進行中の商談がありません(すべて計画済みです)。");
      return;
    }

    const reasoningText = `対応が難しいとのことなので、進行中の商談「${candidateDeal.product_name}」(${candidateDeal.customer_name}様)への提案に差し替えました。`;

    try {
      // 差し替え候補を本物の予定として登録し、元の予定は取り消す(どちらもバックエンドに反映)。
      // 以前はローカル専用の仮 plan_id(900000+deal_id)を使っていたため、結果を記録しようと
      // すると実在しない plan_id で外部キー違反になり得た。
      const created = await createPlan(REP_ID, {
        plan_date: changedPlan.plan_date,
        category: "visit",
        activity_type: "visit",
        customer_id: candidateDeal.customer_id,
        deal_id: candidateDeal.deal_id,
        priority: changedPlan.priority,
        expected_amount: candidateDeal.estimated_amount,
        expected_probability: candidateDeal.win_probability,
        rationale: reasoningText,
      });
      await cancelPlan(REP_ID, planId);

      const candidate: ActivityPlan = {
        plan_id: created.plan_id,
        rep_id: candidateDeal.rep_id,
        plan_date: changedPlan.plan_date,
        // 時間が(手動編集などで)設定済みならそのまま引き継ぐ
        start_time: changedPlan.start_time,
        end_time: changedPlan.end_time,
        category: "visit",
        customer_id: candidateDeal.customer_id,
        customer_name: candidateDeal.customer_name,
        deal_id: candidateDeal.deal_id,
        product_name: candidateDeal.product_name,
        activity_type_name: "訪問",
        priority: changedPlan.priority,
        expected_amount: candidateDeal.estimated_amount,
        expected_probability: candidateDeal.win_probability,
        is_ai_generated: true,
        reasoning_text: reasoningText,
        result_status: "pending",
        memo: null,
        progress_percent: 0,
      };

      const before = calcAchievementRate(plans, target.target_amount);
      const nextPlans = plans.filter((plan) => plan.plan_id !== planId).concat(candidate);
      const after = calcAchievementRate(nextPlans, target.target_amount);

      setPlans(nextPlans);
      setReplan({
        before_achievement_rate: before,
        after_achievement_rate: after,
        reason: `${changedPlan.customer_name}への対応が難しいとのことなので、AIが${candidate.customer_name}への提案に差し替えました`,
      });
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "計画の差し替えに失敗しました");
    }
  }

  if (!selectedRep || isLoading) {
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

  // バックエンドの forecast は成約/失注の実績まで反映した正確な値。
  // 目標(sales_target)が未登録の月は 404 になるため、その場合だけクライアント計算に
  // フォールバックする
  const forecastAmount = forecast ? forecast.forecast_amount : calcForecastAmount(plans);
  const achievementRate = forecast ? forecast.achievement_rate : calcAchievementRate(plans, target.target_amount);
  const openPlanCount = forecast ? forecast.open_plan_count : plans.length;

  return (
    <main className="dashboard-main">
      <h1>営業ダッシュボード</h1>
      <div className="dashboard-layout">
        <div className="dashboard-layout__primary">
          <GoalCard
            rep={selectedRep}
            target={target}
            forecastAmount={forecastAmount}
            achievementRate={achievementRate}
            openPlanCount={openPlanCount}
            onSave={handleTargetSave}
          />
          {replan && <ReplanBanner info={replan} />}
          {altNotice && <p className="activity-plan-list__empty">{altNotice}</p>}
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
            repId={selectedRep.rep_id}
            plans={plans}
            dailyTasks={dailyTasks}
            onResultChange={handleResultChange}
            onRequestAlternative={handleRequestAlternative}
            onEditPlan={handleEditPlan}
            onAddPlan={handleAddPlan}
            onConfirmPlan={handleConfirmPlan}
            onUpdateProgress={handleUpdateProgress}
            onCommitProgress={handleCommitProgress}
          />
        </div>
        <div className="dashboard-layout__sidebar">
          <AiChatPanel
            target={target}
            achievementRate={achievementRate}
            plans={plans}
            affinities={affinities}
          />
          <MapPanel />
          <AiReasoningPanel plans={plans} />
        </div>
      </div>
    </main>
  );
}
