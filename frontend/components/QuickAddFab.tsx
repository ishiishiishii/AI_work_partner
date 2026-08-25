"use client";

import { usePathname } from "next/navigation";
import { useLayoutEffect, useState } from "react";
import { NewCustomerForm } from "@/components/customers/NewCustomerForm";
import { createCustomer, createDeadline, createManualPlan } from "@/lib/api";
import { useQuickAddPlan } from "@/lib/quickAddPlanContext";
import { useRep } from "@/lib/repContext";
import type { ActivityPlan, ActivityPlanCategory } from "@/types";

type AddType = "plan" | "customer" | "deadline";

const TYPE_LABELS: Record<AddType, string> = {
  plan: "予定",
  customer: "新規顧客",
  deadline: "期限",
};

function todayISODate(): string {
  return new Date().toISOString().slice(0, 10);
}

// ダッシュボード(ActivityPlanList)の予定詳細パネルが編集時に使う選択肢と同じもの。
// バックエンドのactivity_typeは自由記述だが、UIとしてはこの一覧から選ばせている。
const EDITABLE_ACTIVITY_TYPES = ["訪問", "電話", "メール", "Web会議", "資料作成", "新規開拓"];

// ダッシュボードの予定詳細パネル(ActivityPlanList)の「作成」時と同じ項目構成。
// 商品/成約確率/メモは元々のパネルでも新規作成時は入力できるが、
// createManualPlanは受け取らない(バックエンドのPlanCreateに該当項目が無い)ため、
// 元のパネル同様ここでも入力はできるが保存には反映されない。
function QuickPlanForm({
  repId,
  defaultPlanDate,
  onDone,
  onCancel,
}: {
  repId: number;
  defaultPlanDate?: string;
  onDone: (plan: ActivityPlan) => void;
  onCancel: () => void;
}) {
  const [category, setCategory] = useState<ActivityPlanCategory>("visit");
  const [planDate, setPlanDate] = useState(defaultPlanDate || todayISODate());
  const [startTime, setStartTime] = useState<string | null>(null);
  const [endTime, setEndTime] = useState<string | null>(null);
  const [activityTypeName, setActivityTypeName] = useState("訪問");
  const [customerName, setCustomerName] = useState("");
  const [productName, setProductName] = useState("");
  const [expectedProbability, setExpectedProbability] = useState(0);
  const [memo, setMemo] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isValid = customerName.trim().length > 0 && planDate.length > 0;

  async function handleSave() {
    if (!isValid) return;
    setIsSaving(true);
    setError(null);
    try {
      const created = await createManualPlan(repId, {
        plan_date: planDate,
        start_time: startTime,
        end_time: endTime,
        category,
        activity_type_name: activityTypeName,
        customer_name: customerName.trim(),
        customer_id: null,
        deal_id: null,
        priority: 3,
      });
      onDone(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "予定の追加に失敗しました");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="plan-modal__detail">
      <dl className="plan-modal__fields">
        <dt>日付</dt>
        <dd>
          <input type="date" value={planDate} onChange={(event) => setPlanDate(event.target.value)} />
        </dd>

        <dt>種別</dt>
        <dd>
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value as ActivityPlanCategory)}
          >
            <option value="visit">企業訪問</option>
            <option value="task">事務作業</option>
          </select>
        </dd>

        <dt>時間</dt>
        <dd>
          <span className="plan-modal__time-inputs">
            <input
              type="time"
              value={startTime ?? ""}
              onChange={(event) => setStartTime(event.target.value || null)}
            />
            〜
            <input
              type="time"
              value={endTime ?? ""}
              onChange={(event) => setEndTime(event.target.value || null)}
            />
          </span>
        </dd>

        <dt>内容</dt>
        <dd>
          <select
            value={activityTypeName}
            onChange={(event) => setActivityTypeName(event.target.value)}
          >
            {EDITABLE_ACTIVITY_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </dd>

        <dt>{category === "visit" ? "会社" : "件名"}</dt>
        <dd>
          <input
            type="text"
            value={customerName}
            onChange={(event) => setCustomerName(event.target.value)}
          />
        </dd>

        {category === "visit" && (
          <>
            <dt>商品</dt>
            <dd>
              <input
                type="text"
                value={productName}
                onChange={(event) => setProductName(event.target.value)}
              />
            </dd>

            <dt>成約確率</dt>
            <dd>
              <span className="plan-modal__percent-input">
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={5}
                  value={expectedProbability}
                  onChange={(event) => setExpectedProbability(Number(event.target.value))}
                />
                %
              </span>
            </dd>

            <dt>メモ</dt>
            <dd>
              <textarea
                className="plan-modal__memo-input"
                value={memo}
                onChange={(event) => setMemo(event.target.value)}
                rows={3}
              />
            </dd>
          </>
        )}
      </dl>

      {error && <p className="new-customer-form__error">{error}</p>}

      <div className="activity-plan-list__edit-actions">
        <button
          type="button"
          className="activity-plan-list__result-button"
          onClick={handleSave}
          disabled={!isValid || isSaving}
        >
          {isSaving ? "登録中..." : "保存"}
        </button>
        <button type="button" className="activity-plan-list__undo-button" onClick={onCancel}>
          キャンセル
        </button>
      </div>
    </div>
  );
}

function QuickDeadlineForm({ repId, onDone }: { repId: number; onDone: () => void }) {
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

// 顧客一覧(とその詳細ページ)では新規顧客、それ以外のページでは予定をデフォルトにする。
// ログインページはAppNav自体が非表示のためここでは考慮不要。
function defaultTypeForPath(pathname: string): AddType {
  return pathname.startsWith("/customers") ? "customer" : "plan";
}

export function QuickAddFab() {
  const pathname = usePathname();
  const { selectedRep } = useRep();
  const { openRichPlanCreator } = useQuickAddPlan();
  const [isOpen, setIsOpen] = useState(false);
  const [activeType, setActiveType] = useState<AddType>("plan");

  // ダッシュボードでは「予定」に元々の詳細な作成パネル(ActivityPlanList)が
  // あるため、この簡易フォームは使わずそちらへ委譲する。開いた後に▼で
  // 「予定」へ切り替えた場合もここで拾えるよう、レイアウト確定前
  // (useLayoutEffect)で閉じて委譲することで簡易フォームがちらつくのを防ぐ。
  useLayoutEffect(() => {
    if (isOpen && activeType === "plan" && openRichPlanCreator) {
      setIsOpen(false);
      openRichPlanCreator();
    }
  }, [isOpen, activeType, openRichPlanCreator]);

  if (!selectedRep) {
    return null;
  }
  const repId = selectedRep.rep_id;

  function open() {
    const type = defaultTypeForPath(pathname);
    if (type === "plan" && openRichPlanCreator) {
      openRichPlanCreator();
      return;
    }
    setActiveType(type);
    setIsOpen(true);
  }

  function close() {
    setIsOpen(false);
  }

  return (
    <>
      <button type="button" className="plan-fab" onClick={open} aria-label="追加" title="追加">
        ＋
      </button>

      {isOpen && (
        <div className="plan-modal-overlay" onClick={close}>
          <div className="plan-modal" onClick={(event) => event.stopPropagation()}>
            <div className="plan-modal__header">
              <h3 className="quick-add-fab__title">
                <select
                  className="quick-add-fab__type-select"
                  value={activeType}
                  onChange={(event) => setActiveType(event.target.value as AddType)}
                  aria-label="追加する種類"
                >
                  <option value="plan">予定</option>
                  <option value="customer">新規顧客</option>
                  <option value="deadline">期限</option>
                </select>
                を追加
              </h3>
              <button
                type="button"
                className="plan-modal__close"
                onClick={close}
                aria-label="閉じる"
              >
                ×
              </button>
            </div>

            {activeType === "plan" && (
              <QuickPlanForm repId={repId} onDone={close} onCancel={close} />
            )}
            {activeType === "customer" && (
              <NewCustomerForm
                onCreate={async (input) => {
                  await createCustomer(repId, input);
                  close();
                }}
              />
            )}
            {activeType === "deadline" && <QuickDeadlineForm repId={repId} onDone={close} />}
          </div>
        </div>
      )}
    </>
  );
}
