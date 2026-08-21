import type { SalesTarget } from "@/types";

export function getApiBaseUrl(): string {
  if (typeof window === "undefined") {
    return process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

// バックエンド未実装のためこの場で値を返すだけのスタブ。
// 実装後は PUT /api/sales-reps/{repId}/targets/{targetMonth} を呼ぶ処理に差し替える。
export async function updateSalesTarget(
  repId: number,
  targetMonth: string,
  input: { target_amount: number; target_deal_count: number },
): Promise<SalesTarget> {
  return {
    rep_id: repId,
    target_month: targetMonth,
    target_amount: input.target_amount,
    target_deal_count: input.target_deal_count,
  };
}
