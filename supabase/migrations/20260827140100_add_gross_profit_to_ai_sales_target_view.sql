-- Extends ai.sales_target (20260824100000_create_ai_reference_views.sql) with
-- target_gross_profit, appended at the end so existing column order stays
-- intact (same CREATE OR REPLACE VIEW pattern as 20260825120100_add_cost_
-- profit_to_ai_view.sql did for ai.deal).
create or replace view ai.sales_target as
select
  t.target_id,
  t.rep_id,
  r.rep_name,
  t.target_month,
  t.target_amount,
  t.target_deal_count,
  t.target_gross_profit
from sales_target t
join sales_rep r on r.rep_id = t.rep_id;
