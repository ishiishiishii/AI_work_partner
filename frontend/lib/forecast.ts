import type { ActivityPlan } from "@/types";

export function calcForecastAmount(plans: ActivityPlan[]): number {
  return plans.reduce((sum, plan) => {
    if (plan.result_status === "won") return sum + plan.expected_amount;
    if (plan.result_status === "lost") return sum;
    return sum + plan.expected_amount * (plan.expected_probability / 100);
  }, 0);
}

export function calcAchievementRate(plans: ActivityPlan[], targetAmount: number): number {
  if (targetAmount <= 0) return 0;
  return (calcForecastAmount(plans) / targetAmount) * 100;
}
