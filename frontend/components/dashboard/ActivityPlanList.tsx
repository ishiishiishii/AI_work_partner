import type { ActivityPlan, DealResultStatus } from "@/types";

type ActivityPlanListProps = {
  plans: ActivityPlan[];
  onResultChange: (planId: number, status: DealResultStatus) => void;
};

const RESULT_OPTIONS: { value: DealResultStatus; label: string }[] = [
  { value: "won", label: "成約" },
  { value: "lost", label: "失注" },
  { value: "postponed", label: "延期" },
];

function formatYen(amount: number): string {
  return `¥${amount.toLocaleString("ja-JP")}`;
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const weekday = "日月火水木金土"[date.getDay()];
  return `${date.getMonth() + 1}/${date.getDate()}(${weekday})`;
}

export function ActivityPlanList({ plans, onResultChange }: ActivityPlanListProps) {
  const sorted = [...plans].sort(
    (a, b) => a.plan_date.localeCompare(b.plan_date) || a.priority - b.priority,
  );

  return (
    <section className="panel activity-plan-list">
      <h2>今週の活動計画</h2>
      <ul className="activity-plan-list__items">
        {sorted.map((plan) => (
          <li key={plan.plan_id} className="activity-plan-list__item">
            <div className="activity-plan-list__date">{formatDate(plan.plan_date)}</div>
            <div className="activity-plan-list__main">
              <div className="activity-plan-list__customer">
                {plan.customer_name}
                {plan.is_ai_generated && <span className="badge badge--ai">AI提案</span>}
              </div>
              <div className="activity-plan-list__meta">
                {plan.activity_type_name}・優先度{plan.priority}・成約確率
                {plan.expected_probability.toFixed(0)}%
              </div>
            </div>
            <div className="activity-plan-list__amount">{formatYen(plan.expected_amount)}</div>
            <div className="activity-plan-list__result-buttons">
              {plan.result_status === "pending" ? (
                RESULT_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    className="activity-plan-list__result-button"
                    onClick={() => onResultChange(plan.plan_id, option.value)}
                  >
                    {option.label}
                  </button>
                ))
              ) : (
                <>
                  <span
                    className={`activity-plan-list__result-button is-active is-active--${plan.result_status}`}
                  >
                    {RESULT_OPTIONS.find((option) => option.value === plan.result_status)?.label}
                  </span>
                  <button
                    type="button"
                    className="activity-plan-list__undo-button"
                    onClick={() => onResultChange(plan.plan_id, plan.result_status)}
                  >
                    取り消す
                  </button>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
