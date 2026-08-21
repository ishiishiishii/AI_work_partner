-- Core schema for customer / deal import (industry, company size, deal phase/result as
-- normalized reference masters per AGENTS.md section 9 design principles).

create table industry (
  industry_id serial primary key,
  industry_name text not null unique
);

create table company_size_master (
  company_size_id serial primary key,
  company_size_name text not null unique
);

create table deal_phase (
  deal_phase_id serial primary key,
  deal_phase_name text not null unique,
  sort_order int not null unique
);

create table deal_result_status (
  deal_result_status_id serial primary key,
  status_code text not null unique
);

create table sales_rep (
  rep_id serial primary key,
  rep_name text not null,
  manager_rep_id int references sales_rep (rep_id)
);

create table customer (
  customer_id int primary key,
  customer_name text not null,
  industry_id int not null references industry (industry_id),
  company_size_id int not null references company_size_master (company_size_id),
  location text not null,
  primary_rep_id int references sales_rep (rep_id)
);

create index customer_industry_id_idx on customer (industry_id);
create index customer_company_size_id_idx on customer (company_size_id);

create table deal (
  deal_id int primary key,
  customer_id int not null references customer (customer_id),
  rep_id int not null references sales_rep (rep_id),
  deal_phase_id int not null references deal_phase (deal_phase_id),
  deal_result_status_id int not null references deal_result_status (deal_result_status_id),
  estimated_amount numeric not null,
  win_probability numeric not null,
  expected_visit_count int not null,
  expected_effort_hours numeric not null,
  deal_start_date date not null,
  contract_date date
);

create index deal_customer_id_idx on deal (customer_id);
create index deal_rep_id_idx on deal (rep_id);

-- Won deals must carry a contract_date; non-won deals must not.
create or replace function enforce_deal_contract_date()
returns trigger as $$
declare
  v_status text;
begin
  select status_code into v_status
  from deal_result_status
  where deal_result_status_id = new.deal_result_status_id;

  if v_status = 'won' and new.contract_date is null then
    raise exception 'contract_date is required when deal_result_status is won';
  elsif v_status <> 'won' and new.contract_date is not null then
    raise exception 'contract_date must be null unless deal_result_status is won';
  end if;

  return new;
end;
$$ language plpgsql;

create trigger trg_deal_contract_date
before insert or update on deal
for each row execute function enforce_deal_contract_date();

-- Backend (FastAPI) connects with the service_role key and needs full access;
-- anon/authenticated get none here since no RLS policies exist yet.
grant usage on schema public to service_role;
grant select, insert, update, delete on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to service_role;
alter default privileges in schema public grant select, insert, update, delete on tables to service_role;
alter default privileges in schema public grant usage, select on sequences to service_role;
