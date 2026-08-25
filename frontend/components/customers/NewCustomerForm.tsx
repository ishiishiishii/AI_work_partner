"use client";

import { useEffect, useState } from "react";
import { fetchMasters } from "@/lib/api";
import type { CompanySize, Industry } from "@/types";

type NewCustomerFormProps = {
  onCreate: (input: {
    customer_name: string;
    industry_id: number;
    company_size_id: number;
    location: string;
  }) => Promise<void>;
};

const initialDraft = {
  customer_name: "",
  industry_id: "",
  company_size_id: "",
  location: "",
};

export function NewCustomerForm({ onCreate }: NewCustomerFormProps) {
  const [industries, setIndustries] = useState<Industry[]>([]);
  const [companySizes, setCompanySizes] = useState<CompanySize[]>([]);
  const [draft, setDraft] = useState(initialDraft);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMasters()
      .then((masters) => {
        setIndustries(masters.industries);
        setCompanySizes(masters.company_sizes);
        setDraft((prev) => ({
          ...prev,
          industry_id: prev.industry_id || String(masters.industries[0]?.industry_id ?? ""),
          company_size_id:
            prev.company_size_id || String(masters.company_sizes[0]?.company_size_id ?? ""),
        }));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "マスタ一覧の取得に失敗しました"));
  }, []);

  const isValid =
    draft.customer_name.trim().length > 0 &&
    draft.location.trim().length > 0 &&
    draft.industry_id !== "" &&
    draft.company_size_id !== "";

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!isValid) return;

    setIsSaving(true);
    setError(null);
    try {
      await onCreate({
        customer_name: draft.customer_name.trim(),
        industry_id: Number(draft.industry_id),
        company_size_id: Number(draft.company_size_id),
        location: draft.location.trim(),
      });
      setDraft({ ...initialDraft, industry_id: draft.industry_id, company_size_id: draft.company_size_id });
    } catch (err) {
      setError(err instanceof Error ? err.message : "登録に失敗しました");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form className="panel new-customer-form" onSubmit={handleSubmit}>
      <h2>新規顧客を登録</h2>
      <div className="new-customer-form__grid">
        <label className="goal-card__field">
          <span>顧客名</span>
          <input
            type="text"
            value={draft.customer_name}
            onChange={(event) => setDraft({ ...draft, customer_name: event.target.value })}
            placeholder="例: D工業株式会社"
          />
        </label>
        <label className="goal-card__field">
          <span>業種</span>
          <select
            value={draft.industry_id}
            onChange={(event) => setDraft({ ...draft, industry_id: event.target.value })}
          >
            {industries.map((industry) => (
              <option key={industry.industry_id} value={industry.industry_id}>
                {industry.industry_name}
              </option>
            ))}
          </select>
        </label>
        <label className="goal-card__field">
          <span>企業規模</span>
          <select
            value={draft.company_size_id}
            onChange={(event) => setDraft({ ...draft, company_size_id: event.target.value })}
          >
            {companySizes.map((companySize) => (
              <option key={companySize.company_size_id} value={companySize.company_size_id}>
                {companySize.company_size_name}
              </option>
            ))}
          </select>
        </label>
        <label className="goal-card__field">
          <span>所在地</span>
          <input
            type="text"
            value={draft.location}
            onChange={(event) => setDraft({ ...draft, location: event.target.value })}
            placeholder="例: 東京都"
          />
        </label>
      </div>

      {error && <p className="new-customer-form__error">{error}</p>}

      <button type="submit" className="goal-card__save" disabled={!isValid || isSaving}>
        {isSaving ? "登録中..." : "登録する"}
      </button>
    </form>
  );
}
