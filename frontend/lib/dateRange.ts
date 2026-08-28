export type ViewMode = "day" | "week" | "month";

export function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const weekday = "日月火水木金土"[date.getDay()];
  return `${date.getMonth() + 1}/${date.getDate()}(${weekday})`;
}

// 以下の日付計算はすべて UTC 基準で行い、タイムゾーンによるズレを避ける
export function parseISODate(dateStr: string): Date {
  const [year, month, day] = dateStr.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

export function formatISODate(date: Date): string {
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

// new Date() は「現在の実時刻」であり UTC 起点のカレンダー日付ではないため、
// formatISODate(new Date()) はJST 0:00〜8:59の間UTC基準で前日を返してしまう。
// 「今日」はローカル(ブラウザ)の暦日で判定する。
export function todayIsoLocal(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function addDays(date: Date, amount: number): Date {
  const next = new Date(date);
  next.setUTCDate(next.getUTCDate() + amount);
  return next;
}

export function getMonday(date: Date): Date {
  const weekday = date.getUTCDay(); // 0(日)〜6(土)
  const diffToMonday = weekday === 0 ? -6 : 1 - weekday;
  return addDays(date, diffToMonday);
}

export function getWeekRange(dateStr: string): { start: string; end: string } {
  const monday = getMonday(parseISODate(dateStr));
  return { start: formatISODate(monday), end: formatISODate(addDays(monday, 6)) };
}

// バックエンド(PlanOut.week_number)と同じ「月内の月曜始まり週をその月の最初の営業日
// から連番で数える」定義のフォールバック計算。楽観的更新で作った予定(APIから
// week_number がまだ返っていない)の表示用に使う。
export function getBusinessWeekNumber(dateStr: string): number {
  const date = parseISODate(dateStr);
  const year = date.getUTCFullYear();
  const month = date.getUTCMonth();
  let firstBusinessDay = new Date(Date.UTC(year, month, 1));
  while (firstBusinessDay.getUTCDay() === 0 || firstBusinessDay.getUTCDay() === 6) {
    firstBusinessDay = addDays(firstBusinessDay, 1);
  }
  const diffDays = Math.round(
    (getMonday(date).getTime() - getMonday(firstBusinessDay).getTime()) / (24 * 60 * 60 * 1000),
  );
  // 月初が土日の場合、その週末日は最初の営業日より前のMondayに属するため、
  // 第1週として扱う(第0週・マイナスは表示上不自然なため切り上げる)
  return Math.max(1, Math.floor(diffDays / 7) + 1);
}

export function getMonthRange(dateStr: string): { start: string; end: string } {
  const date = parseISODate(dateStr);
  const year = date.getUTCFullYear();
  const month = date.getUTCMonth();
  const start = new Date(Date.UTC(year, month, 1));
  const end = new Date(Date.UTC(year, month + 1, 0));
  return { start: formatISODate(start), end: formatISODate(end) };
}

export function getRange(viewMode: ViewMode, selectedDate: string): { start: string; end: string } {
  if (viewMode === "day") return { start: selectedDate, end: selectedDate };
  if (viewMode === "week") return getWeekRange(selectedDate);
  return getMonthRange(selectedDate);
}
