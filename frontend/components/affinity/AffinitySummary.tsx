import { rankAffinities } from "@/lib/affinityRanking";
import type { RepAffinity } from "@/types";

type AffinitySummaryProps = {
  affinities: RepAffinity[];
};

const TOP_COUNT = 3;

export function AffinitySummary({ affinities }: AffinitySummaryProps) {
  const ranked = rankAffinities(affinities);
  const totalDealCount = ranked.reduce((sum, affinity) => sum + affinity.deal_count, 0);
  const totalWonCount = ranked.reduce((sum, affinity) => sum + affinity.won_count, 0);
  const overallWinRate = totalDealCount > 0 ? totalWonCount / totalDealCount : 0;

  // 「自己分析」は成約実績があってこその強みなので、勝率0%の組み合わせはTOP3から除く
  const topAffinities = ranked.filter((affinity) => affinity.won_count > 0).slice(0, TOP_COUNT);

  // pattern_name は "新規開拓・大型" のように「新規開拓/既存深耕」+「大型/小口」を
  // ・区切りで持っているため、前半だけで新規/既存それぞれの商談数・成約数を集計する
  const newAffinities = ranked.filter((affinity) => affinity.pattern_name.startsWith("新規開拓"));
  const newDealCount = newAffinities.reduce((sum, affinity) => sum + affinity.deal_count, 0);
  const newWonCount = newAffinities.reduce((sum, affinity) => sum + affinity.won_count, 0);
  const existingDealCount = totalDealCount - newDealCount;
  const existingWonCount = totalWonCount - newWonCount;
  const newWinRate = newDealCount > 0 ? newWonCount / newDealCount : 0;
  const existingWinRate = existingDealCount > 0 ? existingWonCount / existingDealCount : 0;
  const newRatioPercent = totalDealCount > 0 ? Math.round((newDealCount / totalDealCount) * 100) : 0;
  const existingRatioPercent = 100 - newRatioPercent;

  if (ranked.length === 0) {
    return null;
  }

  return (
    <section className="panel affinity-summary">
      <h2>サマリー</h2>
      <dl className="affinity-summary__totals">
        <div>
          <dt>全体の成約率</dt>
          <dd>{Math.round(overallWinRate * 100)}%</dd>
        </div>
        <div>
          <dt>成約数</dt>
          <dd>{totalWonCount}件</dd>
        </div>
        <div>
          <dt>商談数</dt>
          <dd>{totalDealCount}件</dd>
        </div>
      </dl>

      <h3 className="affinity-summary__subheading">新規開拓・既存深耕の割合(商談数ベース)</h3>
      <div className="affinity-summary__ratio-bar">
        {newRatioPercent > 0 && (
          <div
            className="affinity-summary__ratio-segment affinity-summary__ratio-segment--new"
            style={{ "--ratio-width": `${newRatioPercent}%` } as React.CSSProperties}
          />
        )}
        {existingRatioPercent > 0 && (
          <div
            className="affinity-summary__ratio-segment affinity-summary__ratio-segment--existing"
            style={{ "--ratio-width": `${existingRatioPercent}%` } as React.CSSProperties}
          />
        )}
      </div>
      <dl className="affinity-summary__ratio-legend">
        <div className="affinity-summary__ratio-legend-item affinity-summary__ratio-legend-item--new">
          <dt>新規開拓</dt>
          <dd>
            <strong>{newDealCount}件</strong>(成約率 {Math.round(newWinRate * 100)}%)
          </dd>
        </div>
        <div className="affinity-summary__ratio-legend-item affinity-summary__ratio-legend-item--existing">
          <dt>既存深耕</dt>
          <dd>
            <strong>{existingDealCount}件</strong>(成約率 {Math.round(existingWinRate * 100)}%)
          </dd>
        </div>
      </dl>

      <h3 className="affinity-summary__subheading">自己分析TOP{TOP_COUNT}</h3>
      {topAffinities.length === 0 ? (
        <p className="activity-plan-list__empty">まだ成約実績がありません</p>
      ) : (
        <ol className="affinity-summary__top-list">
          {topAffinities.map((affinity, index) => (
            <li
              key={`${affinity.industry_name}-${affinity.category_name}-${affinity.pattern_name}`}
              className="affinity-summary__top-item"
            >
              <span className="affinity-summary__top-label">
                <span className="affinity-summary__top-rank">{index + 1}.</span>
                {affinity.industry_name}・{affinity.category_name}
                <span className="affinity-ranking__pattern">({affinity.pattern_name})</span>
              </span>
              <span className="affinity-summary__top-rate">
                {affinity.won_count}/{affinity.deal_count}件({Math.round(affinity.win_rate * 100)}%)
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
