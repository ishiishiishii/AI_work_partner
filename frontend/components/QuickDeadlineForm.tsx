"use client";

import { useState } from "react";
import { createDeadline } from "@/lib/api";

function todayISODate(): string {
  return new Date().toISOString().slice(0, 10);
}

export function QuickDeadlineForm({ repId, onDone }: { repId: number; onDone: () => void }) {
  const [title, setTitle] = useState("");
  const [dueDate, setDueDate] = useState(todayISODate());
  const [memo, setMemo] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isValid = title.trim().length > 0 && dueDate.length > 0;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!isValid) return;
    setIsSaving(true);
    setError(null);
    try {
      await createDeadline(repId, {
        title: title.trim(),
        due_date: dueDate,
        memo: memo.trim() || null,
      });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "期限の追加に失敗しました");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form className="new-customer-form" onSubmit={handleSubmit}>
      <div className="new-customer-form__grid">
        <label className="goal-card__field">
          <span>件名</span>
          <input
            type="text"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="例: 見積提出"
          />
        </label>
        <label className="goal-card__field">
          <span>期限日</span>
          <input
            type="date"
            value={dueDate}
            onChange={(event) => setDueDate(event.target.value)}
          />
        </label>
        <label className="goal-card__field">
          <span>メモ</span>
          <input
            type="text"
            value={memo}
            onChange={(event) => setMemo(event.target.value)}
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
