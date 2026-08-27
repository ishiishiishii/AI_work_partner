-- Weekly/monthly route planning: groups multiple daily route_plan rows into
-- a batch. Near-term days are solved in full (CP-SAT + RoutingModel, real
-- Routes API matrix); far-term days are geographically clustered and solved
-- with CP-SAT only, no external routing call, so a month-long batch stays
-- cheap while still giving a usable day-by-day forecast. See
-- app.services.route_planning.create_batch_preview.

create table route_plan_batch (
  batch_id bigserial primary key,
  rep_id int not null references sales_rep(rep_id),
  branch_id int not null references branch(branch_id),
  horizon text not null check (horizon in ('week', 'month')),
  start_date date not null,
  end_date date not null,
  detailed_days int not null,
  policy text not null check (policy in ('balanced','sales','gross_profit','short_travel')),
  weights jsonb not null,
  totals jsonb not null default '{}'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);
create index route_plan_batch_rep_idx on route_plan_batch(rep_id, start_date);

alter table route_plan
  add column if not exists batch_id bigint references route_plan_batch(batch_id) on delete cascade,
  add column if not exists detail_level text not null default 'detailed'
    check (detail_level in ('detailed', 'coarse'));
create index if not exists route_plan_batch_idx on route_plan(batch_id);

-- Coarse-day stops reuse the same table but their leg/time figures are a
-- branch-distance estimate, not a sequenced route -- flag them so the
-- frontend/Qwen never present them with the same confidence as a routed stop.
alter table route_plan_stop
  add column if not exists estimated boolean not null default false;

grant select, insert, update, delete on route_plan_batch to service_role;
grant usage, select on all sequences in schema public to service_role;
