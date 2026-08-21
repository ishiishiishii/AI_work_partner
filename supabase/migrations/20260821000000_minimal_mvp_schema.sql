-- Minimal MVP schema for backend skeleton (step 1).
-- Full master tables / triggers can be added in later migrations.

create extension if not exists "pgcrypto";

create table public.sales_rep (
  rep_id uuid primary key default gen_random_uuid(),
  rep_name text not null,
  coverage_area text,
  created_at timestamptz not null default now()
);

create table public.sales_target (
  rep_id uuid not null references public.sales_rep (rep_id) on delete cascade,
  target_month text not null
    check (target_month ~ '^\d{4}-(0[1-9]|1[0-2])$'),
  target_amount numeric(14, 0) not null check (target_amount >= 0),
  target_deal_count integer not null default 0 check (target_deal_count >= 0),
  primary key (rep_id, target_month)
);

create table public.customer (
  customer_id uuid primary key default gen_random_uuid(),
  customer_name text not null,
  industry text,
  location text,
  estimated_amount numeric(14, 0) not null default 0 check (estimated_amount >= 0),
  win_probability integer not null default 50
    check (win_probability >= 0 and win_probability <= 100),
  primary_rep_id uuid not null references public.sales_rep (rep_id) on delete restrict,
  status text not null default 'prospect'
    check (status in ('prospect', 'active', 'dormant', 'churned')),
  created_at timestamptz not null default now()
);

create index customer_primary_rep_id_idx on public.customer (primary_rep_id);

create table public.deal (
  deal_id uuid primary key default gen_random_uuid(),
  customer_id uuid not null references public.customer (customer_id) on delete cascade,
  rep_id uuid not null references public.sales_rep (rep_id) on delete restrict,
  estimated_amount numeric(14, 0) not null default 0 check (estimated_amount >= 0),
  win_probability integer not null default 50
    check (win_probability >= 0 and win_probability <= 100),
  result_status text not null default 'open'
    check (result_status in ('open', 'won', 'lost', 'deferred')),
  opened_date date not null default current_date,
  unique (deal_id, customer_id)
);

create index deal_rep_id_idx on public.deal (rep_id);
create index deal_customer_id_idx on public.deal (customer_id);

create table public.activity_plan (
  plan_id uuid primary key default gen_random_uuid(),
  rep_id uuid not null references public.sales_rep (rep_id) on delete cascade,
  plan_date date not null,
  customer_id uuid references public.customer (customer_id) on delete set null,
  deal_id uuid,
  activity_type text not null default 'visit',
  priority integer not null default 3 check (priority between 1 and 5),
  expected_amount numeric(14, 0) not null default 0 check (expected_amount >= 0),
  expected_probability integer not null default 0
    check (expected_probability >= 0 and expected_probability <= 100),
  plan_status text not null default 'scheduled'
    check (plan_status in ('scheduled', 'done', 'cancelled', 'changed')),
  is_ai_generated boolean not null default true,
  rationale text,
  created_at timestamptz not null default now(),
  constraint activity_plan_deal_customer_fk
    foreign key (deal_id, customer_id)
    references public.deal (deal_id, customer_id)
    on delete set null
);

create index activity_plan_rep_date_idx on public.activity_plan (rep_id, plan_date);

create table public.activity_result (
  result_id uuid primary key default gen_random_uuid(),
  plan_id uuid references public.activity_plan (plan_id) on delete set null,
  rep_id uuid not null references public.sales_rep (rep_id) on delete cascade,
  result_date date not null default current_date,
  customer_id uuid references public.customer (customer_id) on delete set null,
  deal_id uuid,
  activity_type text not null default 'visit',
  outcome text not null
    check (outcome in ('won', 'lost', 'deferred', 'progress', 'other')),
  outcome_note text,
  created_at timestamptz not null default now(),
  constraint activity_result_deal_customer_fk
    foreign key (deal_id, customer_id)
    references public.deal (deal_id, customer_id)
    on delete set null
);

create index activity_result_rep_date_idx on public.activity_result (rep_id, result_date);
