"use client";

import { useEffect, useRef, useState } from "react";
import type { PlanEditFields } from "@/components/dashboard/ActivityPlanList";
import {
  cancelPlan,
  createManualPlan,
  createPlan,
  deleteActivityResult,
  fetchActivityPlans,
  fetchCustomers,
  fetchDeals,
  fetchForecast,
  fetchRepAffinity,
  fetchRepTerritory,
  fetchSalesTarget,
  generateActivityPlans,
  postActivityResult,
  recalculateRepAffinity,
  replanActivityPlans,
  saveSalesTarget,
  updatePlan,
  updatePlanProgress,
} from "@/lib/api";
import {
  calcAchievementRate,
  calcActualAchievedAmount,
  calcActualAchievementRate,
  calcForecastAmount,
  calcForecastProfit,
} from "@/lib/forecast";
import { todayIsoLocal } from "@/lib/dateRange";
import { useInitialPlanGeneration } from "@/lib/initialPlanGenerationContext";
import { mockTaskSuggestions } from "@/lib/mockData";
import type {
  ActivityPlan,
  Customer,
  Deal,
  DealResultStatus,
  Forecast,
  RepAffinity,
  PlanChange,
  ReplanInfo,
  SalesTarget,
  Territory,
} from "@/types";

// replanActivityPlansは未来のAI予定を全て削除して作り直すため、plan_idでは
// before/afterを突き合わせられない。同じ顧客の予定が消えて別日に現れていれば
// 「移動」、片方にしか無ければ「追加/削除」とみなして差分を組み立てる。
function diffFuturePlans(before: ActivityPlan[], after: ActivityPlan[]): PlanChange[] {
  const today = todayIsoLocal();
  const isFutureAiPending = (plan: ActivityPlan) =>
    plan.is_ai_generated && plan.result_status === "pending" && plan.plan_date >= today;

  const beforeFuture = before.filter(isFutureAiPending);
  const afterFuture = after.filter(isFutureAiPending);

  const identityKey = (plan: ActivityPlan) => `${plan.customer_id ?? plan.customer_name}:${plan.plan_date}`;
  const afterKeys = new Set(afterFuture.map(identityKey));
  const beforeKeys = new Set(beforeFuture.map(identityKey));

  const unmatchedBefore = beforeFuture.filter((plan) => !afterKeys.has(identityKey(plan)));
  const unmatchedAfter = afterFuture.filter((plan) => !beforeKeys.has(identityKey(plan)));

  const customerKey = (plan: ActivityPlan) => String(plan.customer_id ?? plan.customer_name);
  const unmatchedAfterByCustomer = new Map<string, ActivityPlan[]>();
  unmatchedAfter.forEach((plan) => {
    const key = customerKey(plan);
    unmatchedAfterByCustomer.set(key, [...(unmatchedAfterByCustomer.get(key) ?? []), plan]);
  });

  const changes: PlanChange[] = [];
  const consumedAfterPlanIds = new Set<number>();

  for (const beforePlan of unmatchedBefore) {
    const candidates = (unmatchedAfterByCustomer.get(customerKey(beforePlan)) ?? []).filter(
      (plan) => !consumedAfterPlanIds.has(plan.plan_id),
    );
    const match = candidates[0];
    if (match) {
      consumedAfterPlanIds.add(match.plan_id);
      changes.push({
        type: "moved",
        customer_name: beforePlan.customer_name,
        activity_type_name: match.activity_type_name,
        before_date: beforePlan.plan_date,
        after_date: match.plan_date,
        expected_amount: match.expected_amount,
        expected_probability: match.expected_probability,
        reasoning_text: match.reasoning_text,
      });
    } else {
      changes.push({
        type: "removed",
        customer_name: beforePlan.customer_name,
        activity_type_name: beforePlan.activity_type_name,
        before_date: beforePlan.plan_date,
      });
    }
  }

  for (const afterPlan of unmatchedAfter) {
    if (consumedAfterPlanIds.has(afterPlan.plan_id)) continue;
    changes.push({
      type: "added",
      customer_name: afterPlan.customer_name,
      activity_type_name: afterPlan.activity_type_name,
      after_date: afterPlan.plan_date,
      expected_amount: afterPlan.expected_amount,
      expected_probability: afterPlan.expected_probability,
      reasoning_text: afterPlan.reasoning_text,
    });
  }

  changes.sort((a, b) => (a.after_date ?? a.before_date ?? "").localeCompare(b.after_date ?? b.before_date ?? ""));
  return changes;
}

// 以前は "2026-08" にハードコードされており、実際の日付とズレていた
// (AIチャットにも「今日」を伝えていなかった。backend/app/services/qwen_chat.py 参照)。
export function getCurrentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export const TARGET_MONTH = getCurrentMonth();

// 「対応が難しい」ボタンの差し替え提案。ユーザーが確定するまでの一時的な状態
type AltPreview =
  | {
      kind: "task";
      planId: number;
      foundInPlans: boolean;
      changedPlan: ActivityPlan;
      label: string;
      candidateTask: (typeof mockTaskSuggestions)[number];
    }
  | {
      kind: "deal";
      planId: number;
      changedPlan: ActivityPlan;
      label: string;
      candidateDeal: Deal;
    };

// 目標入力→計画生成→根拠→結果入力→再計画のコア体験を、ダッシュボードと
// 活動計画ページの両方で同じ挙動にするための共有フック(MVPコア体験は
// AGENTS.mdの方針によりこの一箇所のロジックのみで実装する)。
export function useDashboardData(repId: number | null) {
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [target, setTarget] = useState<SalesTarget | null>(null);
  const [plans, setPlans] = useState<ActivityPlan[]>([]);
  const [dailyTasks, setDailyTasks] = useState<ActivityPlan[]>([]);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [territory, setTerritory] = useState<Territory | null>(null);
  const [affinities, setAffinities] = useState<RepAffinity[]>([]);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [replan, setReplan] = useState<ReplanInfo | null>(null);
  const [altNotice, setAltNotice] = useState<string | null>(null);
  // 「対応が難しい」の差し替え候補。確定するまでバックエンドには送らない
  const [altPreview, setAltPreview] = useState<AltPreview | null>(null);
  const [isRegenerating, setIsRegenerating] = useState(false);
  // その月の訪問計画がまだ1件も無いか(目標保存時にAI生成を走らせるかの判定に使う)
  const [needsInitialPlan, setNeedsInitialPlan] = useState(false);
  // 生成中フラグはルートレイアウトのProviderで持つ(このフックはページ遷移のたびに
  // 作り直されるため、ローカルstateだと生成中に別ページへ移動して戻った際に「未生成」
  // 状態へ巻き戻って見えてしまい、目標の再保存で生成が二重に走る不具合があった)
  const initialPlanGeneration = useInitialPlanGeneration();
  const initialPlanGenerationKey = repId !== null ? `${repId}:${TARGET_MONTH}` : null;
  const isGeneratingInitialPlan =
    initialPlanGenerationKey !== null && initialPlanGeneration.isGenerating(initialPlanGenerationKey);
  // 商談結果がDBへ保存され、その結果に基づく活動再計画まで完了した時だけ更新する。
  // ダッシュボードの月間ルートが、保存前の古い商談状態で先走って再計算するのを防ぐ。
  const [routeRefreshRevision, setRouteRefreshRevision] = useState(0);
  // plan_id -> バックエンドに登録済みの result_id(取り消し時にどれを消すか特定するため)
  const [resultIdByPlan, setResultIdByPlan] = useState<Record<number, number>>({});

  // 目標(sales_target)がまだ無い月は 404 になるため、その場合はクライアント側計算に
  // フォールバックする(forecastAmount/achievementRate の算出箇所を参照)
  async function refreshForecast(rid: number) {
    try {
      setForecast(await fetchForecast(rid, TARGET_MONTH));
    } catch {
      setForecast(null);
    }
  }

  async function handleRouteApproved(): Promise<void> {
    if (repId === null) return;
    const fresh = await fetchActivityPlans(repId);
    setPlans(fresh.filter((plan) => plan.category === "visit"));
    setDailyTasks(fresh.filter((plan) => plan.category === "task"));
    await refreshForecast(repId);
  }

  useEffect(() => {
    if (repId === null) return;
    const rid = repId;
    let cancelled = false;

    async function load() {
      try {
        setIsLoading(true);
        setLoadError(null);
        const [fetchedTarget, fetchedPlans] = await Promise.all([
          fetchSalesTarget(rid, TARGET_MONTH),
          fetchActivityPlans(rid),
        ]);
        if (cancelled) return;

        // 顧客に紐づかない日次タスクは generate の対象外なので、件数判定には含めない
        const initialVisitPlans = fetchedPlans.filter((plan) => plan.category === "visit");
        // 生成が既に(別ページにいた間も含めて)裏側で走っている場合は、まだ結果が
        // DBに反映されていないだけなので「未生成」扱いに巻き戻さない
        const alreadyGenerating =
          initialPlanGenerationKey !== null && initialPlanGeneration.isGenerating(initialPlanGenerationKey);
        setNeedsInitialPlan(initialVisitPlans.length === 0 && !alreadyGenerating);

        // 自己分析スコアは計算済みのキャッシュなので、表示前に最新の結果を反映させておく
        await recalculateRepAffinity(rid);
        const [fetchedAffinities, fetchedDeals, fetchedCustomers, fetchedTerritory] = await Promise.all([
          fetchRepAffinity(rid),
          fetchDeals({ repId: rid }),
          fetchCustomers(rid),
          fetchRepTerritory(rid),
        ]);
        if (cancelled) return;

        setTarget(
          fetchedTarget ?? {
            rep_id: rid,
            target_month: TARGET_MONTH,
            target_amount: 0,
            target_deal_count: 0,
            target_gross_profit: null,
          },
        );
        setPlans(initialVisitPlans);
        setDailyTasks(fetchedPlans.filter((plan) => plan.category === "task"));
        setAffinities(fetchedAffinities);
        setDeals(fetchedDeals);
        setCustomers(fetchedCustomers);
        setTerritory(fetchedTerritory);
        await refreshForecast(rid);
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
  }, [repId]);

  // 初回AI生成は「目標保存→別ページへ移動→生成完了を待たずに/activityへ戻る」のように
  // 元のフックインスタンスとは別のマウントで完了を迎えることがある。生成中フラグが
  // true→falseに変わったタイミングで、今見えているインスタンス側でも最新の計画を
  // 取り直す(自分自身が生成した場合はgenerateInitialPlan内で既にsetPlans済みだが、
  // 二重取得しても実害はない)。
  const wasGeneratingInitialPlanRef = useRef(isGeneratingInitialPlan);
  useEffect(() => {
    const wasGenerating = wasGeneratingInitialPlanRef.current;
    wasGeneratingInitialPlanRef.current = isGeneratingInitialPlan;
    if (!wasGenerating || isGeneratingInitialPlan || repId === null) return;
    const rid = repId;
    (async () => {
      const fresh = await fetchActivityPlans(rid);
      setPlans(fresh.filter((plan) => plan.category === "visit"));
      setDailyTasks(fresh.filter((plan) => plan.category === "task"));
      await refreshForecast(rid);
    })();
  }, [isGeneratingInitialPlan, repId]);

  async function handleTargetSave(input: {
    target_amount: number;
    target_deal_count: number;
    target_gross_profit: number | null;
  }) {
    if (repId === null) return;
    const rid = repId;
    const updated = await saveSalesTarget(rid, TARGET_MONTH, input);
    setTarget(updated);
    await refreshForecast(rid);

    // 目標保存はここで完了させ(GoalCard側の「保存中...」を即座に終える)、
    // まだ計画が無い月の初回AI生成は裏側で別途走らせる(数分かかり得るため)。
    // ページ遷移をまたいでも生成中フラグが残るので、既に走っている生成に対して
    // 二重に発火することはない(isGeneratingInitialPlanがtrueならneedsInitialPlanは
    // falseになっている)。
    if (needsInitialPlan && !isGeneratingInitialPlan) {
      void generateInitialPlan(rid);
    }
  }

  async function generateInitialPlan(rid: number) {
    const key = `${rid}:${TARGET_MONTH}`;
    initialPlanGeneration.setGenerating(key, true);
    try {
      const generated = await generateActivityPlans(rid, TARGET_MONTH);
      setPlans(generated.filter((plan) => plan.category === "visit"));
      setDailyTasks(generated.filter((plan) => plan.category === "task"));
      setNeedsInitialPlan(false);
      await refreshForecast(rid);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "計画生成に失敗しました");
    } finally {
      initialPlanGeneration.setGenerating(key, false);
    }
  }

  async function handleRegenerate() {
    if (repId === null || !target) return;
    const rid = repId;
    setIsRegenerating(true);
    try {
      const before = calcAchievementRate(plans, target.target_amount, deals);
      const fresh = await generateActivityPlans(rid, TARGET_MONTH);
      const freshVisits = fresh.filter((plan) => plan.category === "visit");
      const after = calcAchievementRate(freshVisits, target.target_amount, deals);
      setPlans(freshVisits);
      setDailyTasks(fresh.filter((plan) => plan.category === "task"));
      setReplan({
        before_achievement_rate: before,
        after_achievement_rate: after,
        target_amount: target.target_amount,
        after_forecast_amount: calcForecastAmount(freshVisits, deals),
        reason: "手動でAIに残り期間の計画を組み直してもらいました",
      });
      await refreshForecast(rid);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "計画生成に失敗しました");
    } finally {
      setIsRegenerating(false);
    }
  }

  async function handleResultChange(planId: number, status: DealResultStatus, activityTypeName: string) {
    const changedPlan = plans.find((plan) => plan.plan_id === planId);
    if (!changedPlan || !target || repId === null) return;

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
        await deleteActivityResult(repId, resultId);
        if (status === "won" || status === "lost") {
          // 成約/失注の取り消しは自己分析スコアにも影響するため、最新値を取り直す
          await recalculateRepAffinity(repId);
          setAffinities(await fetchRepAffinity(repId));
        }
        await refreshForecast(repId);
        setRouteRefreshRevision((revision) => revision + 1);
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

    // 「対応が難しい」で差し替えたローカル専用の計画には実在する deal_id が無いため、
    // バックエンドへは送信せず表示のみ更新する
    if (!changedPlan.deal_id) {
      setPlans(updatedPlans);
      return;
    }

    const beforeReplanRate = calcAchievementRate(updatedPlans, target.target_amount, deals);
    try {
      const result = await postActivityResult(
        repId,
        changedPlan,
        status as Exclude<DealResultStatus, "pending">,
        activityTypeName,
      );
      setResultIdByPlan((prev) => ({ ...prev, [planId]: result.result_id }));
      // DBへの結果保存後に表示へ反映する。これにより月間ルートの再計算も、失注前の
      // 古いdeal状態ではなく保存済みの状態を必ず参照する。
      setPlans(updatedPlans);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "結果の登録に失敗しました");
      return;
    }

    if (status !== "won" && status !== "lost") {
      await refreshForecast(repId);
      setRouteRefreshRevision((revision) => revision + 1);
      return;
    }

    setIsRegenerating(true);
    try {
      // create_resultでwon/lostになった商談は候補SQLから除外される。再計画は未来の
      // AI予定だけを削除して、残った進行中案件と事務作業から組み直す。
      await replanActivityPlans(repId, TARGET_MONTH);
      const [fetchedPlans, fetchedDeals, fetchedAffinities] = await Promise.all([
        fetchActivityPlans(repId),
        fetchDeals({ repId }),
        fetchRepAffinity(repId),
      ]);
      // 再計画のfetchActivityPlansがDBの最新状態を返すまでの間、この画面で既に
      // 確定している結果を先に反映しておく(取得結果と一致すれば上書きは実質no-op)。
      const resultStatusByPlanId = new Map(
        updatedPlans.map((plan) => [plan.plan_id, plan.result_status]),
      );
      const replanned = fetchedPlans.map((plan) => ({
        ...plan,
        result_status: resultStatusByPlanId.get(plan.plan_id) ?? plan.result_status,
      }));
      const replannedVisits = replanned.filter((plan) => plan.category === "visit");
      setPlans(replannedVisits);
      setDailyTasks(replanned.filter((plan) => plan.category === "task"));
      setDeals(fetchedDeals);
      setAffinities(fetchedAffinities);

      const customerName = changedPlan.customer_name;
      const isLost = status === "lost";
      const afterForecastAmount = calcForecastAmount(replannedVisits, fetchedDeals);
      setReplan({
        before_achievement_rate: beforeReplanRate,
        after_achievement_rate: calcAchievementRate(
          replannedVisits,
          target.target_amount,
          fetchedDeals,
        ),
        target_amount: target.target_amount,
        after_forecast_amount: afterForecastAmount,
        outcome: status,
        reason: isLost
          ? `${customerName}の失注を反映し、月末目標の不足分を補うようAIが計画を組み直しました。`
          : `${customerName}の成約を反映し、減った残目標に合わせて将来計画を整理しました。`,
        steps: isLost
          ? [
              "失注案件の期待売上・期待粗利を0円として残目標を再計算",
              "失注案件に紐づく将来のAI訪問・フォロー予定を除外",
              "不足分を補える別案件を売上・粗利・成約確度から再選定",
              "空いた時間へ代替案件の訪問や事務作業を配置",
            ]
          : [
              "成約金額・粗利を実績に反映して残目標を減額",
              "目標に対して余分になった将来のAI訪問を整理",
              "空いた時間へ別案件のフォローや事務作業を配置",
            ],
        changes: diffFuturePlans(updatedPlans, replannedVisits),
      });
    } catch (error) {
      // 結果登録は既に成功しているのでロールバックしない。月間ルート側はこの後の
      // refresh revisionで、保存済み結果を使った既存ルール＋LLM再計画を試行できる。
      setLoadError(
        error instanceof Error
          ? `結果は登録しましたが、活動計画の自動再生成に失敗しました: ${error.message}`
          : "結果は登録しましたが、活動計画の自動再生成に失敗しました",
      );
    } finally {
      setIsRegenerating(false);
      await refreshForecast(repId);
      setRouteRefreshRevision((revision) => revision + 1);
    }
  }

  // 「対応が難しい」と同じパターン(新しい予定を作って元をキャンセル)。結果として
  // 記録すると「取り消す」操作が生え、取り消すと延期先と重複してしまうため避けている。
  async function handlePostpone(planId: number, newDate: string, activityTypeName: string) {
    const changedPlan = plans.find((plan) => plan.plan_id === planId);
    if (!changedPlan || repId === null) return;

    try {
      const created = await createPlan(repId, {
        plan_date: newDate,
        start_time: changedPlan.start_time,
        end_time: changedPlan.end_time,
        category: changedPlan.category,
        activity_type: activityTypeName,
        customer_id: changedPlan.customer_id,
        deal_id: changedPlan.deal_id,
        priority: changedPlan.priority,
        expected_amount: changedPlan.expected_amount,
        expected_probability: changedPlan.expected_probability,
        rationale: `${changedPlan.plan_date}の予定を延期`,
      });
      await cancelPlan(repId, planId);

      const rescheduled: ActivityPlan = {
        ...changedPlan,
        plan_id: created.plan_id,
        plan_date: newDate,
        activity_type_name: activityTypeName,
        is_ai_generated: false,
        reasoning_text: `${changedPlan.plan_date}の予定を延期`,
        result_status: "pending",
        memo: null,
        progress_percent: 0,
      };
      setPlans((prev) => prev.filter((plan) => plan.plan_id !== planId).concat(rescheduled));
      await refreshForecast(repId);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "延期の処理に失敗しました");
    }
  }

  async function handleEditPlan(planId: number, updates: PlanEditFields) {
    if (repId === null) return;
    const targetPlan = [...plans, ...dailyTasks].find((plan) => plan.plan_id === planId);
    if (!targetPlan) return;

    const previousPlans = plans;
    const previousTasks = dailyTasks;
    const updated: ActivityPlan = { ...targetPlan, ...updates };

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
      await updatePlan(repId, planId, updates);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "予定の更新に失敗しました");
      setPlans(previousPlans);
      setDailyTasks(previousTasks);
    }
  }

  async function handleAddPlan(newPlan: ActivityPlan) {
    if (repId === null) return;
    try {
      const created = await createManualPlan(repId, {
        plan_date: newPlan.plan_date,
        start_time: newPlan.start_time,
        end_time: newPlan.end_time,
        category: newPlan.category,
        activity_type_name: newPlan.activity_type_name,
        customer_name: newPlan.customer_name,
        customer_id: newPlan.customer_id,
        deal_id: newPlan.deal_id,
        priority: newPlan.priority,
        product_name: newPlan.product_name,
        expected_amount: newPlan.expected_amount,
        expected_probability: newPlan.expected_probability,
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
    if (repId === null) return;
    try {
      await updatePlanProgress(repId, planId, percent);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "進捗の保存に失敗しました");
    }
  }

  // 候補の計算のみ行う。確定はconfirmAlternativeで、まだ何も送信しない
  function handleRequestAlternative(planId: number) {
    const changedPlan = plans.find((plan) => plan.plan_id === planId) ?? dailyTasks.find((task) => task.plan_id === planId);
    if (!changedPlan) return;
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
      setAltPreview({
        kind: "task",
        planId,
        foundInPlans,
        changedPlan,
        label: candidateTask.title,
        candidateTask,
      });
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
    setAltPreview({
      kind: "deal",
      planId,
      changedPlan,
      label: `${candidateDeal.customer_name}(${candidateDeal.product_name})`,
      candidateDeal,
    });
  }

  function cancelAlternativePreview() {
    setAltPreview(null);
  }

  async function confirmAlternative() {
    if (!altPreview || !target || repId === null) return;
    const preview = altPreview;
    setAltPreview(null);
    const { planId, changedPlan } = preview;

    if (preview.kind === "task") {
      const { candidateTask, foundInPlans } = preview;
      try {
        // 差し替え候補を実在の予定として登録し元の予定は取り消す(どちらもバックエンドに反映。
        // 以前はローカル専用の plan_id しか持たず、リロードすると消えていた)。
        const created = await createPlan(repId, {
          plan_date: changedPlan.plan_date,
          category: "task",
          activity_type: candidateTask.activityTypeName,
          customer_id: null,
          deal_id: null,
          priority: changedPlan.priority,
          title: candidateTask.title,
          rationale: candidateTask.reasoningText,
        });
        await cancelPlan(repId, planId);

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
          is_draft: false,
        };

        if (foundInPlans) {
          setPlans((prev) => prev.filter((plan) => plan.plan_id !== planId).concat(candidate));
        } else {
          setDailyTasks((prev) => prev.filter((task) => task.plan_id !== planId).concat(candidate));
        }
        setReplan({
          before_achievement_rate: calcAchievementRate(plans, target.target_amount, deals),
          after_achievement_rate: calcAchievementRate(plans, target.target_amount, deals),
          target_amount: target.target_amount,
          after_forecast_amount: calcForecastAmount(plans, deals),
          reason: `${changedPlan.customer_name}への対応が難しいとのことなので、AIが「${candidate.customer_name}」に差し替えました`,
        });
      } catch (error) {
        setLoadError(error instanceof Error ? error.message : "予定の差し替えに失敗しました");
      }
      return;
    }

    const { candidateDeal } = preview;
    const reasoningText = `対応が難しいとのことなので、進行中の商談「${candidateDeal.product_name}」(${candidateDeal.customer_name}様)への提案に差し替えました。`;

    try {
      // 差し替え候補を本物の予定として登録し、元の予定は取り消す(どちらもバックエンドに反映)。
      // 以前はローカル専用の仮 plan_id(900000+deal_id)を使っていたため、結果を記録しようと
      // すると実在しない plan_id で外部キー違反になり得た。
      const created = await createPlan(repId, {
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
      await cancelPlan(repId, planId);

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
        is_draft: false,
      };

      const before = calcAchievementRate(plans, target.target_amount, deals);
      const nextPlans = plans.filter((plan) => plan.plan_id !== planId).concat(candidate);
      const after = calcAchievementRate(nextPlans, target.target_amount, deals);

      setPlans(nextPlans);
      setReplan({
        before_achievement_rate: before,
        after_achievement_rate: after,
        target_amount: target.target_amount,
        after_forecast_amount: calcForecastAmount(nextPlans, deals),
        reason: `${changedPlan.customer_name}への対応が難しいとのことなので、AIが${candidate.customer_name}への提案に差し替えました`,
      });
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "計画の差し替えに失敗しました");
    }
  }

  // バックエンドの forecast は成約/失注の実績まで反映した正確な値。
  // 目標(sales_target)が未登録の月は 404 になるため、その場合だけクライアント計算に
  // フォールバックする
  const forecastAmount = forecast ? forecast.forecast_amount : calcForecastAmount(plans, deals);
  const achievementRate = forecast
    ? forecast.achievement_rate
    : target
      ? calcAchievementRate(plans, target.target_amount, deals)
      : 0;

  // 見込み粗利。バックエンドのforecastが粗利も返すようになったので、
  // そちらを優先し、未登録月のフォールバックのみクライアント計算を使う
  const forecastProfitAmount = forecast ? forecast.forecast_profit_amount : calcForecastProfit(plans, deals);

  // 達成"確率"(モンテカルロシミュレーション)。フォールバック計算を持たないため、
  // forecastが無い(目標未登録)月は「算出不可」として0%扱いにする
  const salesAchievementProbability = forecast ? forecast.sales_achievement_probability : 0;
  const profitAchievementProbability = forecast ? forecast.profit_achievement_probability : null;
  const jointAchievementProbability = forecast ? forecast.joint_achievement_probability : 0;

  // 「現在の実績」は成約(won)確定分のみの金額。バックエンドのforecastには
  // 見込み(未対応・延期分含む)しか無いため、常にplansから算出する
  const actualAchievedAmount = calcActualAchievedAmount(plans, deals);
  const actualAchievementRate = target ? calcActualAchievementRate(plans, target.target_amount, deals) : 0;

  return {
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
    dismissReplan: () => setReplan(null),
    altNotice,
    altPreview,
    isRegenerating,
    needsInitialPlan,
    isGeneratingInitialPlan,
    forecastAmount,
    achievementRate,
    forecastProfitAmount,
    salesAchievementProbability,
    profitAchievementProbability,
    jointAchievementProbability,
    actualAchievedAmount,
    actualAchievementRate,
    routeRefreshRevision,
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
  };
}
