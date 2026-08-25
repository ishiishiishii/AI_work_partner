"use client";

import { useRouter } from "next/navigation";
import { Fragment, useEffect, useState } from "react";
import { fetchProducts } from "@/lib/api";
import { mockTaskSuggestions } from "@/lib/mockData";
import type { ActivityPlan, ActivityPlanCategory, DealResultStatus } from "@/types";

export type PlanEditFields = {
  plan_date: string;
  start_time: string | null;
  end_time: string | null;
  category: ActivityPlanCategory;
  activity_type_name: string;
  customer_name: string;
  product_name: string | null;
  expected_probability: number;
  memo: string | null;
};

const CATEGORY_LABELS: Record<ActivityPlanCategory, string> = {
  visit: "企業訪問",
  task: "事務作業",
};

type ActivityPlanListProps = {
  repId: number;
  plans: ActivityPlan[];
  dailyTasks: ActivityPlan[];
  onResultChange: (planId: number, status: DealResultStatus, activityTypeName: string) => void;
  onRequestAlternative: (planId: number) => void;
  onEditPlan: (planId: number, updates: PlanEditFields) => void;
  onAddPlan: (plan: ActivityPlan) => void;
  onConfirmPlan: (planId: number) => void;
  onUpdateProgress: (planId: number, percent: number) => void;
  onCommitProgress: (planId: number, percent: number) => void;
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

// 予定の手動編集(内容)で選べる活動種別。既存のバッジ色分けと合わせている
const EDITABLE_ACTIVITY_TYPES = ["訪問", "電話", "メール", "Web会議", "資料作成", "新規開拓"];

const ACTIVITY_TYPE_CLASS: Record<string, string> = {
  訪問: "activity-plan-list__type--visit",
  電話: "activity-plan-list__type--call",
  メール: "activity-plan-list__type--email",
  Web会議: "activity-plan-list__type--online",
  資料作成: "activity-plan-list__type--prep",
  新規開拓: "activity-plan-list__type--prospect",
};

const VIEW_LABELS: Record<ViewMode, string> = { day: "日", week: "週", month: "月" };

// 進捗の円グラフ(ドーナツ)用の固定サイズ
const PROGRESS_RING_RADIUS = 28;
const PROGRESS_RING_CIRCUMFERENCE = 2 * Math.PI * PROGRESS_RING_RADIUS;

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

type CalendarDay = { date: string; inRange: boolean };

// 週表示の簡易カレンダー用: その週の月〜日の7日分
function getWeekDays(dateStr: string): CalendarDay[] {
  const monday = parseISODate(getWeekRange(dateStr).start);
  return Array.from({ length: 7 }, (_, i) => ({ date: formatISODate(addDays(monday, i)), inRange: true }));
}

// 月表示の簡易カレンダー用: 月の1日を含む週の月曜〜末日を含む週の日曜までを埋める。
// 前後月にはみ出す日付は inRange: false にして薄く表示する
function getMonthGridDays(dateStr: string): CalendarDay[] {
  const { start, end } = getMonthRange(dateStr);
  const monthStart = parseISODate(start);
  const monthEnd = parseISODate(end);
  const startWeekday = monthStart.getUTCDay(); // 0(日)〜6(土)
  const gridStart = addDays(monthStart, startWeekday === 0 ? -6 : 1 - startWeekday);
  const endWeekday = monthEnd.getUTCDay();
  const gridEnd = addDays(monthEnd, endWeekday === 0 ? 0 : 7 - endWeekday);

  const days: CalendarDay[] = [];
  for (let cursor = gridStart; cursor <= gridEnd; cursor = addDays(cursor, 1)) {
    const iso = formatISODate(cursor);
    days.push({ date: iso, inRange: iso >= start && iso <= end });
  }
  return days;
}

// 簡易カレンダーの日付セルに「どこの企業に行くか」を出すため、企業訪問(visit)を
// 日付ごとにまとめる。同じ日に同じ企業への訪問が複数あっても企業名は1つにまとめる
function groupVisitsByDate(items: ActivityPlan[]): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const item of items) {
    if (item.category !== "visit") continue;
    const list = map.get(item.plan_date);
    if (list) {
      if (!list.includes(item.customer_name)) list.push(item.customer_name);
    } else {
      map.set(item.plan_date, [item.customer_name]);
    }
  }
  return map;
}

function formatRangeLabel(viewMode: ViewMode, range: { start: string; end: string }): string {
  if (viewMode === "day") return `${formatDate(range.start)}の活動計画`;
  if (viewMode === "week") return `${formatDate(range.start)}〜${formatDate(range.end)}の活動計画`;
  const [year, month] = range.start.split("-");
  return `${year}年${Number(month)}月に狙うべき企業`;
}

function parseTimeToMinutes(time: string): number {
  const [hours, minutes] = time.split(":").map(Number);
  return hours * 60 + minutes;
}

function formatMinutesToTime(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${String(hours).padStart(2, "0")}:${String(mins).padStart(2, "0")}`;
}

function formatDurationMinutes(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (hours === 0) return `${mins}分`;
  if (mins === 0) return `${hours}時間`;
  return `${hours}時間${mins}分`;
}

// 「月」表示は個々の予定の日時ではなく、今月どの企業を狙うべきかを示す一覧にするため、
// 企業(customer_id)ごとにグルーピングし、グループ内は見込み金額×成約確率の高い順に並べる
type CompanyGroup = { customerName: string; customerId: number | null; items: ActivityPlan[]; totalValue: number };

function groupPlansByCompany(items: ActivityPlan[]): CompanyGroup[] {
  const groups = new Map<string, { customerName: string; customerId: number | null; items: ActivityPlan[] }>();
  for (const item of items) {
    const key = item.customer_id !== null ? String(item.customer_id) : item.customer_name;
    const group = groups.get(key);
    if (group) {
      group.items.push(item);
    } else {
      groups.set(key, { customerName: item.customer_name, customerId: item.customer_id, items: [item] });
    }
  }
  return Array.from(groups.values())
    .map(({ customerName, customerId, items: list }) => {
      const sorted = [...list].sort(
        (a, b) => b.expected_amount * b.expected_probability - a.expected_amount * a.expected_probability,
      );
      const totalValue = sorted.reduce(
        (sum, plan) => sum + (plan.expected_amount * plan.expected_probability) / 100,
        0,
      );
      return { customerName, customerId, items: sorted, totalValue };
    })
    .sort((a, b) => b.totalValue - a.totalValue);
}

// 開始・終了時間が両方わかる予定同士だけを対象に、時間の重複を検出する
function getOverlappingPlanIds(items: ActivityPlan[]): Set<number> {
  const timed = items.filter((item) => item.start_time && item.end_time);
  const overlapping = new Set<number>();
  for (let i = 0; i < timed.length; i++) {
    const aStart = parseTimeToMinutes(timed[i].start_time!);
    const aEnd = parseTimeToMinutes(timed[i].end_time!);
    for (let j = i + 1; j < timed.length; j++) {
      const bStart = parseTimeToMinutes(timed[j].start_time!);
      const bEnd = parseTimeToMinutes(timed[j].end_time!);
      if (aStart < bEnd && bStart < aEnd) {
        overlapping.add(timed[i].plan_id);
        overlapping.add(timed[j].plan_id);
      }
    }
  }
  return overlapping;
}

// 営業担当者の勤務時間(9:00〜17:00)。空き時間・お昼休憩の計算はこの枠内で行う
const WORK_DAY_START_MIN = 9 * 60;
const WORK_DAY_END_MIN = 17 * 60;
const LUNCH_START_MIN = 12 * 60;
const LUNCH_END_MIN = 13 * 60;

type Gap = { kind: "gap" | "lunch"; minutes: number; start: string; end: string };

// [startMin, endMin) の空き時間を、12:00〜13:00のお昼休憩の部分だけ切り出して
// 前後の「できる作業」候補にできる空き時間(gap)と、休憩(lunch)に分割する
function splitByLunch(startMin: number, endMin: number): Gap[] {
  const lunchStart = Math.max(startMin, LUNCH_START_MIN);
  const lunchEnd = Math.min(endMin, LUNCH_END_MIN);
  const segments: { kind: "gap" | "lunch"; startMin: number; endMin: number }[] = [];
  if (lunchStart < lunchEnd) {
    if (startMin < lunchStart) segments.push({ kind: "gap", startMin, endMin: lunchStart });
    segments.push({ kind: "lunch", startMin: lunchStart, endMin: lunchEnd });
    if (lunchEnd < endMin) segments.push({ kind: "gap", startMin: lunchEnd, endMin });
  } else {
    segments.push({ kind: "gap", startMin, endMin });
  }
  return segments
    .filter((segment) => segment.endMin > segment.startMin)
    .map((segment) => ({
      kind: segment.kind,
      minutes: segment.endMin - segment.startMin,
      start: formatMinutesToTime(segment.startMin),
      end: formatMinutesToTime(segment.endMin),
    }));
}

// 時系列順に見て、それまでで一番遅い終了時刻より後に始まる予定の直前に「空き時間」を計算する。
// 勤務時間(9:00〜17:00)を枠として、始業前の空きは最初の予定の前に、終業までの空きは
// 最後の予定の後ろ(trailing)に出す
function getDaySegments(items: ActivityPlan[]): { before: Map<number, Gap[]>; trailing: Gap[] } {
  const before = new Map<number, Gap[]>();
  const timed = items
    .filter((item) => item.start_time && item.end_time)
    .sort((a, b) => a.start_time!.localeCompare(b.start_time!));
  let cursor = WORK_DAY_START_MIN;
  for (const item of timed) {
    const start = parseTimeToMinutes(item.start_time!);
    const end = parseTimeToMinutes(item.end_time!);
    if (start > cursor) {
      before.set(item.plan_id, splitByLunch(cursor, start));
    }
    cursor = Math.max(cursor, end);
  }
  const trailing = cursor < WORK_DAY_END_MIN ? splitByLunch(cursor, WORK_DAY_END_MIN) : [];
  return { before, trailing };
}

export function ActivityPlanList({
  repId,
  plans,
  dailyTasks,
  onResultChange,
  onRequestAlternative,
  onEditPlan,
  onAddPlan,
  onConfirmPlan,
  onUpdateProgress,
  onCommitProgress,
}: ActivityPlanListProps) {
  const router = useRouter();
  const [viewMode, setViewMode] = useState<ViewMode>("day");
  const [contactTypeSelections, setContactTypeSelections] = useState<Record<number, string>>({});
  const [detailPlanId, setDetailPlanId] = useState<number | null>(null);
  const [newPlanDraft, setNewPlanDraft] = useState<ActivityPlan | null>(null);
  const [editDraft, setEditDraft] = useState<(PlanEditFields & { planId: number }) | null>(null);
  const [gapPicker, setGapPicker] = useState<{ start: string; maxEnd: string; end: string } | null>(null);
  // 「月」表示で商品名をダブルクリックした際に商品詳細ページへ飛べるよう、
  // 商品名→product_id の対応をあらかじめ取得しておく
  const [productIdByName, setProductIdByName] = useState<Map<string, number>>(new Map());

  useEffect(() => {
    let cancelled = false;
    fetchProducts()
      .then((products) => {
        if (!cancelled) setProductIdByName(new Map(products.map((product) => [product.product_name, product.product_id])));
      })
      .catch(() => {
        // 商品詳細への導線が使えなくなるだけなので、失敗しても画面全体は壊さない
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const [selectedDate, setSelectedDate] = useState(() => formatISODate(new Date()));

  const range = getRange(viewMode, selectedDate);
  const filteredPlans = plans.filter(
    (plan) => plan.plan_date >= range.start && plan.plan_date <= range.end,
  );
  // 資料作成・新規開拓などの顧客に紐づかない日次タスクは「日」表示でのみ、その日の分だけ
  // 合わせて表示する。商談(deal_id)に紐づくタスク(見積書作成・提案資料準備など)は
  // その企業への提案・契約に向けた準備という位置づけなので、週表示でも期間内の分を表示する。
  // 「月」は日時を持たない商材別の一覧にするため、タスクは対象外
  const filteredTasks =
    viewMode === "day"
      ? dailyTasks.filter((task) => task.plan_date === selectedDate)
      : viewMode === "week"
        ? dailyTasks.filter(
            (task) => task.deal_id !== null && task.plan_date >= range.start && task.plan_date <= range.end,
          )
        : [];
  const filtered = [...filteredPlans, ...filteredTasks].sort((a, b) => {
    if (viewMode === "day") {
      const timeA = a.start_time ?? "99:99";
      const timeB = b.start_time ?? "99:99";
      return timeA.localeCompare(timeB) || a.priority - b.priority;
    }
    return a.plan_date.localeCompare(b.plan_date) || a.priority - b.priority;
  });
  const monthGroups = viewMode === "month" ? groupPlansByCompany(filteredPlans) : [];

  // 週・月表示の上に出す簡易カレンダー。訪問予定は plans に日付を問わず全期間分入っているので、
  // 月表示ではみ出す前後月の日付にも訪問があれば表示できる
  const calendarDays =
    viewMode === "week" ? getWeekDays(selectedDate) : viewMode === "month" ? getMonthGridDays(selectedDate) : [];
  const visitsByDate = viewMode === "day" ? new Map<string, string[]>() : groupVisitsByDate(plans);
  const todayIso = formatISODate(new Date());

  const detailPlan =
    newPlanDraft && detailPlanId === newPlanDraft.plan_id
      ? newPlanDraft
      : detailPlanId !== null
        ? ([...plans, ...dailyTasks].find((plan) => plan.plan_id === detailPlanId) ?? null)
        : null;
  const isCreating = newPlanDraft !== null && detailPlan?.plan_id === newPlanDraft.plan_id;

  // 時間の重複・空き時間は「日」表示でのみ意味があるので、そこだけ計算する
  const overlappingPlanIds = viewMode === "day" ? getOverlappingPlanIds(filtered) : new Set<number>();
  const { before: gapBeforePlanId, trailing: trailingGaps } =
    viewMode === "day" ? getDaySegments(filtered) : { before: new Map<number, Gap[]>(), trailing: [] };

  // 空き時間にできる事務作業の候補(プランA/B/C…)。既にその日の計画で使われている
  // 候補は除外し、固定プールの中で未使用のものを件数の制限なく全て出す
  const usedTaskTitles = new Set([...plans, ...dailyTasks].map((item) => item.customer_name));
  const gapCandidates = mockTaskSuggestions.filter((task) => !usedTaskTitles.has(task.title));

  // 空き時間(gap)はダブルクリックで作業候補を提案できるが、お昼休憩(lunch)はクリック不可の表示のみ
  function renderGapSegment(segment: Gap, key: string) {
    if (segment.kind === "lunch") {
      return (
        <li key={key} className="activity-plan-list__lunch">
          昼休憩 {segment.start}〜{segment.end}
        </li>
      );
    }
    return (
      <li
        key={key}
        className="activity-plan-list__gap"
        onDoubleClick={() => openGapPicker(segment.start, segment.end)}
        title="ダブルクリックでこの時間にできる作業を提案"
      >
        空き時間 {formatDurationMinutes(segment.minutes)}
      </li>
    );
  }

  function openCustomerDetail(customerId: number | null) {
    if (customerId === null) return;
    router.push(`/customers/${customerId}`);
  }

  function openProductDetail(productName: string | null) {
    if (!productName) return;
    const productId = productIdByName.get(productName);
    if (productId === undefined) return;
    router.push(`/products/${productId}`);
  }

  function openGapPicker(start: string, end: string) {
    setGapPicker({ start, maxEnd: end, end });
  }

  function closeGapPicker() {
    setGapPicker(null);
  }

  // 空き時間の枠(start〜maxEnd)を超えない範囲でのみ終了時間を変更できるようにする
  function setGapPickerEnd(end: string) {
    setGapPicker((prev) => (prev ? { ...prev, end: end > prev.maxEnd ? prev.maxEnd : end } : prev));
  }

  function pickGapCandidate(candidate: (typeof mockTaskSuggestions)[number]) {
    if (!gapPicker) return;
    onAddPlan({
      plan_id: -Date.now(),
      rep_id: repId,
      plan_date: selectedDate,
      start_time: gapPicker.start,
      end_time: gapPicker.end > gapPicker.start ? gapPicker.end : gapPicker.maxEnd,
      category: "task",
      customer_id: null,
      customer_name: candidate.title,
      deal_id: null,
      product_name: null,
      activity_type_name: candidate.activityTypeName,
      priority: 3,
      expected_amount: 0,
      expected_probability: 0,
      is_ai_generated: true,
      reasoning_text: candidate.reasoningText,
      result_status: "pending",
      memo: null,
      progress_percent: 0,
    });
    closeGapPicker();
  }

  function getSelectedContactType(plan: ActivityPlan): string {
    return contactTypeSelections[plan.plan_id] ?? plan.activity_type_name;
  }

  // ステータスの記録・取り消しUI。一覧行と詳細モーダルの両方で同じものを使う
  function renderResultControls(plan: ActivityPlan) {
    if (plan.result_status === "pending") {
      return (
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
              onClick={() => onResultChange(plan.plan_id, option.value, getSelectedContactType(plan))}
            >
              {option.label}
            </button>
          ))}
        </>
      );
    }
    return (
      <>
        <span className={`activity-plan-list__result-button is-active is-active--${plan.result_status}`}>
          {RESULT_OPTIONS.find((option) => option.value === plan.result_status)?.label}
        </span>
        <button
          type="button"
          className="activity-plan-list__undo-button"
          onClick={() => onResultChange(plan.plan_id, plan.result_status, getSelectedContactType(plan))}
        >
          取り消す
        </button>
      </>
    );
  }

  // 一覧行・詳細モーダル・「月」表示(企業グループ)から共通で使う予定1件分の中身。
  // dateLabel は「日」の時刻・その他の日付表示用。月表示では日時を出さないため null を渡す。
  // hideCustomerName は「月」表示用: 企業名は既にグループ見出しに出ているため、行側は商品名を主表示にする
  function renderPlanRow(plan: ActivityPlan, dateLabel: string | null, isOverlapping = false, hideCustomerName = false) {
    return (
      <>
        <div
          className="activity-plan-list__clickable"
          onClick={() => openDetail(plan)}
          title="クリックで詳細を表示"
        >
          {dateLabel !== null && <div className="activity-plan-list__date">{dateLabel}</div>}
          <div className="activity-plan-list__main">
            {hideCustomerName && plan.product_name ? (
              <div className="activity-plan-list__customer">
                <span
                  className="activity-plan-list__link"
                  onClick={(event) => {
                    event.stopPropagation();
                    openProductDetail(plan.product_name);
                  }}
                  title="ダブルクリックで商品詳細へ"
                >
                  {plan.product_name}
                </span>
                {plan.is_ai_generated && <span className="badge badge--ai">AI提案</span>}
              </div>
            ) : (
              <>
                <div className="activity-plan-list__customer">
                  {plan.customer_name}
                  {plan.is_ai_generated && <span className="badge badge--ai">AI提案</span>}
                </div>
                {plan.category === "visit" && plan.product_name && (
                  <div className="activity-plan-list__product">商品: {plan.product_name}</div>
                )}
              </>
            )}
            <div className="activity-plan-list__meta">
              <span
                className={`activity-plan-list__type ${
                  ACTIVITY_TYPE_CLASS[plan.activity_type_name] ?? "activity-plan-list__type--default"
                }`}
              >
                {plan.activity_type_name}
              </span>
              {plan.category === "visit" && (
                <span>
                  優先度{plan.priority}・成約確率{plan.expected_probability.toFixed(0)}%
                </span>
              )}
              {isOverlapping && <span className="activity-plan-list__warning">⚠ 時間が重複しています</span>}
            </div>
          </div>
          {plan.expected_amount > 0 && (
            <div className="activity-plan-list__amount">{formatYen(plan.expected_amount)}</div>
          )}
        </div>
        {plan.category === "visit" && (
          <div className="activity-plan-list__result-buttons">
            {renderResultControls(plan)}
            {plan.result_status === "pending" && (
              <button
                type="button"
                className="activity-plan-list__alt-button"
                onClick={() => onRequestAlternative(plan.plan_id)}
              >
                対応が難しい
              </button>
            )}
          </div>
        )}
      </>
    );
  }

  function openDetail(plan: ActivityPlan) {
    setDetailPlanId(plan.plan_id);
    setNewPlanDraft(null);
    setEditDraft(null);
  }

  function closeDetail() {
    setDetailPlanId(null);
    setNewPlanDraft(null);
    setEditDraft(null);
  }

  function startEdit(plan: ActivityPlan) {
    setDetailPlanId(plan.plan_id);
    setEditDraft({
      planId: plan.plan_id,
      plan_date: plan.plan_date,
      start_time: plan.start_time,
      end_time: plan.end_time,
      category: plan.category,
      activity_type_name: plan.activity_type_name,
      customer_name: plan.customer_name,
      product_name: plan.product_name,
      expected_probability: plan.expected_probability,
      memo: plan.memo,
    });
  }

  // 引数無しなら空の新規予定、引数ありなら会社・商品などを引き継いだ「次回の予定」を作る
  function startCreate(base?: ActivityPlan) {
    const draft: ActivityPlan = base
      ? {
          ...base,
          plan_id: -Date.now(),
          plan_date: selectedDate,
          start_time: null,
          end_time: null,
          is_ai_generated: false,
          reasoning_text: "",
          result_status: "pending",
          memo: null,
          progress_percent: 0,
        }
      : {
          plan_id: -Date.now(),
          rep_id: repId,
          plan_date: selectedDate,
          start_time: null,
          end_time: null,
          category: "task",
          customer_id: null,
          customer_name: "",
          deal_id: null,
          product_name: null,
          activity_type_name: "資料作成",
          priority: 3,
          expected_amount: 0,
          expected_probability: 0,
          is_ai_generated: false,
          reasoning_text: "",
          result_status: "pending",
          memo: null,
          progress_percent: 0,
        };
    setNewPlanDraft(draft);
    setDetailPlanId(draft.plan_id);
    setEditDraft({
      planId: draft.plan_id,
      plan_date: draft.plan_date,
      start_time: draft.start_time,
      end_time: draft.end_time,
      category: draft.category,
      activity_type_name: draft.activity_type_name,
      customer_name: draft.customer_name,
      product_name: draft.product_name,
      expected_probability: draft.expected_probability,
      memo: draft.memo,
    });
  }

  function cancelEdit() {
    if (newPlanDraft) {
      setNewPlanDraft(null);
      setDetailPlanId(null);
    }
    setEditDraft(null);
  }

  function saveEdit() {
    if (!editDraft) return;
    const { planId, ...updates } = editDraft;
    const normalized = {
      ...updates,
      customer_name: updates.customer_name.trim() || "(未設定)",
      product_name: updates.product_name?.trim() || null,
      expected_probability: Math.min(100, Math.max(0, updates.expected_probability)),
      memo: updates.memo?.trim() || null,
    };

    if (newPlanDraft && planId === newPlanDraft.plan_id) {
      onAddPlan({ ...newPlanDraft, ...normalized });
      setNewPlanDraft(null);
      setDetailPlanId(null);
      setEditDraft(null);
      return;
    }

    onEditPlan(planId, normalized);
    setEditDraft(null);
  }

  function jumpToDay(date: string) {
    setSelectedDate(date);
    setViewMode("day");
  }

  // 表示中のビュー(日/週/月)を保ったまま、選択日だけ今日に戻す
  function jumpToToday() {
    setSelectedDate(todayIso);
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
    <>
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
        <button
          type="button"
          className="activity-plan-list__today-button"
          onClick={jumpToToday}
          disabled={selectedDate === todayIso}
        >
          今日
        </button>
        <button type="button" onClick={() => handleShift(1)}>
          次へ →
        </button>
      </div>

      {viewMode !== "day" && (
        <div className="mini-calendar">
          <div className="mini-calendar__weekdays">
            {["月", "火", "水", "木", "金", "土", "日"].map((label) => (
              <div key={label} className="mini-calendar__weekday">
                {label}
              </div>
            ))}
          </div>
          <div className={`mini-calendar__grid mini-calendar__grid--${viewMode}`}>
            {calendarDays.map((day) => {
              const companies = visitsByDate.get(day.date) ?? [];
              const visibleCompanies = companies.slice(0, 2);
              const dayNumber = Number(day.date.split("-")[2]);
              return (
                <button
                  type="button"
                  key={day.date}
                  className={`mini-calendar__day${day.inRange ? "" : " mini-calendar__day--outside"}${
                    day.date === selectedDate ? " is-selected" : ""
                  }${day.date === todayIso ? " is-today" : ""}`}
                  onClick={() => jumpToDay(day.date)}
                  title={`クリックで${formatDate(day.date)}の予定へ`}
                >
                  <span className="mini-calendar__day-number">{dayNumber}</span>
                  {visibleCompanies.length > 0 && (
                    <span className="mini-calendar__day-companies">
                      {visibleCompanies.map((name) => (
                        <span key={name} className="mini-calendar__company-chip">
                          {name}
                        </span>
                      ))}
                      {companies.length > visibleCompanies.length && (
                        <span className="mini-calendar__more">+{companies.length - visibleCompanies.length}</span>
                      )}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {viewMode === "month" ? (
        monthGroups.length === 0 ? (
          <p className="activity-plan-list__empty">この期間の活動計画はありません</p>
        ) : (
          <div className="activity-plan-list__groups">
            {monthGroups.map((group) => (
              <div key={group.customerName} className="activity-plan-list__group">
                <h3 className="activity-plan-list__group-title">
                  <span
                    className="activity-plan-list__link"
                    onClick={() => openCustomerDetail(group.customerId)}
                    title="クリックで顧客詳細へ"
                  >
                    {group.customerName}
                  </span>
                  <span className="activity-plan-list__group-total">
                    見込み合計 {formatYen(Math.round(group.totalValue))}
                  </span>
                </h3>
                <ul className="activity-plan-list__items">
                  {group.items.map((plan) => (
                    <li key={plan.plan_id} className="activity-plan-list__item">
                      {renderPlanRow(plan, null, false, true)}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )
      ) : filtered.length === 0 ? (
        <p className="activity-plan-list__empty">この期間の活動計画はありません</p>
      ) : (
        <ul className="activity-plan-list__items">
          {filtered.map((plan) => {
            const gapSegments = gapBeforePlanId.get(plan.plan_id) ?? [];
            const isOverlapping = overlappingPlanIds.has(plan.plan_id);
            const dateLabel =
              viewMode === "day" && plan.start_time
                ? plan.end_time
                  ? `${plan.start_time}〜${plan.end_time}`
                  : plan.start_time
                : formatDate(plan.plan_date);
            return (
              <Fragment key={plan.plan_id}>
                {gapSegments.map((segment, index) => renderGapSegment(segment, `before-${plan.plan_id}-${index}`))}
                <li
                  className={`activity-plan-list__item${
                    isOverlapping ? " activity-plan-list__item--overlap" : ""
                  }`}
                >
                  {renderPlanRow(plan, dateLabel, isOverlapping)}
                </li>
              </Fragment>
            );
          })}
          {trailingGaps.map((segment, index) => renderGapSegment(segment, `trailing-${index}`))}
        </ul>
      )}
    </section>

    {detailPlan && (
      <div className="plan-modal-overlay" onClick={closeDetail}>
        <div className="plan-modal" onClick={(event) => event.stopPropagation()}>
          <div className="plan-modal__header">
            <h3>{isCreating ? "予定を追加" : "予定の詳細"}</h3>
            <button type="button" className="plan-modal__close" onClick={closeDetail} aria-label="閉じる">
              ×
            </button>
          </div>

          {(() => {
            const isEditing = editDraft !== null && editDraft.planId === detailPlan.plan_id;
            const effectiveCategory = isEditing ? editDraft.category : detailPlan.category;
            return (
              <div className="plan-modal__detail">
                <dl className="plan-modal__fields">
                  <dt>日付</dt>
                  <dd>
                    {isEditing ? (
                      <input
                        type="date"
                        value={editDraft.plan_date}
                        onChange={(event) => setEditDraft({ ...editDraft, plan_date: event.target.value })}
                      />
                    ) : (
                      formatDate(detailPlan.plan_date)
                    )}
                  </dd>

                  <dt>種別</dt>
                  <dd>
                    {isEditing ? (
                      <select
                        value={editDraft.category}
                        onChange={(event) =>
                          setEditDraft({ ...editDraft, category: event.target.value as ActivityPlanCategory })
                        }
                      >
                        <option value="visit">{CATEGORY_LABELS.visit}</option>
                        <option value="task">{CATEGORY_LABELS.task}</option>
                      </select>
                    ) : (
                      CATEGORY_LABELS[detailPlan.category]
                    )}
                  </dd>

                  <dt>時間</dt>
                  <dd>
                    {isEditing ? (
                      <span className="plan-modal__time-inputs">
                        <input
                          type="time"
                          value={editDraft.start_time ?? ""}
                          onChange={(event) =>
                            setEditDraft({ ...editDraft, start_time: event.target.value || null })
                          }
                        />
                        〜
                        <input
                          type="time"
                          value={editDraft.end_time ?? ""}
                          onChange={(event) =>
                            setEditDraft({ ...editDraft, end_time: event.target.value || null })
                          }
                        />
                      </span>
                    ) : detailPlan.start_time ? (
                      `${detailPlan.start_time}${detailPlan.end_time ? `〜${detailPlan.end_time}` : ""}`
                    ) : (
                      "未設定"
                    )}
                  </dd>

                  <dt>内容</dt>
                  <dd>
                    {isEditing ? (
                      <select
                        value={editDraft.activity_type_name}
                        onChange={(event) =>
                          setEditDraft({ ...editDraft, activity_type_name: event.target.value })
                        }
                      >
                        {EDITABLE_ACTIVITY_TYPES.map((type) => (
                          <option key={type} value={type}>
                            {type}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span
                        className={`activity-plan-list__type ${
                          ACTIVITY_TYPE_CLASS[detailPlan.activity_type_name] ??
                          "activity-plan-list__type--default"
                        }`}
                      >
                        {detailPlan.activity_type_name}
                      </span>
                    )}
                  </dd>

                  <dt>{effectiveCategory === "visit" ? "会社" : "件名"}</dt>
                  <dd>
                    {isEditing ? (
                      <input
                        type="text"
                        value={editDraft.customer_name}
                        onChange={(event) => setEditDraft({ ...editDraft, customer_name: event.target.value })}
                      />
                    ) : (
                      detailPlan.customer_name
                    )}
                  </dd>

                  {effectiveCategory === "visit" && (
                    <>
                      <dt>商品</dt>
                      <dd>
                        {isEditing ? (
                          <input
                            type="text"
                            value={editDraft.product_name ?? ""}
                            onChange={(event) =>
                              setEditDraft({ ...editDraft, product_name: event.target.value })
                            }
                          />
                        ) : (
                          (detailPlan.product_name ?? "(未設定)")
                        )}
                      </dd>
                    </>
                  )}

                  {detailPlan.expected_amount > 0 && (
                    <>
                      <dt>見込み金額</dt>
                      <dd>{formatYen(detailPlan.expected_amount)}</dd>
                    </>
                  )}
                  {effectiveCategory === "visit" && (
                    <>
                      <dt>優先度</dt>
                      <dd>優先度{detailPlan.priority}</dd>

                      <dt>成約確率</dt>
                      <dd>
                        {isEditing ? (
                          <span className="plan-modal__percent-input">
                            <input
                              type="number"
                              min={0}
                              max={100}
                              step={5}
                              value={editDraft.expected_probability}
                              onChange={(event) =>
                                setEditDraft({
                                  ...editDraft,
                                  expected_probability: Number(event.target.value),
                                })
                              }
                            />
                            %
                          </span>
                        ) : (
                          `${detailPlan.expected_probability.toFixed(0)}%`
                        )}
                      </dd>

                      <dt>メモ</dt>
                      <dd>
                        {isEditing ? (
                          <textarea
                            className="plan-modal__memo-input"
                            value={editDraft.memo ?? ""}
                            onChange={(event) => setEditDraft({ ...editDraft, memo: event.target.value })}
                            rows={3}
                          />
                        ) : (
                          (detailPlan.memo ?? "(メモなし)")
                        )}
                      </dd>

                      <dt>ステータス</dt>
                      <dd className="plan-modal__status-controls">{renderResultControls(detailPlan)}</dd>
                    </>
                  )}
                  {effectiveCategory === "task" && !detailPlan.is_ai_generated && (
                    <>
                      <dt>進捗</dt>
                      <dd>
                        <div className="plan-modal__progress">
                          <svg className="plan-modal__progress-ring" viewBox="0 0 80 80" width="64" height="64">
                            <circle cx="40" cy="40" r={PROGRESS_RING_RADIUS} className="plan-modal__progress-ring-track" />
                            <circle
                              cx="40"
                              cy="40"
                              r={PROGRESS_RING_RADIUS}
                              className="plan-modal__progress-ring-value"
                              strokeDasharray={PROGRESS_RING_CIRCUMFERENCE}
                              strokeDashoffset={
                                PROGRESS_RING_CIRCUMFERENCE * (1 - detailPlan.progress_percent / 100)
                              }
                            />
                            <text x="40" y="45" textAnchor="middle" className="plan-modal__progress-ring-label">
                              {detailPlan.progress_percent}%
                            </text>
                          </svg>
                          <input
                            type="range"
                            min={0}
                            max={100}
                            step={5}
                            value={detailPlan.progress_percent}
                            onChange={(event) => onUpdateProgress(detailPlan.plan_id, Number(event.target.value))}
                            onMouseUp={(event) =>
                              onCommitProgress(detailPlan.plan_id, Number(event.currentTarget.value))
                            }
                            onTouchEnd={(event) =>
                              onCommitProgress(detailPlan.plan_id, Number(event.currentTarget.value))
                            }
                            onKeyUp={(event) =>
                              onCommitProgress(detailPlan.plan_id, Number(event.currentTarget.value))
                            }
                          />
                        </div>
                      </dd>
                    </>
                  )}
                </dl>
                {detailPlan.reasoning_text && (
                  <div className="plan-modal__reasoning">
                    <h4>AIの提案理由</h4>
                    <p>{detailPlan.reasoning_text}</p>
                  </div>
                )}
                <div className="activity-plan-list__edit-actions">
                  {isEditing ? (
                    <>
                      <button type="button" className="activity-plan-list__result-button" onClick={saveEdit}>
                        保存
                      </button>
                      <button type="button" className="activity-plan-list__undo-button" onClick={cancelEdit}>
                        キャンセル
                      </button>
                    </>
                  ) : (
                    <>
                      {detailPlan.is_ai_generated && (
                        <button
                          type="button"
                          className="activity-plan-list__result-button"
                          onClick={() => onConfirmPlan(detailPlan.plan_id)}
                        >
                          確定する
                        </button>
                      )}
                      <button
                        type="button"
                        className="activity-plan-list__result-button"
                        onClick={() => startEdit(detailPlan)}
                      >
                        編集
                      </button>
                      <button
                        type="button"
                        className="activity-plan-list__alt-button"
                        onClick={() => onRequestAlternative(detailPlan.plan_id)}
                      >
                        AI作り直し
                      </button>
                      {detailPlan.category === "visit" && (
                        <button
                          type="button"
                          className="activity-plan-list__result-button"
                          onClick={() => startCreate(detailPlan)}
                        >
                          次回の予定を作成
                        </button>
                      )}
                      <button type="button" className="activity-plan-list__undo-button" onClick={closeDetail}>
                        閉じる
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })()}
        </div>
      </div>
    )}

    {gapPicker && (
      <div className="plan-modal-overlay" onClick={closeGapPicker}>
        <div className="plan-modal" onClick={(event) => event.stopPropagation()}>
          <div className="plan-modal__header">
            <h3>{gapPicker.start}〜にできる作業</h3>
            <button type="button" className="plan-modal__close" onClick={closeGapPicker} aria-label="閉じる">
              ×
            </button>
          </div>
          <label className="gap-picker__end-field">
            終了時間
            <input
              type="time"
              value={gapPicker.end}
              min={gapPicker.start}
              max={gapPicker.maxEnd}
              onChange={(event) => setGapPickerEnd(event.target.value)}
            />
          </label>
          {gapCandidates.length === 0 ? (
            <p className="activity-plan-list__empty">現在、提案できる候補がありません。</p>
          ) : (
            <ul className="gap-picker__options">
              {gapCandidates.map((candidate, index) => (
                <li key={candidate.title} className="gap-picker__option">
                  <div className="gap-picker__option-header">
                    <span className="badge badge--ai">プラン{String.fromCharCode(65 + index)}</span>
                    <span
                      className={`activity-plan-list__type ${
                        ACTIVITY_TYPE_CLASS[candidate.activityTypeName] ?? "activity-plan-list__type--default"
                      }`}
                    >
                      {candidate.activityTypeName}
                    </span>
                  </div>
                  <div className="gap-picker__option-title">{candidate.title}</div>
                  <p className="gap-picker__option-reason">{candidate.reasoningText}</p>
                  <button
                    type="button"
                    className="activity-plan-list__result-button"
                    onClick={() => pickGapCandidate(candidate)}
                  >
                    この作業にする
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    )}

    <button type="button" className="plan-fab" onClick={() => startCreate()} aria-label="予定を追加" title="予定を追加">
      ＋
    </button>
    </>
  );
}
