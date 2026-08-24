-- Adds fields the frontend's "予定の編集" UI and day-view daily tasks
-- (資料作成・新規開拓 etc.) already assume, but had nowhere to persist to:
-- start_time/end_time/category were frontend-only (see frontend/types/index.ts
-- comments "バックエンドにはまだ無い"), and non-deal-linked daily tasks lived
-- only in a hardcoded frontend fixture (mockDailyTasks) for one fixed rep/date.
alter table activity_plan
  add column start_time text check (start_time ~ '^\d{2}:\d{2}$'),
  add column end_time text check (end_time ~ '^\d{2}:\d{2}$'),
  add column category text not null default 'visit' check (category in ('visit', 'task')),
  -- Free-text label. Required in practice for category='task' rows (there is
  -- no customer_id to derive a name from); optional manual override of the
  -- displayed customer name otherwise. Never mutates the customer record itself.
  add column title text,
  -- Optional manual override of the displayed product name (visit only).
  add column product_name_override text;
