-- Login credentials for sales_rep, keyed by the business-facing employee id
-- (e.g. EMP001) rather than the internal serial rep_id. Kept separate from
-- sales_rep so the core rep master stays free of auth concerns.
create extension if not exists pgcrypto;

create table sales_rep_account (
  employee_id text primary key,
  rep_id int not null unique references sales_rep (rep_id) on delete cascade,
  password_hash text not null,
  created_at timestamptz not null default now()
);

create index sales_rep_account_rep_id_idx on sales_rep_account (rep_id);
