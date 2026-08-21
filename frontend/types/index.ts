export type SalesRep = {
  rep_id: string;
  rep_name: string;
};

export type SalesTarget = {
  rep_id: string;
  target_month: string; // "YYYY-MM"
  target_amount: number;
  target_deal_count: number;
};

export type Forecast = {
  rep_id: string;
  target_month: string;
  target_amount: number;
  forecast_amount: number;
  achievement_rate: number;
};

export type RepAffinity = {
  rep_id: string;
  category_id: number;
  category_name: string;
  score: number; // 0-100
};

export type DealResultStatus = "pending" | "won" | "lost" | "postponed";

export type ActivityPlan = {
  plan_id: string;
  rep_id: string;
  plan_date: string; // "YYYY-MM-DD"
  customer_id: string | null;
  customer_name: string;
  deal_id: string | null;
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
