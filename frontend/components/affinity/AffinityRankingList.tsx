"use client";

import { useState } from "react";
import { rankAffinities } from "@/lib/affinityRanking";
import type { RepAffinity } from "@/types";

type AffinityRankingListProps = {
  affinities: RepAffinity[];
};

const PAGE_SIZE = 10;

function formatYen(amount: number): string {
  return `¥${amount.toLocaleString("ja-JP")}`;
}

export function AffinityRankingList({ affinities }: AffinityRankingListProps) {
  const ranked = rankAffinities(affinities);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  if (ranked.length === 0) {
    return <p className="activity-plan-list__empty">まだ成約・失注の実績がありません</p>;
  }

  const visible = ranked.slice(0, visibleCount);
  const remaining = ranked.length - visible.length;

  return (
    <>
      <ul className="affinity-ranking">
        {visible.map((affinity, index) => (
          <li
            key={`${affinity.industry_name}-${affinity.category_name}-${affinity.pattern_name}`}
            className="affinity-ranking__item"
          >
            <span className="affinity-ranking__rank">{index + 1}</span>
            <div className="affinity-ranking__body">
              <div className="affinity-ranking__header">
                <span className="affinity-ranking__label">
                  {affinity.industry_name}・{affinity.category_name}
                  <span className="affinity-ranking__pattern">({affinity.pattern_name})</span>
                </span>
                <span className="affinity-ranking__value">
                  {affinity.won_count}/{affinity.deal_count}件
                </span>
              </div>
              <div className="affinity-ranking__rate-row">
                <div className="affinity-ranking__rate-track">
                  <div
                    className="affinity-ranking__rate-fill"
                    style={{ width: `${Math.round(affinity.win_rate * 100)}%` }}
                  />
                </div>
                <strong className="affinity-ranking__rate-value">
                  {Math.round(affinity.win_rate * 100)}%
                </strong>
              </div>
              {affinity.won_count > 0 ? (
                <div className="affinity-ranking__stats">
                  <span className="affinity-ranking__stat">
                    平均成約額 <strong>{formatYen(affinity.avg_won_amount)}</strong>
                  </span>
                  <span className="affinity-ranking__stat">
                    スコア <strong>{formatYen(affinity.affinity_score)}</strong>
                  </span>
                </div>
              ) : (
                <span className="affinity-ranking__stat">まだ成約実績なし</span>
              )}
            </div>
          </li>
        ))}
      </ul>

      {remaining > 0 && (
        <button
          type="button"
          className="regenerate-button affinity-ranking__more"
          onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}
        >
          もっと見る(残り{remaining}件)
        </button>
      )}
    </>
  );
}
