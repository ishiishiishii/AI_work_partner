-- 顧客の緯度経度。地図表示(feature/customer-map-display)は元々、都道府県庁所在地の
-- 座標にランダムなズレを足すだけの簡易表示(案1)だった。customer.location は
-- 都道府県・市区町村までは実在し番地のみ架空のデモデータのため、番地を除いた
-- 実在部分だけを国土地理院の無料住所検索APIでジオコーディングし、市区町村レベルの
-- 実座標をここに保存する(案2)。NULLのままの行はフロント側で従来の簡易表示に
-- フォールバックする(backend/app/services/geocoding.py 参照)。
alter table customer
  add column lat numeric,
  add column lng numeric;

-- ai.customer には直前の20260826120000でwebsite/contact_nameが追加済み。
-- CREATE OR REPLACE VIEWは既存列の順序・名前を変えられないため、それらを保持した
-- うえでlat/lngを末尾へ追加する。
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
