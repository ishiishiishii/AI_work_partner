import {
  DEAL_PATTERN_NAMES,
  DEAL_PHASE_NAMES,
  DEAL_RESULT_STATUS_NAMES,
  INDUSTRY_NAMES,
} from "@/lib/mockData";
import type {
  ActivityPlan,
  Customer,
  Deal,
  DealResultStatus,
  Product,
  RepAffinity,
  SalesTarget,
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
  industry_id: number;
  company_size_id: number;
  location: string;
  primary_rep_id: number | null;
};

function mapCustomer(row: ApiCustomer): Customer {
  return {
    customer_id: row.customer_id,
    customer_name: row.customer_name,
    industry_id: row.industry_id,
    company_size_id: row.company_size_id,
    location: row.location,
    primary_rep_id: row.primary_rep_id,
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

async function fetchCustomerNames(repId: number): Promise<Map<number, string>> {
  const customers = await fetchCustomers(repId);
  return new Map(customers.map((customer) => [customer.customer_id, customer.customer_name]));
}

type ApiPlan = {
  plan_id: number;
  rep_id: number;
  plan_date: string;
  customer_id: number | null;
  deal_id: number | null;
  activity_type: string;
  priority: number;
  expected_amount: string | number;
  expected_probability: number;
  plan_status: string;
  is_ai_generated: boolean;
  rationale: string | null;
  product_id: number | null;
  product_name: string | null;
};

// plan_status からは成約/失注/延期の区別まではわからないため、
// 取得直後は常に「未入力」として扱う。実際の結果はボタン操作で記録する。
function mapPlan(row: ApiPlan, customerNames: Map<number, string>): ActivityPlan {
  return {
    plan_id: row.plan_id,
    rep_id: row.rep_id,
    plan_date: row.plan_date,
    start_time: null,
    customer_id: row.customer_id,
    customer_name: (row.customer_id && customerNames.get(row.customer_id)) || "(顧客不明)",
    deal_id: row.deal_id,
    product_name: row.product_name,
    activity_type_name: toActivityTypeName(row.activity_type),
    priority: row.priority,
    expected_amount: Number(row.expected_amount),
    expected_probability: row.expected_probability,
    is_ai_generated: row.is_ai_generated,
    reasoning_text: row.rationale ?? "",
    result_status: "pending",
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
): Promise<void> {
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
  rep_id: number;
  deal_phase_id: number;
  deal_result_status_id: number;
  product_id: number;
  estimated_amount: string | number;
  win_probability: string | number;
  expected_visit_count: number;
  expected_effort_hours: string | number;
  deal_start_date: string;
  contract_date: string | null;
};

export async function fetchDeals(repId: number): Promise<Deal[]> {
  const base = getApiBaseUrl();
  const [dealsRes, products, customerNames] = await Promise.all([
    fetch(`${base}/api/deals?rep_id=${repId}`, { cache: "no-store" }),
    fetchProducts(),
    fetchCustomerNames(repId),
  ]);
  if (!dealsRes.ok) throw new Error(`商談一覧の取得に失敗しました (HTTP ${dealsRes.status})`);
  const rows: ApiDeal[] = await dealsRes.json();
  const productNames = new Map(products.map((product) => [product.product_id, product.product_name]));

  return rows.map((row) => ({
    deal_id: row.deal_id,
    customer_id: row.customer_id,
    customer_name: customerNames.get(row.customer_id) ?? "(顧客不明)",
    rep_id: row.rep_id,
    deal_phase_id: row.deal_phase_id,
    deal_phase_name: DEAL_PHASE_NAMES[row.deal_phase_id] ?? "不明",
    deal_result_status_id: row.deal_result_status_id,
    deal_result_status_name: DEAL_RESULT_STATUS_NAMES[row.deal_result_status_id] ?? "不明",
    product_id: row.product_id,
    product_name: productNames.get(row.product_id) ?? "(商品不明)",
    estimated_amount: Number(row.estimated_amount),
    win_probability: Number(row.win_probability),
    expected_visit_count: row.expected_visit_count,
    expected_effort_hours: Number(row.expected_effort_hours),
    deal_start_date: row.deal_start_date,
    contract_date: row.contract_date,
  }));
}

type ApiRepAffinity = {
  rep_id: number;
  industry_id: number;
  category_id: number;
  pattern_id: number;
  deal_count: number;
  won_count: number;
  win_rate: string | number;
  avg_won_amount: string | number;
  affinity_score: string | number;
};

export async function fetchRepAffinity(repId: number): Promise<RepAffinity[]> {
  const base = getApiBaseUrl();
  const [affinityRes, products] = await Promise.all([
    fetch(`${base}/api/reps/${repId}/affinity`, { cache: "no-store" }),
    fetchProducts(),
  ]);
  if (!affinityRes.ok) throw new Error(`得意分野スコアの取得に失敗しました (HTTP ${affinityRes.status})`);
  const rows: ApiRepAffinity[] = await affinityRes.json();
  const categoryNames = new Map(products.map((product) => [product.category_id, product.category_name]));

  return rows.map((row) => ({
    rep_id: row.rep_id,
    industry_id: row.industry_id,
    industry_name: INDUSTRY_NAMES[row.industry_id] ?? "不明",
    category_id: row.category_id,
    category_name: categoryNames.get(row.category_id) ?? "不明",
    pattern_id: row.pattern_id,
    pattern_name: DEAL_PATTERN_NAMES[row.pattern_id] ?? "不明",
    deal_count: row.deal_count,
    won_count: row.won_count,
    win_rate: Number(row.win_rate),
    avg_won_amount: Number(row.avg_won_amount),
    affinity_score: Number(row.affinity_score),
  }));
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
