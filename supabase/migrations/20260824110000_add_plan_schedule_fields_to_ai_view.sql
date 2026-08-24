-- Extends ai.activity_plan (added in 20260824100000) with the
-- start_time/end_time/category/title columns and the product_name_override
-- resolution added to activity_plan in 20260821180000. The two migrations
-- were developed in parallel on separate branches, so the AI view didn't
-- know about these columns yet.
--
-- CREATE OR REPLACE VIEW requires existing columns to keep their name,
-- position, and type, so product_name's expression is updated in place
-- (still column 8) and the new columns are appended at the end rather than
-- inserted next to plan_date where they'd conceptually belong.
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
  ap.title
from activity_plan ap
join sales_rep r on r.rep_id = ap.rep_id
left join customer cu on cu.customer_id = ap.customer_id
left join deal d on d.deal_id = ap.deal_id
left join product p on p.product_id = d.product_id;
