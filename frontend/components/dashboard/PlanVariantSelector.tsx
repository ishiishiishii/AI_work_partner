import { calcAchievementRate, calcForecastAmount } from "@/lib/forecast";
import type { PlanVariant } from "@/types";

type PlanVariantSelectorProps = {
  variants: PlanVariant[];
  activeVariantId: string;
  targetAmount: number;
  onSelect: (variantId: string) => void;
};

function formatYen(amount: number): string {
  return `¥${amount.toLocaleString("ja-JP")}`;
}

export function PlanVariantSelector({
  variants,
  activeVariantId,
  targetAmount,
  onSelect,
}: PlanVariantSelectorProps) {
  return (
    <section className="panel plan-variant-selector">
      <h2>AIが提案する計画プラン</h2>
      <div className="plan-variant-selector__cards">
        {variants.map((variant) => {
          const forecastAmount = calcForecastAmount(variant.plans);
          const achievementRate = calcAchievementRate(variant.plans, targetAmount);
          const isActive = variant.variant_id === activeVariantId;

          return (
            <div
              key={variant.variant_id}
              className={`plan-variant-selector__card${isActive ? " is-active" : ""}`}
            >
              <div className="plan-variant-selector__label">{variant.label}</div>
              <p className="plan-variant-selector__description">{variant.description}</p>
              <dl className="plan-variant-selector__stats">
                <div>
                  <dt>件数</dt>
                  <dd>{variant.plans.length}件</dd>
                </div>
                <div>
                  <dt>見込み売上</dt>
                  <dd>{formatYen(forecastAmount)}</dd>
                </div>
                <div>
                  <dt>達成見込み</dt>
                  <dd>{achievementRate.toFixed(1)}%</dd>
                </div>
              </dl>
              <button
                type="button"
                className="plan-variant-selector__select"
                onClick={() => onSelect(variant.variant_id)}
                disabled={isActive}
              >
                {isActive ? "使用中" : "このプランを使う"}
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}
