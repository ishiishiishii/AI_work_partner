export type SalesRep = {
  rep_id: number;
  rep_name: string;
};

export type SalesTarget = {
  rep_id: number;
  target_month: string; // "YYYY-MM"
  target_amount: number;
  target_deal_count: number;
};

export type Forecast = {
  rep_id: number;
  target_month: string;
  target_amount: number;
  forecast_amount: number;
  achievement_rate: number;
};

// 担当者の実績を「業界 × 商品カテゴリ × 案件パターン」で集計した実データ
// (deal_count/win_rateなどはバックエンドの rep_affinity テーブルの計算結果そのまま)
export type RepAffinity = {
  rep_id: number;
  industry_id: number;
  industry_name: string;
  category_id: number;
  category_name: string;
  pattern_id: number;
  pattern_name: string;
  deal_count: number;
  won_count: number;
  win_rate: number; // 0-1
  avg_won_amount: number;
  affinity_score: number;
};

// 見込み金額・成約確率・ステータスは deal（商談）側に移動したため、
// 顧客そのものは業種・企業規模・所在地のみを持つ（AGENTS.mdの正規化方針に合わせた）。
// industry_id/company_size_id を名称に解決するAPIがまだ無いため、当面は数値のまま扱う。
export type Customer = {
  customer_id: number;
  customer_name: string;
  industry_id: number;
  company_size_id: number;
  location: string;
  primary_rep_id: number | null;
};

export type Product = {
  product_id: number;
  product_name: string;
  subcategory_id: number;
  subcategory_name: string;
  category_id: number;
  category_name: string;
};

export type Deal = {
  deal_id: number;
  customer_id: number;
  customer_name: string;
  rep_id: number;
  deal_phase_id: number;
  deal_phase_name: string;
  deal_result_status_id: number;
  deal_result_status_name: string;
  product_id: number;
  product_name: string;
  estimated_amount: number;
  win_probability: number;
  expected_visit_count: number;
  expected_effort_hours: number;
  deal_start_date: string; // "YYYY-MM-DD"
  contract_date: string | null;
};

export type DealResultStatus = "pending" | "won" | "lost" | "postponed";

export type ActivityPlan = {
  plan_id: number;
  rep_id: number;
  plan_date: string; // "YYYY-MM-DD"
  start_time: string | null; // "HH:MM"（日表示のスケジュール用。バックエンドにはまだ無い）
  customer_id: number | null;
  customer_name: string;
  deal_id: number | null;
  product_name: string | null;
  activity_type_name: string;
  priority: number;
  expected_amount: number;
  expected_probability: number; // 0-100
  is_ai_generated: boolean;
  reasoning_text: string;
  result_status: DealResultStatus;
};

export type ReplanInfo = {
  before_achievement_rate: number;
  after_achievement_rate: number;
  reason: string;
};

export type PlanVariant = {
  variant_id: string;
  label: string;
  description: string;
  plans: ActivityPlan[];
};
