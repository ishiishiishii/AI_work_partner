"use client";

import { useEffect, useRef, useState } from "react";
import {
  approveIdleSalesRouteDay,
  approveSalesRoutePlan,
  previewSalesRouteBatch,
  rejectSalesRoutePlan,
  selectSalesRouteWeekAlternative,
} from "@/lib/api";
import {
  TRAVEL_MODE_LABELS,
  TransitItineraryDetails,
  clock,
  yen,
} from "@/components/dashboard/RoutePlanPanel";
import {
  ROUTE_ECONOMIC_POLICIES,
  routeEconomicPolicyConfig,
} from "@/lib/routeEconomicPolicy";
import { useRouteBatchPlan } from "@/lib/routeBatchPlanContext";
import { LUNCH_BREAK_END, LUNCH_BREAK_START } from "@/lib/workHours";
import type { ActivityPlan, RoutePlanBatchPreview, RoutePlanPreview, RoutePlanWeek } from "@/types";

type Props = {
  onApproved: () => Promise<void>;
  onPlanCalculated?: (batch: RoutePlanBatchPreview | null) => void;
  // Bumped by the dashboard whenever a 商談結果 changes (won/lost/postponed/
  // etc.), so this panel's month/week numbers stay in sync with the day-level
  // plan's own auto-replan instead of only updating when the user clicks the
  // generate button again.
  refreshSignal?: number;
  // その週の活動計画(DB上の確定データ)。ブラウザのlocalStorageに保存した
  // weekBatchesは容量超過等で失われることがあるため、リロード直後で
  // weekBatchesが空でも「activity_planに既にAI生成の訪問予定がある週」は
  // 「計算する」ではなく「再計算」として扱う判定に使う。
  existingPlans?: ActivityPlan[];
};

function dayLabel(dateStr: string): string {
  const date = new Date(`${dateStr}T00:00:00+09:00`);
  return new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo",
    month: "numeric",
    day: "numeric",
    weekday: "short",
  }).format(date);
}

function MonthlyPlanOutlook({ batch }: { batch: RoutePlanBatchPreview }) {
  // PostgreSQL Decimal values may arrive through the API as JSON strings.
  // Convert both operands explicitly so `+` performs arithmetic rather than
  // concatenating values such as "2230000" + "46484836".
  const projectedSales =
    Number(batch.achieved_amount) +
    Number(batch.existing_plan_expected_sales) +
    Number(batch.portfolio_expected_sales);
  const projectedProfit =
    Number(batch.achieved_gross_profit) +
    Number(batch.existing_plan_expected_gross_profit) +
    Number(batch.totals.expected_gross_profit ?? 0);

  return (
    <section className="monthly-outlook" aria-label="月間計画の予想金額">
      <div className="monthly-outlook__metrics">
        <div>
          <small>予想売上</small>
          <strong>{yen(projectedSales)}</strong>
        </div>
        <div>
          <small>予想粗利</small>
          <strong>{yen(projectedProfit)}</strong>
        </div>
      </div>
    </section>
  );
}

export function RouteBatchPlanPanel({
  onApproved,
  onPlanCalculated,
  refreshSignal,
  existingPlans = [],
}: Props) {
  const {
    selectedMonth,
    setSelectedMonth,
    policy,
    setPolicy,
    maxVisits,
    setMaxVisits,
    travelMode,
    setTravelMode,
    batch,
    setBatch,
    weekBatches,
    setWeekBatches,
    decisions,
    setDecisions,
  } = useRouteBatchPlan();
  const [alternativeReasons, setAlternativeReasons] = useState<Record<number, string>>({});
  const [calculatingWeek, setCalculatingWeek] = useState<number | null>(null);
  const [idleDayDecisions, setIdleDayDecisions] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [weekErrors, setWeekErrors] = useState<Record<number, string>>({});
  const economicPolicy = routeEconomicPolicyConfig(policy);
  const salesWeightPercent = economicPolicy.salesWeightPercent;
  const grossProfitWeightPercent = 100 - salesWeightPercent;
  const isFirstRefreshSignal = useRef(true);

  useEffect(() => {
    if (isFirstRefreshSignal.current) {
      isFirstRefreshSignal.current = false;
      return;
    }
    // Only re-run if a preview already exists -- a deal-result change
    // shouldn't trigger the first, unrequested API call for this panel.
    if (batch) {
      void createMonthOutline();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshSignal]);

  async function createMonthOutline() {
    if (!/^\d{4}-\d{2}$/.test(selectedMonth)) {
      setError("計画対象月を選択してください");
      return;
    }
    setBusy(true);
    setError(null);
    setWeekErrors({});
    setDecisions({});
    setIdleDayDecisions({});
    setWeekBatches({});
    setAlternativeReasons({});
    onPlanCalculated?.(null);
    try {
      const result = await previewSalesRouteBatch({
          start_date: `${selectedMonth}-01`,
          horizon: "month",
          outline_only: true,
          detailed_days: 0,
          policy,
          sales_weight_percent: salesWeightPercent,
          gross_profit_weight_percent: grossProfitWeightPercent,
          max_visits: maxVisits,
          travel_mode: travelMode,
          start_location: { kind: "branch" },
          end_location: { kind: "branch" },
          search_area: { kind: "auto" },
          break_enabled: true,
          break_start: LUNCH_BREAK_START,
          break_end: LUNCH_BREAK_END,
          turnaround_buffer_min: 20,
          travel_time_buffer_percent: 20,
          access_buffer_min: 10,
          return_buffer_min: 30,
        });
      setBatch(result);
      onPlanCalculated?.(result);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "月間営業スケジュールの作成に失敗しました");
    } finally {
      setBusy(false);
    }
  }

  async function calculateWeek(week: RoutePlanWeek) {
    if (!batch) return;
    const portfolioAssignments = batch.selected_customers
      .map((customer) => ({
        customer_id: customer.customer_id,
        visit_count: customer.assigned_dates.filter(
          (assignedDate) => assignedDate >= week.start_date && assignedDate <= week.end_date,
        ).length,
      }))
      .filter((assignment) => assignment.visit_count > 0);
    if (portfolioAssignments.length === 0) {
      setWeekErrors((prev) => ({
        ...prev,
        [week.week_number]: `第${week.week_number}週には月間最適化で割り当てられた訪問候補がありません。`,
      }));
      return;
    }

    setCalculatingWeek(week.week_number);
    setWeekErrors((prev) => {
      const { [week.week_number]: _removed, ...rest } = prev;
      return rest;
    });
    try {
      const economicsWeightTotal = batch.weights.sales + batch.weights.gross_profit;
      const monthlySalesWeightPercent =
        economicsWeightTotal > 0
          ? Math.round((batch.weights.sales / economicsWeightTotal) * 100)
          : salesWeightPercent;
      const result = await previewSalesRouteBatch({
        start_date: week.start_date,
        end_date: week.end_date,
        horizon: "week",
        detailed_days: week.days.length,
        portfolio_assignments: portfolioAssignments,
        target_amount_override: week.target_amount,
        target_gross_profit_override: week.target_gross_profit,
        policy: batch.policy,
        sales_weight_percent: monthlySalesWeightPercent,
        gross_profit_weight_percent: 100 - monthlySalesWeightPercent,
        max_visits: maxVisits,
        travel_mode: travelMode,
        start_location: { kind: "branch" },
        end_location: { kind: "branch" },
        search_area: { kind: "auto" },
        break_enabled: true,
        break_start: LUNCH_BREAK_START,
        break_end: LUNCH_BREAK_END,
        turnaround_buffer_min: 20,
        travel_time_buffer_percent: 20,
        access_buffer_min: 10,
        return_buffer_min: 30,
      });
      setWeekBatches((current) => ({ ...current, [week.week_number]: result }));
      // previewSalesRouteBatch は下書き(plan_status='draft')の活動計画も同じ
      // リクエスト内でDBへ即時反映するため、ダッシュボード側の活動計画一覧を
      // 明示的に再取得しないと画面には反映されない(次のリロードまで表示が古いまま
      // になってしまう)。approveDay と同じ再取得を呼んでおく。
      await onApproved();
    } catch (requestError) {
      setWeekErrors((prev) => ({
        ...prev,
        [week.week_number]:
          requestError instanceof Error
            ? requestError.message
            : `第${week.week_number}週の計算に失敗しました`,
      }));
    } finally {
      setCalculatingWeek(null);
    }
  }

  async function showWeekAlternative(weekNumber: number) {
    const calculatedBatch = weekBatches[weekNumber];
    if (!calculatedBatch) return;
    const planIds = calculatedBatch.days
      .map((day) => day.plan_id)
      .filter((planId): planId is number => planId !== null && decisions[planId] === undefined);
    if (planIds.length === 0) {
      setError(`第${weekNumber}週には別案へ切り替えられる未採用の予定がありません。`);
      return;
    }

    setCalculatingWeek(weekNumber);
    setError(null);
    try {
      const alternative = await selectSalesRouteWeekAlternative(planIds);
      const updatedDays = calculatedBatch.days.map((day) => {
        if (day.plan_id !== alternative.change.plan_id) return day;
        const expectedSales = alternative.change.totals.expected_sales;
        return {
          ...day,
          totals: alternative.change.totals,
          stops: alternative.change.stops,
          shortfall_amount: Math.max(0, day.target_amount - expectedSales),
          attainment_rate: day.target_amount > 0 ? expectedSales / day.target_amount : 0,
        };
      });
      const expectedSales = updatedDays.reduce((sum, day) => sum + day.totals.expected_sales, 0);
      const expectedGrossProfit = updatedDays.reduce(
        (sum, day) => sum + (day.totals.expected_gross_profit ?? 0),
        0,
      );
      const visitCount = updatedDays.reduce((sum, day) => sum + day.totals.visit_count, 0);
      const updatedWeeks = calculatedBatch.weeks.map((week, index) =>
        index === 0
          ? {
              ...week,
              days: updatedDays,
              expected_sales: expectedSales,
              expected_gross_profit: expectedGrossProfit,
              visit_count: visitCount,
              shortfall_amount: Math.max(0, week.target_amount - expectedSales),
              attainment_rate: week.target_amount > 0 ? expectedSales / week.target_amount : 0,
            }
          : week,
      );
      setWeekBatches((current) => ({
        ...current,
        [weekNumber]: {
          ...calculatedBatch,
          days: updatedDays,
          weeks: updatedWeeks,
          totals: {
            ...calculatedBatch.totals,
            planned_sales: updatedDays.reduce(
              (sum, day) => sum + day.totals.planned_sales,
              0,
            ),
            planned_gross_profit: updatedDays.reduce(
              (sum, day) => sum + (day.totals.planned_gross_profit ?? 0),
              0,
            ),
            expected_sales: expectedSales,
            expected_gross_profit: expectedGrossProfit,
            total_travel_min: updatedDays.reduce(
              (sum, day) => sum + day.totals.total_travel_min,
              0,
            ),
            total_distance_m: updatedDays.reduce(
              (sum, day) => sum + day.totals.total_distance_m,
              0,
            ),
            visit_count: visitCount,
          },
        },
      }));
      setAlternativeReasons((current) => ({ ...current, [weekNumber]: alternative.reason }));
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : `第${weekNumber}週の別案取得に失敗しました`,
      );
    } finally {
      setCalculatingWeek(null);
    }
  }

  async function approveDay(planId: number) {
    setBusy(true);
    setError(null);
    try {
      await approveSalesRoutePlan(planId);
      setDecisions((prev) => ({ ...prev, [planId]: "approved" }));
      await onApproved();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "承認に失敗しました");
    } finally {
      setBusy(false);
    }
  }

  async function approveIdleDay(batchId: number, targetDate: string) {
    setBusy(true);
    setError(null);
    try {
      const result = await approveIdleSalesRouteDay(batchId, targetDate);
      setIdleDayDecisions((current) => ({
        ...current,
        [targetDate]: result.summary,
      }));
      await onApproved();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "商談なし日の予定採用に失敗しました",
      );
    } finally {
      setBusy(false);
    }
  }

  async function rejectDay(planId: number) {
    setBusy(true);
    setError(null);
    try {
      await rejectSalesRoutePlan(planId);
      setDecisions((prev) => ({ ...prev, [planId]: "rejected" }));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "却下に失敗しました");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel route-plan">
      <h2>月間営業スケジュール</h2>
      <p>
        先に対象月の週数と月間顧客ポートフォリオを確定し、その月全体の売上・粗利を
        最大化する方針を保ったまま、必要な週だけ詳細ルートを計算します。
      </p>
      <div className="route-plan__controls">
        <label>
          計画対象月
          <input
            type="month"
            value={selectedMonth}
            onChange={(event) => setSelectedMonth(event.target.value)}
            required
          />
        </label>
        <label>
          移動手段
          <select value={travelMode} onChange={(event) => setTravelMode(event.target.value as RoutePlanPreview["travel_mode"])}>
            <option value="driving">車</option>
            <option value="transit">公共交通（徒歩＋電車・バス）</option>
            <option value="walking">徒歩</option>
            <option value="cycling">自転車</option>
          </select>
        </label>
        <label>
          1日の最大訪問数
          <input type="number" min={1} max={10} value={maxVisits} onChange={(event) => setMaxVisits(Number(event.target.value))} />
        </label>
      </div>
      <small>
        月を設計する段階では移動ルートを計算しません。月間候補と週配分を確認してから、各週を個別に計算できます。
      </small>

      <fieldset className="route-plan__group">
        <legend>売上・粗利の考え方</legend>
        <div className="route-plan__policy-options">
          {ROUTE_ECONOMIC_POLICIES.map((option) => (
            <label
              key={option.value}
              className={`route-plan__policy-option${policy === option.value ? " is-selected" : ""}`}
            >
              <input
                type="radio"
                name="batch-economic-policy"
                value={option.value}
                checked={policy === option.value}
                onChange={() => setPolicy(option.value)}
              />
              <strong>{option.label}</strong>
              <small>{option.description}</small>
            </label>
          ))}
        </div>
        <small>
          選択した方針を月間顧客選定・週計算・エラー発生後のLLM再計画まで引き継ぎます。
        </small>
      </fieldset>

      <button type="button" className="regenerate-button" onClick={createMonthOutline} disabled={busy || calculatingWeek !== null}>
        {busy ? "月の顧客・週配分を計算中…" : batch ? "月の設計を作り直す" : "月の設計を作る"}
      </button>

      {error && <p className="new-customer-form__error">{error}</p>}

      {batch && (
        <div className="route-plan__result">
          <p>
            {batch.start_date}〜{batch.end_date}・{batch.rep_name}・{batch.branch.branch_name}営業所
          </p>
          <MonthlyPlanOutlook batch={batch} />
          <div className="route-plan-batch__flow" aria-label="月、週、日の計画フロー">
            <article>
              <small>1. 月の逆算</small>
              <strong>{yen(batch.remaining_target_amount)}</strong>
              <span>
                月目標 {yen(batch.monthly_target_amount)}・開始日前までの成約済み {yen(batch.achieved_amount)}
              </span>
            </article>
            <article>
              <small>2. 顧客選択（ルール＋LLM）</small>
              <strong>{batch.selected_customers.length}社</strong>
              <span>
                新規{batch.selected_customers.filter((customer) => customer.customer_type === "new").length}社・
                商談中{batch.selected_customers.filter((customer) => customer.customer_type === "ongoing").length}社・
                商談{batch.selected_customers.reduce((total, customer) => total + customer.planned_visit_count, 0)}回・
                期待売上{yen(batch.portfolio_expected_sales)}（目標比{Math.round(batch.portfolio_coverage_rate * 100)}%）
              </span>
            </article>
            <article>
              <small>3. 週ごとに詳細計算</small>
              <strong>{batch.weeks.length}週・{batch.days.length}営業日</strong>
              <span>
                計算済み{" "}
                {
                  batch.weeks.filter(
                    (week) =>
                      weekBatches[week.week_number] !== undefined ||
                      existingPlans.some(
                        (plan) =>
                          plan.is_ai_generated &&
                          plan.plan_date >= week.start_date &&
                          plan.plan_date <= week.end_date,
                      ),
                  ).length
                }
                /{batch.weeks.length}週
              </span>
            </article>
          </div>

          <div className="route-plan__totals">
            <span>期間目標 {yen(batch.planning_target_amount)}</span>
            <span>月間ポートフォリオ期待売上 {yen(batch.totals.expected_sales)}</span>
            <span>月間ポートフォリオ期待粗利 {yen(batch.totals.expected_gross_profit)}</span>
            <span>月間割当 {batch.totals.visit_count}訪問</span>
          </div>
          <div className="route-plan-batch__weeks">
            {batch.weeks.map((outlineWeek) => {
              const calculatedBatch = weekBatches[outlineWeek.week_number];
              const week = calculatedBatch?.weeks[0] ?? outlineWeek;
              // weekBatches(localStorage経由で復元)がリロードで失われていても、
              // 活動計画側に既にAI生成の訪問予定が保存されていれば「計算済みの週」
              // として扱い、「計算する」ではなく「再計算」を表示する。
              const hasExistingPlans = existingPlans.some(
                (plan) =>
                  plan.is_ai_generated &&
                  plan.plan_date >= outlineWeek.start_date &&
                  plan.plan_date <= outlineWeek.end_date,
              );
              const isCalculated = calculatedBatch !== undefined || hasExistingPlans;
              const activeWarnings = calculatedBatch?.warnings ?? batch.warnings;
              const assignedVisitCount = batch.selected_customers.reduce(
                (count, customer) => count + customer.assigned_dates.filter(
                  (assignedDate) =>
                    assignedDate >= outlineWeek.start_date && assignedDate <= outlineWeek.end_date,
                ).length,
                0,
              );
              return (
              <details
                key={`${outlineWeek.start_date}-${outlineWeek.end_date}`}
                className="route-plan-batch__week"
                open={outlineWeek.week_number === 1}
              >
                <summary className="route-plan-batch__week-summary">
                  <span>第{outlineWeek.week_number}週</span>
                  <strong>週目標 {yen(outlineWeek.target_amount)}</strong>
                  <span>
                    期待売上 {yen(week.expected_sales)}・商談
                    {week.visit_count + week.days.reduce(
                      (sum, day) => sum + day.existing_visit_count,
                      0,
                    )}件・
                    達成見込み{Math.round(week.attainment_rate * 100)}%
                  </span>
                </summary>
                <div className="route-plan-batch__week-body">
                  <div className="route-plan__actions">
                    <button
                      type="button"
                      className="goal-card__save"
                      onClick={() =>
                        isCalculated
                          ? showWeekAlternative(outlineWeek.week_number)
                          : calculateWeek(outlineWeek)
                      }
                      disabled={busy || calculatingWeek !== null || assignedVisitCount === 0}
                    >
                      {calculatingWeek === outlineWeek.week_number
                        ? isCalculated
                          ? `第${outlineWeek.week_number}週の別案を選定中…`
                          : `第${outlineWeek.week_number}週を計算中…`
                        : isCalculated
                          ? `第${outlineWeek.week_number}週の別案を表示`
                          : `第${outlineWeek.week_number}週を計算`}
                    </button>
                    <span>
                      {isCalculated
                        ? "月間ポートフォリオを使った詳細ルート計算済み"
                        : assignedVisitCount > 0
                          ? `月間設計から${assignedVisitCount}訪問を引き継ぎます`
                          : "この週の訪問割り当てはありません"}
                    </span>
                  </div>
                  {alternativeReasons[outlineWeek.week_number] && (
                    <p className="route-plan__success">
                      AIが計算済み候補から選んだ別案：{alternativeReasons[outlineWeek.week_number]}
                    </p>
                  )}
                  {weekErrors[outlineWeek.week_number] && (
                    <p className="new-customer-form__error">{weekErrors[outlineWeek.week_number]}</p>
                  )}
                  <p>
                    {week.focus_is_ai_generated && (
                      <span className="route-plan-batch__badge route-plan-batch__badge--detailed">
                        AI
                      </span>
                    )}{" "}
                    {week.focus}
                  </p>
                  {week.deal_progress_goals.length > 0 && (
                    <ul className="route-plan-batch__progress-goals">
                      {week.deal_progress_goals.map((goal, goalIndex) => (
                        <li key={`${goal.deal_id ?? `new-${goal.customer_id}`}-${goalIndex}`}>
                          <strong>
                            {goal.customer_name}: {goal.current_phase_name} → {goal.target_phase_name}
                          </strong>
                          <br />
                          <small>{goal.rationale}</small>
                        </li>
                      ))}
                    </ul>
                  )}
                  {week.shortfall_amount > 0 && (
                    <p className="route-plan__warning">週目標まで {yen(week.shortfall_amount)} 不足する見込みです。</p>
                  )}
                  <div className="route-plan-batch__days">
                    {week.days.map((day) => (
                      <details key={day.target_date} className="route-plan-batch__day">
                        <summary className="route-plan-batch__day-summary">
                          <span className="route-plan-batch__day-date">{dayLabel(day.target_date)}</span>
                          <span className={`route-plan-batch__badge route-plan-batch__badge--${day.detail_level}`}>
                            {!isCalculated
                              ? "月間配分"
                              : day.detail_level === "detailed"
                                ? "詳細ルート"
                                : "概算"}
                          </span>
                          <span className="route-plan-batch__day-figures">
                            日目標{yen(day.target_amount)}・期待売上{yen(day.totals.expected_sales)}・
                            商談合計{day.existing_visit_count + day.totals.visit_count}件
                            （既存{day.existing_visit_count}・AI追加{day.totals.visit_count}）
                          </span>
                        </summary>

                        <div className="route-plan-batch__day-body">
                          {day.plan_id === null ? (
                            <div className="route-plan-batch__day-empty">
                              <p>{day.warnings[0] ?? "この日の営業先候補はありません。"}</p>
                              {day.existing_visit_count > 0 && (
                                <p>
                                  活動計画には既に商談が{day.existing_visit_count}件あります。
                                  ここでは重複訪問を追加せず、空き時間をAIが補完します。
                                </p>
                              )}
                              {idleDayDecisions[day.target_date] ? (
                                <p className="route-plan__success">
                                  {idleDayDecisions[day.target_date]}
                                </p>
                              ) : day.detail_level === "detailed" ? (
                                <button
                                  type="button"
                                  className="goal-card__save"
                                  onClick={() =>
                                    approveIdleDay(calculatedBatch.batch_id, day.target_date)
                                  }
                                  disabled={busy || calculatingWeek !== null}
                                >
                                  この日の予定を採用（AIで空き時間補完）
                                </button>
                              ) : (
                                <small>週の詳細計算後に予定を採用できます。</small>
                              )}
                            </div>
                          ) : (
                            <>
                              <ol className="route-plan__stops">
                                {day.stops.map((stop) => (
                                  <li key={stop.customer_id}>
                                    <strong>
                                      {stop.estimated ? "概算 " : ""}
                                      {clock(stop.arrival_at)}–{clock(stop.departure_at)} {stop.customer_name}
                                    </strong>
                                    <span>
                                      {stop.economics.customer_type === "new" ? "新規" : "商談中"}・
                                      商談{stop.economics.visit_sequence}/{stop.economics.planned_visit_count}回目・
                                      前区間 {stop.leg_travel_min}分 / {(stop.leg_distance_m / 1000).toFixed(1)}km・
                                      案件期待売上 {yen(stop.economics.opportunity_expected_sales)}・
                                      今回の売上見込 {yen(stop.economics.expected_sales)}
                                    </span>
                                    <small>{stop.selection_reason}</small>
                                    {travelMode === "transit" && stop.leg_details && (
                                      <TransitItineraryDetails title="この訪問先まで" itinerary={stop.leg_details} />
                                    )}
                                  </li>
                                ))}
                              </ol>
                              {day.shortfall_amount > 0 && (
                                <p className="route-plan__warning">
                                  日目標まで {yen(day.shortfall_amount)} 不足するため、候補追加か週内での補完が必要です。
                                </p>
                              )}
                              {day.warnings
                                .filter((warning) => !activeWarnings.includes(warning))
                                .map((warning) => (
                                  <p className="route-plan__warning" key={warning}>{warning}</p>
                                ))}
                              {day.detail_level === "coarse" ? (
                                <p className="route-plan__warning">概算日のため、詳細ルートへ更新後に採用できます。</p>
                              ) : decisions[day.plan_id] === undefined ? (
                                <div className="route-plan__actions">
                                  <button
                                    type="button"
                                    className="goal-card__save"
                                    onClick={() => approveDay(day.plan_id as number)}
                                    disabled={busy || calculatingWeek !== null}
                                  >
                                    この日の予定を採用
                                  </button>
                                  <button
                                    type="button"
                                    className="goal-card__cancel"
                                    onClick={() => rejectDay(day.plan_id as number)}
                                    disabled={busy || calculatingWeek !== null}
                                  >
                                    却下
                                  </button>
                                </div>
                              ) : (
                                <p>
                                  {decisions[day.plan_id] === "approved"
                                    ? "活動予定へ保存しました。"
                                    : "この日の計画案を却下しました。"}
                                </p>
                              )}
                            </>
                          )}
                        </div>
                      </details>
                    ))}
                  </div>
                </div>
              </details>
              );
            })}
          </div>

          <small>
            日別計画の移動手段は{TRAVEL_MODE_LABELS[travelMode]}です。詳細ルートはGoogle Routes API
            {travelMode === "transit" ? "／ODPT + OpenTripPlanner" : ""}
            の実移動時間を利用しています。
          </small>
        </div>
      )}
    </section>
  );
}
