"use client";

import { useState } from "react";
import { approveSalesRoutePlan, previewSalesRoutePlan } from "@/lib/api";
import type { RoutePlanPreview } from "@/types";

type Props = {
  onSaved: () => Promise<void>;
};

type SavedSummary = {
  targetDate: string;
  visitCount: number;
  targetMet: boolean;
  shortfallSales: number;
  shortfallGrossProfit: number;
  warnings: string[];
};

function tomorrowInTokyo(): string {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  return formatter.format(new Date(Date.now() + 24 * 60 * 60 * 1000));
}

function yen(value: number): string {
  return `${value.toLocaleString("ja-JP")}円`;
}

export function RoutePlanPanel({ onSaved }: Props) {
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
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<SavedSummary | null>(null);
  const grossProfitWeightPercent = 100 - salesWeightPercent;

  async function createAndSavePlan() {
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
    setSaved(null);
    try {
      const preview = await previewSalesRoutePlan({
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
      });
      await approveSalesRoutePlan(preview.plan_id);
      await onSaved();
      setSaved({
        targetDate: preview.target_date,
        visitCount: preview.totals.visit_count,
        targetMet: preview.target_met,
        shortfallSales: preview.shortfalls.expected_sales,
        shortfallGrossProfit: preview.shortfalls.expected_gross_profit,
        warnings: preview.warnings,
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "ルート作成に失敗しました");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel route-plan">
      <h2>1日の営業ルート計画</h2>
      <label>
        対象日
        <input type="date" value={targetDate} onChange={(event) => setTargetDate(event.target.value)} />
      </label>

      <details className="route-plan__details">
        <summary>詳細設定(方針・出発地点・エリア・休憩など)</summary>

        <div className="route-plan__controls">
          <label>
            方針
            <select value={policy} onChange={(event) => setPolicy(event.target.value as RoutePlanPreview["policy"])}>
              <option value="balanced">通常(売上・粗利は下のスライダーで調整)</option>
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
      </details>

      <button type="button" className="regenerate-button" onClick={createAndSavePlan} disabled={busy}>
        {busy ? "計算中…" : "ルート案を作る"}
      </button>

      {travelMode === "transit" && (
        <div className="route-plan__warning">
          <p>
            現在のローカルGTFS収録範囲は東京都交通局（都営地下鉄・都営バス）です。
            横浜方面の電車経路にはJR東日本などのGTFS追加が必要です。
          </p>
        </div>
      )}

      {error && <p className="new-customer-form__error">{error}</p>}
      {saved && (
        <p className="route-plan__success">
          {saved.targetDate}の訪問予定を{saved.visitCount}件、活動計画に追加しました。下の活動計画でご確認ください。
        </p>
      )}
      {saved && !saved.targetMet && (
        <p className="route-plan__warning">
          最低条件未達: 期待売上 {yen(saved.shortfallSales)}、期待粗利 {yen(saved.shortfallGrossProfit)}不足
        </p>
      )}
      {saved?.warnings.map((warning) => (
        <p className="route-plan__warning" key={warning}>{warning}</p>
      ))}
    </section>
  );
}
