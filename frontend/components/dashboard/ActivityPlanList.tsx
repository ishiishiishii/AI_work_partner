"use client";

import { useState } from "react";
import type { ActivityPlan, DealResultStatus } from "@/types";

type ActivityPlanListProps = {
  plans: ActivityPlan[];
  dailyTasks: ActivityPlan[];
  onResultChange: (planId: number, status: DealResultStatus, activityTypeName: string) => void;
  onRequestAlternative: (planId: number) => void;
};

type ViewMode = "day" | "week" | "month";

const RESULT_OPTIONS: { value: DealResultStatus; label: string }[] = [
  { value: "won", label: "成約" },
  { value: "lost", label: "失注" },
  { value: "postponed", label: "延期" },
];

// バックエンドの計画生成は今のところ「訪問」しか作らないため、
// 記録時に実際どう対応したかをここで選べるようにしている
const CONTACT_TYPE_OPTIONS = ["訪問", "電話", "メール", "Web会議"];

const ACTIVITY_TYPE_CLASS: Record<string, string> = {
  訪問: "activity-plan-list__type--visit",
  電話: "activity-plan-list__type--call",
  メール: "activity-plan-list__type--email",
  Web会議: "activity-plan-list__type--online",
  資料作成: "activity-plan-list__type--prep",
  新規開拓: "activity-plan-list__type--prospect",
};

const VIEW_LABELS: Record<ViewMode, string> = { day: "日", week: "週", month: "月" };

function formatYen(amount: number): string {
  return `¥${amount.toLocaleString("ja-JP")}`;
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const weekday = "日月火水木金土"[date.getDay()];
  return `${date.getMonth() + 1}/${date.getDate()}(${weekday})`;
}

// 以下の日付計算はすべて UTC 基準で行い、タイムゾーンによるズレを避ける
function parseISODate(dateStr: string): Date {
  const [year, month, day] = dateStr.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

function formatISODate(date: Date): string {
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addDays(date: Date, amount: number): Date {
  const next = new Date(date);
  next.setUTCDate(next.getUTCDate() + amount);
  return next;
}

function getWeekRange(dateStr: string): { start: string; end: string } {
  const date = parseISODate(dateStr);
  const weekday = date.getUTCDay(); // 0(日)〜6(土)
  const diffToMonday = weekday === 0 ? -6 : 1 - weekday;
  const monday = addDays(date, diffToMonday);
  return { start: formatISODate(monday), end: formatISODate(addDays(monday, 6)) };
}

function getMonthRange(dateStr: string): { start: string; end: string } {
  const date = parseISODate(dateStr);
  const year = date.getUTCFullYear();
  const month = date.getUTCMonth();
  const start = new Date(Date.UTC(year, month, 1));
  const end = new Date(Date.UTC(year, month + 1, 0));
  return { start: formatISODate(start), end: formatISODate(end) };
}

function getRange(viewMode: ViewMode, selectedDate: string): { start: string; end: string } {
  if (viewMode === "day") return { start: selectedDate, end: selectedDate };
  if (viewMode === "week") return getWeekRange(selectedDate);
  return getMonthRange(selectedDate);
}

function formatRangeLabel(viewMode: ViewMode, range: { start: string; end: string }): string {
  if (viewMode === "day") return `${formatDate(range.start)}の活動計画`;
  if (viewMode === "week") return `${formatDate(range.start)}〜${formatDate(range.end)}の活動計画`;
  const [year, month] = range.start.split("-");
  return `${year}年${Number(month)}月の活動計画`;
}

export function ActivityPlanList({
  plans,
  dailyTasks,
  onResultChange,
  onRequestAlternative,
}: ActivityPlanListProps) {
  const [viewMode, setViewMode] = useState<ViewMode>("week");
  const [contactTypeSelections, setContactTypeSelections] = useState<Record<number, string>>({});
  const [selectedDate, setSelectedDate] = useState(() => {
    const earliest = plans.reduce(
      (min, plan) => (plan.plan_date < min ? plan.plan_date : min),
      plans[0]?.plan_date,
    );
    return earliest ?? formatISODate(new Date());
  });

  const range = getRange(viewMode, selectedDate);
  const filteredPlans = plans.filter(
    (plan) => plan.plan_date >= range.start && plan.plan_date <= range.end,
  );
  // 資料作成・新規開拓などの日次タスクは「日」表示でのみ、その日の分だけ合わせて表示する
  const filteredTasks =
    viewMode === "day" ? dailyTasks.filter((task) => task.plan_date === selectedDate) : [];
  const filtered = [...filteredPlans, ...filteredTasks].sort((a, b) => {
    if (viewMode === "day") {
      const timeA = a.start_time ?? "99:99";
      const timeB = b.start_time ?? "99:99";
      return timeA.localeCompare(timeB) || a.priority - b.priority;
    }
    return a.plan_date.localeCompare(b.plan_date) || a.priority - b.priority;
  });

  function getSelectedContactType(plan: ActivityPlan): string {
    return contactTypeSelections[plan.plan_id] ?? plan.activity_type_name;
  }

  function handleShift(direction: -1 | 1) {
    const date = parseISODate(selectedDate);
    if (viewMode === "day") {
      setSelectedDate(formatISODate(addDays(date, direction)));
    } else if (viewMode === "week") {
      setSelectedDate(formatISODate(addDays(date, direction * 7)));
    } else {
      const year = date.getUTCFullYear();
      const month = date.getUTCMonth();
      setSelectedDate(formatISODate(new Date(Date.UTC(year, month + direction, 1))));
    }
  }

  return (
    <section className="panel activity-plan-list">
      <div className="activity-plan-list__header">
        <h2>{formatRangeLabel(viewMode, range)}</h2>
        <div className="activity-plan-list__tabs">
          {(Object.keys(VIEW_LABELS) as ViewMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              className={`activity-plan-list__tab${viewMode === mode ? " is-active" : ""}`}
              onClick={() => setViewMode(mode)}
            >
              {VIEW_LABELS[mode]}
            </button>
          ))}
        </div>
      </div>

      <div className="activity-plan-list__nav">
        <button type="button" onClick={() => handleShift(-1)}>
          ← 前へ
        </button>
        <button type="button" onClick={() => handleShift(1)}>
          次へ →
        </button>
      </div>

      {filtered.length === 0 ? (
        <p className="activity-plan-list__empty">この期間の活動計画はありません</p>
      ) : (
        <ul className="activity-plan-list__items">
          {filtered.map((plan) => (
            <li key={plan.plan_id} className="activity-plan-list__item">
              <div className="activity-plan-list__date">
                {viewMode === "day" && plan.start_time ? plan.start_time : formatDate(plan.plan_date)}
              </div>
              <div className="activity-plan-list__main">
                <div className="activity-plan-list__customer">
                  {plan.customer_name}
                  {plan.is_ai_generated && <span className="badge badge--ai">AI提案</span>}
                </div>
                <div className="activity-plan-list__meta">
                  <span
                    className={`activity-plan-list__type ${
                      ACTIVITY_TYPE_CLASS[plan.activity_type_name] ??
                      "activity-plan-list__type--default"
                    }`}
                  >
                    {plan.activity_type_name}
                  </span>
                  {plan.customer_id && (
                    <span>
                      優先度{plan.priority}・成約確率{plan.expected_probability.toFixed(0)}%
                    </span>
                  )}
                </div>
              </div>
              {plan.expected_amount > 0 && (
                <div className="activity-plan-list__amount">{formatYen(plan.expected_amount)}</div>
              )}
              {plan.customer_id && (
                <div className="activity-plan-list__result-buttons">
                  {plan.result_status === "pending" ? (
                    <>
                      <label className="activity-plan-list__contact-type">
                        実際の対応:
                        <select
                          value={getSelectedContactType(plan)}
                          onChange={(event) =>
                            setContactTypeSelections((prev) => ({
                              ...prev,
                              [plan.plan_id]: event.target.value,
                            }))
                          }
                        >
                          {CONTACT_TYPE_OPTIONS.map((type) => (
                            <option key={type} value={type}>
                              {type}
                            </option>
                          ))}
                        </select>
                      </label>
                      {RESULT_OPTIONS.map((option) => (
                        <button
                          key={option.value}
                          type="button"
                          className="activity-plan-list__result-button"
                          onClick={() =>
                            onResultChange(plan.plan_id, option.value, getSelectedContactType(plan))
                          }
                        >
                          {option.label}
                        </button>
                      ))}
                      <button
                        type="button"
                        className="activity-plan-list__alt-button"
                        onClick={() => onRequestAlternative(plan.plan_id)}
                      >
                        対応が難しい
                      </button>
                    </>
                  ) : (
                    <>
                      <span
                        className={`activity-plan-list__result-button is-active is-active--${plan.result_status}`}
                      >
                        {RESULT_OPTIONS.find((option) => option.value === plan.result_status)?.label}
                      </span>
                      <button
                        type="button"
                        className="activity-plan-list__undo-button"
                        onClick={() =>
                          onResultChange(plan.plan_id, plan.result_status, getSelectedContactType(plan))
                        }
                      >
                        取り消す
                      </button>
                    </>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
