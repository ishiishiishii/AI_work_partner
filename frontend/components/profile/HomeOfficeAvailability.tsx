"use client";

import { useState } from "react";
import { saveHomeOfficeAvailability } from "@/lib/api";
import type { RepHomeOfficeDay } from "@/types";

const WEEKDAY_LABELS = ["月", "火", "水", "木", "金", "土", "日"];

type HomeOfficeAvailabilityProps = {
  repId: number;
  days: RepHomeOfficeDay[];
  onChange: (days: RepHomeOfficeDay[]) => void;
};

export function HomeOfficeAvailability({ repId, days, onChange }: HomeOfficeAvailabilityProps) {
  const [savingDay, setSavingDay] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const byDay = new Map(days.map((day) => [day.day_of_week, day.is_home_available]));

  async function toggleDay(dayOfWeek: number, current: boolean) {
    const next = !current;
    setSavingDay(dayOfWeek);
    setError(null);
    try {
      await saveHomeOfficeAvailability(repId, dayOfWeek, next);
      const updated = new Map(byDay);
      updated.set(dayOfWeek, next);
      onChange(
        WEEKDAY_LABELS.map((_, index) => ({
          day_of_week: index,
          is_home_available: updated.get(index) ?? false,
        })),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存に失敗しました");
    } finally {
      setSavingDay(null);
    }
  }

  return (
    <section className="panel profile-section">
      <h2>在宅可否</h2>
      <p className="profile-section__hint">曜日ごとに在宅勤務できるかを設定します。</p>
      <div className="profile-weekday-grid">
        {WEEKDAY_LABELS.map((label, dayOfWeek) => {
          const isHomeAvailable = byDay.get(dayOfWeek) ?? false;
          return (
            <button
              key={dayOfWeek}
              type="button"
              className={`profile-weekday-toggle${isHomeAvailable ? " is-active" : ""}`}
              disabled={savingDay === dayOfWeek}
              onClick={() => toggleDay(dayOfWeek, isHomeAvailable)}
            >
              <span className="profile-weekday-toggle__label">{label}</span>
              <span className="profile-weekday-toggle__state">
                {isHomeAvailable ? "在宅可" : "要出社"}
              </span>
            </button>
          );
        })}
      </div>
      {error && <p className="new-customer-form__error">{error}</p>}
    </section>
  );
}
