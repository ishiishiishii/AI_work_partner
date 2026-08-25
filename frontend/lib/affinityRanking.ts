import type { RepAffinity } from "@/types";

// 実績が無い(deal_count=0)組み合わせは比較にならないので除外する。
// 成約率だけで並べると 1/1(100%)のような母数の小さい特殊例が最上位に来てしまうため、
// 成約数(実績の多さ)を優先し、同数なら成約率、さらに同率なら商談数・スコアの順で判定する。
export function rankAffinities(affinities: RepAffinity[]): RepAffinity[] {
  return [...affinities]
    .filter((affinity) => affinity.deal_count > 0)
    .sort(
      (a, b) =>
        b.won_count - a.won_count ||
        b.win_rate - a.win_rate ||
        b.deal_count - a.deal_count ||
        b.affinity_score - a.affinity_score,
    );
}
