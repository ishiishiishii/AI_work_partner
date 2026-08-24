import Link from "next/link";
import type { StaleCustomer } from "@/types";

type StaleCustomerListProps = {
  customers: StaleCustomer[];
};

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const weekday = "日月火水木金土"[date.getDay()];
  return `${date.getMonth() + 1}/${date.getDate()}(${weekday})`;
}

export function StaleCustomerList({ customers }: StaleCustomerListProps) {
  // 経過日数が長い(＝接点が最も遠い)順に並べる。接点が一度も無い顧客は最優先で先頭に出す
  const sorted = [...customers].sort(
    (a, b) => (b.days_since_contact ?? Infinity) - (a.days_since_contact ?? Infinity),
  );

  if (sorted.length === 0) {
    return <p className="activity-plan-list__empty">休眠中の顧客はいません</p>;
  }

  return (
    <ul className="customer-table">
      {sorted.map((customer) => (
        <li key={customer.customer_id} className="customer-table__row">
          <div className="customer-table__main">
            <div className="customer-table__name">
              <Link href={`/customers/${customer.customer_id}`}>{customer.customer_name}</Link>
              <span className="badge customer-table__size">{customer.company_size_name}</span>
            </div>
            <div className="customer-table__meta">
              {customer.industry_name}・{customer.location}
              {" ・ "}
              {customer.last_contact_date
                ? `最終接点 ${formatDate(customer.last_contact_date)}(${customer.days_since_contact}日前)`
                : "接点なし"}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
