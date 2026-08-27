"use client";

import { useEffect, useState } from "react";
import { ProductPickerField, type ProductFieldValue } from "@/components/ProductPickerField";
import { fetchMasters } from "@/lib/api";
import type { DealPhase } from "@/types";

type NewDealFormProps = {
  onCreate: (input: {
    product_id: number;
    deal_phase_id: number;
    estimated_amount: number;
    expected_visit_count: number;
    expected_effort_hours: number;
    deal_start_date?: string;
    memo?: string;
  }) => Promise<void>;
  showTitle?: boolean;
};

const initialDraft = {
  deal_phase_id: "",
  estimated_amount: "",
  expected_visit_count: "",
  expected_effort_hours: "",
  deal_start_date: "",
  memo: "",
};

export function NewDealForm({ onCreate, showTitle = true }: NewDealFormProps) {
  const [product, setProduct] = useState<ProductFieldValue>({ productId: null, productName: "" });
  const [dealPhases, setDealPhases] = useState<DealPhase[]>([]);
  const [draft, setDraft] = useState(initialDraft);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
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
    product.productId !== null &&
    draft.deal_phase_id !== "" &&
    draft.estimated_amount !== "" &&
    draft.expected_visit_count !== "" &&
    draft.expected_effort_hours !== "";

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!isValid || product.productId === null) return;

    setIsSaving(true);
    setError(null);
    try {
      await onCreate({
        product_id: product.productId,
        deal_phase_id: Number(draft.deal_phase_id),
        estimated_amount: Number(draft.estimated_amount),
        expected_visit_count: Number(draft.expected_visit_count),
        expected_effort_hours: Number(draft.expected_effort_hours),
        deal_start_date: draft.deal_start_date || undefined,
        memo: draft.memo || undefined,
      });
      setProduct({ productId: null, productName: "" });
      setDraft({ ...initialDraft, deal_phase_id: draft.deal_phase_id });
    } catch (err) {
      setError(err instanceof Error ? err.message : "登録に失敗しました");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form className="panel new-customer-form" onSubmit={handleSubmit}>
      {showTitle && <h2>商談を追加</h2>}
      <div className="new-customer-form__grid">
        <label className="goal-card__field">
          <span>商品</span>
          <ProductPickerField value={product} onChange={setProduct} placeholder="例: AI画像解析カメラ" />
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
        <label className="goal-card__field">
          <span>メモ</span>
          <textarea
            className="plan-modal__memo-input"
            value={draft.memo}
            onChange={(event) => setDraft({ ...draft, memo: event.target.value })}
            rows={3}
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
