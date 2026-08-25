-- 新規顧客登録フォームの拡張用: 顧客企業のウェブサイトと、先方の窓口担当者名。
-- どちらも社内の過去入力を再利用するためのもので(社名検索でヒットした既存顧客の
-- 値を新規登録フォームに流用する)、外部の企業データベース連携ではない。
alter table customer add column website text;
alter table customer add column contact_name text;

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
  c.contact_name
from customer c
join industry i on i.industry_id = c.industry_id
join company_size_master csm on csm.company_size_id = c.company_size_id
left join sales_rep r on r.rep_id = c.primary_rep_id;
