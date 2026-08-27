import Link from "next/link";
import { companySizeBadgeClass } from "@/lib/companySize";
import { industryHue } from "@/lib/industryColor";
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
            <Link href={`/customers/${customer.customer_id}`} className="customer-table__name">
              {customer.customer_name}
            </Link>
            <div className="customer-table__tags">
              <span
                className="badge badge--industry"
                style={{ "--industry-hue": industryHue(customer.industry_name) } as React.CSSProperties}
              >
                {customer.industry_name}
              </span>
              <span className={`badge customer-table__size ${companySizeBadgeClass(customer.company_size_name)}`}>
                {customer.company_size_name}
              </span>
            </div>
          </div>
          <div className="customer-table__location">{customer.location}</div>
        </li>
      ))}
    </ul>
  );
}
