"use client";

import { useEffect, useState } from "react";
import { TeamMemberTable, type TeamMemberRow } from "@/components/team/TeamMemberTable";
import { TeamSummary } from "@/components/team/TeamSummary";
import { fetchForecast, fetchReps } from "@/lib/api";
import { useRep } from "@/lib/repContext";
import type { Forecast, SalesRep } from "@/types";

function getCurrentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

// 直近12ヶ月分(過去11ヶ月+当月)を選択肢にする
function buildMonthOptions(): string[] {
  const now = new Date();
  const months: string[] = [];
  for (let i = 11; i >= 0; i -= 1) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return months;
}

function formatMonth(targetMonth: string): string {
  const [year, month] = targetMonth.split("-");
  return `${year}年${Number(month)}月`;
}

export default function TeamPage() {
  const { selectedRep } = useRep();
  const REP_ID = selectedRep?.rep_id ?? null;
  const [targetMonth, setTargetMonth] = useState(getCurrentMonth());
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [rows, setRows] = useState<TeamMemberRow[]>([]);

  useEffect(() => {
    if (REP_ID === null || !selectedRep) return;
    const branchId = selectedRep.branch_id;
    let cancelled = false;

    async function load() {
      try {
        setIsLoading(true);
        setLoadError(null);
        const allReps = await fetchReps();
        const branchReps = allReps
          .filter((rep) => rep.branch_id === branchId)
          .sort((a, b) => a.rep_id - b.rep_id);

        const results = await Promise.all(
          branchReps.map(async (rep): Promise<TeamMemberRow> => {
            try {
              const forecast = await fetchForecast(rep.rep_id, targetMonth);
              return { rep, forecast };
            } catch {
              // その月の目標(sales_target)が未登録の担当者は「未設定」扱いにする
              return { rep, forecast: null };
            }
          }),
        );

        if (!cancelled) setRows(results);
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
  }, [REP_ID, selectedRep, targetMonth]);

  if (!selectedRep) {
    return (
      <main className="wide-main">
        <h1>管理者画面(今後拡張予定)</h1>
        <p>読み込み中...</p>
      </main>
    );
  }

  const forecasts = rows.map((row) => row.forecast).filter((f): f is Forecast => f !== null);

  return (
    <main className="wide-main">
      <h1>管理者画面(今後拡張予定)</h1>
      <p>{selectedRep.branch_name}支店の目標・見込み売上を一覧で確認できます。</p>

      <label className="team-month-select">
        <span>対象月</span>
        <select value={targetMonth} onChange={(event) => setTargetMonth(event.target.value)}>
          {buildMonthOptions().map((month) => (
            <option key={month} value={month}>
              {formatMonth(month)}
            </option>
          ))}
        </select>
      </label>

      {loadError ? (
        <p className="activity-plan-list__empty">
          データの取得に失敗しました({loadError})。バックエンド(API・Supabase)が起動しているか確認してください。
        </p>
      ) : isLoading ? (
        <p>読み込み中...</p>
      ) : (
        <>
          <TeamSummary branchName={selectedRep.branch_name} forecasts={forecasts} />
          <TeamMemberTable rows={rows} />
        </>
      )}
    </main>
  );
}
