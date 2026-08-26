"use client";

import { useEffect, useState } from "react";
import { CustomerTable } from "@/components/customers/CustomerTable";
import { StaleCustomerList } from "@/components/customers/StaleCustomerList";
import { fetchCustomers, fetchStaleCustomers } from "@/lib/api";
import { useRep } from "@/lib/repContext";
import type { Customer, StaleCustomer } from "@/types";

export default function CustomersPage() {
  const { selectedRep } = useRep();
  const REP_ID = selectedRep?.rep_id ?? null;
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [staleCustomers, setStaleCustomers] = useState<StaleCustomer[]>([]);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    if (REP_ID === null) return;
    const repId = REP_ID;
    let cancelled = false;

    async function load() {
      try {
        setIsLoading(true);
        setLoadError(null);
        const [fetched, fetchedStale] = await Promise.all([
          fetchCustomers(repId),
          fetchStaleCustomers(repId),
        ]);
        if (!cancelled) {
          setCustomers(fetched);
          setStaleCustomers(fetchedStale);
        }
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
  }, [REP_ID]);

  const normalizedQuery = searchQuery.trim().toLowerCase();
  const filteredCustomers = normalizedQuery
    ? customers.filter((customer) =>
        [customer.customer_name, customer.industry_name, customer.location, customer.company_size_name]
          .join(" ")
          .toLowerCase()
          .includes(normalizedQuery)
      )
    : customers;
  const inTerritoryCustomers = filteredCustomers.filter((customer) => customer.in_territory);
  const outOfTerritoryCustomers = filteredCustomers.filter((customer) => !customer.in_territory);
  const registeredCustomers = inTerritoryCustomers.filter((customer) => customer.has_relationship);
  const areaCandidateCustomers = inTerritoryCustomers.filter((customer) => !customer.has_relationship);

  if (!selectedRep) {
    return (
      <main>
        <h1>顧客一覧</h1>
        <p>読み込み中...</p>
      </main>
    );
  }

  return (
    <main className="wide-main">
      <h1>顧客一覧</h1>
      <p>{selectedRep.rep_name}さんが担当する顧客候補です。</p>

      {isLoading ? (
        <p>読み込み中...</p>
      ) : loadError ? (
        <p className="activity-plan-list__empty">
          データの取得に失敗しました({loadError})。バックエンド(API・Supabase)が起動しているか確認してください。
        </p>
      ) : (
        <div className="customer-grid">
          <section className="panel">
            <h2>登録済みの顧客</h2>
            <form className="product-search" onSubmit={(event) => event.preventDefault()}>
              <input
                type="text"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="顧客名・業種・所在地で検索"
              />
              {searchQuery && (
                <button type="button" className="regenerate-button" onClick={() => setSearchQuery("")}>
                  クリア
                </button>
              )}
            </form>
            {normalizedQuery && filteredCustomers.length === 0 ? (
              <p className="activity-plan-list__empty">「{searchQuery}」に一致する顧客がありません</p>
            ) : (
              <CustomerTable customers={registeredCustomers} />
            )}
          </section>

          <section className="panel">
            <h2>休眠顧客</h2>
            <p>60日以上接点の無い顧客です。フォローの優先候補として確認してください。</p>
            <StaleCustomerList customers={staleCustomers} />
          </section>

          {outOfTerritoryCustomers.length > 0 && (
            <section className="panel">
              <h2>エリア外の顧客</h2>
              <p>
                転勤等で担当エリア外に残っている既存の顧客です。担当の引き継ぎ状況を確認してください。
              </p>
              <CustomerTable customers={outOfTerritoryCustomers} />
            </section>
          )}

          {areaCandidateCustomers.length > 0 && (
            <section className="panel">
              <h2>担当していない自分のエリアの顧客</h2>
              <p>
                あなたの担当エリア内にありますが、まだ担当・商談履歴のない顧客です。新規開拓の候補として確認してください。
              </p>
              <CustomerTable customers={areaCandidateCustomers} />
            </section>
          )}
        </div>
      )}

    </main>
  );
}
