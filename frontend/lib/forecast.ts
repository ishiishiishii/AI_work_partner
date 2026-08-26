import type { ActivityPlan, Deal } from "@/types";

export function calcForecastAmount(plans: ActivityPlan[]): number {
  return plans.reduce((sum, plan) => {
    if (plan.result_status === "lost") return sum;
    return sum + plan.expected_amount;
  }, 0);
}

// 見込み粗利。plan は cost/profit を持たないため、紐づくdeal(deal.profit =
// estimated_amount - cost)から引く。deal_idが無い予定(事務作業など)は0円扱い
export function calcForecastProfit(plans: ActivityPlan[], deals: Deal[]): number {
  const dealById = new Map(deals.map((deal) => [deal.deal_id, deal]));
  return plans.reduce((sum, plan) => {
    if (plan.result_status === "lost" || plan.deal_id === null) return sum;
    const deal = dealById.get(plan.deal_id);
    return deal ? sum + deal.profit : sum;
  }, 0);
}

export function calcAchievementRate(plans: ActivityPlan[], targetAmount: number): number {
  if (targetAmount <= 0) return 0;
  return (calcForecastAmount(plans) / targetAmount) * 100;
}

// 「現在の実績」= 成約(won)が確定した予定の金額のみ(見込みの計画は含めない)
export function calcActualAchievedAmount(plans: ActivityPlan[]): number {
  return plans.reduce((sum, plan) => {
    if (plan.result_status !== "won") return sum;
    return sum + plan.expected_amount;
  }, 0);
}

export function calcActualAchievementRate(plans: ActivityPlan[], targetAmount: number): number {
  if (targetAmount <= 0) return 0;
  return (calcActualAchievedAmount(plans) / targetAmount) * 100;
}
