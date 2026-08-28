import type { DealEditFields } from "@/components/customers/DealHistoryList";
import { getAccessToken } from "@/lib/supabase";
import type { RoutePlanBatchPreview, RoutePlanPreview, RoutePlanWeekAlternative } from "@/types";
import { DEAL_RESULT_STATUS_NAMES } from "@/lib/mockData";
import type {
  ActivityPlan,
  ActivityPlanCategory,
  AdminTaskType,
  Customer,
  CustomerSuggestion,
  Deadline,
  Deal,
  DealResultStatus,
  Forecast,
  Masters,
  Product,
  RepAffinity,
  RepProfile,
  SalesRep,
  SalesTarget,
  StaleCustomer,
  Territory,
} from "@/types";

export function getApiBaseUrl(): string {
  if (typeof window === "undefined") {
    return process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  }
  const configured = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  try {
    const url = new URL(configured);
    const pageHost = window.location.hostname;
    const isLoopback = (host: string) => host === "localhost" || host === "127.0.0.1";
    const isPrivateIpv4 = (host: string) => {
      const octets = host.split(".").map(Number);
      if (octets.length !== 4 || octets.some((value) => !Number.isInteger(value) || value < 0 || value > 255)) {
        return false;
      }
      return (
        octets[0] === 10 ||
        (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31) ||
        (octets[0] === 192 && octets[1] === 168)
      );
    };
    // Codespaces-style forwarding gives the web page and the API distinct
    // real hostnames on purpose (a separate subdomain per port -- see
    // .devcontainer/write-codespace-env.sh) -- leave those alone. Only
    // rewrite when either side is a bare loopback address that doesn't
    // actually describe where the browser is: e.g. NEXT_PUBLIC_API_URL baked
    // in as a LAN IP for direct-LAN demos, while this browser reached the
    // page through a localhost-forwarded tunnel instead (or the reverse,
    // the original case this handled) -- swap in whichever host the page
    // itself was actually loaded from. A configured private-LAN address also
    // follows the page host so the same build works over Tailscale when Wi-Fi
    // client isolation blocks direct device-to-device traffic.
    if (
      pageHost !== url.hostname &&
      (isLoopback(pageHost) || isLoopback(url.hostname) || isPrivateIpv4(url.hostname))
    ) {
      url.hostname = pageHost;
    }
    return url.origin;
  } catch {
    return configured;
  }
}

export async function fetchReps(): Promise<SalesRep[]> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/reps`, { cache: "no-store" });
  if (!res.ok) throw new Error(`担当者一覧の取得に失敗しました (HTTP ${res.status})`);
  return res.json();
}

// 担当者の営業所が管轄する都道府県一覧(地図の表示範囲・顧客の絞り込みに使う)。
export async function fetchRepTerritory(repId: number): Promise<Territory> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/reps/${repId}/territory`, { cache: "no-store" });
  if (!res.ok) throw new Error(`担当エリアの取得に失敗しました (HTTP ${res.status})`);
  return res.json();
}

// 業種・企業規模・商談フェーズのマスタ一覧(新規登録・編集フォームのセレクトボックス用)。
// 以前は supabase/seed.sql の投入順を前提にフロントへハードコードしていた
// (frontend/lib/mockData.ts の旧 INDUSTRY_NAMES 等)。
export async function fetchMasters(): Promise<Masters> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/masters`, { cache: "no-store" });
  if (!res.ok) throw new Error(`マスタ一覧の取得に失敗しました (HTTP ${res.status})`);
  return res.json();
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
  target_gross_profit: string | number | null;
};

function mapTarget(row: ApiTarget): SalesTarget {
  return {
    rep_id: row.rep_id,
    target_month: row.target_month,
    target_amount: Number(row.target_amount),
    target_deal_count: row.target_deal_count,
    target_gross_profit: row.target_gross_profit === null ? null : Number(row.target_gross_profit),
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
  // バックエンドはPATCHではなく全量upsertなので、この画面で編集していない
  // フィールドも呼び出し側が必ず現在値を詰めて送ること。target_gross_profit を
  // 省略すると、次の保存で無条件にNULL(粗利目標なし)へ消えてしまう。
  input: { target_amount: number; target_deal_count: number; target_gross_profit: number | null },
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
      target_gross_profit: input.target_gross_profit,
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
  in_territory: boolean;
  has_relationship: boolean;
  website: string | null;
  contact_name: string | null;
  lat?: number | null;
  lng?: number | null;
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
    in_territory: row.in_territory,
    has_relationship: row.has_relationship,
    website: row.website,
    contact_name: row.contact_name,
    lat: row.lat ?? null,
    lng: row.lng ?? null,
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
    website?: string | null;
    contact_name?: string | null;
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
      website: input.website || null,
      contact_name: input.contact_name || null,
    }),
  });
  if (!res.ok) throw new Error(`顧客の登録に失敗しました (HTTP ${res.status})`);
  return mapCustomer(await res.json());
}

type ApiCustomerSuggestion = {
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

// 新規顧客登録フォームの「顧客名で検索」用。担当エリアに関わらず全社の登録済み
// 顧客から部分一致で探す(他の担当者の重複登録に気づけるようにするため)。
export async function searchCustomers(query: string): Promise<CustomerSuggestion[]> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/customers/search?q=${encodeURIComponent(query)}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`顧客の検索に失敗しました (HTTP ${res.status})`);
  const rows: ApiCustomerSuggestion[] = await res.json();
  return rows;
}

type ApiDeadline = {
  deadline_id: number;
  rep_id: number;
  title: string;
  due_date: string;
  customer_id: number | null;
  deal_id: number | null;
  is_done: boolean;
  memo: string | null;
};

function mapDeadline(row: ApiDeadline): Deadline {
  return {
    deadline_id: row.deadline_id,
    rep_id: row.rep_id,
    title: row.title,
    due_date: row.due_date,
    customer_id: row.customer_id,
    deal_id: row.deal_id,
    is_done: row.is_done,
    memo: row.memo,
  };
}

export async function createDeadline(
  repId: number,
  input: { title: string; due_date: string; memo: string | null },
): Promise<Deadline> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/deadlines`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rep_id: repId,
      title: input.title,
      due_date: input.due_date,
      memo: input.memo,
    }),
  });
  if (!res.ok) throw new Error(`期限の登録に失敗しました (HTTP ${res.status})`);
  return mapDeadline(await res.json());
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
  progress_percent: number;
  memo: string | null;
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
    memo: row.memo,
    progress_percent: row.progress_percent,
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

// 成約・失注などの実績確定後に、当日以降のAI生成予定だけを残目標から組み直す。
// 手動予定はバックエンド側で保持されるため、結果入力による自動再計画専用として
// /plans/generate と呼び分ける。
export async function replanActivityPlans(repId: number, targetMonth: string): Promise<void> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/plans/replan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rep_id: repId, target_month: targetMonth }),
  });
  if (!res.ok) throw new Error(`自動再計画に失敗しました (HTTP ${res.status})`);
}

// 予定の手動追加の保存。title/customer_id/deal_id の扱いは updatePlan と同じ考え方
// (title があれば表示上そちらを優先するが、customer_id/deal_id が分かっていれば
// 商談への紐付けとして残す)。createPlan(差し替え提案の永続化用。plan_id しか返らない)
// とは用途が異なるため名前を分けている。
export async function createManualPlan(
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
    product_name: string | null;
    expected_amount: number;
    expected_probability: number;
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
        product_name_override: input.product_name,
        expected_amount: input.expected_amount,
        expected_probability: input.expected_probability,
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
    expected_amount: number;
    expected_probability: number;
    memo: string | null;
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
      expected_amount: updates.expected_amount,
      expected_probability: updates.expected_probability,
      memo: updates.memo,
    }),
  });
  if (!res.ok) throw new Error(`予定の更新に失敗しました (HTTP ${res.status})`);
}

// 事務作業の進捗スライダーは操作中に何度も onChange が飛ぶため、呼び出し側は
// ドラッグ完了時(onMouseUp/onTouchEnd)にだけこれを呼ぶこと。
export async function updatePlanProgress(
  repId: number,
  planId: number,
  progressPercent: number,
): Promise<void> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/plans/${planId}/progress?rep_id=${repId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ progress_percent: progressPercent }),
  });
  if (!res.ok) throw new Error(`進捗の保存に失敗しました (HTTP ${res.status})`);
}

export async function createPlan(
  repId: number,
  input: {
    plan_date: string;
    start_time?: string | null;
    end_time?: string | null;
    category: ActivityPlanCategory;
    activity_type: string;
    customer_id: number | null;
    deal_id: number | null;
    priority: number;
    expected_amount?: number;
    expected_probability?: number;
    rationale?: string | null;
    title?: string | null;
  },
): Promise<{ plan_id: number }> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/plans`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rep_id: repId, ...input }),
  });
  if (!res.ok) throw new Error(`予定の作成に失敗しました (HTTP ${res.status})`);
  return res.json();
}

// 「対応が難しい」で差し替えられた予定の取り消し用。ソフトキャンセル(plan_status='cancelled')
// なので、一覧には出なくなるが記録自体は残る。
export async function cancelPlan(repId: number, planId: number): Promise<void> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/plans/${planId}?rep_id=${repId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`予定の取り消しに失敗しました (HTTP ${res.status})`);
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
  product_id: number;
  deal_phase_id: number;
  cost: string | number;
  profit: string | number;
  expected_close_date: string | null;
  next_action: string | null;
  actual_amount: string | number | null;
  memo: string | null;
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
    product_id: row.product_id,
    product_name: row.product_name,
    subcategory_name: row.subcategory_name,
    category_name: row.category_name,
    deal_phase_id: row.deal_phase_id,
    estimated_amount: Number(row.estimated_amount),
    win_probability: Number(row.win_probability),
    expected_visit_count: row.expected_visit_count,
    expected_effort_hours: Number(row.expected_effort_hours),
    deal_start_date: row.deal_start_date,
    contract_date: row.contract_date,
    cost: Number(row.cost),
    profit: Number(row.profit),
    expected_close_date: row.expected_close_date,
    next_action: row.next_action,
    actual_amount: row.actual_amount === null ? null : Number(row.actual_amount),
    memo: row.memo,
  };
}

export async function fetchDeals(filters: { repId?: number; customerId?: number }): Promise<Deal[]> {
  const base = getApiBaseUrl();
  const params = new URLSearchParams();
  if (filters.repId != null) params.set("rep_id", String(filters.repId));
  if (filters.customerId != null) params.set("customer_id", String(filters.customerId));
  const res = await fetch(`${base}/api/deals?${params.toString()}`, { cache: "no-store" });
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
    expected_visit_count: number;
    expected_effort_hours: number;
    deal_start_date?: string;
    expected_close_date?: string;
    next_action?: string;
    memo?: string;
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
      expected_visit_count: input.expected_visit_count,
      expected_effort_hours: input.expected_effort_hours,
      deal_start_date: input.deal_start_date || null,
      expected_close_date: input.expected_close_date || null,
      next_action: input.next_action || null,
      memo: input.memo || null,
    }),
  });
  if (!res.ok) {
    const body: { detail?: string } = await res.json().catch(() => ({}));
    throw new Error(body.detail || `商談の登録に失敗しました (HTTP ${res.status})`);
  }
  return mapDeal(await res.json());
}

export async function updateDeal(
  repId: number,
  dealId: number,
  updates: DealEditFields,
): Promise<Deal> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/deals/${dealId}?rep_id=${repId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error(`商談の更新に失敗しました (HTTP ${res.status})`);
  return mapDeal(await res.json());
}

export async function deleteDeal(repId: number, dealId: number): Promise<void> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/deals/${dealId}?rep_id=${repId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`商談の削除に失敗しました (HTTP ${res.status})`);
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
  if (!res.ok) throw new Error(`自己分析スコアの取得に失敗しました (HTTP ${res.status})`);
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

export type CustomerWinRate = {
  customer_id: number;
  closed_count: number;
  won_count: number;
  win_rate: number | null;
};

export async function fetchCustomerWinRate(customerId: number): Promise<CustomerWinRate> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/customers/${customerId}/win-rate`, { cache: "no-store" });
  if (!res.ok) throw new Error(`成約率の取得に失敗しました (HTTP ${res.status})`);
  return res.json();
}

type ApiForecast = {
  rep_id: number;
  target_month: string;
  target_amount: string | number;
  expected_amount: string | number;
  attainment_ratio: number;
  open_plan_count: number;
  target_gross_profit: string | number | null;
  expected_gross_profit: string | number;
  gross_profit_attainment_ratio: number | null;
  sales_achievement_probability: number;
  profit_achievement_probability: number | null;
  joint_achievement_probability: number;
  sales_gap_amount: string | number;
  profit_gap_amount: string | number | null;
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
    open_plan_count: row.open_plan_count,
    target_gross_profit: row.target_gross_profit === null ? null : Number(row.target_gross_profit),
    forecast_profit_amount: Number(row.expected_gross_profit),
    gross_profit_achievement_rate:
      row.gross_profit_attainment_ratio === null ? null : row.gross_profit_attainment_ratio * 100,
    sales_achievement_probability: row.sales_achievement_probability * 100,
    profit_achievement_probability:
      row.profit_achievement_probability === null ? null : row.profit_achievement_probability * 100,
    joint_achievement_probability: row.joint_achievement_probability * 100,
    sales_gap_amount: Number(row.sales_gap_amount),
    profit_gap_amount: row.profit_gap_amount === null ? null : Number(row.profit_gap_amount),
  };
}

// 自己分析スコアはバックエンドの計算結果をキャッシュしたテーブルのため、
// 表示前に最新の商談結果を反映させておく
export async function recalculateRepAffinity(repId: number): Promise<void> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/reps/affinity/recalculate?rep_id=${repId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`自己分析スコアの再計算に失敗しました (HTTP ${res.status})`);
}

export async function fetchAdminTaskTypes(): Promise<AdminTaskType[]> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/admin-task-types`, { cache: "no-store" });
  if (!res.ok) throw new Error(`事務作業タスク一覧の取得に失敗しました (HTTP ${res.status})`);
  return res.json();
}

export async function createAdminTaskType(taskName: string): Promise<AdminTaskType> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/admin-task-types`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_name: taskName }),
  });
  if (!res.ok) throw new Error(`タスクの追加に失敗しました (HTTP ${res.status})`);
  return res.json();
}

export async function fetchRepProfile(repId: number): Promise<RepProfile> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/reps/${repId}/profile`, { cache: "no-store" });
  if (!res.ok) throw new Error(`プロフィール(今後拡張予定)の取得に失敗しました (HTTP ${res.status})`);
  return res.json();
}

export async function saveHomeOfficeAvailability(
  repId: number,
  dayOfWeek: number,
  isHomeAvailable: boolean,
): Promise<void> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/reps/${repId}/home-office`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ day_of_week: dayOfWeek, is_home_available: isHomeAvailable }),
  });
  if (!res.ok) throw new Error(`在宅可否の保存に失敗しました (HTTP ${res.status})`);
}

export async function saveAdminTaskDuration(
  repId: number,
  taskTypeId: number,
  durationMinutes: number,
): Promise<void> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/reps/${repId}/task-durations/${taskTypeId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ duration_minutes: durationMinutes }),
  });
  if (!res.ok) throw new Error(`所要時間の保存に失敗しました (HTTP ${res.status})`);
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
  // ブラウザから FastAPI の localhost:8000 を直接参照すると、別PCでの
  // デモ時にそのPC自身へ接続してしまう。Next.js の同一オリジン経由で中継する。
  const token = await getAccessToken();
  const res = await fetch("/api/ai/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
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



async function routePlanError(res: Response, fallback: string): Promise<Error> {
  const body: { detail?: string | { message?: string } } = await res.json().catch(() => ({}));
  const detail =
    typeof body.detail === "string" ? body.detail : body.detail?.message;
  return new Error(detail || `${fallback} (HTTP ${res.status})`);
}

export async function previewSalesRoutePlan(input: {
  target_date: string;
  policy: RoutePlanPreview["policy"];
  sales_weight_percent?: number;
  gross_profit_weight_percent?: number;
  max_visits: number;
  travel_mode: RoutePlanPreview["travel_mode"];
  start_location: { kind: "branch" | "custom"; address?: string };
  end_location: { kind: "branch" | "custom"; address?: string };
  search_area: { kind: "auto" | "custom"; query?: string; radius_km?: number };
  break_enabled: boolean;
  break_start: string;
  break_end: string;
  turnaround_buffer_min: number;
  travel_time_buffer_percent: number;
  access_buffer_min: number;
  return_buffer_min: number;
  min_expected_sales?: number;
  min_expected_gross_profit?: number;
}): Promise<RoutePlanPreview> {
  const token = await getAccessToken();
  const res = await fetch(`${getApiBaseUrl()}/api/route-plans/preview`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw await routePlanError(res, "営業ルート案の作成に失敗しました");
  return res.json();
}

export async function approveSalesRoutePlan(
  planId: number,
): Promise<{ plan_id: number; status: "approved"; activity_plan_ids: number[] }> {
  const token = await getAccessToken();
  const res = await fetch(`${getApiBaseUrl()}/api/route-plans/${planId}/approve`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw await routePlanError(res, "営業ルート案の承認に失敗しました");
  return res.json();
}

export async function approveIdleSalesRouteDay(
  batchId: number,
  targetDate: string,
): Promise<{
  target_date: string;
  status: "approved";
  activity_plan_ids: number[];
  summary: string;
}> {
  const token = await getAccessToken();
  const res = await fetch(`${getApiBaseUrl()}/api/route-plans/idle-day/approve`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ batch_id: batchId, target_date: targetDate }),
  });
  if (!res.ok) throw await routePlanError(res, "商談なし日のAI活動計画の採用に失敗しました");
  return res.json();
}

export async function rejectSalesRoutePlan(planId: number): Promise<void> {
  const token = await getAccessToken();
  const res = await fetch(`${getApiBaseUrl()}/api/route-plans/${planId}/reject`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw await routePlanError(res, "営業ルート案の却下に失敗しました");
}

export async function previewSalesRouteBatch(input: {
  start_date: string;
  end_date?: string;
  horizon: RoutePlanBatchPreview["horizon"];
  outline_only?: boolean;
  detailed_days?: number;
  portfolio_assignments?: Array<{ customer_id: number; visit_count: number }>;
  target_amount_override?: number;
  target_gross_profit_override?: number;
  policy: RoutePlanBatchPreview["policy"];
  sales_weight_percent?: number;
  gross_profit_weight_percent?: number;
  max_visits: number;
  travel_mode: RoutePlanPreview["travel_mode"];
  start_location: { kind: "branch" | "custom"; address?: string };
  end_location: { kind: "branch" | "custom"; address?: string };
  search_area: { kind: "auto" | "custom"; query?: string; radius_km?: number };
  break_enabled: boolean;
  break_start: string;
  break_end: string;
  turnaround_buffer_min: number;
  travel_time_buffer_percent: number;
  access_buffer_min: number;
  return_buffer_min: number;
  min_expected_sales?: number;
  min_expected_gross_profit?: number;
}): Promise<RoutePlanBatchPreview> {
  const token = await getAccessToken();
  const res = await fetch(`${getApiBaseUrl()}/api/route-plans/batch-preview`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw await routePlanError(res, "週・月の営業ルート案の作成に失敗しました");
  return res.json();
}

export async function selectSalesRouteWeekAlternative(
  planIds: number[],
): Promise<RoutePlanWeekAlternative> {
  const token = await getAccessToken();
  const res = await fetch(`${getApiBaseUrl()}/api/route-plans/week-alternative`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ plan_ids: planIds, minimum_economic_ratio: 0.9 }),
  });
  if (!res.ok) throw await routePlanError(res, "週の別案取得に失敗しました");
  return res.json();
}
