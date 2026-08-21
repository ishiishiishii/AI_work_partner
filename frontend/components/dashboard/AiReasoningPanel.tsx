import type { ActivityPlan, RepAffinity } from "@/types";

type AiReasoningPanelProps = {
  plans: ActivityPlan[];
  affinities: RepAffinity[];
};

function formatYen(amount: number): string {
  return `¥${amount.toLocaleString("ja-JP")}`;
}

const TOP_AFFINITY_COUNT = 5;

export function AiReasoningPanel({ plans, affinities }: AiReasoningPanelProps) {
  const aiPlans = [...plans]
    .filter((plan) => plan.is_ai_generated)
    .sort((a, b) => a.priority - b.priority);

  // 実績が無い(deal_count=0)組み合わせは比較にならないので除外し、スコア順で上位のみ見せる
  const topAffinities = [...affinities]
    .filter((affinity) => affinity.deal_count > 0)
    .sort((a, b) => b.affinity_score - a.affinity_score)
    .slice(0, TOP_AFFINITY_COUNT);
  const maxScore = Math.max(...topAffinities.map((affinity) => affinity.affinity_score), 1);

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

      <h3 className="ai-reasoning__subheading">得意分野スコア(過去の成約実績から算出)</h3>
      {topAffinities.length === 0 ? (
        <p className="activity-plan-list__empty">まだ成約・失注の実績がありません</p>
      ) : (
        <ul className="ai-reasoning__affinities">
          {topAffinities.map((affinity) => (
            <li
              key={`${affinity.industry_id}-${affinity.category_id}-${affinity.pattern_id}`}
              className="ai-reasoning__affinity"
            >
              <span className="ai-reasoning__affinity-label">
                {affinity.industry_name}・{affinity.category_name}
                <span className="ai-reasoning__affinity-pattern">({affinity.pattern_name})</span>
              </span>
              <div className="ai-reasoning__affinity-track">
                <div
                  className="ai-reasoning__affinity-fill"
                  style={{ width: `${(affinity.affinity_score / maxScore) * 100}%` }}
                />
              </div>
              <span className="ai-reasoning__affinity-score">
                勝率{Math.round(affinity.win_rate * 100)}%・平均{formatYen(affinity.avg_won_amount)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
