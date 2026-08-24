-- Extends ai.deal (20260824100000) with product_id/deal_phase_id, appended at
-- the end so the existing column order stays intact (CREATE OR REPLACE VIEW
-- requirement -- see 20260824110000 for the same pattern on ai.activity_plan).
--
-- The original ai.deal comment says surrogate master ids are "never needed by
-- the AI layer" -- that's still true for read-only display/explanation, but
-- an edit form (PATCH /api/deals/{deal_id}) is an ordinary CRUD write path,
-- not the AI layer, and genuinely needs the real ids to submit a valid update.
create or replace view ai.deal as
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
  d.contract_date,
  d.product_id,
  d.deal_phase_id
from deal d
join customer c on c.customer_id = d.customer_id
join sales_rep r on r.rep_id = d.rep_id
join deal_phase dp on dp.deal_phase_id = d.deal_phase_id
join deal_result_status drs on drs.deal_result_status_id = d.deal_result_status_id
join product p on p.product_id = d.product_id
join product_subcategory ps on ps.subcategory_id = p.subcategory_id
join product_category pc on pc.category_id = ps.category_id;
