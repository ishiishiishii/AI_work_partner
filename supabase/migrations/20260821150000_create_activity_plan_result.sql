-- Activity plan / result tables backing the core MVP loop (AGENTS.md section 7):
-- plan generation -> rationale -> result input -> replanning.

create table activity_plan (
  plan_id serial primary key,
  rep_id int not null references sales_rep (rep_id) on delete cascade,
  plan_date date not null,
  customer_id int references customer (customer_id) on delete set null,
  deal_id int references deal (deal_id) on delete set null,
  activity_type text not null default 'visit',
  priority int not null default 3 check (priority between 1 and 5),
  expected_amount numeric not null default 0 check (expected_amount >= 0),
  expected_probability int not null default 0
    check (expected_probability between 0 and 100),
  plan_status text not null default 'scheduled'
    check (plan_status in ('scheduled', 'done', 'cancelled', 'changed')),
  is_ai_generated boolean not null default true,
  rationale text,
  created_at timestamptz not null default now()
);

create index activity_plan_rep_date_idx on activity_plan (rep_id, plan_date);

create table activity_result (
  result_id serial primary key,
  plan_id int references activity_plan (plan_id) on delete set null,
  rep_id int not null references sales_rep (rep_id) on delete cascade,
  result_date date not null default current_date,
  customer_id int references customer (customer_id) on delete set null,
  deal_id int references deal (deal_id) on delete set null,
  activity_type text not null default 'visit',
  outcome text not null
    check (outcome in ('won', 'lost', 'deferred', 'progress', 'other')),
  outcome_note text,
  created_at timestamptz not null default now()
);

create index activity_result_rep_date_idx on activity_result (rep_id, result_date);
