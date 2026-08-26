-- 20260826120000でai.customerにwebsite/contact_nameを追加したが、20260827100000が
-- 同じビューをlat/lng追加のためCREATE OR REPLACEし、website/contact_nameを消してしまって
-- いた(並行して作業していた別ブランチのマイグレーションのため、互いのビュー定義を
-- 知らないまま上書きしていた)。両方の列を持つ最終形として作り直す。
create or replace view ai.customer as
select
  c.customer_id,
  c.customer_name,
  i.industry_name,
  csm.company_size_name,
  c.location,
  c.primary_rep_id,
  r.rep_name as primary_rep_name,
  c.website,
  c.contact_name,
  c.lat,
  c.lng
from customer c
join industry i on i.industry_id = c.industry_id
join company_size_master csm on csm.company_size_id = c.company_size_id
left join sales_rep r on r.rep_id = c.primary_rep_id;
