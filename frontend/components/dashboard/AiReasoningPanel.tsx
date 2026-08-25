import type { ActivityPlan } from "@/types";

type AiReasoningPanelProps = {
  plans: ActivityPlan[];
};

export function AiReasoningPanel({ plans }: AiReasoningPanelProps) {
  const aiPlans = [...plans]
    .filter((plan) => plan.is_ai_generated)
    .sort((a, b) => a.priority - b.priority);

  return (
    <section className="panel ai-reasoning">
      <h2>この計画にした理由</h2>

      <ul className="ai-reasoning__list">
        {aiPlans.map((plan) => (
          <li key={plan.plan_id} className="ai-reasoning__item">
            <span className="ai-reasoning__customer">{plan.customer_name}</span>
            <p className="ai-reasoning__text">{plan.reasoning_text}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
