"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { DealHistoryList } from "@/components/customers/DealHistoryList";
import { NewDealForm } from "@/components/customers/NewDealForm";
import { createDeal, fetchCustomers, fetchDeals } from "@/lib/api";
import { useRep } from "@/lib/repContext";
import type { Customer, Deal } from "@/types";

export default function CustomerDetailPage() {
  const { customerId } = useParams<{ customerId: string }>();
  const { selectedRep } = useRep();
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [deals, setDeals] = useState<Deal[]>([]);

  const REP_ID = selectedRep?.rep_id ?? null;

  useEffect(() => {
    if (REP_ID === null) return;
    const repId = REP_ID;
    let cancelled = false;
    const targetId = Number(customerId);

    async function load() {
      try {
        setIsLoading(true);
        setLoadError(null);
        const [customers, repDeals] = await Promise.all([fetchCustomers(repId), fetchDeals(repId)]);
        if (cancelled) return;
        setCustomer(customers.find((item) => item.customer_id === targetId) ?? null);
        setDeals(repDeals.filter((deal) => deal.customer_id === targetId));
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
  }, [REP_ID, customerId]);

  async function handleCreateDeal(input: {
    product_id: number;
    deal_phase_id: number;
    estimated_amount: number;
    win_probability: number;
    expected_visit_count: number;
    expected_effort_hours: number;
    deal_start_date?: string;
  }) {
    if (REP_ID === null || !customer) return;
    const created = await createDeal(REP_ID, { ...input, customer_id: customer.customer_id });
    setDeals((prev) => [...prev, created]);
  }

  if (!selectedRep || isLoading) {
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

  return (
    <main>
      <Link href="/customers" className="customer-detail__back">
        ← 顧客一覧に戻る
      </Link>
      <h1>{customer.customer_name}</h1>
      <p>
        {customer.industry_name}・{customer.location}
      </p>

      <section className="panel">
        <dl className="goal-card__numbers customer-detail__summary">
          <div>
            <dt>企業規模</dt>
            <dd>{customer.company_size_name}</dd>
          </div>
          <div>
            <dt>業種</dt>
            <dd>{customer.industry_name}</dd>
          </div>
          <div>
            <dt>所在地</dt>
            <dd>{customer.location}</dd>
          </div>
        </dl>
      </section>

      <section className="panel">
        <h2>商談履歴</h2>
        <DealHistoryList deals={deals} />
      </section>

      <NewDealForm onCreate={handleCreateDeal} />
    </main>
  );
}
