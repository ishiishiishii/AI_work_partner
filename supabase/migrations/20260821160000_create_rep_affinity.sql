-- Rep affinity: a rep's track record by industry x product-category x deal-pattern
-- (AGENTS.md section 9: rep_affinity / deal_pattern masters, used to personalize
-- plan generation and to explain "why this rep for this customer").
--
-- This table is a computed cache, not a source of truth: every column is derived
-- from deal + customer + product data that already exists. It is rebuilt by
-- backend/app/services/affinity.py, never hand-edited.

create table deal_pattern (
  pattern_id serial primary key,
  pattern_name text not null unique
);

-- Rule-based classification (see services/affinity.py): a deal is
-- 新規開拓 (new-logo) if it's the company's first-ever deal with that customer
-- (across all reps), else 既存深耕 (existing-account); 大型 (large) if its
-- amount is at/above the category's median closed-deal amount, else 小口 (small).
insert into deal_pattern (pattern_name) values
  ('新規開拓・大型'),
  ('新規開拓・小口'),
  ('既存深耕・大型'),
  ('既存深耕・小口');

create table rep_affinity (
  rep_id int not null references sales_rep (rep_id) on delete cascade,
  industry_id int not null references industry (industry_id),
  category_id int not null references product_category (category_id),
  pattern_id int not null references deal_pattern (pattern_id),
  deal_count int not null default 0,
  won_count int not null default 0,
  win_rate numeric not null default 0,
  avg_won_amount numeric not null default 0,
  affinity_score numeric not null default 0,
  calculated_at timestamptz not null default now(),
  primary key (rep_id, industry_id, category_id, pattern_id)
);

create index rep_affinity_rep_id_idx on rep_affinity (rep_id);
