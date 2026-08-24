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

// AI 参照用の第一正規形ビュー(ai.rep_affinity)の形にそのまま対応させている。
// 得意分野の判定は業種・商材カテゴリ・案件パターンの組み合わせなので、名前解決済みの
// 3つの名称で識別する(数値idはAIの説明文にもUIにも不要)。
export type RepAffinity = {
  rep_id: number;
  rep_name: string;
  industry_name: string;
  category_name: string;
  pattern_name: string;
  deal_count: number;
  won_count: number;
  win_rate: number; // 0-1
  avg_won_amount: number;
  affinity_score: number;
};

// 見込み金額・成約確率・ステータスは deal（商談）側に移動したため、
// 顧客そのものは業種・企業規模・所在地のみを持つ（AGENTS.mdの正規化方針に合わせた）。
// industry_name/company_size_name はバックエンドの AI 参照用ビュー(ai.customer)が
// 名称まで解決して返すため、ここでは id を持たずそのまま表示に使う。
export type Customer = {
  customer_id: number;
  customer_name: string;
  industry_name: string;
  company_size_name: string;
  location: string;
  primary_rep_id: number | null;
  primary_rep_name: string | null;
};

export type Product = {
  product_id: number;
  product_name: string;
  subcategory_id: number;
  subcategory_name: string;
  category_id: number;
  category_name: string;
};

// AI 参照用ビュー(ai.deal)の形にそのまま対応させている。deal_result_status は
// DB上の status_code("ongoing"/"won"/"lost")で、表示用の日本語名は
// deal_result_status_name に別途持たせる(mockData.DEAL_RESULT_STATUS_NAMESで解決)。
export type Deal = {
  deal_id: number;
  customer_id: number;
  customer_name: string;
  rep_id: number;
  rep_name: string;
  deal_phase_name: string;
  deal_result_status: string;
  deal_result_status_name: string;
  product_id: number; // 表示は product_name を使うが、編集フォームの送信にはIDが要る
  product_name: string;
  subcategory_name: string;
  category_name: string;
  deal_phase_id: number; // 同上(編集フォーム用)
  estimated_amount: number;
  win_probability: number;
  expected_visit_count: number;
  expected_effort_hours: number;
  deal_start_date: string; // "YYYY-MM-DD"
  contract_date: string | null;
};

export type DealResultStatus = "pending" | "won" | "lost" | "postponed";

// 企業訪問(商談)か、資料作成などの事務作業か。UI上の見た目・操作の出し分けに使う
// （customer_id/deal_idの有無とは独立。編集で種別だけ切り替えられるようにするため）
export type ActivityPlanCategory = "visit" | "task";

export type ActivityPlan = {
  plan_id: number;
  rep_id: number;
  plan_date: string; // "YYYY-MM-DD"
  start_time: string | null; // "HH:MM"（日表示のスケジュール用）
  end_time: string | null; // "HH:MM"
  category: ActivityPlanCategory;
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
