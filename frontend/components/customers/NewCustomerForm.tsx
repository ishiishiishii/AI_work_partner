"use client";

import { useEffect, useRef, useState } from "react";
import { fetchMasters, searchCustomers } from "@/lib/api";
import type { CompanySize, CustomerSuggestion, Industry } from "@/types";

type NewCustomerFormProps = {
  onCreate: (input: {
    customer_name: string;
    industry_id: number;
    company_size_id: number;
    location: string;
    website: string | null;
    contact_name: string | null;
  }) => Promise<void>;
};

const initialDraft = {
  customer_name: "",
  industry_id: "",
  company_size_id: "",
  location: "",
  website: "",
  contact_name: "",
};

// 顧客名の入力が止まってから検索するまでの待ち時間。1文字ごとに検索を
// 飛ばすと無駄なリクエストが増えるため。
const SEARCH_DEBOUNCE_MS = 300;

export function NewCustomerForm({ onCreate }: NewCustomerFormProps) {
  const [industries, setIndustries] = useState<Industry[]>([]);
  const [companySizes, setCompanySizes] = useState<CompanySize[]>([]);
  const [draft, setDraft] = useState(initialDraft);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [suggestions, setSuggestions] = useState<CustomerSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  // 候補を選んだ直後は、その値で再検索してドロップダウンが出っぱなしになるのを防ぐ
  const suppressSearchRef = useRef(false);

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

  useEffect(() => {
    if (suppressSearchRef.current) {
      suppressSearchRef.current = false;
      return;
    }
    const query = draft.customer_name.trim();
    if (query.length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      searchCustomers(query)
        .then((results) => {
          if (cancelled) return;
          setSuggestions(results);
          setShowSuggestions(results.length > 0);
        })
        .catch(() => {
          if (!cancelled) setSuggestions([]);
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [draft.customer_name]);

  function applySuggestion(suggestion: CustomerSuggestion) {
    suppressSearchRef.current = true;
    setDraft({
      customer_name: suggestion.customer_name,
      industry_id: String(suggestion.industry_id),
      company_size_id: String(suggestion.company_size_id),
      location: suggestion.location,
      website: suggestion.website ?? "",
      contact_name: suggestion.contact_name ?? "",
    });
    setShowSuggestions(false);
  }

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
        website: draft.website.trim() || null,
        contact_name: draft.contact_name.trim() || null,
      });
      setDraft({ ...initialDraft, industry_id: draft.industry_id, company_size_id: draft.company_size_id });
    } catch (err) {
      setError(err instanceof Error ? err.message : "登録に失敗しました");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form className="new-customer-form" onSubmit={handleSubmit}>
      <div className="new-customer-form__grid">
        <label className="goal-card__field new-customer-form__name-field">
          <span>顧客名</span>
          <input
            type="text"
            value={draft.customer_name}
            onChange={(event) => setDraft({ ...draft, customer_name: event.target.value })}
            onFocus={() => setShowSuggestions(suggestions.length > 0)}
            onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
            placeholder="例: D工業株式会社"
            autoComplete="off"
          />
          {showSuggestions && (
            <ul className="new-customer-form__suggestions">
              {suggestions.map((suggestion) => (
                <li key={suggestion.customer_id}>
                  <button
                    type="button"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => applySuggestion(suggestion)}
                  >
                    <span className="new-customer-form__suggestion-name">
                      {suggestion.customer_name}
                    </span>
                    <span className="new-customer-form__suggestion-meta">
                      {suggestion.industry_name}・{suggestion.location}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <span className="new-customer-form__hint">
            登録済みの顧客名と一致すると候補が表示されます(選ぶと他の項目も自動入力)
          </span>
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
        <label className="goal-card__field">
          <span>ウェブサイト</span>
          <input
            type="text"
            value={draft.website}
            onChange={(event) => setDraft({ ...draft, website: event.target.value })}
            placeholder="任意"
          />
        </label>
        <label className="goal-card__field">
          <span>先方のご担当者名</span>
          <input
            type="text"
            value={draft.contact_name}
            onChange={(event) => setDraft({ ...draft, contact_name: event.target.value })}
            placeholder="任意"
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
