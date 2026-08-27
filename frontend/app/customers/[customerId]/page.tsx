"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { DealHistoryList, type DealEditFields } from "@/components/customers/DealHistoryList";
import { NewDealForm } from "@/components/customers/NewDealForm";
import {
  createDeal,
  deleteDeal,
  fetchCustomers,
  fetchCustomerWinRate,
  fetchDeals,
  fetchMasters,
  fetchProducts,
  updateDeal,
} from "@/lib/api";
import { useRep } from "@/lib/repContext";
import type { Customer, Deal, DealPhase, Product } from "@/types";

export default function CustomerDetailPage() {
  const { customerId } = useParams<{ customerId: string }>();
  const { selectedRep } = useRep();
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [dealPhases, setDealPhases] = useState<DealPhase[]>([]);
  const [winRate, setWinRate] = useState<{ closedCount: number; wonCount: number; rate: number | null } | null>(
    null,
  );

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
        const [customers, customerDeals, allProducts, masters] = await Promise.all([
          fetchCustomers(repId),
          fetchDeals({ customerId: targetId }),
          fetchProducts(),
          fetchMasters(),
        ]);
        if (cancelled) return;
        setCustomer(customers.find((item) => item.customer_id === targetId) ?? null);
        setDeals(customerDeals);
        setProducts(allProducts);
        setDealPhases(masters.deal_phases);

        // 付加情報なので、取得失敗でページ全体は失敗させない
        fetchCustomerWinRate(targetId)
          .then((customerWinRate) => {
            if (cancelled) return;
            setWinRate({
              closedCount: customerWinRate.closed_count,
              wonCount: customerWinRate.won_count,
              rate: customerWinRate.win_rate,
            });
          })
          .catch(() => {});
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
    expected_visit_count: number;
    expected_effort_hours: number;
    deal_start_date?: string;
    memo?: string;
  }) {
    if (REP_ID === null || !customer) return;
    const created = await createDeal(REP_ID, { ...input, customer_id: customer.customer_id });
    setDeals((prev) => [...prev, created]);
  }

  async function handleUpdateDeal(dealId: number, updates: DealEditFields) {
    if (REP_ID === null) return;
    const previousDeals = deals;
    setDeals((prev) => prev.map((deal) => (deal.deal_id === dealId ? { ...deal, ...updates } : deal)));
    try {
      const updated = await updateDeal(REP_ID, dealId, updates);
      setDeals((prev) => prev.map((deal) => (deal.deal_id === dealId ? updated : deal)));
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "商談の更新に失敗しました");
      setDeals(previousDeals);
    }
  }

  async function handleDeleteDeal(dealId: number) {
    if (REP_ID === null) return;
    const previousDeals = deals;
    setDeals((prev) => prev.filter((deal) => deal.deal_id !== dealId));
    try {
      await deleteDeal(REP_ID, dealId);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "商談の削除に失敗しました");
      setDeals(previousDeals);
    }
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
    <main className="wide-main">
      <Link href="/customers" className="customer-detail__back">
        ← 顧客一覧に戻る
      </Link>
      <h1>{customer.customer_name}</h1>
      <p>
        {customer.industry_name}・{customer.location}
      </p>

      <div className="customer-detail__layout">
        <div className="customer-detail__column">
          <section className="panel customer-detail__info">
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
              <div>
                <dt>過去の成約率</dt>
                <dd>
                  {winRate && winRate.rate !== null
                    ? `${winRate.rate}%(${winRate.closedCount}件中${winRate.wonCount}件)`
                    : "実績なし"}
                </dd>
              </div>
              <div className="customer-detail__website">
                <dt>ウェブサイト</dt>
                <dd>
                  {customer.website ? (
                    <a href={customer.website} target="_blank" rel="noopener noreferrer">
                      {customer.website}
                    </a>
                  ) : (
                    "未登録"
                  )}
                </dd>
              </div>
            </dl>
          </section>

          <NewDealForm onCreate={handleCreateDeal} />
        </div>

        <section className="panel customer-detail__deals">
          <h2>商談履歴</h2>
          <DealHistoryList
            deals={deals}
            products={products}
            dealPhases={dealPhases}
            currentRepId={REP_ID}
            onUpdateDeal={handleUpdateDeal}
            onDeleteDeal={handleDeleteDeal}
          />
        </section>
      </div>
    </main>
  );
}
