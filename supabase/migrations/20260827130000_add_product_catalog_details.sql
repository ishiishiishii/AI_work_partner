-- Product detail fields (description / price range / lead time / features) used by the
-- product detail page. Previously generated as client-side dummy data (frontend/lib/mockData.ts
-- getProductDummyDetails); now stored on the product master itself.

alter table product
  add column description text not null,
  add column price_min integer not null,
  add column price_max integer not null,
  add column lead_time_days integer not null,
  add column features text[] not null;

alter table product add constraint product_price_range_check check (price_max >= price_min);
alter table product add constraint product_lead_time_positive_check check (lead_time_days > 0);
