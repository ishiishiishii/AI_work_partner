"use client";

import { useEffect, useState } from "react";
import { fetchMasters, fetchProducts } from "@/lib/api";
import type { DealPhase, Product } from "@/types";

type NewDealFormProps = {
  onCreate: (input: {
    product_id: number;
    deal_phase_id: number;
    estimated_amount: number;
    win_probability: number;
    expected_visit_count: number;
    expected_effort_hours: number;
    deal_start_date?: string;
  }) => Promise<void>;
};

const initialDraft = {
  product_id: "",
  deal_phase_id: "",
  estimated_amount: "",
  win_probability: "",
  expected_visit_count: "",
  expected_effort_hours: "",
  deal_start_date: "",
};

export function NewDealForm({ onCreate }: NewDealFormProps) {
  const [products, setProducts] = useState<Product[]>([]);
  const [dealPhases, setDealPhases] = useState<DealPhase[]>([]);
  const [draft, setDraft] = useState(initialDraft);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchProducts()
      .then((fetched) => {
        setProducts(fetched);
        setDraft((prev) => ({ ...prev, product_id: prev.product_id || String(fetched[0]?.product_id ?? "") }));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "商品一覧の取得に失敗しました"));
    fetchMasters()
      .then((masters) => {
        setDealPhases(masters.deal_phases);
        setDraft((prev) => ({
          ...prev,
          deal_phase_id: prev.deal_phase_id || String(masters.deal_phases[0]?.deal_phase_id ?? ""),
        }));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "商談フェーズ一覧の取得に失敗しました"));
  }, []);

  const isValid =
    draft.product_id !== "" &&
    draft.deal_phase_id !== "" &&
    draft.estimated_amount !== "" &&
    draft.win_probability !== "" &&
    draft.expected_visit_count !== "" &&
    draft.expected_effort_hours !== "";

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!isValid) return;

    setIsSaving(true);
    setError(null);
    try {
      await onCreate({
        product_id: Number(draft.product_id),
        deal_phase_id: Number(draft.deal_phase_id),
        estimated_amount: Number(draft.estimated_amount),
        win_probability: Number(draft.win_probability),
        expected_visit_count: Number(draft.expected_visit_count),
        expected_effort_hours: Number(draft.expected_effort_hours),
        deal_start_date: draft.deal_start_date || undefined,
      });
      setDraft({ ...initialDraft, product_id: draft.product_id, deal_phase_id: draft.deal_phase_id });
    } catch (err) {
      setError(err instanceof Error ? err.message : "登録に失敗しました");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form className="panel new-customer-form" onSubmit={handleSubmit}>
      <h2>商談を追加</h2>
      <div className="new-customer-form__grid">
        <label className="goal-card__field">
          <span>商品</span>
          <select
            value={draft.product_id}
            onChange={(event) => setDraft({ ...draft, product_id: event.target.value })}
          >
            {products.map((product) => (
              <option key={product.product_id} value={product.product_id}>
                {product.product_name}
              </option>
            ))}
          </select>
        </label>
        <label className="goal-card__field">
          <span>商談フェーズ</span>
          <select
            value={draft.deal_phase_id}
            onChange={(event) => setDraft({ ...draft, deal_phase_id: event.target.value })}
          >
            {dealPhases.map((phase) => (
              <option key={phase.deal_phase_id} value={phase.deal_phase_id}>
                {phase.deal_phase_name}
              </option>
            ))}
          </select>
        </label>
        <label className="goal-card__field">
          <span>見込み金額(円)</span>
          <input
            type="number"
            min={0}
            value={draft.estimated_amount}
            onChange={(event) => setDraft({ ...draft, estimated_amount: event.target.value })}
            placeholder="例: 500000"
          />
        </label>
        <label className="goal-card__field">
          <span>成約確率(%)</span>
          <input
            type="number"
            min={0}
            max={100}
            value={draft.win_probability}
            onChange={(event) => setDraft({ ...draft, win_probability: event.target.value })}
            placeholder="例: 30"
          />
        </label>
        <label className="goal-card__field">
          <span>想定訪問回数</span>
          <input
            type="number"
            min={0}
            value={draft.expected_visit_count}
            onChange={(event) => setDraft({ ...draft, expected_visit_count: event.target.value })}
            placeholder="例: 3"
          />
        </label>
        <label className="goal-card__field">
          <span>想定工数(時間)</span>
          <input
            type="number"
            min={0}
            step="0.1"
            value={draft.expected_effort_hours}
            onChange={(event) => setDraft({ ...draft, expected_effort_hours: event.target.value })}
            placeholder="例: 5"
          />
        </label>
        <label className="goal-card__field">
          <span>商談開始日</span>
          <input
            type="date"
            value={draft.deal_start_date}
            onChange={(event) => setDraft({ ...draft, deal_start_date: event.target.value })}
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
