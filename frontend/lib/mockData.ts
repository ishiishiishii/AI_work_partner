import type { ActivityPlan, Customer, DealHistoryItem, RepAffinity, SalesRep } from "@/types";

// 担当者一覧を返すAPIがまだ無いため、担当者情報を直書きしている。
// 「山田 太郎」のみ supabase/seed.sql に実在する担当者で、他はUI確認用の仮の担当者。
// 仮の担当者は顧客・計画のデータがまだ無い（バックエンドのsales_repテーブルにも存在しない）ため、
// 顧客の新規登録など、バックエンドに書き込む操作は行えない。
export const mockSalesReps: SalesRep[] = [
  { rep_id: "11111111-1111-1111-1111-111111111111", rep_name: "山田 太郎" },
  { rep_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", rep_name: "佐藤 花子" },
  { rep_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", rep_name: "鈴木 次郎" },
];

export const mockSalesRep: SalesRep = mockSalesReps[0];

// rep_affinity（得意分野スコア）はバックエンドにまだ無いテーブルのため、引き続きモック
export const mockRepAffinities: RepAffinity[] = [
  {
    rep_id: "11111111-1111-1111-1111-111111111111",
    category_id: 1,
    category_name: "製造業",
    score: 82,
  },
  {
    rep_id: "11111111-1111-1111-1111-111111111111",
    category_id: 2,
    category_name: "卸売業",
    score: 55,
  },
  {
    rep_id: "11111111-1111-1111-1111-111111111111",
    category_id: 3,
    category_name: "小売業",
    score: 30,
  },
  {
    rep_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    category_id: 1,
    category_name: "情報通信業",
    score: 75,
  },
  {
    rep_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    category_id: 2,
    category_name: "卸売業",
    score: 60,
  },
  {
    rep_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    category_id: 3,
    category_name: "小売業",
    score: 35,
  },
  {
    rep_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    category_id: 1,
    category_name: "建設業",
    score: 70,
  },
  {
    rep_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    category_id: 2,
    category_name: "製造業",
    score: 65,
  },
  {
    rep_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    category_id: 3,
    category_name: "小売業",
    score: 20,
  },
];

// 「対応が難しい」を押した際にAIが差し替える候補。
// バックエンドの顧客データがまだ3社しかなく予備がないため、当面はローカルの候補で代替する。
// customer_id/deal_id が無い(実在の顧客ではない)ため、この計画に結果を記録してもバックエンドには送信されない。
export const mockAlternativeCandidates: ActivityPlan[] = [
  {
    plan_id: "mock-alt-1",
    rep_id: "11111111-1111-1111-1111-111111111111",
    plan_date: "2026-08-10",
    start_time: null,
    customer_id: null,
    customer_name: "東西システムズ",
    deal_id: null,
    activity_type_name: "Web会議",
    priority: 3,
    expected_amount: 520000,
    expected_probability: 50,
    is_ai_generated: true,
    reasoning_text: "対応が難しいとのことなので、負担の少ないWeb会議から始められる案件に差し替えました。",
    result_status: "pending",
  },
  {
    plan_id: "mock-alt-2",
    rep_id: "11111111-1111-1111-1111-111111111111",
    plan_date: "2026-08-17",
    start_time: null,
    customer_id: null,
    customer_name: "北陸精密",
    deal_id: null,
    activity_type_name: "メール",
    priority: 4,
    expected_amount: 380000,
    expected_probability: 45,
    is_ai_generated: true,
    reasoning_text: "対応が難しいとのことなので、まずはメールでの軽い接点から関係構築できる案件を提案しました。",
    result_status: "pending",
  },
];

// 「日」表示用の1日のスケジュール。資料作成・新規開拓など、
// 顧客・商談に紐づかない活動もここでは扱う（customer_id/deal_idは無し）。
// 実データが来るまでの仮データ。バックエンドの実案件がある2026-08-01を基準にしている。
export const mockDailyTasks: ActivityPlan[] = [
  {
    plan_id: "mock-task-1",
    rep_id: "11111111-1111-1111-1111-111111111111",
    plan_date: "2026-08-01",
    start_time: "09:00",
    customer_id: null,
    customer_name: "提案書の最終確認(A製作所向け)",
    deal_id: null,
    activity_type_name: "資料作成",
    priority: 2,
    expected_amount: 0,
    expected_probability: 0,
    is_ai_generated: true,
    reasoning_text: "午後の訪問前に、見積・提案内容を最終確認しておくことを提案しました。",
    result_status: "pending",
  },
  {
    plan_id: "mock-task-2",
    rep_id: "11111111-1111-1111-1111-111111111111",
    plan_date: "2026-08-01",
    start_time: "10:00",
    customer_id: null,
    customer_name: "新規リストへの架電・飛び込み候補の洗い出し",
    deal_id: null,
    activity_type_name: "新規開拓",
    priority: 3,
    expected_amount: 0,
    expected_probability: 0,
    is_ai_generated: true,
    reasoning_text: "午前中の空き時間を使い、新規開拓の候補を増やすことを提案しました。",
    result_status: "pending",
  },
  {
    plan_id: "mock-task-3",
    rep_id: "11111111-1111-1111-1111-111111111111",
    plan_date: "2026-08-01",
    start_time: "15:00",
    customer_id: null,
    customer_name: "Cテックへのフォロー架電",
    deal_id: null,
    activity_type_name: "電話",
    priority: 4,
    expected_amount: 0,
    expected_probability: 0,
    is_ai_generated: true,
    reasoning_text: "訪問後の移動時間を使い、他の見込み客にも短時間で接点を作ることを提案しました。",
    result_status: "pending",
  },
  {
    plan_id: "mock-task-4",
    rep_id: "11111111-1111-1111-1111-111111111111",
    plan_date: "2026-08-01",
    start_time: "16:30",
    customer_id: null,
    customer_name: "週次報告書の作成",
    deal_id: null,
    activity_type_name: "資料作成",
    priority: 5,
    expected_amount: 0,
    expected_probability: 0,
    is_ai_generated: true,
    reasoning_text: "1日の活動を振り返り、報告書としてまとめる時間を確保しました。",
    result_status: "pending",
  },
];

// 顧客詳細ページの「商談履歴」用の仮データ。
// バックエンドに商談履歴を取得するAPI(GET /api/deals・GET /api/results 相当)がまだ無いため、
// 顧客自身の実データ(見込み金額・成約確率・ステータス)を元にそれらしい履歴を組み立てている。
export function mockDealHistoryFor(customer: Customer): DealHistoryItem[] {
  const baseAmount = customer.estimated_amount || 500000;
  const isActive = customer.status === "active";

  return [
    {
      history_id: `${customer.customer_id}-h1`,
      date: "2026-07-05",
      activity_type_name: "訪問",
      status: "in_progress",
      amount: baseAmount,
      note: `${customer.customer_name}へ初回提案を実施。反応は前向きだった。`,
    },
    {
      history_id: `${customer.customer_id}-h2`,
      date: "2026-07-20",
      activity_type_name: "電話",
      status: "in_progress",
      amount: baseAmount,
      note: "見積内容についてフォロー連絡。社内稟議中とのこと。",
    },
    {
      history_id: `${customer.customer_id}-h3`,
      date: "2026-08-01",
      activity_type_name: "メール",
      status: isActive ? "won" : "in_progress",
      amount: Math.round(baseAmount * (customer.win_probability / 100)),
      note: isActive
        ? "契約締結。次回更新提案に向けて関係構築中。"
        : "追加資料を送付し、次回訪問の日程を調整中。",
    },
  ];
}
