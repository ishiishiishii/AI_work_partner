// deal_result_status テーブルは status_code(英語)しか持たないため、表示用の
// 日本語名はここで解決する。deal_phase_name・pattern_name 等は ai.* ビューが
// マスタの日本語名をそのまま返すため、ここでのハードコードは不要。
export const DEAL_RESULT_STATUS_NAMES: Record<string, string> = {
  ongoing: "進行中",
  won: "成約",
  lost: "失注",
};

// 事務作業(category='task')の「対応が難しい」差し替え候補プール。商談と違って実データが
// 無いため、固定の候補から未使用のものを提示する。差し替え自体は POST /api/plans で
// 実在の予定として保存する(dashboard/page.tsx の handleRequestAlternative 参照)。
export const mockTaskSuggestions: { title: string; activityTypeName: string; reasoningText: string }[] = [
  {
    title: "見積書の見直し",
    activityTypeName: "資料作成",
    reasoningText: "他の予定と重なっていたため、見積内容の見直しに差し替えました。",
  },
  {
    title: "新規リストへの架電",
    activityTypeName: "新規開拓",
    reasoningText: "空いた時間を使って新規開拓の候補を増やすことを提案しました。",
  },
  {
    title: "既存顧客へのフォローメール",
    activityTypeName: "メール",
    reasoningText: "短時間でも接点を作れるよう、フォローメールに差し替えました。",
  },
  {
    title: "週次報告書の作成",
    activityTypeName: "資料作成",
    reasoningText: "活動の振り返りと報告書作成の時間として提案しました。",
  },
];
