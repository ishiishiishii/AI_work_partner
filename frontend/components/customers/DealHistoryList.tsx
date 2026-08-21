import type { Deal } from "@/types";

type DealHistoryListProps = {
  deals: Deal[];
};

const STATUS_CLASS: Record<number, string> = {
  1: "in_progress",
  2: "won",
  3: "lost",
};

function formatYen(amount: number): string {
  return `¥${amount.toLocaleString("ja-JP")}`;
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const weekday = "日月火水木金土"[date.getDay()];
  return `${date.getMonth() + 1}/${date.getDate()}(${weekday})`;
}

export function DealHistoryList({ deals }: DealHistoryListProps) {
  const sorted = [...deals].sort((a, b) => b.deal_start_date.localeCompare(a.deal_start_date));

  if (sorted.length === 0) {
    return <p className="activity-plan-list__empty">商談履歴はまだありません</p>;
  }

  return (
    <ul className="deal-history">
      {sorted.map((deal) => (
        <li key={deal.deal_id} className="deal-history__item">
          <div className="deal-history__date">{formatDate(deal.deal_start_date)}</div>
          <div className="deal-history__main">
            <div className="deal-history__head">
              <span className="deal-history__type">{deal.product_name}</span>
              <span
                className={`deal-history__status deal-history__status--${
                  STATUS_CLASS[deal.deal_result_status_id] ?? "in_progress"
                }`}
              >
                {deal.deal_result_status_name}
              </span>
            </div>
            <p className="deal-history__note">
              {deal.deal_phase_name}・成約確率{deal.win_probability}%
              {deal.contract_date && `・契約日 ${formatDate(deal.contract_date)}`}
            </p>
          </div>
          <div className="deal-history__amount">{formatYen(deal.estimated_amount)}</div>
        </li>
      ))}
    </ul>
  );
}
