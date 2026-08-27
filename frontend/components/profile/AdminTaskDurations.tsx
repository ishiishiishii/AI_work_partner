"use client";

import { useState } from "react";
import { createAdminTaskType, saveAdminTaskDuration } from "@/lib/api";
import type { RepAdminTaskDuration } from "@/types";

type AdminTaskDurationsProps = {
  repId: number;
  taskDurations: RepAdminTaskDuration[];
  onChange: (taskDurations: RepAdminTaskDuration[]) => void;
};

export function AdminTaskDurations({ repId, taskDurations, onChange }: AdminTaskDurationsProps) {
  const [draftMinutes, setDraftMinutes] = useState<Record<number, string>>({});
  const [savingTaskTypeId, setSavingTaskTypeId] = useState<number | null>(null);
  const [newTaskName, setNewTaskName] = useState("");
  const [isAddingTask, setIsAddingTask] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function minutesFor(task: RepAdminTaskDuration): string {
    if (draftMinutes[task.task_type_id] !== undefined) return draftMinutes[task.task_type_id];
    return task.duration_minutes === null ? "" : String(task.duration_minutes);
  }

  async function handleSave(task: RepAdminTaskDuration) {
    const raw = minutesFor(task);
    if (raw === "") return;
    const minutes = Number(raw);
    if (!Number.isFinite(minutes) || minutes < 0) return;

    setSavingTaskTypeId(task.task_type_id);
    setError(null);
    try {
      await saveAdminTaskDuration(repId, task.task_type_id, minutes);
      onChange(
        taskDurations.map((item) =>
          item.task_type_id === task.task_type_id ? { ...item, duration_minutes: minutes } : item,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存に失敗しました");
    } finally {
      setSavingTaskTypeId(null);
    }
  }

  async function handleAddTask(event: React.FormEvent) {
    event.preventDefault();
    const taskName = newTaskName.trim();
    if (!taskName) return;

    setIsAddingTask(true);
    setError(null);
    try {
      const created = await createAdminTaskType(taskName);
      if (!taskDurations.some((item) => item.task_type_id === created.task_type_id)) {
        onChange([
          ...taskDurations,
          { task_type_id: created.task_type_id, task_name: created.task_name, duration_minutes: null },
        ]);
      }
      setNewTaskName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "タスクの追加に失敗しました");
    } finally {
      setIsAddingTask(false);
    }
  }

  return (
    <section className="panel profile-section">
      <h2>事務作業の所要時間</h2>
      <p className="profile-section__hint">
        タスクごとに、1回あたりどれくらいの時間で終わるかを記録します(例: 資料作成 1時間)。
      </p>

      <ul className="profile-task-duration-list">
        {taskDurations.map((task) => (
          <li key={task.task_type_id} className="profile-task-duration-list__item">
            <span className="profile-task-duration-list__name">{task.task_name}</span>
            <div className="profile-task-duration-list__input">
              <input
                type="number"
                min={0}
                step={5}
                value={minutesFor(task)}
                placeholder="分"
                onChange={(event) =>
                  setDraftMinutes({ ...draftMinutes, [task.task_type_id]: event.target.value })
                }
              />
              <span>分</span>
              <button
                type="button"
                className="goal-card__save"
                disabled={savingTaskTypeId === task.task_type_id || minutesFor(task) === ""}
                onClick={() => handleSave(task)}
              >
                保存
              </button>
            </div>
          </li>
        ))}
      </ul>

      <form className="profile-task-duration-add" onSubmit={handleAddTask}>
        <input
          type="text"
          value={newTaskName}
          onChange={(event) => setNewTaskName(event.target.value)}
          placeholder="タスクを追加(例: 見積書作成)"
        />
        <button type="submit" className="goal-card__save" disabled={isAddingTask || !newTaskName.trim()}>
          追加
        </button>
      </form>

      {error && <p className="new-customer-form__error">{error}</p>}
    </section>
  );
}
