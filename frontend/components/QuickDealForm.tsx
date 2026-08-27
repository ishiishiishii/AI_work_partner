"use client";

import { useEffect, useState } from "react";
import { CompanyAutocompleteField, type CompanyFieldValue } from "@/components/CompanyAutocompleteField";
import { NewDealForm } from "@/components/customers/NewDealForm";
import { createDeal, fetchCustomers } from "@/lib/api";
import type { Customer } from "@/types";

// 商談は顧客に紐づくため、まず対象の顧客を選ばせてから既存のNewDealFormを表示する。
// 会社名の検索・新規顧客登録は「予定を追加」と同じCompanyAutocompleteFieldを使う。
export function QuickDealForm({ repId, onDone }: { repId: number; onDone: () => void }) {
  const [company, setCompany] = useState<CompanyFieldValue>({ customerId: null, customerName: "" });
  // エリア外の顧客も選べてしまうと、フォーム一式を入力した後にサーバー側で
  // 弾かれてしまう(既存の営業支店チェック)。選択直後に警告を出せるよう、
  // 担当者から見た顧客一覧(in_territoryを含む)をあらかじめ取得しておく。
  const [customers, setCustomers] = useState<Customer[]>([]);

  useEffect(() => {
    fetchCustomers(repId)
      .then(setCustomers)
      .catch(() => setCustomers([]));
  }, [repId]);

  async function handleCreate(input: {
    product_id: number;
    deal_phase_id: number;
    estimated_amount: number;
    expected_visit_count: number;
    expected_effort_hours: number;
    deal_start_date?: string;
  }) {
    if (!company.customerId) return;
    await createDeal(repId, { ...input, customer_id: company.customerId });
    onDone();
  }

  const selectedCustomer = customers.find((customer) => customer.customer_id === company.customerId);
  const isOutOfTerritory = selectedCustomer !== undefined && !selectedCustomer.in_territory;

  return (
    <div className="plan-modal__detail">
      <div className="new-customer-form__grid">
        <div className="goal-card__field">
          <span>顧客</span>
          <CompanyAutocompleteField
            repId={repId}
            value={company}
            onChange={setCompany}
            placeholder="例: D工業株式会社"
          />
        </div>
      </div>

      {isOutOfTerritory && (
        <p className="new-customer-form__error">
          この顧客は担当エリア外のため、商談を登録できない可能性があります。
        </p>
      )}

      {company.customerId && <NewDealForm onCreate={handleCreate} showTitle={false} />}
    </div>
  );
}
