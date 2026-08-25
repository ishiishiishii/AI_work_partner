"use client";

import { useEffect, useState } from "react";
import { CustomerTable } from "@/components/customers/CustomerTable";
import { NewCustomerForm } from "@/components/customers/NewCustomerForm";
import { StaleCustomerList } from "@/components/customers/StaleCustomerList";
import {
  createCustomer,
  fetchCompanySizes,
  fetchCustomers,
  fetchIndustries,
  fetchStaleCustomers,
} from "@/lib/api";
import { useRep } from "@/lib/repContext";
import type { CompanySize, Customer, Industry, StaleCustomer } from "@/types";

export default function CustomersPage() {
  const { selectedRep } = useRep();
  const REP_ID = selectedRep?.rep_id ?? null;
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [staleCustomers, setStaleCustomers] = useState<StaleCustomer[]>([]);
  const [industries, setIndustries] = useState<Industry[]>([]);
  const [companySizes, setCompanySizes] = useState<CompanySize[]>([]);

  useEffect(() => {
    if (REP_ID === null) return;
    const repId = REP_ID;
    let cancelled = false;

    async function load() {
      try {
        setIsLoading(true);
        setLoadError(null);
        const [fetched, fetchedStale, fetchedIndustries, fetchedCompanySizes] = await Promise.all([
          fetchCustomers(repId),
          fetchStaleCustomers(repId),
          fetchIndustries(),
          fetchCompanySizes(),
        ]);
        if (!cancelled) {
          setCustomers(fetched);
          setStaleCustomers(fetchedStale);
          setIndustries(fetchedIndustries);
          setCompanySizes(fetchedCompanySizes);
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

  async function handleCreate(input: {
    customer_name: string;
    industry_id: number;
    company_size_id: number;
    location: string;
  }) {
    if (REP_ID === null) return;
    const created = await createCustomer(REP_ID, input);
    setCustomers((prev) => [...prev, created]);
  }

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
        <div className="page-layout">
          <div className="page-layout__primary">
            <section className="panel">
              <h2>登録済みの顧客</h2>
              <CustomerTable customers={customers} />
            </section>
          </div>
          <div className="page-layout__sidebar">
            <section className="panel">
              <h2>休眠顧客</h2>
              <p>60日以上接点の無い顧客です。フォローの優先候補として確認してください。</p>
              <StaleCustomerList customers={staleCustomers} />
            </section>
          </div>
        </div>
      )}

      <NewCustomerForm industries={industries} companySizes={companySizes} onCreate={handleCreate} />
    </main>
  );
}
