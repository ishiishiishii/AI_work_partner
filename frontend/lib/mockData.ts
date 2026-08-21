import type { ActivityPlan, SalesRep } from "@/types";

// industry/company_size/deal_phase/deal_result_status/deal_pattern の名称を返すAPIが
// まだ無いため、supabase/seed.sql・migration の投入順(= serial の採番順)を前提に
// ハードコードしている。マスタの並びが変わるとズレるため、名称解決APIが追加され次第そちらに差し替える。
export const INDUSTRY_NAMES: Record<number, string> = {
  1: "製造業",
  2: "建設業",
  3: "金融・保険業",
  4: "教育",
  5: "不動産業",
  6: "情報通信業",
  7: "小売業",
  8: "卸売業",
  9: "医療・福祉",
  10: "運輸業",
  11: "サービス業",
  12: "飲食業",
};

export const COMPANY_SIZE_NAMES: Record<number, string> = {
  1: "中小企業",
  2: "中堅企業",
  3: "大企業",
};

export const DEAL_PHASE_NAMES: Record<number, string> = {
  1: "初回接触",
  2: "ヒアリング",
  3: "提案",
  4: "見積",
  5: "契約交渉",
};

export const DEAL_RESULT_STATUS_NAMES: Record<number, string> = {
  1: "進行中",
  2: "成約",
  3: "失注",
};

export const DEAL_PATTERN_NAMES: Record<number, string> = {
  1: "新規開拓・大型",
  2: "新規開拓・小口",
  3: "既存深耕・大型",
  4: "既存深耕・小口",
};

// 担当者一覧を返すAPIがまだ無いため、supabase/seed.sql に実在する18人を直書きしている。
// 名称解決APIが追加され次第、GET /api/sales-reps 相当のAPI呼び出しに差し替える。
export const mockSalesReps: SalesRep[] = [
  { rep_id: 1, rep_name: "石川次郎" },
  { rep_id: 2, rep_name: "村上花子" },
  { rep_id: 3, rep_name: "小林綾子" },
  { rep_id: 4, rep_name: "木村さゆり" },
  { rep_id: 5, rep_name: "加藤拓也" },
  { rep_id: 6, rep_name: "遠藤直樹" },
  { rep_id: 7, rep_name: "近藤拓也" },
  { rep_id: 8, rep_name: "井上愛" },
  { rep_id: 9, rep_name: "吉田直樹" },
  { rep_id: 10, rep_name: "高橋健二" },
  { rep_id: 11, rep_name: "林慎一" },
  { rep_id: 12, rep_name: "井上健太" },
  { rep_id: 13, rep_name: "林麻衣" },
  { rep_id: 14, rep_name: "岡田健二" },
  { rep_id: 15, rep_name: "吉田陽子" },
  { rep_id: 16, rep_name: "石川大輔" },
  { rep_id: 17, rep_name: "岡本裕子" },
  { rep_id: 18, rep_name: "後藤大輔" },
];

export const mockSalesRep: SalesRep = mockSalesReps[0];

// 「日」表示用の1日のスケジュール。資料作成・新規開拓など、
// 顧客・商談に紐づかない活動もここでは扱う（customer_id/deal_idは無し）。
// 実データが来るまでの仮データ。バックエンドの実案件がある2026-08-01を基準にしている。
export const mockDailyTasks: ActivityPlan[] = [
  {
    plan_id: 900101,
    rep_id: 1,
    plan_date: "2026-08-01",
    start_time: "09:00",
    customer_id: null,
    customer_name: "提案書の最終確認",
    deal_id: null,
    product_name: null,
    activity_type_name: "資料作成",
    priority: 2,
    expected_amount: 0,
    expected_probability: 0,
    is_ai_generated: true,
    reasoning_text: "午後の訪問前に、見積・提案内容を最終確認しておくことを提案しました。",
    result_status: "pending",
  },
  {
    plan_id: 900102,
    rep_id: 1,
    plan_date: "2026-08-01",
    start_time: "10:00",
    customer_id: null,
    customer_name: "新規リストへの架電・飛び込み候補の洗い出し",
    deal_id: null,
    product_name: null,
    activity_type_name: "新規開拓",
    priority: 3,
    expected_amount: 0,
    expected_probability: 0,
    is_ai_generated: true,
    reasoning_text: "午前中の空き時間を使い、新規開拓の候補を増やすことを提案しました。",
    result_status: "pending",
  },
  {
    plan_id: 900103,
    rep_id: 1,
    plan_date: "2026-08-01",
    start_time: "15:00",
    customer_id: null,
    customer_name: "既存顧客へのフォロー架電",
    deal_id: null,
    product_name: null,
    activity_type_name: "電話",
    priority: 4,
    expected_amount: 0,
    expected_probability: 0,
    is_ai_generated: true,
    reasoning_text: "訪問後の移動時間を使い、他の見込み客にも短時間で接点を作ることを提案しました。",
    result_status: "pending",
  },
  {
    plan_id: 900104,
    rep_id: 1,
    plan_date: "2026-08-01",
    start_time: "16:30",
    customer_id: null,
    customer_name: "週次報告書の作成",
    deal_id: null,
    product_name: null,
    activity_type_name: "資料作成",
    priority: 5,
    expected_amount: 0,
    expected_probability: 0,
    is_ai_generated: true,
    reasoning_text: "1日の活動を振り返り、報告書としてまとめる時間を確保しました。",
    result_status: "pending",
  },
];
