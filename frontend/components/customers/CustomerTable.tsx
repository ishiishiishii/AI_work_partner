import type { Customer } from "@/types";

type CustomerTableProps = {
  customers: Customer[];
};

const STATUS_LABELS: Record<Customer["status"], string> = {
  prospect: "見込み客",
  active: "取引中",
  dormant: "休眠",
  churned: "離反",
};

function formatYen(amount: number): string {
  return `¥${amount.toLocaleString("ja-JP")}`;
}

export function CustomerTable({ customers }: CustomerTableProps) {
  const sorted = [...customers].sort(
    (a, b) => b.estimated_amount * b.win_probability - a.estimated_amount * a.win_probability,
  );

  if (sorted.length === 0) {
    return <p className="activity-plan-list__empty">登録されている顧客がありません</p>;
  }

  return (
    <ul className="customer-table">
      {sorted.map((customer) => (
        <li key={customer.customer_id} className="customer-table__row">
          <div className="customer-table__main">
            <div className="customer-table__name">
              {customer.customer_name}
              <span className={`badge customer-table__status--${customer.status}`}>
                {STATUS_LABELS[customer.status]}
              </span>
            </div>
            <div className="customer-table__meta">
              {customer.industry ?? "業種未設定"}・{customer.location ?? "所在地未設定"}
            </div>
          </div>

          <div className="customer-table__amount">{formatYen(customer.estimated_amount)}</div>

          <div className="customer-table__probability">
            <div className="customer-table__probability-track">
              <div
                className="customer-table__probability-fill"
                style={{ width: `${customer.win_probability}%` }}
              />
            </div>
            <span>{customer.win_probability}%</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
