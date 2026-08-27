"use client";

import { usePathname } from "next/navigation";
import { useState } from "react";
import { CompanyAutocompleteField, type CompanyFieldValue } from "@/components/CompanyAutocompleteField";
import { ProductAutocompleteField } from "@/components/ProductAutocompleteField";
import { NewCustomerForm } from "@/components/customers/NewCustomerForm";
import { QuickDealForm } from "@/components/QuickDealForm";
import { QuickDeadlineForm } from "@/components/QuickDeadlineForm";
import { createCustomer, createManualPlan } from "@/lib/api";
import { ADD_TYPE_LABELS, type AddType } from "@/lib/quickAddTypes";
import { useQuickAddPlan } from "@/lib/quickAddPlanContext";
import { useRep } from "@/lib/repContext";
import type { ActivityPlan, ActivityPlanCategory } from "@/types";

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
  const [company, setCompany] = useState<CompanyFieldValue>({ customerId: null, customerName: "" });
  const [productName, setProductName] = useState("");
  const [expectedProbability, setExpectedProbability] = useState(0);
  const [memo, setMemo] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isValid = company.customerName.trim().length > 0 && planDate.length > 0;

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
        customer_name: company.customerName.trim(),
        customer_id: company.customerId,
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
          {category === "visit" ? (
            <CompanyAutocompleteField
              repId={repId}
              value={company}
              onChange={setCompany}
              placeholder="例: D工業株式会社"
            />
          ) : (
            <input
              type="text"
              value={company.customerName}
              onChange={(event) => setCompany({ customerId: null, customerName: event.target.value })}
            />
          )}
        </dd>

        {category === "visit" && (
          <>
            <dt>商品</dt>
            <dd>
              <ProductAutocompleteField value={productName} onChange={setProductName} />
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

  if (!selectedRep) {
    return null;
  }
  const repId = selectedRep.rep_id;

  // ダッシュボードでは「予定」に元々の詳細な作成パネル(ActivityPlanList)があり、
  // そちらでは予定以外の種類にも切り替えられるため、そのまま委譲する。
  // それ以外のページでは、この種類選択モーダルを開く。
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
                  {Object.entries(ADD_TYPE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
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
            {activeType === "deal" && <QuickDealForm repId={repId} onDone={close} />}
          </div>
        </div>
      )}
    </>
  );
}
