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

export type RepAffinity = {
  rep_id: number;
  category_id: number;
  category_name: string;
  score: number; // 0-100
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

export type DealHistoryStatus = "in_progress" | "won" | "lost" | "postponed";

export type DealHistoryItem = {
  history_id: string;
  date: string; // "YYYY-MM-DD"
  activity_type_name: string;
  status: DealHistoryStatus;
  amount: number;
  note: string;
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
