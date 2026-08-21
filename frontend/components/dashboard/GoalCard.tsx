"use client";

import { useState } from "react";
import type { SalesRep, SalesTarget } from "@/types";

type GoalCardProps = {
  rep: SalesRep;
  target: SalesTarget;
  forecastAmount: number;
  achievementRate: number;
  onSave: (input: { target_amount: number; target_deal_count: number }) => Promise<void> | void;
};

function formatYen(amount: number): string {
  return `¥${amount.toLocaleString("ja-JP")}`;
}

function formatMonth(targetMonth: string): string {
  const [year, month] = targetMonth.split("-");
  return `${year}年${Number(month)}月`;
}

export function GoalCard({ rep, target, forecastAmount, achievementRate, onSave }: GoalCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [draftAmount, setDraftAmount] = useState(String(target.target_amount));
  const [draftCount, setDraftCount] = useState(String(target.target_deal_count));

  const rate = Math.max(0, achievementRate);
  const ringProgress = Math.min(rate, 100);
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - ringProgress / 100);

  const amountValue = Number(draftAmount);
  const countValue = Number(draftCount);
  const isDraftValid =
    Number.isFinite(amountValue) && amountValue > 0 && Number.isFinite(countValue) && countValue > 0;

  function startEditing() {
    setDraftAmount(String(target.target_amount));
    setDraftCount(String(target.target_deal_count));
    setIsEditing(true);
  }

  async function handleSave() {
    if (!isDraftValid) {
      return;
    }
    setIsSaving(true);
    await onSave({ target_amount: amountValue, target_deal_count: countValue });
    setIsSaving(false);
    setIsEditing(false);
  }

  return (
    <section className="panel goal-card">
      <div className="goal-card__header">
        <h2>{formatMonth(target.target_month)}の目標</h2>
        <span className="goal-card__rep">{rep.rep_name}</span>
      </div>

      <div className="goal-card__body">
        <svg className="goal-card__ring" viewBox="0 0 120 120" width="120" height="120">
          <circle cx="60" cy="60" r={radius} className="goal-card__ring-track" />
          <circle
            cx="60"
            cy="60"
            r={radius}
            className="goal-card__ring-progress"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
          />
          <text x="60" y="56" textAnchor="middle" className="goal-card__ring-value">
            {rate.toFixed(1)}%
          </text>
          <text x="60" y="76" textAnchor="middle" className="goal-card__ring-label">
            達成見込み
          </text>
        </svg>

        <div className="goal-card__details">
          {isEditing ? (
            <div className="goal-card__edit">
              <label className="goal-card__field">
                <span>目標金額</span>
                <input
                  type="number"
                  inputMode="numeric"
                  min={0}
                  value={draftAmount}
                  onChange={(event) => setDraftAmount(event.target.value)}
                />
              </label>
              <label className="goal-card__field">
                <span>目標件数</span>
                <input
                  type="number"
                  inputMode="numeric"
                  min={0}
                  value={draftCount}
                  onChange={(event) => setDraftCount(event.target.value)}
                />
              </label>
              <div className="goal-card__actions">
                <button
                  type="button"
                  className="goal-card__save"
                  onClick={handleSave}
                  disabled={!isDraftValid || isSaving}
                >
                  {isSaving ? "保存中..." : "保存"}
                </button>
                <button
                  type="button"
                  className="goal-card__cancel"
                  onClick={() => setIsEditing(false)}
                  disabled={isSaving}
                >
                  キャンセル
                </button>
              </div>
            </div>
          ) : (
            <>
              <dl className="goal-card__numbers">
                <div>
                  <dt>目標金額</dt>
                  <dd>{formatYen(target.target_amount)}</dd>
                </div>
                <div>
                  <dt>目標件数</dt>
                  <dd>{target.target_deal_count}件</dd>
                </div>
                <div>
                  <dt>見込み売上</dt>
                  <dd className="goal-card__forecast">{formatYen(forecastAmount)}</dd>
                </div>
              </dl>
              <button type="button" className="goal-card__edit-button" onClick={startEditing}>
                目標を変更する
              </button>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
