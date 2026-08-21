-- Product catalog (category > subcategory > product) and its link from deal.
-- product_category matches the master table named in AGENTS.md section 9;
-- product_subcategory is an extension to carry the requested sub-category dimension.

create table product_category (
  category_id serial primary key,
  category_name text not null unique
);

create table product_subcategory (
  subcategory_id serial primary key,
  category_id int not null references product_category (category_id),
  subcategory_name text not null,
  unique (category_id, subcategory_name)
);

create index product_subcategory_category_id_idx on product_subcategory (category_id);

create table product (
  product_id serial primary key,
  product_name text not null,
  subcategory_id int not null references product_subcategory (subcategory_id)
);

create index product_subcategory_id_idx on product (subcategory_id);

-- Every deal sells exactly one catalog product; category/sub-category consistency
-- is guaranteed by the product -> subcategory -> category FK chain, so a deal can
-- never reference a (category, sub-category, product) combination that doesn't
-- actually exist together in the catalog.
alter table deal add column product_id int not null references product (product_id);

create index deal_product_id_idx on deal (product_id);
