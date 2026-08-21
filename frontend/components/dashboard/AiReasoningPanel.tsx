import type { ActivityPlan, RepAffinity } from "@/types";

type AiReasoningPanelProps = {
  plans: ActivityPlan[];
  affinities: RepAffinity[];
};

export function AiReasoningPanel({ plans, affinities }: AiReasoningPanelProps) {
  const aiPlans = [...plans]
    .filter((plan) => plan.is_ai_generated)
    .sort((a, b) => a.priority - b.priority);

  const sortedAffinities = [...affinities].sort((a, b) => b.score - a.score);

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

      <h3 className="ai-reasoning__subheading">得意分野スコア</h3>
      <ul className="ai-reasoning__affinities">
        {sortedAffinities.map((affinity) => (
          <li key={affinity.category_id} className="ai-reasoning__affinity">
            <span className="ai-reasoning__affinity-label">{affinity.category_name}</span>
            <div className="ai-reasoning__affinity-track">
              <div
                className="ai-reasoning__affinity-fill"
                style={{ width: `${affinity.score}%` }}
              />
            </div>
            <span className="ai-reasoning__affinity-score">{affinity.score}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
