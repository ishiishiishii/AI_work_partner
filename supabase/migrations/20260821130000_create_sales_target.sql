-- Monthly sales targets per rep, per AGENTS.md section 9 (sales_target: (rep_id, target_month) UNIQUE).

create table sales_target (
  target_id serial primary key,
  rep_id int not null references sales_rep (rep_id),
  target_month date not null,
  target_amount numeric not null,
  target_deal_count int not null default 0,
  unique (rep_id, target_month)
);

create index sales_target_rep_id_idx on sales_target (rep_id);
