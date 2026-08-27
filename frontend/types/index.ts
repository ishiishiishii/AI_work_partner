export type SalesRep = {
  rep_id: number;
  rep_name: string;
  branch_id: number;
  branch_name: string;
};

// 担当者の営業所(branch)が管轄する都道府県一覧。GET /api/reps/{rep_id}/territory が返す。
export type Territory = {
  branch_name: string;
  prefectures: string[];
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
  open_plan_count: number; // まだ結果未入力の予定件数
};

// AI 参照用の第一正規形ビュー(ai.rep_affinity)の形にそのまま対応させている。
// 自己分析の判定は業種・商材カテゴリ・案件パターンの組み合わせなので、名前解決済みの
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

// 曜日ごとの在宅可否と、事務作業タスク種別ごとの所要時間見積もり。
// 将来的にルート計画(work_start/work_end/turnaround_buffer_min)の初期値に
// 反映する想定だが、現時点では表示・記録のみで route_planning 側は未連携。
export type AdminTaskType = {
  task_type_id: number;
  task_name: string;
  is_default: boolean;
};

export type RepHomeOfficeDay = {
  day_of_week: number; // 0=月, 1=火, ... 6=日
  is_home_available: boolean;
};

export type RepAdminTaskDuration = {
  task_type_id: number;
  task_name: string;
  duration_minutes: number | null;
};

export type RepProfile = {
  rep_id: number;
  home_office: RepHomeOfficeDay[];
  task_durations: RepAdminTaskDuration[];
};

// 見込み金額・成約確率・ステータスは deal（商談）側に移動したため、
// 顧客そのものは業種・企業規模・所在地のみを持つ（AGENTS.mdの正規化方針に合わせた）。
// industry_name/company_size_name はバックエンドの AI 参照用ビュー(ai.customer)が
// 名称まで解決して返すため、ここでは id を持たずそのまま表示に使う。
// in_territory: 所在地が担当者の管轄支店(prefecture/branchマスタ)に含まれるか。
// 既存の関係(担当者紐付け・商談履歴)がある顧客は、エリア外でも一覧からは除外され
// ない(転勤等でエリア外に既存顧客が残るケースがあるため)。false の場合はその
// 「エリア外だが関係がある」ケースなので、フロント側で別枠表示に使う。
// has_relationship: この担当者に紐付いている(primary_rep_id一致)か、この担当者
// との商談履歴があるか。in_territory=true かつ has_relationship=false は、
// 「自分のエリア内だが担当していない」未接触の候補顧客。
export type Customer = {
  customer_id: number;
  customer_name: string;
  industry_name: string;
  company_size_name: string;
  location: string;
  primary_rep_id: number | null;
  primary_rep_name: string | null;
  in_territory: boolean;
  has_relationship: boolean;
  website: string | null;
  contact_name: string | null;
  // 市区町村レベルの実座標(国土地理院APIでジオコーディング済みの場合のみ)。
  // 未ジオコーディングの間はnull。地図表示では lib/geo.ts の coordinatesForCustomer が
  // nullの場合に都道府県+ランダムズレへフォールバックする。
  lat: number | null;
  lng: number | null;
};

// 新規顧客登録フォームの「顧客名で検索」候補。他の担当者が登録済みの同名顧客
// から業種/企業規模/所在地などを丸ごと流用するため、名称だけでなくidも持つ
// (CustomerとちがいIDが要るのはフォームのセレクトボックスへ反映するため)。
export type CustomerSuggestion = {
  customer_id: number;
  customer_name: string;
  industry_id: number;
  industry_name: string;
  company_size_id: number;
  company_size_name: string;
  location: string;
  website: string | null;
  contact_name: string | null;
};

// 休眠顧客(しばらく接点の無い顧客)一覧。Customer に加えて最終接点日と
// 経過日数を持つ(接点が一度も無ければ last_contact_date は null)。
export type StaleCustomer = Customer & {
  last_contact_date: string | null; // "YYYY-MM-DD"
  days_since_contact: number | null;
};

export type Product = {
  product_id: number;
  product_name: string;
  subcategory_id: number;
  subcategory_name: string;
  category_id: number;
  category_name: string;
  description: string;
  price_min: number;
  price_max: number;
  lead_time_days: number;
  features: string[];
};

// 新規顧客登録・商談登録/編集フォームのセレクトボックス用マスタ。GET /api/masters が返す。
export type Industry = {
  industry_id: number;
  industry_name: string;
};

export type CompanySize = {
  company_size_id: number;
  company_size_name: string;
};

export type DealPhase = {
  deal_phase_id: number;
  deal_phase_name: string;
};

export type Masters = {
  industries: Industry[];
  company_sizes: CompanySize[];
  deal_phases: DealPhase[];
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
  cost: number; // 原価。ユーザー入力ではなくバックエンドが自動算出(見込み金額の50〜95%)
  profit: number; // 見込み利益 = estimated_amount - cost(DB側のgenerated column)
  actual_amount: number | null; // 実際の契約金額。成約(won)時のみ値を持つ
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
  memo: string | null; // 企業訪問での自由メモ
  progress_percent: number; // 0-100。事務作業を確定した後の進捗表示に使う
};

export type TransitLeg = {
  mode: string;
  departure_at: string;
  arrival_at: string;
  scheduled_departure_at: string;
  scheduled_arrival_at: string;
  departure_delay_sec: number;
  arrival_delay_sec: number;
  duration_sec: number;
  scheduled_duration_sec: number;
  distance_m: number;
  from_name: string;
  to_name: string;
  from_stop_id: string | null;
  to_stop_id: string | null;
  from_platform: string | null;
  to_platform: string | null;
  route_name: string | null;
  route_id: string | null;
  headsign: string | null;
  trip_id: string | null;
  real_time: boolean;
};

export type TransitItinerary = {
  departure_at: string;
  arrival_at: string;
  requested_departure_at: string;
  planned_arrival_at: string;
  duration_sec: number;
  scheduled_duration_sec: number;
  distance_m: number;
  walk_distance_m: number;
  contingency_buffer_min: number;
  appointment_wait_min: number;
  real_time: boolean;
  data_status: string;
  legs: TransitLeg[];
};

export type RoutePlanStop = {
  visit_order: number;
  customer_id: number;
  customer_name: string;
  deal_ids: number[];
  phase_names: string[];
  arrival_at: string;
  departure_at: string;
  visit_duration_min: number;
  turnaround_buffer_min: number;
  leg_travel_min: number;
  leg_distance_m: number;
  leg_details?: TransitItinerary;
  economics: {
    planned_sales: number;
    planned_gross_profit: number | null;
    gross_profit_margin: number | null;
    expected_sales: number;
    expected_gross_profit: number | null;
    value_score: number;
    gross_profit_available: boolean;
    salesperson_fit_score: number;
    affinity_matches: Array<{
      industry_name: string;
      category_name: string;
      deal_count: number;
      won_count: number;
      win_rate: number;
      match_score: number;
    }>;
  };
  selection_reason: string;
  latitude: number;
  longitude: number;
};

export type RoutePlanEndpoint = {
  kind: "branch" | "custom";
  label: string;
  address: string;
  latitude: number;
  longitude: number;
  geocode_accuracy?: string;
};

export type RoutePlanSearchArea = {
  kind: "auto" | "custom";
  label: string;
  query: string | null;
  latitude: number;
  longitude: number;
  radius_km: number | null;
  geocode_accuracy?: string;
};

export type RoutePlanPreview = {
  plan_id: number;
  status: "proposed" | "failed";
  rep_id: number;
  rep_name: string;
  target_date: string;
  branch: {
    branch_id: number;
    branch_name: string;
    location: string;
    latitude: number;
    longitude: number;
  };
  start_location: RoutePlanEndpoint;
  end_location: RoutePlanEndpoint;
  search_area: RoutePlanSearchArea;
  travel_mode: "driving" | "transit" | "walking" | "cycling";
  break_time: { start: string; end: string } | null;
  realism: {
    turnaround_buffer_min: number;
    travel_time_buffer_percent: number;
    access_buffer_min: number;
    return_buffer_min: number;
  };
  policy: "balanced" | "sales" | "gross_profit" | "short_travel";
  weights: {
    sales: number;
    gross_profit: number;
    affinity: number;
    urgency: number;
    phase: number;
    target_gap: number;
  };
  work_start: string;
  work_end: string;
  target_met: boolean;
  shortfalls: {
    expected_sales: number;
    expected_gross_profit: number;
  };
  totals: {
    planned_sales: number;
    planned_gross_profit: number | null;
    expected_sales: number;
    expected_gross_profit: number | null;
    total_travel_min: number;
    total_distance_m: number;
    total_wait_min: number;
    total_turnaround_min: number;
    visit_count: number;
    route_end_at: string;
  };
  stops: RoutePlanStop[];
  return_leg: TransitItinerary | null;
  options: Array<{
    rank: number;
    selected: boolean;
    cp_sat_status: string;
    routing_status: string;
    business_value: number;
    rejection_reason: string | null;
  }>;
  selection_reason: string;
  excluded_reasons: string[];
  warnings: string[];
};

// 汎用のタスク期限。activity_planとは別で、顧客/商談との紐付けは任意。
export type Deadline = {
  deadline_id: number;
  rep_id: number;
  title: string;
  due_date: string; // "YYYY-MM-DD"
  customer_id: number | null;
  deal_id: number | null;
  is_done: boolean;
  memo: string | null;
};

export type ReplanInfo = {
  before_achievement_rate: number;
  after_achievement_rate: number;
  reason: string;
};
