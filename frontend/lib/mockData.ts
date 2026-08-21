import type { ActivityPlan, RepAffinity, SalesRep } from "@/types";

// 担当者一覧を返すAPIがまだ無いため、supabase/seed.sql の担当者情報を直書きしている
export const mockSalesRep: SalesRep = {
  rep_id: "11111111-1111-1111-1111-111111111111",
  rep_name: "山田 太郎",
};

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
];

// 「対応が難しい」を押した際にAIが差し替える候補。
// バックエンドの顧客データがまだ3社しかなく予備がないため、当面はローカルの候補で代替する。
// customer_id/deal_id が無い(実在の顧客ではない)ため、この計画に結果を記録してもバックエンドには送信されない。
export const mockAlternativeCandidates: ActivityPlan[] = [
  {
    plan_id: "mock-alt-1",
    rep_id: "11111111-1111-1111-1111-111111111111",
    plan_date: "2026-08-10",
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
