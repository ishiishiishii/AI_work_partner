-- Qwen sales route planning MVP: geospatial data, proposal audit tables,
-- route-matrix cache, and approval-safe persistence boundaries.
create extension if not exists postgis;

alter table branch
  add column if not exists location text,
  add column if not exists latitude numeric(9, 6),
  add column if not exists longitude numeric(9, 6),
  add column if not exists geo_point geography(point, 4326);

update branch set
  location = case branch_name
    when '札幌' then '北海道札幌市北区北8条西2丁目'
    when '仙台' then '宮城県仙台市青葉区中央1丁目1-1'
    when '東京' then '東京都千代田区丸の内1丁目9-1'
    when '中部' then '愛知県名古屋市中村区名駅1丁目1-4'
    when '神戸' then '兵庫県神戸市中央区相生町3丁目1-1'
    when '広島' then '広島県広島市南区松原町2-37'
    when '九州' then '福岡県福岡市博多区博多駅中央街1-1'
  end,
  latitude = case branch_name
    when '札幌' then 43.068661 when '仙台' then 38.260132
    when '東京' then 35.681236 when '中部' then 35.170915
    when '神戸' then 34.679667 when '広島' then 34.397385
    when '九州' then 33.589728 end,
  longitude = case branch_name
    when '札幌' then 141.350755 when '仙台' then 140.882437
    when '東京' then 139.767125 when '中部' then 136.881537
    when '神戸' then 135.178221 when '広島' then 132.475592
    when '九州' then 130.420727 end
where branch_name in ('札幌', '仙台', '東京', '中部', '神戸', '広島', '九州');

update branch
set geo_point = st_setsrid(st_makepoint(longitude, latitude), 4326)::geography
where latitude is not null and longitude is not null;

alter table branch
  alter column location set not null,
  alter column latitude set not null,
  alter column longitude set not null,
  alter column geo_point set not null;

alter table customer
  add column if not exists latitude numeric(9, 6),
  add column if not exists longitude numeric(9, 6),
  add column if not exists geo_point geography(point, 4326),
  add column if not exists place_id text,
  add column if not exists geocoding_status text not null default 'pending',
  add column if not exists geocode_accuracy text,
  add column if not exists geocoded_at timestamptz,
  add constraint customer_geocoding_status_check
    check (geocoding_status in ('pending', 'success', 'review', 'failed'));

-- Missing cost means gross-profit evaluation is unavailable, never zero.
alter table deal alter column cost drop not null;
alter table deal
  add column if not exists visit_duration_min int not null default 60
    check (visit_duration_min between 1 and 480),
  add column if not exists visit_window_start time,
  add column if not exists visit_window_end time,
  add column if not exists must_visit boolean not null default false,
  add column if not exists visit_deadline date,
  add constraint deal_visit_window_check check (
    visit_window_start is null or visit_window_end is null
    or visit_window_start < visit_window_end
  );

create or replace function sync_customer_geocoding()
returns trigger language plpgsql as $$
begin
  if tg_op = 'UPDATE' and new.location is distinct from old.location then
    new.latitude := null;
    new.longitude := null;
    new.geo_point := null;
    new.place_id := null;
    new.geocode_accuracy := null;
    new.geocoded_at := null;
    new.geocoding_status := 'pending';
  elsif new.latitude is not null and new.longitude is not null then
    new.geo_point := st_setsrid(st_makepoint(new.longitude, new.latitude), 4326)::geography;
  elsif new.latitude is null or new.longitude is null then
    new.geo_point := null;
  end if;
  return new;
end $$;

drop trigger if exists trg_sync_customer_geocoding on customer;
create trigger trg_sync_customer_geocoding
before insert or update of location, latitude, longitude on customer
for each row execute function sync_customer_geocoding();

create index if not exists customer_geo_point_gix on customer using gist (geo_point);

create table prefecture_branch (
  prefecture_name text primary key,
  branch_id int not null references branch(branch_id)
);

insert into prefecture_branch (prefecture_name, branch_id)
select p.prefecture_name, b.branch_id
from (values
  ('北海道','札幌'),
  ('青森県','仙台'),('岩手県','仙台'),('宮城県','仙台'),('秋田県','仙台'),('山形県','仙台'),('福島県','仙台'),
  ('茨城県','東京'),('栃木県','東京'),('群馬県','東京'),('埼玉県','東京'),('千葉県','東京'),('東京都','東京'),('神奈川県','東京'),
  ('新潟県','中部'),('富山県','中部'),('石川県','中部'),('福井県','中部'),('山梨県','中部'),('長野県','中部'),('岐阜県','中部'),('静岡県','中部'),('愛知県','中部'),
  ('三重県','神戸'),('滋賀県','神戸'),('京都府','神戸'),('大阪府','神戸'),('兵庫県','神戸'),('奈良県','神戸'),('和歌山県','神戸'),
  ('鳥取県','広島'),('島根県','広島'),('岡山県','広島'),('広島県','広島'),('山口県','広島'),('徳島県','広島'),('香川県','広島'),('愛媛県','広島'),('高知県','広島'),
  ('福岡県','九州'),('佐賀県','九州'),('長崎県','九州'),('熊本県','九州'),('大分県','九州'),('宮崎県','九州'),('鹿児島県','九州'),('沖縄県','九州')
) as p(prefecture_name, branch_name)
join branch b on b.branch_name = p.branch_name
on conflict (prefecture_name) do update set branch_id = excluded.branch_id;

create table route_plan (
  route_plan_id bigserial primary key,
  rep_id int not null references sales_rep(rep_id),
  target_date date not null,
  branch_id int not null references branch(branch_id),
  status text not null check (status in ('proposed','approved','rejected','failed')),
  policy text not null check (policy in ('balanced','sales','gross_profit','short_travel')),
  work_start time not null,
  work_end time not null,
  max_visits int not null,
  min_expected_sales numeric,
  min_expected_gross_profit numeric,
  weights jsonb not null,
  constraints jsonb not null default '{}'::jsonb,
  solver_metadata jsonb not null default '{}'::jsonb,
  totals jsonb not null default '{}'::jsonb,
  selection_reason text,
  warnings jsonb not null default '[]'::jsonb,
  qwen_model text,
  prompt_version text not null default 'route-plan-v1',
  approved_at timestamptz,
  created_at timestamptz not null default now()
);
create index route_plan_rep_date_idx on route_plan(rep_id, target_date);

create table route_plan_option (
  option_id bigserial primary key,
  route_plan_id bigint not null references route_plan(route_plan_id) on delete cascade,
  rank int not null,
  selected boolean not null default false,
  cp_sat_status text not null,
  routing_status text not null,
  business_value numeric not null,
  totals jsonb not null,
  rejection_reason text,
  unique(route_plan_id, rank)
);

create table route_plan_stop (
  stop_id bigserial primary key,
  route_plan_id bigint not null references route_plan(route_plan_id) on delete cascade,
  option_id bigint not null references route_plan_option(option_id) on delete cascade,
  visit_order int not null,
  customer_id int not null references customer(customer_id),
  deal_ids int[] not null,
  arrival_at timestamptz not null,
  departure_at timestamptz not null,
  visit_duration_min int not null,
  leg_travel_min int not null,
  leg_distance_m int not null,
  economics jsonb not null,
  selection_reason text,
  unique(option_id, customer_id),
  unique(option_id, visit_order)
);

create table route_matrix_cache (
  origin_key text not null,
  destination_key text not null,
  travel_mode text not null,
  departure_bucket timestamptz not null,
  duration_sec int not null,
  distance_m int not null,
  expires_at timestamptz not null,
  primary key(origin_key, destination_key, travel_mode, departure_bucket)
);

create table route_plan_activity (
  route_plan_id bigint not null references route_plan(route_plan_id) on delete cascade,
  stop_id bigint not null references route_plan_stop(stop_id) on delete cascade,
  activity_plan_id int not null references activity_plan(plan_id) on delete cascade,
  primary key(route_plan_id, activity_plan_id)
);

grant select, insert, update, delete on route_plan, route_plan_option,
  route_plan_stop, route_matrix_cache, route_plan_activity to service_role;
grant usage, select on all sequences in schema public to service_role;
