"use client";

import { useEffect, useRef, useState } from "react";
import {
  approveSalesRoutePlan,
  previewSalesRouteBatch,
  rejectSalesRoutePlan,
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
import type { RoutePlanBatchPreview, RoutePlanPreview, RoutePlanWeek } from "@/types";

type Props = {
  onApproved: () => Promise<void>;
  // Bumped by the dashboard whenever a 商談結果 changes (won/lost/postponed/
  // etc.), so this panel's month/week numbers stay in sync with the day-level
  // plan's own auto-replan instead of only updating when the user clicks the
  // generate button again.
  refreshSignal?: number;
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
  const salesTarget = batch.monthly_target_amount ?? 0;
  const projectedSales = batch.achieved_amount + batch.portfolio_expected_sales;
  const salesRate = salesTarget > 0 ? (projectedSales / salesTarget) * 100 : null;
  const salesGap = Math.max(0, salesTarget - projectedSales);

  const profitTarget = batch.monthly_target_gross_profit;
  const projectedProfit = batch.achieved_gross_profit + (batch.totals.expected_gross_profit ?? 0);
  const profitRate =
    profitTarget !== null && profitTarget > 0 ? (projectedProfit / profitTarget) * 100 : null;
  const profitGap = Math.max(0, (profitTarget ?? 0) - projectedProfit);
  const expectedTargetsMet =
    salesRate !== null && salesRate >= 100 && (profitRate === null || profitRate >= 100);
  const jointProbability =
    batch.joint_achievement_probability <= 1
      ? batch.joint_achievement_probability * 100
      : batch.joint_achievement_probability;

  const outlook = expectedTargetsMet
    ? jointProbability >= 60
      ? {
          level: "good",
          label: "達成見込みは良好",
          message: "期待値と商談確度の両面で、月末目標の達成圏内です。",
        }
      : {
          level: "watch",
          label: "金額は達成圏内・確度に注意",
          message: "期待着地は目標以上ですが、成約確度を踏まえると継続フォローが必要です。",
        }
    : {
        level: "risk",
        label: "追加の補填が必要",
        message: `期待値では${[
          salesGap > 0 ? `売上${yen(salesGap)}` : null,
          profitGap > 0 ? `粗利${yen(profitGap)}` : null,
        ].filter(Boolean).join("・")}が不足する見込みです。`,
      };

  return (
    <section className={`monthly-outlook monthly-outlook--${outlook.level}`}>
      <div className="monthly-outlook__heading">
        <div>
          <small>この月間計画の総合判定</small>
          <strong>{outlook.label}</strong>
        </div>
        <div className="monthly-outlook__probability">
          <span>{jointProbability.toFixed(0)}%</span>
          <small>売上・粗利の同時達成確率</small>
        </div>
      </div>
      <p>{outlook.message}</p>
      <div className="monthly-outlook__metrics">
        <div>
          <span><strong>売上 {salesRate?.toFixed(0) ?? "—"}%</strong><small>{yen(projectedSales)} / {yen(salesTarget)}</small></span>
          <progress max={100} value={Math.min(salesRate ?? 0, 100)} />
        </div>
        {profitTarget !== null && (
          <div>
            <span><strong>粗利 {profitRate?.toFixed(0) ?? "—"}%</strong><small>{yen(projectedProfit)} / {yen(profitTarget)}</small></span>
            <progress max={100} value={Math.min(profitRate ?? 0, 100)} />
          </div>
        )}
      </div>
      <small className="monthly-outlook__note">
        期待着地は、成約済み実績と今回の計画に含まれる顧客の期待値を合算しています。
      </small>
    </section>
  );
}

export function RouteBatchPlanPanel({ onApproved, refreshSignal }: Props) {
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
  const [calculatingWeek, setCalculatingWeek] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
    setDecisions({});
    setWeekBatches({});
    try {
      setBatch(
        await previewSalesRouteBatch({
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
          break_start: "12:00",
          break_end: "13:00",
          turnaround_buffer_min: 20,
          travel_time_buffer_percent: 20,
          access_buffer_min: 10,
          return_buffer_min: 30,
        }),
      );
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
      setError(`第${week.week_number}週には月間最適化で割り当てられた訪問候補がありません。`);
      return;
    }

    setCalculatingWeek(week.week_number);
    setError(null);
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
        break_start: "12:00",
        break_end: "13:00",
        turnaround_buffer_min: 20,
        travel_time_buffer_percent: 20,
        access_buffer_min: 10,
        return_buffer_min: 30,
      });
      setWeekBatches((current) => ({ ...current, [week.week_number]: result }));
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : `第${week.week_number}週の計算に失敗しました`,
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
              <span>計算済み {Object.keys(weekBatches).length}/{batch.weeks.length}週</span>
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
              const isCalculated = calculatedBatch !== undefined;
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
                    期待売上 {yen(week.expected_sales)}・訪問{week.visit_count}件・
                    達成見込み{Math.round(week.attainment_rate * 100)}%
                  </span>
                </summary>
                <div className="route-plan-batch__week-body">
                  <div className="route-plan__actions">
                    <button
                      type="button"
                      className="goal-card__save"
                      onClick={() => calculateWeek(outlineWeek)}
                      disabled={busy || calculatingWeek !== null || assignedVisitCount === 0}
                    >
                      {calculatingWeek === outlineWeek.week_number
                        ? `第${outlineWeek.week_number}週を計算中…`
                        : isCalculated
                          ? `第${outlineWeek.week_number}週を再計算`
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
                      {week.deal_progress_goals.map((goal) => (
                        <li key={goal.deal_id ?? `new-${goal.customer_id}`}>
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
                            訪問{day.totals.visit_count}件
                          </span>
                        </summary>

                        <div className="route-plan-batch__day-body">
                          {day.plan_id === null ? (
                            <p className="route-plan-batch__day-empty">
                              {day.warnings[0] ?? "この日の営業先候補はありません。"}
                            </p>
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
