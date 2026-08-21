"use client";

import { useState } from "react";

type NewCustomerFormProps = {
  onCreate: (input: {
    customer_name: string;
    industry: string;
    location: string;
    estimated_amount: number;
    win_probability: number;
  }) => Promise<void>;
};

const initialDraft = {
  customer_name: "",
  industry: "",
  location: "",
  estimated_amount: "",
  win_probability: "50",
};

export function NewCustomerForm({ onCreate }: NewCustomerFormProps) {
  const [draft, setDraft] = useState(initialDraft);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const amountValue = Number(draft.estimated_amount);
  const probabilityValue = Number(draft.win_probability);
  const isValid =
    draft.customer_name.trim().length > 0 &&
    Number.isFinite(amountValue) &&
    amountValue >= 0 &&
    Number.isFinite(probabilityValue) &&
    probabilityValue >= 0 &&
    probabilityValue <= 100;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!isValid) return;

    setIsSaving(true);
    setError(null);
    try {
      await onCreate({
        customer_name: draft.customer_name.trim(),
        industry: draft.industry.trim(),
        location: draft.location.trim(),
        estimated_amount: amountValue,
        win_probability: probabilityValue,
      });
      setDraft(initialDraft);
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
            placeholder="例: D工業"
          />
        </label>
        <label className="goal-card__field">
          <span>業種</span>
          <input
            type="text"
            value={draft.industry}
            onChange={(event) => setDraft({ ...draft, industry: event.target.value })}
            placeholder="例: 製造業"
          />
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
          <span>見込み金額</span>
          <input
            type="number"
            inputMode="numeric"
            min={0}
            value={draft.estimated_amount}
            onChange={(event) => setDraft({ ...draft, estimated_amount: event.target.value })}
            placeholder="1000000"
          />
        </label>
        <label className="goal-card__field">
          <span>成約確率(%)</span>
          <input
            type="number"
            inputMode="numeric"
            min={0}
            max={100}
            value={draft.win_probability}
            onChange={(event) => setDraft({ ...draft, win_probability: event.target.value })}
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
