import { formatDate, getRange, type ViewMode } from "@/lib/dateRange";
import { useRouteBatchPlan } from "@/lib/routeBatchPlanContext";
import type { ActivityPlan, RoutePlanPortfolioCustomer } from "@/types";

type AiReasoningPanelProps = {
  plans: ActivityPlan[];
  viewMode: ViewMode;
  selectedDate: string;
};

type ReasonEntry = { key: string; customerName: string; text: string };

const HEADINGS: Record<ViewMode, string> = {
  day: "今日の営業活動についての理由",
  week: "なぜこの企業に行くことを提案したか",
  month: "企業を選んだ理由",
};

function customerEntries(customers: RoutePlanPortfolioCustomer[]): ReasonEntry[] {
  return customers.map((customer) => ({
    key: String(customer.customer_id),
    customerName: customer.customer_name,
    text: customer.selection_reason,
  }));
}

export function AiReasoningPanel({ plans, viewMode, selectedDate }: AiReasoningPanelProps) {
  const { batch, weekBatches } = useRouteBatchPlan();
  const range = getRange(viewMode, selectedDate);
  const heading =
    viewMode === "day"
      ? `${formatDate(selectedDate)}の営業活動についての理由`
      : HEADINGS[viewMode];

  let entries: ReasonEntry[] = [];
  let emptyMessage = "";

  if (viewMode === "day") {
    entries = [...plans]
      .filter((plan) => plan.is_ai_generated && plan.plan_date === selectedDate)
      .sort((a, b) => a.priority - b.priority)
      .map((plan) => ({ key: String(plan.plan_id), customerName: plan.customer_name, text: plan.reasoning_text }));
    emptyMessage = "この日のAI提案予定はまだありません。";
  } else if (viewMode === "month") {
    if (batch && batch.start_date <= range.end && batch.end_date >= range.start) {
      entries = customerEntries(batch.selected_customers);
    }
    emptyMessage = "この月の月間営業スケジュールがまだ作成されていません。";
  } else {
    const week = batch?.weeks.find((candidate) => candidate.start_date <= selectedDate && selectedDate <= candidate.end_date);
    const weekBatch = week ? weekBatches[week.week_number] : undefined;
    if (weekBatch) {
      entries = weekBatch.weeks[0].days.flatMap((day) =>
        day.stops.map((stop) => ({
          key: `${day.target_date}-${stop.customer_id}`,
          customerName: stop.customer_name,
          text: stop.selection_reason,
        })),
      );
    } else if (week) {
      const assignedCustomers = (batch?.selected_customers ?? []).filter((customer) =>
        customer.assigned_dates.some((date) => date >= week.start_date && date <= week.end_date),
      );
      entries = customerEntries(assignedCustomers);
    }
    emptyMessage = week
      ? "この週はまだ計算されていません。月間営業スケジュールで計算してください。"
      : "この週の月間営業スケジュールがまだ作成されていません。";
  }

  return (
    <section className="panel ai-reasoning">
      <h2>{heading}</h2>

      {entries.length === 0 ? (
        <p className="ai-reasoning__empty">{emptyMessage}</p>
      ) : (
        <ul className="ai-reasoning__list">
          {entries.map((entry) => (
            <li key={entry.key} className="ai-reasoning__item">
              <span className="ai-reasoning__customer">{entry.customerName}</span>
              <p className="ai-reasoning__text">{entry.text}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
