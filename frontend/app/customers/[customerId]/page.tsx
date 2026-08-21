"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { DealHistoryList } from "@/components/customers/DealHistoryList";
import { fetchCustomers } from "@/lib/api";
import { mockDealHistoryFor } from "@/lib/mockData";
import { useRep } from "@/lib/repContext";
import type { Customer } from "@/types";

const STATUS_LABELS: Record<Customer["status"], string> = {
  prospect: "見込み客",
  active: "取引中",
  dormant: "休眠",
  churned: "離反",
};

function formatYen(amount: number): string {
  return `¥${amount.toLocaleString("ja-JP")}`;
}

export default function CustomerDetailPage() {
  const { customerId } = useParams<{ customerId: string }>();
  const { selectedRep } = useRep();
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setIsLoading(true);
        setLoadError(null);
        const customers = await fetchCustomers(selectedRep.rep_id);
        if (cancelled) return;
        setCustomer(customers.find((item) => item.customer_id === customerId) ?? null);
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
        {customer.industry ?? "業種未設定"}・{customer.location ?? "所在地未設定"}
      </p>

      <section className="panel">
        <dl className="goal-card__numbers customer-detail__summary">
          <div>
            <dt>見込み金額</dt>
            <dd>{formatYen(customer.estimated_amount)}</dd>
          </div>
          <div>
            <dt>成約確率</dt>
            <dd>{customer.win_probability}%</dd>
          </div>
          <div>
            <dt>ステータス</dt>
            <dd>{STATUS_LABELS[customer.status]}</dd>
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
