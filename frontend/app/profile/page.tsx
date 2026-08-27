"use client";

import { useEffect, useState } from "react";
import { AdminTaskDurations } from "@/components/profile/AdminTaskDurations";
import { HomeOfficeAvailability } from "@/components/profile/HomeOfficeAvailability";
import { fetchRepProfile } from "@/lib/api";
import { useRep } from "@/lib/repContext";
import type { RepProfile } from "@/types";

export default function ProfilePage() {
  const { selectedRep } = useRep();
  const REP_ID = selectedRep?.rep_id ?? null;
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [profileData, setProfileData] = useState<RepProfile | null>(null);

  useEffect(() => {
    if (REP_ID === null) return;
    const repId = REP_ID;
    let cancelled = false;

    async function load() {
      try {
        setIsLoading(true);
        setLoadError(null);
        const fetched = await fetchRepProfile(repId);
        if (!cancelled) setProfileData(fetched);
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
        <h1>プロフィール(今後拡張予定)</h1>
        <p>読み込み中...</p>
      </main>
    );
  }

  return (
    <main className="wide-main">
      <h1>プロフィール(今後拡張予定)</h1>
      <p>{selectedRep.rep_name}さんの働き方を記録します。将来的に営業ルート計画の初期値に反映していく予定です。</p>

      {loadError ? (
        <p className="activity-plan-list__empty">
          データの取得に失敗しました({loadError})。バックエンド(API・Supabase)が起動しているか確認してください。
        </p>
      ) : isLoading || !profileData ? (
        <p>読み込み中...</p>
      ) : (
        <>
          <HomeOfficeAvailability
            repId={selectedRep.rep_id}
            days={profileData.home_office}
            onChange={(days) => setProfileData({ ...profileData, home_office: days })}
          />
          <AdminTaskDurations
            repId={selectedRep.rep_id}
            taskDurations={profileData.task_durations}
            onChange={(taskDurations) => setProfileData({ ...profileData, task_durations: taskDurations })}
          />
        </>
      )}
    </main>
  );
}
