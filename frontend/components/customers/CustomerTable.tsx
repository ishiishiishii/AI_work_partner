import Link from "next/link";
import { COMPANY_SIZE_NAMES, INDUSTRY_NAMES } from "@/lib/mockData";
import type { Customer } from "@/types";

type CustomerTableProps = {
  customers: Customer[];
};

export function CustomerTable({ customers }: CustomerTableProps) {
  const sorted = [...customers].sort((a, b) => a.customer_name.localeCompare(b.customer_name, "ja"));

  if (sorted.length === 0) {
    return <p className="activity-plan-list__empty">登録されている顧客がありません</p>;
  }

  return (
    <ul className="customer-table">
      {sorted.map((customer) => (
        <li key={customer.customer_id} className="customer-table__row">
          <div className="customer-table__main">
            <div className="customer-table__name">
              <Link href={`/customers/${customer.customer_id}`}>{customer.customer_name}</Link>
              <span className="badge customer-table__size">
                {COMPANY_SIZE_NAMES[customer.company_size_id] ?? "規模不明"}
              </span>
            </div>
            <div className="customer-table__meta">
              {INDUSTRY_NAMES[customer.industry_id] ?? "業種不明"}・{customer.location}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
