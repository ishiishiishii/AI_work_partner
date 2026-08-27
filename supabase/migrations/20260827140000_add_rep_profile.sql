-- Adds a per-rep profile: weekly home-office availability and admin-task
-- duration estimates. Feeds into route planning defaults later (not yet --
-- route_planning.py still uses its own hardcoded work_start/work_end/
-- turnaround_buffer_min); this migration only introduces the data.

create table admin_task_type (
  task_type_id serial primary key,
  task_name text not null unique,
  is_default boolean not null default false,
  display_order int not null default 0
);

-- Seeded defaults so every rep sees a starting list; reps can add their own
-- (is_default=false) as their work style gets personalized over time.
insert into admin_task_type (task_name, is_default, display_order) values
  ('資料作成', true, 1),
  ('社内報告', true, 2),
  ('日報', true, 3)
on conflict (task_name) do nothing;

create table rep_home_office_availability (
  rep_id int not null references sales_rep (rep_id),
  day_of_week smallint not null check (day_of_week between 0 and 6),
  is_home_available boolean not null default false,
  primary key (rep_id, day_of_week)
);

create table rep_admin_task_duration (
  rep_id int not null references sales_rep (rep_id),
  task_type_id int not null references admin_task_type (task_type_id),
  duration_minutes int not null check (duration_minutes >= 0),
  updated_at timestamptz not null default now(),
  primary key (rep_id, task_type_id)
);
