-- 事務作業(category='task')の進捗表示は、これまでフロントの React state だけで
-- 完結しており(frontend/types/index.ts の progress_percent コメント参照)、
-- リロードすると失われていた。バックエンドに保存できるようにする。
alter table activity_plan
  add column progress_percent integer not null default 0
    check (progress_percent between 0 and 100);

-- ai.activity_plan (20260824100000 で作成、20260824110000 で拡張) に
-- progress_percent を追加。CREATE OR REPLACE VIEW は既存列の並び順を
-- 変更できないため、今回も末尾に追加する。
create or replace view ai.activity_plan as
select
  ap.plan_id,
  ap.rep_id,
  r.rep_name,
  ap.plan_date,
  ap.customer_id,
  cu.customer_name,
  ap.deal_id,
  coalesce(ap.product_name_override, p.product_name) as product_name,
  ap.activity_type,
  ap.priority,
  ap.expected_amount,
  ap.expected_probability,
  ap.plan_status,
  ap.is_ai_generated,
  ap.rationale,
  ap.created_at,
  ap.start_time,
  ap.end_time,
  ap.category,
  ap.title,
  ap.progress_percent
from activity_plan ap
join sales_rep r on r.rep_id = ap.rep_id
left join customer cu on cu.customer_id = ap.customer_id
left join deal d on d.deal_id = ap.deal_id
left join product p on p.product_id = d.product_id;
