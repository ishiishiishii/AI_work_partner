import { DEAL_RESULT_STATUS_NAMES } from "@/lib/mockData";
import type {
  ActivityPlan,
  ActivityPlanCategory,
  Customer,
  Deal,
  DealResultStatus,
  Forecast,
  Product,
  RepAffinity,
  SalesTarget,
  StaleCustomer,
} from "@/types";

export function getApiBaseUrl(): string {
  if (typeof window === "undefined") {
    return process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

const ACTIVITY_TYPE_LABELS: Record<string, string> = {
  visit: "訪問",
  call: "電話",
  email: "メール",
  online: "Web会議",
};

const ACTIVITY_TYPE_CODES: Record<string, string> = {
  訪問: "visit",
  電話: "call",
  メール: "email",
  Web会議: "online",
};

function toActivityTypeName(activityType: string): string {
  return ACTIVITY_TYPE_LABELS[activityType] ?? activityType;
}

export function toActivityTypeCode(activityTypeName: string): string {
  return ACTIVITY_TYPE_CODES[activityTypeName] ?? "visit";
}

type ApiTarget = {
  rep_id: number;
  target_month: string;
  target_amount: string | number;
  target_deal_count: number;
};

function mapTarget(row: ApiTarget): SalesTarget {
  return {
    rep_id: row.rep_id,
    target_month: row.target_month,
    target_amount: Number(row.target_amount),
    target_deal_count: row.target_deal_count,
  };
}

export async function fetchSalesTarget(
  repId: number,
  targetMonth: string,
): Promise<SalesTarget | null> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/targets?rep_id=${repId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`目標の取得に失敗しました (HTTP ${res.status})`);
  const rows: ApiTarget[] = await res.json();
  const row = rows.find((item) => item.target_month === targetMonth);
  return row ? mapTarget(row) : null;
}

export async function saveSalesTarget(
  repId: number,
  targetMonth: string,
  input: { target_amount: number; target_deal_count: number },
): Promise<SalesTarget> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/targets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rep_id: repId,
      target_month: targetMonth,
      target_amount: input.target_amount,
      target_deal_count: input.target_deal_count,
    }),
  });
  if (!res.ok) throw new Error(`目標の保存に失敗しました (HTTP ${res.status})`);
  return mapTarget(await res.json());
}

type ApiCustomer = {
  customer_id: number;
  customer_name: string;
  industry_name: string;
  company_size_name: string;
  location: string;
  primary_rep_id: number | null;
  primary_rep_name: string | null;
};

function mapCustomer(row: ApiCustomer): Customer {
  return {
    customer_id: row.customer_id,
    customer_name: row.customer_name,
    industry_name: row.industry_name,
    company_size_name: row.company_size_name,
    location: row.location,
    primary_rep_id: row.primary_rep_id,
    primary_rep_name: row.primary_rep_name,
  };
}

export async function fetchCustomers(repId: number): Promise<Customer[]> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/customers?rep_id=${repId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`顧客一覧の取得に失敗しました (HTTP ${res.status})`);
  const rows: ApiCustomer[] = await res.json();
  return rows.map(mapCustomer);
}

export async function createCustomer(
  repId: number,
  input: {
    customer_name: string;
    industry_id: number;
    company_size_id: number;
    location: string;
  },
): Promise<Customer> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/customers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      customer_name: input.customer_name,
      primary_rep_id: repId,
      industry_id: input.industry_id,
      company_size_id: input.company_size_id,
      location: input.location,
    }),
  });
  if (!res.ok) throw new Error(`顧客の登録に失敗しました (HTTP ${res.status})`);
  return mapCustomer(await res.json());
}

type ApiStaleCustomer = ApiCustomer & {
  last_contact_date: string | null;
  days_since_contact: number | null;
};

export async function fetchStaleCustomers(repId: number): Promise<StaleCustomer[]> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/customers/stale?rep_id=${repId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`休眠顧客一覧の取得に失敗しました (HTTP ${res.status})`);
  const rows: ApiStaleCustomer[] = await res.json();
  return rows.map((row) => ({
    ...mapCustomer(row),
    last_contact_date: row.last_contact_date,
    days_since_contact: row.days_since_contact,
  }));
}

async function fetchCustomerNames(repId: number): Promise<Map<number, string>> {
  const customers = await fetchCustomers(repId);
  return new Map(customers.map((customer) => [customer.customer_id, customer.customer_name]));
}

type ApiPlan = {
  plan_id: number;
  rep_id: number;
  plan_date: string;
  start_time: string | null;
  end_time: string | null;
  category: ActivityPlanCategory;
  title: string | null;
  customer_id: number | null;
  deal_id: number | null;
  activity_type: string;
  priority: number;
  expected_amount: string | number;
  expected_probability: number;
  plan_status: string;
  is_ai_generated: boolean;
  rationale: string | null;
  product_name: string | null;
};

// plan_status からは成約/失注/延期の区別まではわからないため、
// 取得直後は常に「未入力」として扱う。実際の結果はボタン操作で記録する。
// customer_name は、顧客に紐づかない予定(category='task')では title を、
// 商談に紐づく予定では customer_id から解決した名前を使う。
function mapPlan(row: ApiPlan, customerNames: Map<number, string>): ActivityPlan {
  return {
    plan_id: row.plan_id,
    rep_id: row.rep_id,
    plan_date: row.plan_date,
    start_time: row.start_time,
    end_time: row.end_time,
    category: row.category,
    customer_id: row.customer_id,
    customer_name:
      row.title || (row.customer_id && customerNames.get(row.customer_id)) || "(顧客不明)",
    deal_id: row.deal_id,
    product_name: row.product_name,
    activity_type_name: toActivityTypeName(row.activity_type),
    priority: row.priority,
    expected_amount: Number(row.expected_amount),
    expected_probability: row.expected_probability,
    is_ai_generated: row.is_ai_generated,
    reasoning_text: row.rationale ?? "",
    result_status: "pending",
    memo: null,
    progress_percent: 0,
  };
}

export async function fetchActivityPlans(repId: number): Promise<ActivityPlan[]> {
  const base = getApiBaseUrl();
  const [plansRes, customerNames] = await Promise.all([
    fetch(`${base}/api/plans?rep_id=${repId}`, { cache: "no-store" }),
    fetchCustomerNames(repId),
  ]);
  if (!plansRes.ok) throw new Error(`活動計画の取得に失敗しました (HTTP ${plansRes.status})`);
  const rows: ApiPlan[] = await plansRes.json();
  return rows.map((row) => mapPlan(row, customerNames));
}

export async function generateActivityPlans(
  repId: number,
  targetMonth: string,
): Promise<ActivityPlan[]> {
  const base = getApiBaseUrl();
  const [genRes, customerNames] = await Promise.all([
    fetch(`${base}/api/plans/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rep_id: repId, target_month: targetMonth }),
    }),
    fetchCustomerNames(repId),
  ]);
  if (!genRes.ok) throw new Error(`計画生成に失敗しました (HTTP ${genRes.status})`);
  const body: { plans: ApiPlan[] } = await genRes.json();
  return body.plans.map((row) => mapPlan(row, customerNames));
}

export async function replanActivityPlans(
  repId: number,
  targetMonth: string,
): Promise<ActivityPlan[]> {
  const base = getApiBaseUrl();
  const [replanRes, customerNames] = await Promise.all([
    fetch(`${base}/api/plans/replan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rep_id: repId, target_month: targetMonth }),
    }),
    fetchCustomerNames(repId),
  ]);
  if (!replanRes.ok) throw new Error(`再計画に失敗しました (HTTP ${replanRes.status})`);
  const body: { plans: ApiPlan[] } = await replanRes.json();
  return body.plans.map((row) => mapPlan(row, customerNames));
}

// 予定の手動追加の保存。title/customer_id/deal_id の扱いは updatePlan と同じ考え方
// (title があれば表示上そちらを優先するが、customer_id/deal_id が分かっていれば
// 商談への紐付けとして残す)。
export async function createPlan(
  repId: number,
  input: {
    plan_date: string;
    start_time: string | null;
    end_time: string | null;
    category: ActivityPlanCategory;
    activity_type_name: string;
    customer_name: string;
    customer_id: number | null;
    deal_id: number | null;
    priority: number;
  },
): Promise<ActivityPlan> {
  const base = getApiBaseUrl();
  const [res, customerNames] = await Promise.all([
    fetch(`${base}/api/plans`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        rep_id: repId,
        plan_date: input.plan_date,
        category: input.category,
        activity_type: input.activity_type_name,
        start_time: input.start_time,
        end_time: input.end_time,
        title: input.customer_name,
        customer_id: input.customer_id,
        deal_id: input.deal_id,
        priority: input.priority,
      }),
    }),
    fetchCustomerNames(repId),
  ]);
  if (!res.ok) throw new Error(`予定の追加に失敗しました (HTTP ${res.status})`);
  const row: ApiPlan = await res.json();
  return mapPlan(row, customerNames);
}

// 予定の手動編集の保存。activity_type_name/customer_name/product_name はコード変換せず
// そのまま送る(バックエンドの activity_type は自由記述で、EDITABLE_ACTIVITY_TYPES には
// visit/call/email/online のコード変換対象に無い値も含まれるため)。
export async function updatePlan(
  repId: number,
  planId: number,
  updates: {
    start_time: string | null;
    end_time: string | null;
    category: ActivityPlanCategory;
    activity_type_name: string;
    customer_name: string;
    product_name: string | null;
  },
): Promise<void> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/plans/${planId}?rep_id=${repId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      start_time: updates.start_time,
      end_time: updates.end_time,
      category: updates.category,
      activity_type: updates.activity_type_name,
      title: updates.customer_name,
      product_name_override: updates.product_name,
    }),
  });
  if (!res.ok) throw new Error(`予定の更新に失敗しました (HTTP ${res.status})`);
}

const RESULT_OUTCOME: Record<Exclude<DealResultStatus, "pending">, string> = {
  won: "won",
  lost: "lost",
  postponed: "deferred",
};

export async function postActivityResult(
  repId: number,
  plan: ActivityPlan,
  status: Exclude<DealResultStatus, "pending">,
  activityTypeName: string,
): Promise<{ result_id: number }> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/results`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rep_id: repId,
      outcome: RESULT_OUTCOME[status],
      plan_id: plan.plan_id,
      customer_id: plan.customer_id,
      deal_id: plan.deal_id,
      activity_type: toActivityTypeCode(activityTypeName),
    }),
  });
  if (!res.ok) throw new Error(`結果の登録に失敗しました (HTTP ${res.status})`);
  return res.json();
}

// 同じ結果ボタンをもう一度押したときの「取り消し」用。
// 商談/計画のステータスもバックエンド側で登録前の状態に戻る。
export async function deleteActivityResult(repId: number, resultId: number): Promise<void> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/results/${resultId}?rep_id=${repId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`結果の取り消しに失敗しました (HTTP ${res.status})`);
}

export async function fetchProducts(name?: string): Promise<Product[]> {
  const base = getApiBaseUrl();
  const query = name ? `?name=${encodeURIComponent(name)}` : "";
  const res = await fetch(`${base}/api/products${query}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`商品一覧の取得に失敗しました (HTTP ${res.status})`);
  return res.json();
}

type ApiDeal = {
  deal_id: number;
  customer_id: number;
  customer_name: string;
  rep_id: number;
  rep_name: string;
  deal_phase_name: string;
  deal_result_status: string;
  product_name: string;
  subcategory_name: string;
  category_name: string;
  estimated_amount: string | number;
  win_probability: string | number;
  expected_visit_count: number;
  expected_effort_hours: string | number;
  deal_start_date: string;
  contract_date: string | null;
};

function mapDeal(row: ApiDeal): Deal {
  return {
    deal_id: row.deal_id,
    customer_id: row.customer_id,
    customer_name: row.customer_name,
    rep_id: row.rep_id,
    rep_name: row.rep_name,
    deal_phase_name: row.deal_phase_name,
    deal_result_status: row.deal_result_status,
    deal_result_status_name: DEAL_RESULT_STATUS_NAMES[row.deal_result_status] ?? "不明",
    product_name: row.product_name,
    subcategory_name: row.subcategory_name,
    category_name: row.category_name,
    estimated_amount: Number(row.estimated_amount),
    win_probability: Number(row.win_probability),
    expected_visit_count: row.expected_visit_count,
    expected_effort_hours: Number(row.expected_effort_hours),
    deal_start_date: row.deal_start_date,
    contract_date: row.contract_date,
  };
}

export async function fetchDeals(repId: number): Promise<Deal[]> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/deals?rep_id=${repId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`商談一覧の取得に失敗しました (HTTP ${res.status})`);
  const rows: ApiDeal[] = await res.json();
  return rows.map(mapDeal);
}

export async function createDeal(
  repId: number,
  input: {
    customer_id: number;
    product_id: number;
    deal_phase_id: number;
    estimated_amount: number;
    win_probability: number;
    expected_visit_count: number;
    expected_effort_hours: number;
    deal_start_date?: string;
  },
): Promise<Deal> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/deals`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      customer_id: input.customer_id,
      rep_id: repId,
      product_id: input.product_id,
      deal_phase_id: input.deal_phase_id,
      estimated_amount: input.estimated_amount,
      win_probability: input.win_probability,
      expected_visit_count: input.expected_visit_count,
      expected_effort_hours: input.expected_effort_hours,
      deal_start_date: input.deal_start_date || null,
    }),
  });
  if (!res.ok) throw new Error(`商談の登録に失敗しました (HTTP ${res.status})`);
  return mapDeal(await res.json());
}

type ApiRepAffinity = {
  rep_id: number;
  rep_name: string;
  industry_name: string;
  category_name: string;
  pattern_name: string;
  deal_count: number;
  won_count: number;
  win_rate: string | number;
  avg_won_amount: string | number;
  affinity_score: string | number;
};

export async function fetchRepAffinity(repId: number): Promise<RepAffinity[]> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/reps/${repId}/affinity`, { cache: "no-store" });
  if (!res.ok) throw new Error(`得意分野スコアの取得に失敗しました (HTTP ${res.status})`);
  const rows: ApiRepAffinity[] = await res.json();

  return rows.map((row) => ({
    rep_id: row.rep_id,
    rep_name: row.rep_name,
    industry_name: row.industry_name,
    category_name: row.category_name,
    pattern_name: row.pattern_name,
    deal_count: row.deal_count,
    won_count: row.won_count,
    win_rate: Number(row.win_rate),
    avg_won_amount: Number(row.avg_won_amount),
    affinity_score: Number(row.affinity_score),
  }));
}

type ApiForecast = {
  rep_id: number;
  target_month: string;
  target_amount: string | number;
  expected_amount: string | number;
  attainment_ratio: number;
  open_plan_count: number;
};

// sales_target がまだ登録されていない月は 404 になる(呼び出し側でフォールバックすること)
export async function fetchForecast(repId: number, targetMonth: string): Promise<Forecast> {
  const base = getApiBaseUrl();
  const res = await fetch(
    `${base}/api/forecast?rep_id=${repId}&target_month=${targetMonth}`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error(`達成見込みの取得に失敗しました (HTTP ${res.status})`);
  const row: ApiForecast = await res.json();
  return {
    rep_id: row.rep_id,
    target_month: row.target_month,
    target_amount: Number(row.target_amount),
    forecast_amount: Number(row.expected_amount),
    achievement_rate: row.attainment_ratio * 100,
  };
}

// 得意分野スコアはバックエンドの計算結果をキャッシュしたテーブルのため、
// 表示前に最新の商談結果を反映させておく
export async function recalculateRepAffinity(repId: number): Promise<void> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/reps/affinity/recalculate?rep_id=${repId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`得意分野スコアの再計算に失敗しました (HTTP ${res.status})`);
}

export type AiChatHistoryMessage = {
  role: "user" | "assistant";
  content: string;
};

export async function askAiQuestion(
  question: string,
  history: AiChatHistoryMessage[],
  dashboard: {
    target: SalesTarget;
    achievementRate: number;
    plans: ActivityPlan[];
    affinities: RepAffinity[];
  },
): Promise<string> {
  const base = getApiBaseUrl();
  const res = await fetch(base + "/api/ai/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      history,
      context: {
        target: dashboard.target,
        achievement_rate: dashboard.achievementRate,
        plans: dashboard.plans.map((plan) => ({
          plan_id: plan.plan_id,
          plan_date: plan.plan_date,
          customer_name: plan.customer_name,
          product_name: plan.product_name,
          priority: plan.priority,
          expected_amount: plan.expected_amount,
          expected_probability: plan.expected_probability,
          rationale: plan.reasoning_text,
          result_status: plan.result_status,
        })),
        affinities: dashboard.affinities.map((affinity) => ({
          industry_name: affinity.industry_name,
          category_name: affinity.category_name,
          pattern_name: affinity.pattern_name,
          deal_count: affinity.deal_count,
          win_rate: affinity.win_rate,
          avg_won_amount: affinity.avg_won_amount,
          affinity_score: affinity.affinity_score,
        })),
      },
    }),
  });

  if (!res.ok) {
    const body: { detail?: string } = await res.json().catch(() => ({}));
    throw new Error(body.detail || "AIへの質問に失敗しました (HTTP " + res.status + ")");
  }

  const body: { answer: string } = await res.json();
  return body.answer;
}

