"use client";

import { useEffect, useRef, useState } from "react";
import { createCustomer, fetchMasters, searchCustomers } from "@/lib/api";
import type { CompanySize, CustomerSuggestion, Industry } from "@/types";

// 顧客名の入力が止まってから検索するまでの待ち時間。1文字ごとに検索を
// 飛ばすと無駄なリクエストが増えるため。NewCustomerFormと同じ値。
const SEARCH_DEBOUNCE_MS = 300;

export type CompanyFieldValue = {
  customerId: number | null;
  customerName: string;
};

type CompanyAutocompleteFieldProps = {
  repId: number;
  value: CompanyFieldValue;
  onChange: (value: CompanyFieldValue) => void;
  placeholder?: string;
};

const newCustomerInitialDraft = {
  industry_id: "",
  company_size_id: "",
  location: "",
  website: "",
  contact_name: "",
};

// 既存顧客名のオートコンプリート(NewCustomerFormと同じ検索API)に加えて、
// 一致する顧客が無い場合はその場で新規顧客として登録し、作成中の予定に
// customer_idを紐付けられるようにする入力欄。
export function CompanyAutocompleteField({
  repId,
  value,
  onChange,
  placeholder,
}: CompanyAutocompleteFieldProps) {
  const [suggestions, setSuggestions] = useState<CustomerSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  // 候補を選んだ直後は、その値で再検索してドロップダウンが出っぱなしになるのを防ぐ
  const suppressSearchRef = useRef(false);

  const [isRegistering, setIsRegistering] = useState(false);
  const [industries, setIndustries] = useState<Industry[]>([]);
  const [companySizes, setCompanySizes] = useState<CompanySize[]>([]);
  const [newCustomerDraft, setNewCustomerDraft] = useState(newCustomerInitialDraft);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (suppressSearchRef.current) {
      suppressSearchRef.current = false;
      return;
    }
    const query = value.customerName.trim();
    if (value.customerId !== null || query.length < 2) {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value.customerName, value.customerId]);

  function handleNameChange(name: string) {
    onChange({ customerId: null, customerName: name });
    setIsRegistering(false);
  }

  function applySuggestion(suggestion: CustomerSuggestion) {
    suppressSearchRef.current = true;
    onChange({ customerId: suggestion.customer_id, customerName: suggestion.customer_name });
    setShowSuggestions(false);
    setIsRegistering(false);
  }

  function startRegister() {
    setIsRegistering(true);
    setShowSuggestions(false);
    if (industries.length === 0) {
      fetchMasters()
        .then((masters) => {
          setIndustries(masters.industries);
          setCompanySizes(masters.company_sizes);
          setNewCustomerDraft((prev) => ({
            ...prev,
            industry_id: prev.industry_id || String(masters.industries[0]?.industry_id ?? ""),
            company_size_id:
              prev.company_size_id || String(masters.company_sizes[0]?.company_size_id ?? ""),
          }));
        })
        .catch((err) => setError(err instanceof Error ? err.message : "マスタ一覧の取得に失敗しました"));
    }
  }

  const isRegisterValid =
    value.customerName.trim().length > 0 &&
    newCustomerDraft.location.trim().length > 0 &&
    newCustomerDraft.industry_id !== "" &&
    newCustomerDraft.company_size_id !== "";

  async function handleRegisterSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!isRegisterValid) return;
    setIsSaving(true);
    setError(null);
    try {
      const created = await createCustomer(repId, {
        customer_name: value.customerName.trim(),
        industry_id: Number(newCustomerDraft.industry_id),
        company_size_id: Number(newCustomerDraft.company_size_id),
        location: newCustomerDraft.location.trim(),
        website: newCustomerDraft.website.trim() || null,
        contact_name: newCustomerDraft.contact_name.trim() || null,
      });
      onChange({ customerId: created.customer_id, customerName: created.customer_name });
      setIsRegistering(false);
      setNewCustomerDraft(newCustomerInitialDraft);
    } catch (err) {
      setError(err instanceof Error ? err.message : "顧客の登録に失敗しました");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="company-autocomplete">
      <div className="new-customer-form__name-field">
        <input
          type="text"
          value={value.customerName}
          onChange={(event) => handleNameChange(event.target.value)}
          onFocus={() => setShowSuggestions(suggestions.length > 0)}
          onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
          placeholder={placeholder}
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
      </div>

      {value.customerId !== null && (
        <span className="company-autocomplete__linked">既存顧客と紐付け済み</span>
      )}

      {value.customerId === null && value.customerName.trim().length > 0 && !isRegistering && (
        <button type="button" className="company-autocomplete__register-link" onClick={startRegister}>
          「{value.customerName.trim()}」を新規顧客として登録
        </button>
      )}

      {isRegistering && (
        <form className="new-customer-form company-autocomplete__register-form" onSubmit={handleRegisterSubmit}>
          <div className="new-customer-form__grid">
            <label className="goal-card__field">
              <span>業種</span>
              <select
                value={newCustomerDraft.industry_id}
                onChange={(event) =>
                  setNewCustomerDraft({ ...newCustomerDraft, industry_id: event.target.value })
                }
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
                value={newCustomerDraft.company_size_id}
                onChange={(event) =>
                  setNewCustomerDraft({ ...newCustomerDraft, company_size_id: event.target.value })
                }
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
                value={newCustomerDraft.location}
                onChange={(event) =>
                  setNewCustomerDraft({ ...newCustomerDraft, location: event.target.value })
                }
                placeholder="例: 東京都"
              />
            </label>
            <label className="goal-card__field">
              <span>ウェブサイト</span>
              <input
                type="text"
                value={newCustomerDraft.website}
                onChange={(event) =>
                  setNewCustomerDraft({ ...newCustomerDraft, website: event.target.value })
                }
                placeholder="任意"
              />
            </label>
            <label className="goal-card__field">
              <span>先方のご担当者名</span>
              <input
                type="text"
                value={newCustomerDraft.contact_name}
                onChange={(event) =>
                  setNewCustomerDraft({ ...newCustomerDraft, contact_name: event.target.value })
                }
                placeholder="任意"
              />
            </label>
          </div>

          {error && <p className="new-customer-form__error">{error}</p>}

          <div className="activity-plan-list__edit-actions">
            <button type="submit" className="goal-card__save" disabled={!isRegisterValid || isSaving}>
              {isSaving ? "登録中..." : "顧客として登録する"}
            </button>
            <button
              type="button"
              className="activity-plan-list__undo-button"
              onClick={() => setIsRegistering(false)}
            >
              キャンセル
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
