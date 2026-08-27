export type RouteEconomicPolicy = "balanced" | "sales" | "gross_profit";

export const ROUTE_ECONOMIC_POLICIES: Array<{
  value: RouteEconomicPolicy;
  label: string;
  description: string;
  salesWeightPercent: number;
}> = [
  {
    value: "balanced",
    label: "バランス",
    description: "売上と粗利を同じくらい重視",
    salesWeightPercent: 50,
  },
  {
    value: "sales",
    label: "売上重視",
    description: "売上規模を優先して顧客を選定",
    salesWeightPercent: 70,
  },
  {
    value: "gross_profit",
    label: "粗利重視",
    description: "利益への貢献を優先して顧客を選定",
    salesWeightPercent: 30,
  },
];

export function routeEconomicPolicyConfig(policy: RouteEconomicPolicy) {
  return ROUTE_ECONOMIC_POLICIES.find((item) => item.value === policy) ?? ROUTE_ECONOMIC_POLICIES[0];
}

export function routeEconomicPolicyLabel(policy: string): string {
  return ROUTE_ECONOMIC_POLICIES.find((item) => item.value === policy)?.label ?? "バランス";
}
