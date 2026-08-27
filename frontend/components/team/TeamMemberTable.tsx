import type { Forecast, SalesRep } from "@/types";

export type TeamMemberRow = {
  rep: SalesRep;
  forecast: Forecast | null;
};

type TeamMemberTableProps = {
  rows: TeamMemberRow[];
};

function formatYen(amount: number): string {
  return `¥${Math.round(amount).toLocaleString("ja-JP")}`;
}

export function TeamMemberTable({ rows }: TeamMemberTableProps) {
  return (
    <section className="panel team-member-table">
      <h2>メンバー一覧</h2>
      <table className="team-member-table__table">
        <thead>
          <tr>
            <th>担当者</th>
            <th>目標金額</th>
            <th>見込み売上</th>
            <th>達成率</th>
            <th>未対応の予定</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ rep, forecast }) => (
            <tr key={rep.rep_id}>
              <td>{rep.rep_name}</td>
              {forecast ? (
                <>
                  <td>{formatYen(forecast.target_amount)}</td>
                  <td>{formatYen(forecast.forecast_amount)}</td>
                  <td>{Math.round(forecast.achievement_rate)}%</td>
                  <td>{forecast.open_plan_count}件</td>
                </>
              ) : (
                <td colSpan={4} className="team-member-table__no-target">
                  この月の目標が未設定です
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
