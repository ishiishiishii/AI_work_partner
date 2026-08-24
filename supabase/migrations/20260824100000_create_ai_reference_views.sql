-- AI-facing reference schema (AGENTS.md section 9 / 11.5: AI must stay on a
-- replaceable, explainable data boundary).
--
-- The tables created by earlier migrations are a normalized (3NF) schema kept
-- for human staff (Supabase Studio, future admin screens): masters are split
-- out so industry/company size/deal phase/etc. are each stored once.
--
-- AI (and any FE/BE code that assembles AI-facing plans, rationale, or
-- analysis) does not need that split -- it needs one flat, first-normal-form
-- row per entity with every foreign key already resolved to the human-
-- readable name it stands for, and with surrogate master ids that carry no
-- meaning on their own (industry_id, company_size_id, deal_phase_id,
-- deal_result_status_id, product/category/subcategory id, pattern_id) left
-- out entirely -- e.g. a deal's product_id is never needed by the AI layer,
-- only its product_name is.
--
-- Every object below is a VIEW, not a copied table: it is computed live from
-- the 3NF tables on every read, so there is no second copy of the data that
-- could drift out of sync when the underlying tables are updated. Entity ids
-- that other AI/FE/BE code still needs to reference or filter by (rep_id,
-- customer_id, deal_id, plan_id, result_id, target_id) are kept.

create schema if not exists ai;

create view ai.sales_rep as
select
  r.rep_id,
  r.rep_name,
  m.rep_name as manager_rep_name
from sales_rep r
left join sales_rep m on m.rep_id = r.manager_rep_id;

create view ai.customer as
select
  c.customer_id,
  c.customer_name,
  i.industry_name,
  csm.company_size_name,
  c.location,
  c.primary_rep_id,
  r.rep_name as primary_rep_name
from customer c
join industry i on i.industry_id = c.industry_id
join company_size_master csm on csm.company_size_id = c.company_size_id
left join sales_rep r on r.rep_id = c.primary_rep_id;

-- Company-wide last contact per customer: any rep's deal start, or any logged
-- activity_result -- so imported historical deals (no activity_result rows)
-- still count. Mirrors planning.py's former _LAST_CONTACT_CTE.
create view ai.customer_activity as
select
  cu.customer_id,
  cu.customer_name,
  cu.industry_name,
  cu.company_size_name,
  cu.location,
  cu.primary_rep_id,
  cu.primary_rep_name,
  lc.last_contact_date,
  (current_date - lc.last_contact_date) as days_since_contact
from ai.customer cu
left join (
  select customer_id, max(contact_date) as last_contact_date
  from (
    select customer_id, deal_start_date as contact_date from deal
    union all
    select customer_id, result_date as contact_date
    from activity_result
    where customer_id is not null
  ) contacts
  group by customer_id
) lc on lc.customer_id = cu.customer_id;

create view ai.deal as
select
  d.deal_id,
  d.customer_id,
  c.customer_name,
  d.rep_id,
  r.rep_name,
  dp.deal_phase_name,
  drs.status_code as deal_result_status,
  p.product_name,
  ps.subcategory_name,
  pc.category_name,
  d.estimated_amount,
  d.win_probability,
  d.expected_visit_count,
  d.expected_effort_hours,
  d.deal_start_date,
  d.contract_date
from deal d
join customer c on c.customer_id = d.customer_id
join sales_rep r on r.rep_id = d.rep_id
join deal_phase dp on dp.deal_phase_id = d.deal_phase_id
join deal_result_status drs on drs.deal_result_status_id = d.deal_result_status_id
join product p on p.product_id = d.product_id
join product_subcategory ps on ps.subcategory_id = p.subcategory_id
join product_category pc on pc.category_id = ps.category_id;

create view ai.sales_target as
select
  t.target_id,
  t.rep_id,
  r.rep_name,
  t.target_month,
  t.target_amount,
  t.target_deal_count
from sales_target t
join sales_rep r on r.rep_id = t.rep_id;

create view ai.activity_plan as
select
  ap.plan_id,
  ap.rep_id,
  r.rep_name,
  ap.plan_date,
  ap.customer_id,
  cu.customer_name,
  ap.deal_id,
  p.product_name,
  ap.activity_type,
  ap.priority,
  ap.expected_amount,
  ap.expected_probability,
  ap.plan_status,
  ap.is_ai_generated,
  ap.rationale,
  ap.created_at
from activity_plan ap
join sales_rep r on r.rep_id = ap.rep_id
left join customer cu on cu.customer_id = ap.customer_id
left join deal d on d.deal_id = ap.deal_id
left join product p on p.product_id = d.product_id;

create view ai.activity_result as
select
  ar.result_id,
  ar.plan_id,
  ar.rep_id,
  r.rep_name,
  ar.result_date,
  ar.customer_id,
  cu.customer_name,
  ar.deal_id,
  ar.activity_type,
  ar.outcome,
  ar.outcome_note,
  ar.created_at
from activity_result ar
join sales_rep r on r.rep_id = ar.rep_id
left join customer cu on cu.customer_id = ar.customer_id;

create view ai.rep_affinity as
select
  ra.rep_id,
  r.rep_name,
  i.industry_name,
  pc.category_name,
  dp.pattern_name,
  ra.deal_count,
  ra.won_count,
  ra.win_rate,
  ra.avg_won_amount,
  ra.affinity_score,
  ra.calculated_at
from rep_affinity ra
join sales_rep r on r.rep_id = ra.rep_id
join industry i on i.industry_id = ra.industry_id
join product_category pc on pc.category_id = ra.category_id
join deal_pattern dp on dp.pattern_id = ra.pattern_id;

-- Same access model as the public schema (migration 20260821120000): backend
-- connects as service_role and needs read access to these views.
grant usage on schema ai to service_role;
grant select on all tables in schema ai to service_role;
alter default privileges in schema ai grant select on tables to service_role;
