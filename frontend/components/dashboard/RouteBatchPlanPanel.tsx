"use client";

import { useState } from "react";
import {
  approveSalesRoutePlan,
  previewSalesRouteBatch,
  rejectSalesRoutePlan,
} from "@/lib/api";
import {
  TRAVEL_MODE_LABELS,
  TransitItineraryDetails,
  clock,
  tomorrowInTokyo,
  yen,
} from "@/components/dashboard/RoutePlanPanel";
import type { RoutePlanBatchPreview, RoutePlanPreview } from "@/types";

type Props = {
  onApproved: () => Promise<void>;
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

export function RouteBatchPlanPanel({ onApproved }: Props) {
  const [startDate, setStartDate] = useState(tomorrowInTokyo);
  const [policy, setPolicy] = useState<RoutePlanBatchPreview["policy"]>("balanced");
  const [salesWeightPercent, setSalesWeightPercent] = useState(50);
  const [maxVisits, setMaxVisits] = useState(4);
  const [travelMode, setTravelMode] = useState<RoutePlanPreview["travel_mode"]>("driving");
  const [startKind, setStartKind] = useState<"branch" | "custom">("branch");
  const [startAddress, setStartAddress] = useState("");
  const [endKind, setEndKind] = useState<"branch" | "custom">("branch");
  const [endAddress, setEndAddress] = useState("");
  const [areaKind, setAreaKind] = useState<"auto" | "custom">("auto");
  const [areaQuery, setAreaQuery] = useState("");
  const [areaRadiusKm, setAreaRadiusKm] = useState(5);
  const [breakEnabled, setBreakEnabled] = useState(true);
  const [breakStart, setBreakStart] = useState("12:00");
  const [breakEnd, setBreakEnd] = useState("13:00");
  const [batch, setBatch] = useState<RoutePlanBatchPreview | null>(null);
  const [decisions, setDecisions] = useState<Record<number, "approved" | "rejected">>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const grossProfitWeightPercent = 100 - salesWeightPercent;

  function changePolicy(nextPolicy: RoutePlanBatchPreview["policy"]) {
    setPolicy(nextPolicy);
    if (nextPolicy === "sales") setSalesWeightPercent(70);
    else if (nextPolicy === "gross_profit") setSalesWeightPercent(30);
    else setSalesWeightPercent(50);
  }

  async function createBatchPreview() {
    if (startKind === "custom" && !startAddress.trim()) {
      setError("スタート住所を入力してください");
      return;
    }
    if (endKind === "custom" && !endAddress.trim()) {
      setError("ゴール住所を入力してください");
      return;
    }
    if (areaKind === "custom" && !areaQuery.trim()) {
      setError("訪問エリアの区名または駅名を入力してください");
      return;
    }
    if (breakEnabled && breakStart >= breakEnd) {
      setError("休憩終了は休憩開始より後に設定してください");
      return;
    }
    setBusy(true);
    setError(null);
    setDecisions({});
    try {
      setBatch(
        await previewSalesRouteBatch({
          start_date: startDate,
          horizon: "month",
          // The integrated view promises a detailed route for every business
          // day. The backend clamps this to the actual days left in the month.
          detailed_days: 31,
          policy,
          sales_weight_percent: salesWeightPercent,
          gross_profit_weight_percent: grossProfitWeightPercent,
          max_visits: maxVisits,
          travel_mode: travelMode,
          start_location: {
            kind: startKind,
            ...(startKind === "custom" ? { address: startAddress } : {}),
          },
          end_location: {
            kind: endKind,
            ...(endKind === "custom" ? { address: endAddress } : {}),
          },
          search_area: {
            kind: areaKind,
            ...(areaKind === "custom"
              ? { query: areaQuery, radius_km: areaRadiusKm }
              : {}),
          },
          break_enabled: breakEnabled,
          break_start: breakStart,
          break_end: breakEnd,
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
        月の残目標から新規客と商談中の顧客を一緒に選び、必要な商談回数を
        週目標・日目標へ割り当てたうえで、各営業日の訪問順と時間を作成します。
      </p>
      <div className="route-plan__controls">
        <label>
          計画開始日
          <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        </label>
        <label>
          方針
          <select value={policy} onChange={(event) => changePolicy(event.target.value as RoutePlanBatchPreview["policy"])}>
            <option value="balanced">売上・粗利のバランス</option>
            <option value="sales">売上重視</option>
            <option value="gross_profit">粗利重視</option>
            <option value="short_travel">移動時間重視</option>
          </select>
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
        開始日から当月末までの営業日を対象にします。日ごとの期待売上条件は月目標から自動で配分されます。
      </small>

      <fieldset className="route-plan__group route-plan__balance">
        <legend>売上・粗利の重み</legend>
        <div className="route-plan__balance-values">
          <strong>売上 {salesWeightPercent}%</strong>
          <strong>粗利 {grossProfitWeightPercent}%</strong>
        </div>
        <input
          type="range"
          min={0}
          max={100}
          step={5}
          value={salesWeightPercent}
          aria-label="売上を重視する割合"
          onChange={(event) => setSalesWeightPercent(Number(event.target.value))}
        />
        <div className="route-plan__balance-scale" aria-hidden="true">
          <span>粗利重視</span>
          <span>バランス</span>
          <span>売上重視</span>
        </div>
      </fieldset>

      <fieldset className="route-plan__group">
        <legend>出発・帰着地点</legend>
        <div className="route-plan__controls">
          <label>
            スタート位置
            <select value={startKind} onChange={(event) => setStartKind(event.target.value as "branch" | "custom")}>
              <option value="branch">所属営業所（デフォルト）</option>
              <option value="custom">任意の住所</option>
            </select>
          </label>
          {startKind === "custom" && (
            <label>
              スタート住所
              <input value={startAddress} onChange={(event) => setStartAddress(event.target.value)} placeholder="例：東京都千代田区丸の内1丁目" required />
            </label>
          )}
          <label>
            ゴール位置
            <select value={endKind} onChange={(event) => setEndKind(event.target.value as "branch" | "custom")}>
              <option value="branch">所属営業所（デフォルト）</option>
              <option value="custom">任意の住所</option>
            </select>
          </label>
          {endKind === "custom" && (
            <label>
              ゴール住所
              <input value={endAddress} onChange={(event) => setEndAddress(event.target.value)} placeholder="例：東京都新宿区西新宿2丁目" required />
            </label>
          )}
        </div>
      </fieldset>

      <fieldset className="route-plan__group">
        <legend>訪問エリアの絞り込み</legend>
        <div className="route-plan__controls">
          <label>
            エリア指定
            <select value={areaKind} onChange={(event) => setAreaKind(event.target.value as "auto" | "custom")}>
              <option value="auto">出発地点周辺から自動探索</option>
              <option value="custom">区名・駅名を入力</option>
            </select>
          </label>
          {areaKind === "custom" && (
            <>
              <label>
                区名・駅名
                <input
                  value={areaQuery}
                  onChange={(event) => setAreaQuery(event.target.value)}
                  placeholder="例：新宿区、東京駅"
                  required
                />
              </label>
              <label>
                中心からの半径（km）
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={areaRadiusKm}
                  onChange={(event) => setAreaRadiusKm(Number(event.target.value))}
                />
              </label>
            </>
          )}
        </div>
      </fieldset>

      <fieldset className="route-plan__group">
        <legend>休憩時間</legend>
        <label className="route-plan__check">
          <input type="checkbox" checked={breakEnabled} onChange={(event) => setBreakEnabled(event.target.checked)} />
          休憩時間を確保する
        </label>
        {breakEnabled && (
          <div className="route-plan__controls">
            <label>
              休憩開始
              <input type="time" value={breakStart} onChange={(event) => setBreakStart(event.target.value)} />
            </label>
            <label>
              休憩終了
              <input type="time" value={breakEnd} onChange={(event) => setBreakEnd(event.target.value)} />
            </label>
          </div>
        )}
      </fieldset>

      <button type="button" className="regenerate-button" onClick={createBatchPreview} disabled={busy}>
        {busy ? "月→週→日の計画を計算中…" : batch ? "月間計画を作り直す" : "月間スケジュールを作る"}
      </button>

      {error && <p className="new-customer-form__error">{error}</p>}

      {batch && (
        <div className="route-plan__result">
          <p>
            {batch.start_date}〜{batch.end_date}・{batch.rep_name}・{batch.branch.branch_name}営業所
          </p>
          <div className="route-plan-batch__flow" aria-label="月、週、日の計画フロー">
            <article>
              <small>1. 月の逆算</small>
              <strong>{yen(batch.remaining_target_amount)}</strong>
              <span>
                月目標 {yen(batch.monthly_target_amount)}・成約済み {yen(batch.achieved_amount)}
              </span>
            </article>
            <article>
              <small>2. 顧客選択</small>
              <strong>{batch.selected_customers.length}社</strong>
              <span>
                新規{batch.selected_customers.filter((customer) => customer.customer_type === "new").length}社・
                商談中{batch.selected_customers.filter((customer) => customer.customer_type === "ongoing").length}社・
                商談{batch.selected_customers.reduce((total, customer) => total + customer.planned_visit_count, 0)}回・
                期待売上{yen(batch.portfolio_expected_sales)}（目標比{Math.round(batch.portfolio_coverage_rate * 100)}%）
              </span>
            </article>
            <article>
              <small>3. 週・日へ展開</small>
              <strong>{batch.weeks.length}週・{batch.days.length}営業日</strong>
              <span>日別ルート {batch.detailed_days}日分を詳細計算</span>
            </article>
          </div>

          <div className="route-plan__totals">
            <span>期間目標 {yen(batch.planning_target_amount)}</span>
            <span>ルート期待売上 {yen(batch.totals.expected_sales)}</span>
            <span>予定粗利 {yen(batch.totals.expected_gross_profit)}</span>
            <span>訪問 {batch.totals.visit_count}件</span>
            <span>移動 {batch.totals.total_travel_min}分</span>
          </div>
          {batch.warnings.map((warning) => (
            <p className="route-plan__warning" key={warning}>{warning}</p>
          ))}

          <section className="route-plan-batch__portfolio">
            <h3>月の顧客候補</h3>
            <p>
              残目標に対して約10%の余裕を持たせ、新規・商談中を混ぜて、期待売上・粗利・
              担当者適合度・必要商談回数から選びます。
            </p>
            <div className="route-plan-batch__customer-grid">
              {batch.selected_customers.map((customer) => (
                <article key={customer.customer_id}>
                  <strong>
                    {customer.customer_type === "new" ? "新規" : "商談中"}・{customer.customer_name}
                  </strong>
                  <span>{customer.assigned_dates.map(dayLabel).join("、")}に割当</span>
                  <span>
                    必要{customer.required_visit_count}回・完了{customer.completed_visit_count}回・
                    確定済み{customer.scheduled_visit_count}回・今回{customer.planned_visit_count}回
                  </span>
                  <span>期待売上 {yen(customer.expected_sales)}</span>
                  <small>{customer.selection_reason}</small>
                </article>
              ))}
              {batch.selected_customers.length === 0 && (
                <p className="route-plan-batch__day-empty">追加の訪問候補はありません。</p>
              )}
            </div>
          </section>

          <div className="route-plan-batch__weeks">
            {batch.weeks.map((week) => (
              <details
                key={`${week.start_date}-${week.end_date}`}
                className="route-plan-batch__week"
                open={week.week_number === 1}
              >
                <summary className="route-plan-batch__week-summary">
                  <span>第{week.week_number}週</span>
                  <strong>週目標 {yen(week.target_amount)}</strong>
                  <span>
                    期待売上 {yen(week.expected_sales)}・訪問{week.visit_count}件・
                    達成見込み{Math.round(week.attainment_rate * 100)}%
                  </span>
                </summary>
                <div className="route-plan-batch__week-body">
                  <p>{week.focus}</p>
                  {week.shortfall_amount > 0 && (
                    <p className="route-plan__warning">週目標まで {yen(week.shortfall_amount)} 不足する見込みです。</p>
                  )}
                  <div className="route-plan-batch__days">
                    {week.days.map((day) => (
                      <details key={day.target_date} className="route-plan-batch__day">
                        <summary className="route-plan-batch__day-summary">
                          <span className="route-plan-batch__day-date">{dayLabel(day.target_date)}</span>
                          <span className={`route-plan-batch__badge route-plan-batch__badge--${day.detail_level}`}>
                            {day.detail_level === "detailed" ? "詳細ルート" : "概算"}
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
                                .filter((warning) => !batch.warnings.includes(warning))
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
                                    disabled={busy}
                                  >
                                    この日の予定を採用
                                  </button>
                                  <button
                                    type="button"
                                    className="goal-card__cancel"
                                    onClick={() => rejectDay(day.plan_id as number)}
                                    disabled={busy}
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
            ))}
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
