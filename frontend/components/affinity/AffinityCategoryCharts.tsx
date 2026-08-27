import { CategoryBarChart } from "@/components/charts/CategoryBarChart";
import type { RepAffinity } from "@/types";

type AffinityCategoryChartsProps = {
  affinities: RepAffinity[];
};

type Group = { dealCount: number; wonCount: number };

// pattern_name(新規開拓/既存深耕 × 大型/小口)をまたいで、業界別・商品カテゴリ別に
// 成約率を集計する。実績が無い(deal_count=0)組み合わせは元データに含まれないため、
// ここに出てくるのは実際に商談実績がある業界・カテゴリのみ
function groupWinRate(affinities: RepAffinity[], key: "industry_name" | "category_name") {
  const groups = new Map<string, Group>();
  for (const affinity of affinities) {
    const name = affinity[key];
    const group = groups.get(name) ?? { dealCount: 0, wonCount: 0 };
    group.dealCount += affinity.deal_count;
    group.wonCount += affinity.won_count;
    groups.set(name, group);
  }
  return Array.from(groups.entries()).map(([label, group]) => ({
    label,
    count: group.dealCount,
    value: group.dealCount > 0 ? (group.wonCount / group.dealCount) * 100 : 0,
  }));
}

export function AffinityCategoryCharts({ affinities }: AffinityCategoryChartsProps) {
  const byIndustry = groupWinRate(affinities, "industry_name");
  const byCategory = groupWinRate(affinities, "category_name");

  if (byIndustry.length === 0 && byCategory.length === 0) {
    return null;
  }

  return (
    <div className="category-bar-chart__grid">
      {byIndustry.length > 0 && (
        <CategoryBarChart title="業界別の成約率" items={byIndustry} color="var(--accent)" />
      )}
      {byCategory.length > 0 && (
        <CategoryBarChart title="商品カテゴリ別の成約率" items={byCategory} color="var(--ai)" />
      )}
    </div>
  );
}
