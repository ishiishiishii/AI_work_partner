import type { Forecast } from "@/types";

type TeamSummaryProps = {
  branchName: string;
  forecasts: Forecast[];
};

function formatYen(amount: number): string {
  return `¥${Math.round(amount).toLocaleString("ja-JP")}`;
}

export function TeamSummary({ branchName, forecasts }: TeamSummaryProps) {
  const totalTarget = forecasts.reduce((sum, f) => sum + f.target_amount, 0);
  const totalForecast = forecasts.reduce((sum, f) => sum + f.forecast_amount, 0);
  const achievementRate = totalTarget > 0 ? (totalForecast / totalTarget) * 100 : 0;

  return (
    <section className="panel team-summary">
      <h2>{branchName}支店 合計</h2>
      <dl className="goal-card__numbers">
        <div>
          <dt>目標金額合計</dt>
          <dd>{formatYen(totalTarget)}</dd>
        </div>
        <div>
          <dt>見込み売上合計</dt>
          <dd>{formatYen(totalForecast)}</dd>
        </div>
        <div>
          <dt>達成率</dt>
          <dd>{Math.round(achievementRate)}%</dd>
        </div>
      </dl>
    </section>
  );
}
