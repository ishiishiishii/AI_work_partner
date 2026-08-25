-- 企業訪問の自由メモは frontend/types/index.ts に「バックエンドにはまだ無い」と
-- 明記された通りフロントのローカルstateのみで完結しており、編集してもリロードすると
-- 消えていた。activity_plan に永続化先を追加する。
alter table activity_plan
  add column memo text;

-- ai.activity_plan (20260824100000 作成、20260824110000/20260824130000 で拡張) に
-- memo を追加。CREATE OR REPLACE VIEW は既存列の並び順を変更できないため、
-- 今回も末尾に追加する。
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
  ap.progress_percent,
  ap.memo
from activity_plan ap
join sales_rep r on r.rep_id = ap.rep_id
left join customer cu on cu.customer_id = ap.customer_id
left join deal d on d.deal_id = ap.deal_id
left join product p on p.product_id = d.product_id;
