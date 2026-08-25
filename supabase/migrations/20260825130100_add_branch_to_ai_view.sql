-- Extends ai.sales_rep (20260824100000) with branch_name, appended at the end
-- so the existing column order stays intact (CREATE OR REPLACE VIEW
-- requirement -- see 20260824120000/20260825120100 for the same pattern).
create or replace view ai.sales_rep as
select
  r.rep_id,
  r.rep_name,
  m.rep_name as manager_rep_name,
  b.branch_name
from sales_rep r
left join sales_rep m on m.rep_id = r.manager_rep_id
join branch b on b.branch_id = r.branch_id;
