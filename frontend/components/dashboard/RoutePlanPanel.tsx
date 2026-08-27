"use client";

import { useState } from "react";
import {
  approveSalesRoutePlan,
  previewSalesRoutePlan,
  rejectSalesRoutePlan,
} from "@/lib/api";
import type { RoutePlanPreview, TransitItinerary } from "@/types";

type Props = {
  plan: RoutePlanPreview | null;
  onPlanChange: (plan: RoutePlanPreview | null) => void;
  onApproved: () => Promise<void>;
};

// 週・月バッチプレビュー(RouteBatchPlanPanel)も同じ書式・ラベルを使うため export する。
export function tomorrowInTokyo(): string {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  return formatter.format(new Date(Date.now() + 24 * 60 * 60 * 1000));
}

export function yen(value: number | null): string {
  return value === null ? "粗利評価不可" : `${value.toLocaleString("ja-JP")}円`;
}

export function clock(value: string): string {
  return new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

export function shortClock(value: string): string {
  return value.slice(0, 5);
}

export function googleTransitDirectionsUrl(
  origin?: { latitude: number; longitude: number },
  destination?: { latitude: number; longitude: number },
): string {
  const params = new URLSearchParams({ api: "1", travelmode: "transit" });
  if (origin) params.set("origin", `${origin.latitude},${origin.longitude}`);
  if (destination) params.set("destination", `${destination.latitude},${destination.longitude}`);
  return `https://www.google.com/maps/dir/?${params.toString()}`;
}

export const TRAVEL_MODE_LABELS: Record<RoutePlanPreview["travel_mode"], string> = {
  driving: "車",
  transit: "公共交通（徒歩＋電車・バス）",
  walking: "徒歩",
  cycling: "自転車",
};

const TRANSIT_LEG_LABELS: Record<string, string> = {
  WALK: "徒歩",
  SUBWAY: "地下鉄",
  RAIL: "電車",
  BUS: "バス",
  TRAM: "路面電車",
  FERRY: "船",
};

const TOEI_ROUTE_LABELS: Record<string, string> = {
  "Asakusa Line": "浅草線",
  "Mita Line": "三田線",
  "Shinjuku Line": "新宿線",
  "Oedo Line": "大江戸線",
  "Nippori-Toneri Liner": "日暮里・舎人ライナー",
  "Tokyo Sakura Tram (Arakawa Line)": "東京さくらトラム（都電荒川線）",
};

export function TransitItineraryDetails({ title, itinerary }: { title: string; itinerary: TransitItinerary }) {
  return (
    <div className="route-plan__transit-itinerary">
      <strong>
        {title}：{clock(itinerary.departure_at)}発–{clock(itinerary.arrival_at)}着
      </strong>
      <small>
        {itinerary.data_status}・予定到着には余裕時間{itinerary.contingency_buffer_min}分を加算
      </small>
      <ol>
        {itinerary.legs.map((leg, index) => {
          const routeName = leg.route_name ? TOEI_ROUTE_LABELS[leg.route_name] ?? leg.route_name : null;
          return (
            <li key={`${leg.departure_at}-${index}`}>
              <span>
                {clock(leg.departure_at)}–{clock(leg.arrival_at)} {TRANSIT_LEG_LABELS[leg.mode] ?? leg.mode}：
                {leg.from_name} → {leg.to_name}
              </span>
              {(routeName || leg.headsign) && (
                <small>
                  {routeName ?? "公共交通"}
                  {leg.headsign ? `・${leg.headsign}行き` : ""}
                  {leg.from_platform ? `・${leg.from_platform}番線` : ""}
                </small>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function RoutePlanPanel({ plan, onPlanChange, onApproved }: Props) {
  const [targetDate, setTargetDate] = useState(tomorrowInTokyo);
  const [policy, setPolicy] = useState<RoutePlanPreview["policy"]>("balanced");
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
  const [turnaroundBuffer, setTurnaroundBuffer] = useState(20);
  const [travelBufferPercent, setTravelBufferPercent] = useState(20);
  const [accessBuffer, setAccessBuffer] = useState(10);
  const [returnBuffer, setReturnBuffer] = useState(30);
  const [minSales, setMinSales] = useState("");
  const [minProfit, setMinProfit] = useState("");
  const [busy, setBusy] = useState(false);
  const [decision, setDecision] = useState<"approved" | "rejected" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const grossProfitWeightPercent = 100 - salesWeightPercent;
  const resultEconomicWeight = plan
    ? plan.weights.sales + plan.weights.gross_profit
    : 0;

  function changePolicy(nextPolicy: RoutePlanPreview["policy"]) {
    setPolicy(nextPolicy);
    if (nextPolicy === "sales") setSalesWeightPercent(70);
    else if (nextPolicy === "gross_profit") setSalesWeightPercent(30);
    else setSalesWeightPercent(50);
  }

  async function createPreview() {
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
    setDecision(null);
    try {
      onPlanChange(
        await previewSalesRoutePlan({
          target_date: targetDate,
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
          turnaround_buffer_min: turnaroundBuffer,
          travel_time_buffer_percent: travelBufferPercent,
          access_buffer_min: accessBuffer,
          return_buffer_min: returnBuffer,
          ...(minSales ? { min_expected_sales: Number(minSales) } : {}),
          ...(minProfit ? { min_expected_gross_profit: Number(minProfit) } : {}),
        }),
      );
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "ルート作成に失敗しました");
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!plan) return;
    setBusy(true);
    setError(null);
    try {
      await approveSalesRoutePlan(plan.plan_id);
      setDecision("approved");
      await onApproved();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "承認に失敗しました");
    } finally {
      setBusy(false);
    }
  }

  async function reject() {
    if (!plan) return;
    setBusy(true);
    setError(null);
    try {
      await rejectSalesRoutePlan(plan.plan_id);
      setDecision("rejected");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "却下に失敗しました");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel route-plan">
      <h2>1日の営業ルート計画</h2>
      <div className="route-plan__controls">
        <label>
          対象日
          <input type="date" value={targetDate} onChange={(event) => setTargetDate(event.target.value)} />
        </label>
        <label>
          方針
          <select value={policy} onChange={(event) => changePolicy(event.target.value as RoutePlanPreview["policy"])}>
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
          最大訪問数
          <input type="number" min={1} max={10} value={maxVisits} onChange={(event) => setMaxVisits(Number(event.target.value))} />
        </label>
        <label>
          最低期待売上
          <input type="number" min={0} value={minSales} onChange={(event) => setMinSales(event.target.value)} placeholder="任意" />
        </label>
        <label>
          最低期待粗利
          <input type="number" value={minProfit} onChange={(event) => setMinProfit(event.target.value)} placeholder="任意" />
        </label>
      </div>

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
        <small>
          この比率に加えて、担当者の業種×商品カテゴリ別の成約実績、期限、商談フェーズ、移動時間も評価します。
        </small>
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
        <small>任意の訪問候補をこの範囲に絞ります。その日の必須商談は範囲外でも残します。</small>
      </fieldset>

      <fieldset className="route-plan__group">
        <legend>休憩・時間の余裕</legend>
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
        <details className="route-plan__details">
          <summary>余裕時間の詳細設定</summary>
          <div className="route-plan__controls">
            <label>
              商談前後の余裕（分）
              <input type="number" min={0} max={60} value={turnaroundBuffer} onChange={(event) => setTurnaroundBuffer(Number(event.target.value))} />
            </label>
            <label>
              移動時間の上乗せ（%）
              <input type="number" min={0} max={100} value={travelBufferPercent} onChange={(event) => setTravelBufferPercent(Number(event.target.value))} />
            </label>
            <label>
              各移動前後の余裕（分）
              <input type="number" min={0} max={60} value={accessBuffer} onChange={(event) => setAccessBuffer(Number(event.target.value))} />
            </label>
            <label>
              帰着後の事務時間（分）
              <input type="number" min={0} max={120} value={returnBuffer} onChange={(event) => setReturnBuffer(Number(event.target.value))} />
            </label>
          </div>
        </details>
      </fieldset>

      <button type="button" className="regenerate-button" onClick={createPreview} disabled={busy}>
        {busy ? "計算中…" : plan ? "作り直す" : "ルート案を作る"}
      </button>

      {travelMode === "transit" && (
        <div className="route-plan__warning">
          <p>
            現在のローカルGTFS収録範囲は東京都交通局（都営地下鉄・都営バス）です。
            横浜方面の電車経路にはJR東日本などのGTFS追加が必要です。
          </p>
          <a href={googleTransitDirectionsUrl()} target="_blank" rel="noopener noreferrer">
            Googleマップで公共交通経路を確認する（外部サイト）
          </a>
        </div>
      )}

      {error && <p className="new-customer-form__error">{error}</p>}
      {plan && (
        <div className="route-plan__result">
          <p>
            {plan.target_date}・{plan.rep_name}・{TRAVEL_MODE_LABELS[plan.travel_mode]}
          </p>
          <p className="route-plan__locations">
            <strong>出発：</strong>{plan.start_location.label}
            <span aria-hidden="true">→</span>
            <strong>帰着：</strong>{plan.end_location.label}
          </p>
          <p className="route-plan__locations">
            <strong>訪問エリア：</strong>{plan.search_area.label}
          </p>
          <p>
            {plan.break_time
              ? `休憩 ${shortClock(plan.break_time.start)}–${shortClock(plan.break_time.end)}・`
              : "休憩指定なし・"}
            帰着予定 {clock(plan.totals.route_end_at)}
          </p>
          <div className="route-plan__totals">
            <span>売上予定額 {yen(plan.totals.planned_sales)}</span>
            <span>予定粗利 {yen(plan.totals.planned_gross_profit)}</span>
            <span>期待売上 {yen(plan.totals.expected_sales)}</span>
            <span>期待粗利 {yen(plan.totals.expected_gross_profit)}</span>
            <span>移動 {plan.totals.total_travel_min}分 / {(plan.totals.total_distance_m / 1000).toFixed(1)}km</span>
          </div>
          {resultEconomicWeight > 0 && (
            <p className="route-plan__evaluation-summary">
              収益評価の配分：売上 {Math.round(plan.weights.sales / resultEconomicWeight * 100)}%・
              粗利 {Math.round(plan.weights.gross_profit / resultEconomicWeight * 100)}%／
              担当者適合度も評価済み
            </p>
          )}
          {!plan.target_met && (
            <p className="route-plan__warning">
              最低条件未達: 期待売上 {yen(plan.shortfalls.expected_sales)}、
              期待粗利 {yen(plan.shortfalls.expected_gross_profit)}不足
            </p>
          )}
          <ol className="route-plan__stops">
            {plan.stops.map((stop, index) => (
              <li key={stop.customer_id}>
                <strong>{clock(stop.arrival_at)}–{clock(stop.departure_at)} {stop.customer_name}</strong>
                <span>
                  {stop.economics.customer_type === "new" ? "新規" : "商談中"}・
                  必要{stop.economics.required_visit_count}回・
                  未予定残り{stop.economics.remaining_visit_count}回・
                  前区間 {stop.leg_travel_min}分 / {(stop.leg_distance_m / 1000).toFixed(1)}km・
                  案件期待売上 {yen(stop.economics.opportunity_expected_sales)}・
                  今回の売上見込 {yen(stop.economics.expected_sales)}・
                  担当者適合度 {Math.round(stop.economics.salesperson_fit_score)}/100
                </span>
                <small>商談後の準備・記録時間 {stop.turnaround_buffer_min}分</small>
                <small>{stop.selection_reason}</small>
                {plan.travel_mode === "transit" && stop.leg_details && (
                  <TransitItineraryDetails title="この訪問先まで" itinerary={stop.leg_details} />
                )}
                {plan.travel_mode === "transit" && (
                  <small>
                    <a
                      href={googleTransitDirectionsUrl(index === 0 ? plan.start_location : plan.stops[index - 1], stop)}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      この区間をGoogleマップで見る
                    </a>
                  </small>
                )}
              </li>
            ))}
          </ol>
          {plan.travel_mode === "transit" && (
            <div>
              {plan.return_leg && (
                <TransitItineraryDetails title="帰着地点まで" itinerary={plan.return_leg} />
              )}
              <p>
                <a
                  href={googleTransitDirectionsUrl(plan.stops.at(-1) ?? plan.start_location, plan.end_location)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  最終訪問先から帰着地点までGoogleマップで見る
                </a>
              </p>
            </div>
          )}
          <p>{plan.selection_reason}</p>
          <details>
            <summary>比較した{plan.options.length}案の求解状態と不採用理由</summary>
            <ul>
              {plan.options.map((option) => (
                <li key={option.rank}>
                  案{option.rank}: CP-SAT {option.cp_sat_status} / Routing {option.routing_status}
                  {option.selected ? "（採用）" : ` — ${option.rejection_reason || "経路化不可"}`}
                </li>
              ))}
            </ul>
          </details>
          {plan.warnings.map((warning) => (
            <p className="route-plan__warning" key={warning}>{warning}</p>
          ))}
          {(plan.travel_mode === "walking" || plan.travel_mode === "cycling") && (
            <p className="route-plan__warning">
              Googleの徒歩・自転車経路はベータ版で、歩道や自転車経路が一部反映されない場合があります。
            </p>
          )}
          <small>
            Routing: {plan.travel_mode === "transit" ? "ODPT + OpenTripPlanner（徒歩＋公共交通） / Transit data: 東京都交通局・公共交通オープンデータ協議会" : "Google Routes API"}
            {" / "}Map data: © OpenStreetMap contributors
          </small>
          {decision === null ? (
            <div className="route-plan__actions">
              <button type="button" className="goal-card__save" onClick={approve} disabled={busy}>
                この計画を採用
              </button>
              <button type="button" className="goal-card__cancel" onClick={reject} disabled={busy}>
                却下
              </button>
            </div>
          ) : (
            <p>{decision === "approved" ? "活動予定へ保存しました。" : "計画案を却下しました。"}</p>
          )}
        </div>
      )}
    </section>
  );
}
