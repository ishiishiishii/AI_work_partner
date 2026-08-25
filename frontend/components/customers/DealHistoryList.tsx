"use client";

import { useState } from "react";
import type { Deal, DealPhase, Product } from "@/types";

export type DealEditFields = {
  product_id: number;
  deal_phase_id: number;
  estimated_amount: number;
  win_probability: number;
  expected_visit_count: number;
  expected_effort_hours: number;
};

type DealHistoryListProps = {
  deals: Deal[];
  products: Product[];
  dealPhases: DealPhase[];
  onUpdateDeal: (dealId: number, updates: DealEditFields) => void;
  onDeleteDeal: (dealId: number) => void;
};

const STATUS_CLASS: Record<string, string> = {
  ongoing: "in_progress",
  won: "won",
  lost: "lost",
};

function formatYen(amount: number): string {
  return `¥${amount.toLocaleString("ja-JP")}`;
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const weekday = "日月火水木金土"[date.getDay()];
  return `${date.getMonth() + 1}/${date.getDate()}(${weekday})`;
}

export function DealHistoryList({ deals, products, dealPhases, onUpdateDeal, onDeleteDeal }: DealHistoryListProps) {
  const [editDraft, setEditDraft] = useState<(DealEditFields & { dealId: number }) | null>(null);

  const sorted = [...deals].sort((a, b) => b.deal_start_date.localeCompare(a.deal_start_date));

  if (sorted.length === 0) {
    return <p className="activity-plan-list__empty">商談履歴はまだありません</p>;
  }

  function startEdit(deal: Deal) {
    setEditDraft({
      dealId: deal.deal_id,
      product_id: deal.product_id,
      deal_phase_id: deal.deal_phase_id,
      estimated_amount: deal.estimated_amount,
      win_probability: deal.win_probability,
      expected_visit_count: deal.expected_visit_count,
      expected_effort_hours: deal.expected_effort_hours,
    });
  }

  function cancelEdit() {
    setEditDraft(null);
  }

  function saveEdit() {
    if (!editDraft) return;
    const { dealId, ...updates } = editDraft;
    onUpdateDeal(dealId, updates);
    setEditDraft(null);
  }

  function handleDelete(dealId: number) {
    if (!window.confirm("この商談を削除します。よろしいですか？")) return;
    onDeleteDeal(dealId);
  }

  return (
    <ul className="deal-history">
      {sorted.map((deal) => {
        const isEditing = editDraft !== null && editDraft.dealId === deal.deal_id;

        return (
          <li key={deal.deal_id} className="deal-history__item">
            <div className="deal-history__date">{formatDate(deal.deal_start_date)}</div>
            <div className="deal-history__main">
              <div className="deal-history__head">
                <span className="deal-history__type">{deal.product_name}</span>
                <span
                  className={`deal-history__status deal-history__status--${
                    STATUS_CLASS[deal.deal_result_status] ?? "in_progress"
                  }`}
                >
                  {deal.deal_result_status_name}
                </span>
              </div>

              {isEditing ? (
                <div className="deal-history__edit-form">
                  <label>
                    商品
                    <select
                      value={editDraft.product_id}
                      onChange={(event) =>
                        setEditDraft({ ...editDraft, product_id: Number(event.target.value) })
                      }
                    >
                      {products.map((product) => (
                        <option key={product.product_id} value={product.product_id}>
                          {product.product_name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    フェーズ
                    <select
                      value={editDraft.deal_phase_id}
                      onChange={(event) =>
                        setEditDraft({ ...editDraft, deal_phase_id: Number(event.target.value) })
                      }
                    >
                      {dealPhases.map((phase) => (
                        <option key={phase.deal_phase_id} value={phase.deal_phase_id}>
                          {phase.deal_phase_name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    見込み金額
                    <input
                      type="number"
                      min={0}
                      value={editDraft.estimated_amount}
                      onChange={(event) =>
                        setEditDraft({ ...editDraft, estimated_amount: Number(event.target.value) })
                      }
                    />
                  </label>
                  <label>
                    成約確率(%)
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={editDraft.win_probability}
                      onChange={(event) =>
                        setEditDraft({ ...editDraft, win_probability: Number(event.target.value) })
                      }
                    />
                  </label>
                  <label>
                    想定訪問回数
                    <input
                      type="number"
                      min={0}
                      value={editDraft.expected_visit_count}
                      onChange={(event) =>
                        setEditDraft({ ...editDraft, expected_visit_count: Number(event.target.value) })
                      }
                    />
                  </label>
                  <label>
                    想定工数(時間)
                    <input
                      type="number"
                      min={0}
                      step="0.1"
                      value={editDraft.expected_effort_hours}
                      onChange={(event) =>
                        setEditDraft({ ...editDraft, expected_effort_hours: Number(event.target.value) })
                      }
                    />
                  </label>
                  <div className="activity-plan-list__edit-actions">
                    <button type="button" className="activity-plan-list__result-button" onClick={saveEdit}>
                      保存
                    </button>
                    <button type="button" className="activity-plan-list__undo-button" onClick={cancelEdit}>
                      キャンセル
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <p className="deal-history__note">
                    {deal.deal_phase_name}・成約確率{deal.win_probability}%
                    {deal.contract_date && `・契約日 ${formatDate(deal.contract_date)}`}
                  </p>
                  <div className="activity-plan-list__edit-actions">
                    <button
                      type="button"
                      className="activity-plan-list__result-button"
                      onClick={() => startEdit(deal)}
                    >
                      編集
                    </button>
                    <button
                      type="button"
                      className="activity-plan-list__undo-button"
                      onClick={() => handleDelete(deal.deal_id)}
                    >
                      削除
                    </button>
                  </div>
                </>
              )}
            </div>
            <div className="deal-history__amount">{formatYen(deal.estimated_amount)}</div>
          </li>
        );
      })}
    </ul>
  );
}
