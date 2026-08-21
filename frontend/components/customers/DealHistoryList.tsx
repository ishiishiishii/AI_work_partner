import type { DealHistoryItem } from "@/types";

type DealHistoryListProps = {
  items: DealHistoryItem[];
};

const STATUS_LABELS: Record<DealHistoryItem["status"], string> = {
  in_progress: "進行中",
  won: "成約",
  lost: "失注",
  postponed: "延期",
};

function formatYen(amount: number): string {
  return `¥${amount.toLocaleString("ja-JP")}`;
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const weekday = "日月火水木金土"[date.getDay()];
  return `${date.getMonth() + 1}/${date.getDate()}(${weekday})`;
}

export function DealHistoryList({ items }: DealHistoryListProps) {
  const sorted = [...items].sort((a, b) => b.date.localeCompare(a.date));

  if (sorted.length === 0) {
    return <p className="activity-plan-list__empty">商談履歴はまだありません</p>;
  }

  return (
    <ul className="deal-history">
      {sorted.map((item) => (
        <li key={item.history_id} className="deal-history__item">
          <div className="deal-history__date">{formatDate(item.date)}</div>
          <div className="deal-history__main">
            <div className="deal-history__head">
              <span className="deal-history__type">{item.activity_type_name}</span>
              <span className={`deal-history__status deal-history__status--${item.status}`}>
                {STATUS_LABELS[item.status]}
              </span>
            </div>
            <p className="deal-history__note">{item.note}</p>
          </div>
          <div className="deal-history__amount">{formatYen(item.amount)}</div>
        </li>
      ))}
    </ul>
  );
}
