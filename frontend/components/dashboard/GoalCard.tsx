"use client";

import { useState } from "react";
import type { SalesRep, SalesTarget } from "@/types";

type GoalCardProps = {
  rep: SalesRep;
  target: SalesTarget;
  forecastAmount: number;
  forecastProfitAmount: number;
  actualAchievedAmount: number;
  actualAchievementRate: number;
  onSave: (input: { target_amount: number; target_deal_count: number }) => Promise<void> | void;
  willGeneratePlan?: boolean;
};

function formatYen(amount: number): string {
  return `¥${amount.toLocaleString("ja-JP")}`;
}

function formatMonth(targetMonth: string): string {
  const [year, month] = targetMonth.split("-");
  return `${year}年${Number(month)}月`;
}

function AchievementRing({
  rate,
  label,
  modifierClass,
}: {
  rate: number;
  label: string;
  modifierClass?: string;
}) {
  const clampedRate = Math.max(0, rate);
  const ringProgress = Math.min(clampedRate, 100);
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - ringProgress / 100);

  return (
    <svg className="goal-card__ring" viewBox="0 0 120 120" width="120" height="120">
      <circle cx="60" cy="60" r={radius} className="goal-card__ring-track" />
      <circle
        cx="60"
        cy="60"
        r={radius}
        className={`goal-card__ring-progress${modifierClass ? ` ${modifierClass}` : ""}`}
        strokeDasharray={circumference}
        strokeDashoffset={dashOffset}
      />
      <text x="60" y="56" textAnchor="middle" className="goal-card__ring-value">
        {clampedRate.toFixed(1)}%
      </text>
      <text x="60" y="76" textAnchor="middle" className="goal-card__ring-label">
        {label}
      </text>
    </svg>
  );
}

export function GoalCard({
  rep,
  target,
  forecastAmount,
  forecastProfitAmount,
  actualAchievedAmount,
  actualAchievementRate,
  onSave,
  willGeneratePlan = false,
}: GoalCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [draftAmount, setDraftAmount] = useState(String(target.target_amount));

  const amountValue = Number(draftAmount);
  const isDraftValid = Number.isFinite(amountValue) && amountValue > 0;

  function startEditing() {
    setDraftAmount(String(target.target_amount));
    setIsEditing(true);
  }

  async function handleSave() {
    if (!isDraftValid) {
      return;
    }
    setIsSaving(true);
    // 目標件数はこの画面では編集不可のため、既存値をそのまま引き継いで送信する
    await onSave({ target_amount: amountValue, target_deal_count: target.target_deal_count });
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
        <div className="goal-card__rings">
          <AchievementRing
            rate={actualAchievementRate}
            label="現在の実績"
            modifierClass="goal-card__ring-progress--actual"
          />
        </div>

        <div className="goal-card__details">
          <dl className="goal-card__numbers">
            <div>
              <dt>目標金額</dt>
              <dd>
                {isEditing ? (
                  <form
                    className="goal-card__amount-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      handleSave();
                    }}
                  >
                    <input
                      type="number"
                      inputMode="numeric"
                      min={0}
                      value={draftAmount}
                      onChange={(event) => setDraftAmount(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Escape") setIsEditing(false);
                      }}
                      disabled={isSaving}
                      autoFocus
                    />
                    <button
                      type="submit"
                      className="goal-card__save"
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
                  </form>
                ) : (
                  <button
                    type="button"
                    className="goal-card__amount-button"
                    onClick={startEditing}
                    aria-label="目標金額を変更する"
                  >
                    {formatYen(target.target_amount)}
                  </button>
                )}
              </dd>
            </div>
            <div>
              <dt>見込み売上</dt>
              <dd className="goal-card__forecast">{formatYen(forecastAmount)}</dd>
            </div>
            <div>
              <dt>見込み粗利</dt>
              <dd className="goal-card__forecast">{formatYen(forecastProfitAmount)}</dd>
            </div>
            <div>
              <dt>現在の実績</dt>
              <dd className="goal-card__actual">{formatYen(actualAchievedAmount)}</dd>
            </div>
          </dl>
          {isEditing && willGeneratePlan && (
            <p className="goal-card__hint">保存すると、AIが今月の活動計画を作成します</p>
          )}
          <button
            type="button"
            className="goal-card__edit-button"
            onClick={startEditing}
            disabled={isEditing}
          >
            目標を変更する
          </button>
        </div>
      </div>
    </section>
  );
}
