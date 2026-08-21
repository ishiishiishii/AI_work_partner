export type SalesRep = {
  rep_id: number;
  rep_name: string;
  department_id: number;
  manager_rep_id: number | null;
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

export type DealResultStatus = "pending" | "won" | "lost" | "postponed";

export type ActivityPlan = {
  plan_id: number;
  rep_id: number;
  plan_date: string; // "YYYY-MM-DD"
  customer_id: number;
  customer_name: string;
  deal_id: number | null;
  activity_type_id: number;
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
