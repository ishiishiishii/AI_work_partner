"use client";

import { useMemo, useState } from "react";
import type { Deal, DealPhase, Product } from "@/types";

export type DealEditFields = {
  product_id: number;
  deal_phase_id: number;
  estimated_amount: number;
  expected_visit_count: number;
  expected_effort_hours: number;
  // 成約(won)済みの商談でのみ送る。未成約の商談で送るとバックエンドのトリガーに拒否される
  actual_amount?: number | null;
  memo: string;
};

type DealHistoryListProps = {
  deals: Deal[];
  products: Product[];
  dealPhases: DealPhase[];
  currentRepId: number | null;
  onUpdateDeal: (dealId: number, updates: DealEditFields) => void;
  onDeleteDeal: (dealId: number) => void;
};

type DealGroup = {
  key: string;
  deals: Deal[]; // 新しい順
  totalAmount: number;
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

// 同じ担当者×同じ商品の商談を1カードにまとめる。ただし一度「成約」した商談が
// あると、そこでその取引サイクルは終了とみなし、以降の同じ担当者×同じ商品の
// 商談は新しいカードとして扱う(再取引を過去の成約案件と混ぜないため)。
function groupDeals(deals: Deal[]): DealGroup[] {
  const chronological = [...deals].sort(
    (a, b) => a.deal_start_date.localeCompare(b.deal_start_date) || a.deal_id - b.deal_id,
  );

  const openGroups = new Map<string, Deal[]>();
  const groups: Deal[][] = [];

  for (const deal of chronological) {
    const cycleKey = `${deal.rep_id}_${deal.product_id}`;
    let group = openGroups.get(cycleKey);
    if (!group) {
      group = [];
      groups.push(group);
      openGroups.set(cycleKey, group);
    }
    group.push(deal);
    if (deal.deal_result_status === "won") {
      openGroups.delete(cycleKey);
    }
  }

  return groups
    .map((groupDeals) => {
      const sorted = [...groupDeals].sort((a, b) => b.deal_start_date.localeCompare(a.deal_start_date));
      return {
        key: `${sorted[0].rep_id}_${sorted[0].product_id}_${sorted[sorted.length - 1].deal_id}`,
        deals: sorted,
        totalAmount: groupDeals.reduce((sum, deal) => sum + deal.estimated_amount, 0),
      };
    })
    .sort((a, b) => b.deals[0].deal_start_date.localeCompare(a.deals[0].deal_start_date));
}

export function DealHistoryList({
  deals,
  products,
  dealPhases,
  currentRepId,
  onUpdateDeal,
  onDeleteDeal,
}: DealHistoryListProps) {
  const [editDraft, setEditDraft] = useState<(DealEditFields & { dealId: number }) | null>(null);
  const [breakdownGroupKey, setBreakdownGroupKey] = useState<string | null>(null);
  const [detailDealId, setDetailDealId] = useState<number | null>(null);

  const groups = useMemo(() => groupDeals(deals), [deals]);
  const breakdownGroup = groups.find((group) => group.key === breakdownGroupKey) ?? null;
  const detailDeal = deals.find((deal) => deal.deal_id === detailDealId) ?? null;

  if (groups.length === 0) {
    return <p className="activity-plan-list__empty">商談履歴はまだありません</p>;
  }

  function openGroup(group: DealGroup) {
    if (group.deals.length === 1) {
      setDetailDealId(group.deals[0].deal_id);
    } else {
      setBreakdownGroupKey(group.key);
    }
  }

  function openDealFromBreakdown(deal: Deal) {
    setBreakdownGroupKey(null);
    setDetailDealId(deal.deal_id);
  }

  function closeBreakdown() {
    setBreakdownGroupKey(null);
  }

  function closeDetail() {
    setDetailDealId(null);
    setEditDraft(null);
  }

  function startEdit(deal: Deal) {
    setEditDraft({
      dealId: deal.deal_id,
      product_id: deal.product_id,
      deal_phase_id: deal.deal_phase_id,
      estimated_amount: deal.estimated_amount,
      expected_visit_count: deal.expected_visit_count,
      expected_effort_hours: deal.expected_effort_hours,
      actual_amount:
        deal.deal_result_status === "won" ? (deal.actual_amount ?? deal.estimated_amount) : null,
      memo: deal.memo ?? "",
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
    closeDetail();
  }

  return (
    <>
      <ul className="deal-history">
        {groups.map((group) => {
          const latest = group.deals[0];
          const isMine = currentRepId !== null && latest.rep_id === currentRepId;

          return (
            <li
              key={group.key}
              className={`deal-history__item deal-history__item--clickable${
                isMine ? "" : " deal-history__item--other-rep"
              }`}
              onClick={() => openGroup(group)}
            >
              <div className="deal-history__date">{formatDate(latest.deal_start_date)}</div>
              <div className="deal-history__main">
                <div className="deal-history__head">
                  <span className="deal-history__type">{latest.product_name}</span>
                  <span
                    className={`deal-history__status deal-history__status--${
                      STATUS_CLASS[latest.deal_result_status] ?? "in_progress"
                    }`}
                  >
                    {latest.deal_result_status_name}
                  </span>
                  <span className={`deal-history__rep${isMine ? " deal-history__rep--mine" : ""}`}>
                    {isMine ? `あなたの担当・${latest.rep_name}` : latest.rep_name}
                  </span>
                  {group.deals.length > 1 && (
                    <span className="deal-history__count">{group.deals.length}件</span>
                  )}
                </div>
                <p className="deal-history__note">
                  {latest.deal_phase_name}
                  {latest.deal_result_status === "ongoing" && `・成約確率${latest.win_probability}%`}
                  {latest.contract_date && `・契約日 ${formatDate(latest.contract_date)}`}
                </p>
              </div>
              <div className="deal-history__amount">
                {formatYen(group.totalAmount)}
                {group.deals.length > 1 && (
                  <span className="deal-history__profit">合計 {group.deals.length}件</span>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      {breakdownGroup && (
        <div className="plan-modal-overlay" onClick={closeBreakdown}>
          <div className="plan-modal" onClick={(event) => event.stopPropagation()}>
            <div className="plan-modal__header">
              <div className="plan-modal__header-text">
                <span className="plan-modal__eyebrow">{breakdownGroup.deals.length}件の商談</span>
                <h3>{breakdownGroup.deals[0].product_name}</h3>
              </div>
              <button type="button" className="plan-modal__close" onClick={closeBreakdown} aria-label="閉じる">
                ×
              </button>
            </div>
            <ul className="deal-history">
              {breakdownGroup.deals.map((deal) => (
                <li
                  key={deal.deal_id}
                  className="deal-history__item deal-history__item--clickable"
                  onClick={() => openDealFromBreakdown(deal)}
                >
                  <div className="deal-history__date">{formatDate(deal.deal_start_date)}</div>
                  <div className="deal-history__main">
                    <div className="deal-history__head">
                      <span
                        className={`deal-history__status deal-history__status--${
                          STATUS_CLASS[deal.deal_result_status] ?? "in_progress"
                        }`}
                      >
                        {deal.deal_result_status_name}
                      </span>
                    </div>
                    <p className="deal-history__note">{deal.deal_phase_name}</p>
                  </div>
                  <div className="deal-history__amount">
                    {formatYen(deal.estimated_amount)}
                    {deal.deal_result_status === "won" && deal.actual_amount != null && (
                      <span className="deal-history__profit">実際 {formatYen(deal.actual_amount)}</span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {detailDeal &&
        (() => {
          const isMine = currentRepId !== null && detailDeal.rep_id === currentRepId;
          const isEditing = editDraft !== null && editDraft.dealId === detailDeal.deal_id;

          return (
            <div className="plan-modal-overlay" onClick={closeDetail}>
              <div className="plan-modal" onClick={(event) => event.stopPropagation()}>
                <div className="plan-modal__header">
                  <div className="plan-modal__header-text">
                    <span className="plan-modal__eyebrow">
                      {isMine ? "あなたの担当" : detailDeal.rep_name}
                    </span>
                    <h3>{detailDeal.product_name}</h3>
                  </div>
                  <button type="button" className="plan-modal__close" onClick={closeDetail} aria-label="閉じる">
                    ×
                  </button>
                </div>

                <div className="plan-modal__stats">
                  <span
                    className={`deal-history__status deal-history__status--${
                      STATUS_CLASS[detailDeal.deal_result_status] ?? "in_progress"
                    }`}
                  >
                    {detailDeal.deal_result_status_name}
                  </span>
                  <span className="plan-modal__stat-amount">{formatYen(detailDeal.estimated_amount)}</span>
                </div>

                <dl className="plan-modal__fields">
                  <dt>担当者</dt>
                  <dd>{detailDeal.rep_name}</dd>

                  <dt>商品</dt>
                  <dd>
                    {isEditing ? (
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
                    ) : (
                      detailDeal.product_name
                    )}
                  </dd>

                  <dt>フェーズ</dt>
                  <dd>
                    {isEditing ? (
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
                    ) : (
                      detailDeal.deal_phase_name
                    )}
                  </dd>

                  <dt>見込み金額</dt>
                  <dd>
                    {isEditing ? (
                      <input
                        type="number"
                        min={0}
                        value={editDraft.estimated_amount}
                        onChange={(event) =>
                          setEditDraft({ ...editDraft, estimated_amount: Number(event.target.value) })
                        }
                      />
                    ) : (
                      formatYen(detailDeal.estimated_amount)
                    )}
                  </dd>

                  {detailDeal.deal_result_status === "won" && (
                    <>
                      <dt>実際の契約金額</dt>
                      <dd>
                        {isEditing ? (
                          <input
                            type="number"
                            min={0}
                            value={editDraft.actual_amount ?? editDraft.estimated_amount}
                            onChange={(event) =>
                              setEditDraft({ ...editDraft, actual_amount: Number(event.target.value) })
                            }
                          />
                        ) : (
                          detailDeal.actual_amount != null ? formatYen(detailDeal.actual_amount) : "-"
                        )}
                      </dd>
                    </>
                  )}

                  {detailDeal.deal_result_status === "ongoing" && (
                    <>
                      <dt>成約確率</dt>
                      <dd>{detailDeal.win_probability}%</dd>
                    </>
                  )}

                  {detailDeal.contract_date && (
                    <>
                      <dt>契約日</dt>
                      <dd>{formatDate(detailDeal.contract_date)}</dd>
                    </>
                  )}

                  <dt>想定訪問回数</dt>
                  <dd>
                    {isEditing ? (
                      <input
                        type="number"
                        min={0}
                        value={editDraft.expected_visit_count}
                        onChange={(event) =>
                          setEditDraft({ ...editDraft, expected_visit_count: Number(event.target.value) })
                        }
                      />
                    ) : (
                      `${detailDeal.expected_visit_count}回`
                    )}
                  </dd>

                  <dt>想定工数</dt>
                  <dd>
                    {isEditing ? (
                      <input
                        type="number"
                        min={0}
                        step="0.1"
                        value={editDraft.expected_effort_hours}
                        onChange={(event) =>
                          setEditDraft({ ...editDraft, expected_effort_hours: Number(event.target.value) })
                        }
                      />
                    ) : (
                      `${detailDeal.expected_effort_hours}時間`
                    )}
                  </dd>

                  <dt>原価</dt>
                  <dd>{formatYen(detailDeal.cost)}</dd>

                  <dt>粗利</dt>
                  <dd>{formatYen(detailDeal.profit)}</dd>

                  <dt>メモ</dt>
                  <dd>
                    {isEditing ? (
                      <textarea
                        className="plan-modal__memo-input"
                        value={editDraft.memo}
                        onChange={(event) => setEditDraft({ ...editDraft, memo: event.target.value })}
                        rows={3}
                      />
                    ) : (
                      <span className="plan-modal__memo-display">{detailDeal.memo || "(メモなし)"}</span>
                    )}
                  </dd>
                </dl>

                {isMine && (
                  <div className="activity-plan-list__edit-actions plan-modal__actions">
                    {isEditing ? (
                      <>
                        <button
                          type="button"
                          className="activity-plan-list__result-button plan-modal__primary-button"
                          onClick={saveEdit}
                        >
                          保存
                        </button>
                        <button type="button" className="activity-plan-list__undo-button" onClick={cancelEdit}>
                          キャンセル
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          className="activity-plan-list__result-button"
                          onClick={() => startEdit(detailDeal)}
                        >
                          編集
                        </button>
                        <button
                          type="button"
                          className="activity-plan-list__undo-button"
                          onClick={() => handleDelete(detailDeal.deal_id)}
                        >
                          削除
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })()}
    </>
  );
}
