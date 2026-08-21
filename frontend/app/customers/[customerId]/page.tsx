"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { DealHistoryList } from "@/components/customers/DealHistoryList";
import { fetchCustomers } from "@/lib/api";
import { COMPANY_SIZE_NAMES, INDUSTRY_NAMES, mockDealHistoryFor } from "@/lib/mockData";
import { useRep } from "@/lib/repContext";
import type { Customer } from "@/types";

export default function CustomerDetailPage() {
  const { customerId } = useParams<{ customerId: string }>();
  const { selectedRep } = useRep();
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);

  useEffect(() => {
    let cancelled = false;
    const targetId = Number(customerId);

    async function load() {
      try {
        setIsLoading(true);
        setLoadError(null);
        const customers = await fetchCustomers(selectedRep.rep_id);
        if (cancelled) return;
        setCustomer(customers.find((item) => item.customer_id === targetId) ?? null);
      } catch (error) {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : "読み込みに失敗しました");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [selectedRep.rep_id, customerId]);

  if (isLoading) {
    return (
      <main>
        <p>読み込み中...</p>
      </main>
    );
  }

  if (loadError || !customer) {
    return (
      <main>
        <p className="activity-plan-list__empty">
          {loadError ? `データの取得に失敗しました(${loadError})` : "この顧客は見つかりませんでした"}
        </p>
        <Link href="/customers">← 顧客一覧に戻る</Link>
      </main>
    );
  }

  const history = mockDealHistoryFor(customer);

  return (
    <main>
      <Link href="/customers" className="customer-detail__back">
        ← 顧客一覧に戻る
      </Link>
      <h1>{customer.customer_name}</h1>
      <p>
        {INDUSTRY_NAMES[customer.industry_id] ?? "業種不明"}・{customer.location}
      </p>

      <section className="panel">
        <dl className="goal-card__numbers customer-detail__summary">
          <div>
            <dt>企業規模</dt>
            <dd>{COMPANY_SIZE_NAMES[customer.company_size_id] ?? "不明"}</dd>
          </div>
          <div>
            <dt>業種</dt>
            <dd>{INDUSTRY_NAMES[customer.industry_id] ?? "不明"}</dd>
          </div>
          <div>
            <dt>所在地</dt>
            <dd>{customer.location}</dd>
          </div>
        </dl>
      </section>

      <section className="panel">
        <h2>商談履歴</h2>
        <p className="customer-detail__mock-note">
          ※ 現在は仮のデータです。バックエンドに商談履歴を取得するAPIが追加され次第、実データに差し替えます。
        </p>
        <DealHistoryList items={history} />
      </section>
    </main>
  );
}
