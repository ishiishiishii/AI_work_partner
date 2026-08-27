export type AddType = "plan" | "customer" | "deadline" | "deal";

export const ADD_TYPE_LABELS: Record<AddType, string> = {
  plan: "予定",
  customer: "新規顧客",
  deadline: "期限",
  deal: "商談",
};
