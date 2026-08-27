import type { ActivityPlan, Deal, DealResultStatus } from "@/types";

// 同じ商談に複数の予定(訪問+関連タスク等)が紐づく場合、商談単位で1回だけ数える。
// 状態が割れている場合は won > 進行中 > lost の優先順で代表の予定を選ぶ。
function statusPriority(status: DealResultStatus): number {
  if (status === "won") return 2;
  if (status === "lost") return 0;
  return 1; // pending, postponed
}

function isBetterDealRepresentative(candidate: ActivityPlan, current: ActivityPlan): boolean {
  const candidatePriority = [
    statusPriority(candidate.result_status),
    candidate.category === "visit" ? 1 : 0,
    candidate.expected_amount,
  ];
  const currentPriority = [
    statusPriority(current.result_status),
    current.category === "visit" ? 1 : 0,
    current.expected_amount,
  ];
  for (let index = 0; index < candidatePriority.length; index += 1) {
    if (candidatePriority[index] !== currentPriority[index]) {
      return candidatePriority[index] > currentPriority[index];
    }
  }
  return false;
}

function uniqueByDeal(plans: ActivityPlan[]): ActivityPlan[] {
  const dealless = plans.filter((plan) => plan.deal_id === null);
  const bestByDeal = new Map<number, ActivityPlan>();
  for (const plan of plans) {
    if (plan.deal_id === null) continue;
    const current = bestByDeal.get(plan.deal_id);
    if (!current || isBetterDealRepresentative(plan, current)) {
      bestByDeal.set(plan.deal_id, plan);
    }
  }
  return [...dealless, ...bestByDeal.values()];
}

// 成約(won)の金額は、plan.expected_amount(計画作成時点の見込みのスナップショット)
// ではなく、記録されていればdeal.actual_amount(実際の契約金額)を優先する
function wonAmount(plan: ActivityPlan, dealById: Map<number, Deal>): number {
  const deal = plan.deal_id !== null ? dealById.get(plan.deal_id) : undefined;
  return deal?.actual_amount ?? plan.expected_amount;
}

// 成約(won)は実契約金額(未記録ならexpected_amount)、進行中(pending/postponed)は
// 成約確度(expected_probability)で重み付けした期待値、失注(lost)は0円として合算する。
// deal_idの無い予定(次回予定作成時に参考としてコピーされただけの商品・金額など)は
// 実体の商談が存在せず成約しようがないため、expected_amountを入力していても見込みには
// 一切加算しない
export function calcForecastAmount(plans: ActivityPlan[], deals: Deal[]): number {
  const dealById = new Map(deals.map((deal) => [deal.deal_id, deal]));
  return uniqueByDeal(plans).reduce((sum, plan) => {
    if (plan.deal_id === null) return sum;
    if (plan.result_status === "lost") return sum;
    if (plan.result_status === "won") return sum + wonAmount(plan, dealById);
    return sum + plan.expected_amount * (plan.expected_probability / 100);
  }, 0);
}

// 見込み粗利。plan は cost/profit を持たないため、紐づくdeal(deal.profit =
// estimated_amount - cost)から引く。deal_idが無い予定(事務作業など)は0円扱い
export function calcForecastProfit(plans: ActivityPlan[], deals: Deal[]): number {
  const dealById = new Map(deals.map((deal) => [deal.deal_id, deal]));
  return uniqueByDeal(plans).reduce((sum, plan) => {
    if (plan.result_status === "lost" || plan.deal_id === null) return sum;
    const deal = dealById.get(plan.deal_id);
    if (!deal) return sum;
    const weight = plan.result_status === "won" ? 1 : plan.expected_probability / 100;
    return sum + deal.profit * weight;
  }, 0);
}

export function calcAchievementRate(plans: ActivityPlan[], targetAmount: number, deals: Deal[]): number {
  if (targetAmount <= 0) return 0;
  return (calcForecastAmount(plans, deals) / targetAmount) * 100;
}

// 「現在の実績」= 成約(won)が確定した予定の金額のみ(見込みの計画は含めない)
export function calcActualAchievedAmount(plans: ActivityPlan[], deals: Deal[]): number {
  const dealById = new Map(deals.map((deal) => [deal.deal_id, deal]));
  return uniqueByDeal(plans).reduce((sum, plan) => {
    if (plan.result_status !== "won") return sum;
    return sum + wonAmount(plan, dealById);
  }, 0);
}

export function calcActualAchievementRate(plans: ActivityPlan[], targetAmount: number, deals: Deal[]): number {
  if (targetAmount <= 0) return 0;
  return (calcActualAchievedAmount(plans, deals) / targetAmount) * 100;
}
