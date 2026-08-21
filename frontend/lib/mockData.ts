import type { ActivityPlan, RepAffinity, SalesRep, SalesTarget } from "@/types";

export const mockSalesRep: SalesRep = {
  rep_id: 1,
  rep_name: "山田太郎",
  department_id: 1,
  manager_rep_id: null,
};

export const mockSalesTarget: SalesTarget = {
  rep_id: 1,
  target_month: "2026-08",
  target_amount: 4950000,
  target_deal_count: 4,
};

export const mockActivityPlans: ActivityPlan[] = [
  {
    plan_id: 1,
    rep_id: 1,
    plan_date: "2026-08-24",
    customer_id: 10,
    customer_name: "大東物産",
    deal_id: 101,
    activity_type_id: 1,
    activity_type_name: "訪問",
    priority: 1,
    expected_amount: 950000,
    expected_probability: 60,
    is_ai_generated: true,
    reasoning_text: "過去の製造業向け商談での成約率が高く、優先度を高く設定しました。",
    result_status: "pending",
  },
  {
    plan_id: 2,
    rep_id: 1,
    plan_date: "2026-08-25",
    customer_id: 10,
    customer_name: "大東物産",
    deal_id: 102,
    activity_type_id: 2,
    activity_type_name: "電話",
    priority: 2,
    expected_amount: 480000,
    expected_probability: 45,
    is_ai_generated: true,
    reasoning_text: "前回訪問のフォローアップとして、確度が下がる前の週内連絡を提案しました。",
    result_status: "pending",
  },
  {
    plan_id: 3,
    rep_id: 1,
    plan_date: "2026-08-26",
    customer_id: 11,
    customer_name: "さくら商事",
    deal_id: 103,
    activity_type_id: 1,
    activity_type_name: "訪問",
    priority: 3,
    expected_amount: 400000,
    expected_probability: 25,
    is_ai_generated: true,
    reasoning_text: "過去に同規模案件を一度見送りとなっているため、優先度は抑えつつも接点は維持する計画です。",
    result_status: "pending",
  },
];

// 既存の計画が失注・延期になった際に、AIが代わりに差し込む候補（自動再計画のデモ用）
export const mockReplacementCandidates: ActivityPlan[] = [
  {
    plan_id: 104,
    rep_id: 1,
    plan_date: "2026-08-27",
    customer_id: 12,
    customer_name: "東西システムズ",
    deal_id: 104,
    activity_type_id: 1,
    activity_type_name: "訪問",
    priority: 2,
    expected_amount: 520000,
    expected_probability: 50,
    is_ai_generated: true,
    reasoning_text: "既存計画の失注・延期を補うため、直近で提案余地のある東西システムズを追加しました。",
    result_status: "pending",
  },
];

export const mockRepAffinities: RepAffinity[] = [
  { rep_id: 1, category_id: 1, category_name: "製造業", score: 82 },
  { rep_id: 1, category_id: 2, category_name: "卸売業", score: 55 },
  { rep_id: 1, category_id: 3, category_name: "小売業", score: 30 },
];
