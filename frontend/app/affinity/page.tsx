"use client";

import { useEffect, useState } from "react";
import { AffinityCategoryCharts } from "@/components/affinity/AffinityCategoryCharts";
import { AffinityRankingList } from "@/components/affinity/AffinityRankingList";
import { AffinitySummary } from "@/components/affinity/AffinitySummary";
import { fetchRepAffinity, recalculateRepAffinity } from "@/lib/api";
import { useRep } from "@/lib/repContext";
import type { RepAffinity } from "@/types";

export default function AffinityPage() {
  const { selectedRep } = useRep();
  const REP_ID = selectedRep?.rep_id ?? null;
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [affinities, setAffinities] = useState<RepAffinity[]>([]);

  useEffect(() => {
    if (REP_ID === null) return;
    const repId = REP_ID;
    let cancelled = false;

    async function load() {
      try {
        setIsLoading(true);
        setLoadError(null);
        // 自己分析スコアは計算済みのキャッシュなので、表示前に最新の商談結果を反映させておく
        await recalculateRepAffinity(repId);
        const fetched = await fetchRepAffinity(repId);
        if (!cancelled) setAffinities(fetched);
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

  if (!selectedRep) {
    return (
      <main className="wide-main">
        <h1>自己分析</h1>
        <p>読み込み中...</p>
      </main>
    );
  }

  return (
    <main className="wide-main">
      <h1>自己分析</h1>
      <p>
        {selectedRep.rep_name}さんの過去の成約・失注実績から、業種・商材カテゴリ・案件パターンごとの成約率を算出しています。
      </p>

      {isLoading ? (
        <p>読み込み中...</p>
      ) : loadError ? (
        <p className="activity-plan-list__empty">
          データの取得に失敗しました({loadError})。バックエンド(API・Supabase)が起動しているか確認してください。
        </p>
      ) : (
        <>
          <AffinitySummary affinities={affinities} />
          <section className="panel">
            <h2>業界・商品カテゴリ別の成約率</h2>
            <AffinityCategoryCharts affinities={affinities} />
          </section>
          <section className="panel">
            <h2>商談履歴(業界・カテゴリ別)</h2>
            <AffinityRankingList affinities={affinities} />
          </section>
        </>
      )}
    </main>
  );
}
