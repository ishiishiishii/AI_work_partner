-- EMP010（高橋健二）専用: 成約・失注後の自動再計画デモを初期化する。
--
-- このスクリプトはEMP010の商談・活動計画・活動結果・期限・自己分析を
-- デモ用データへ置き換える。初回実行時だけ元データをdemo_backupスキーマへ
-- 退避するため、replan_demo_emp010_restore.sqlで復元できる。
-- 成約版と失注版を続けて試す場合も、各デモの前にこのSQLを再実行する。

begin;

create schema if not exists demo_backup;

create table if not exists demo_backup.emp010_snapshot (
  snapshot_key text primary key,
  created_at timestamptz not null default now()
);
create table if not exists demo_backup.emp010_deal as
  select * from deal where false;
create table if not exists demo_backup.emp010_activity_plan as
  select * from activity_plan where false;
create table if not exists demo_backup.emp010_activity_result as
  select * from activity_result where false;
create table if not exists demo_backup.emp010_deadline as
  select * from deadline where false;
create table if not exists demo_backup.emp010_sales_target as
  select * from sales_target where false;
create table if not exists demo_backup.emp010_rep_affinity as
  select * from rep_affinity where false;
create table if not exists demo_backup.emp010_route_plan_activity as
  select * from route_plan_activity where false;

do $$
begin
  if not exists (
    select 1
    from demo_backup.emp010_snapshot
    where snapshot_key = 'before_replan_demo'
  ) then
    insert into demo_backup.emp010_deal
      select * from deal where rep_id = 10;
    insert into demo_backup.emp010_activity_plan
      select * from activity_plan where rep_id = 10;
    insert into demo_backup.emp010_activity_result
      select * from activity_result where rep_id = 10;
    insert into demo_backup.emp010_deadline
      select * from deadline where rep_id = 10;
    insert into demo_backup.emp010_sales_target
      select * from sales_target where rep_id = 10 and target_month = date '2026-08-01';
    insert into demo_backup.emp010_rep_affinity
      select * from rep_affinity where rep_id = 10;
    insert into demo_backup.emp010_route_plan_activity
      select rpa.*
      from route_plan_activity rpa
      join activity_plan ap on ap.plan_id = rpa.activity_plan_id
      where ap.rep_id = 10;

    insert into demo_backup.emp010_snapshot (snapshot_key)
    values ('before_replan_demo');
  end if;
end $$;

-- 商談を先に消すと既存計画のdeal_idがnullになるため、依存データから消す。
delete from activity_result where rep_id = 10;
delete from activity_plan where rep_id = 10;
delete from deadline where rep_id = 10;
delete from rep_affinity where rep_id = 10;
delete from deal where rep_id = 10;
delete from sales_target where rep_id = 10 and target_month = date '2026-08-01';

-- 再実行時は同じ顧客を使い回す。ルート計画履歴から参照されていても安全に初期化できる。
insert into customer (
  customer_name, industry_id, company_size_id, location, primary_rep_id,
  latitude, longitude, geocoding_status, geocode_accuracy, geocoded_at,
  website, contact_name, lat, lng
)
select
  '【結果入力デモ】中央DX製作所',
  (select industry_id from industry where industry_name = '製造業'),
  (select company_size_id from company_size_master where company_size_name = '中堅企業'),
  '東京都千代田区丸の内1-9-1', 10,
  35.681236, 139.767125, 'success', 'rooftop', now(),
  'https://demo-central-dx.example.com', '佐藤 部長', 35.681236, 139.767125
where not exists (
  select 1 from customer where customer_name = '【結果入力デモ】中央DX製作所'
);

insert into customer (
  customer_name, industry_id, company_size_id, location, primary_rep_id,
  latitude, longitude, geocoding_status, geocode_accuracy, geocoded_at,
  website, contact_name, lat, lng
)
select
  '【代替候補A】日本橋クラウド株式会社',
  (select industry_id from industry where industry_name = '情報通信業'),
  (select company_size_id from company_size_master where company_size_name = '中堅企業'),
  '東京都中央区日本橋2-7-1', 10,
  35.681410, 139.773100, 'success', 'rooftop', now(),
  'https://demo-nihonbashi-cloud.example.com', '鈴木 課長', 35.681410, 139.773100
where not exists (
  select 1 from customer where customer_name = '【代替候補A】日本橋クラウド株式会社'
);

insert into customer (
  customer_name, industry_id, company_size_id, location, primary_rep_id,
  latitude, longitude, geocoding_status, geocode_accuracy, geocoded_at,
  website, contact_name, lat, lng
)
select
  '【代替候補B】虎ノ門セキュリティ株式会社',
  (select industry_id from industry where industry_name = '情報通信業'),
  (select company_size_id from company_size_master where company_size_name = '大企業'),
  '東京都港区虎ノ門1-23-1', 10,
  35.667120, 139.749650, 'success', 'rooftop', now(),
  'https://demo-toranomon-security.example.com', '田中 部長', 35.667120, 139.749650
where not exists (
  select 1 from customer where customer_name = '【代替候補B】虎ノ門セキュリティ株式会社'
);

insert into customer (
  customer_name, industry_id, company_size_id, location, primary_rep_id,
  latitude, longitude, geocoding_status, geocode_accuracy, geocoded_at,
  website, contact_name, lat, lng
)
select
  '【予備候補】新宿ワークス株式会社',
  (select industry_id from industry where industry_name = 'サービス業'),
  (select company_size_id from company_size_master where company_size_name = '中小企業'),
  '東京都新宿区西新宿2-8-1', 10,
  35.689610, 139.691760, 'success', 'rooftop', now(),
  'https://demo-shinjuku-works.example.com', '山田 社長', 35.689610, 139.691760
where not exists (
  select 1 from customer where customer_name = '【予備候補】新宿ワークス株式会社'
);

-- 既に顧客が存在する再実行でも、EMP010の担当・座標を確実に揃える。
update customer
set primary_rep_id = 10
where customer_name in (
  '【結果入力デモ】中央DX製作所',
  '【代替候補A】日本橋クラウド株式会社',
  '【代替候補B】虎ノ門セキュリティ株式会社',
  '【予備候補】新宿ワークス株式会社'
);

insert into sales_target (
  rep_id, target_month, target_amount, target_deal_count, target_gross_profit
) values (10, date '2026-08-01', 10000000, 2, 3000000);

-- 基準案件: 800万円。成約なら残目標は200万円まで縮み、後半候補は1社に絞られる。
insert into deal (
  deal_id, customer_id, rep_id, deal_phase_id, deal_result_status_id,
  estimated_amount, win_probability, expected_visit_count, expected_effort_hours,
  deal_start_date, contract_date, product_id, cost, visit_duration_min,
  visit_window_start, visit_window_end, must_visit, visit_deadline,
  actual_amount, memo, expected_close_date, next_action
) values (
  9900101,
  (select customer_id from customer where customer_name = '【結果入力デモ】中央DX製作所' order by customer_id limit 1),
  10,
  (select deal_phase_id from deal_phase where deal_phase_name = '契約交渉'),
  (select deal_result_status_id from deal_result_status where status_code = 'ongoing'),
  8000000, 80, 3, 5, date '2026-07-01', null, 51, 5000000, 60,
  time '10:00', time '12:00', true, date '2026-08-10',
  null, '8月10日の最終商談で成約・失注を入力するデモ用案件',
  date '2026-08-10', '最終条件を確認し、成約可否を登録する'
);

-- 代替候補は600万・500万・400万円。目標1,000万円なら上位2社、
-- 成約後の残目標200万円なら上位1社だけが選ばれる金額構成。
insert into deal (
  deal_id, customer_id, rep_id, deal_phase_id, deal_result_status_id,
  estimated_amount, win_probability, expected_visit_count, expected_effort_hours,
  deal_start_date, contract_date, product_id, cost, visit_duration_min,
  visit_window_start, visit_window_end, must_visit, visit_deadline,
  actual_amount, memo, expected_close_date, next_action
) values
  (
    9900102,
    (select customer_id from customer where customer_name = '【代替候補A】日本橋クラウド株式会社' order by customer_id limit 1),
    10,
    (select deal_phase_id from deal_phase where deal_phase_name = '見積'),
    (select deal_result_status_id from deal_result_status where status_code = 'ongoing'),
    6000000, 75, 1, 3, date '2026-07-08', null, 41, 3600000, 60,
    time '09:00', time '17:00', false, date '2026-08-21',
    null, '失注時に最優先で追加される代替候補',
    date '2026-08-21', '見積条件の最終確認'
  ),
  (
    9900103,
    (select customer_id from customer where customer_name = '【代替候補B】虎ノ門セキュリティ株式会社' order by customer_id limit 1),
    10,
    (select deal_phase_id from deal_phase where deal_phase_name = '提案'),
    (select deal_result_status_id from deal_result_status where status_code = 'ongoing'),
    5000000, 70, 1, 3, date '2026-07-10', null, 29, 3000000, 60,
    time '09:00', time '17:00', false, date '2026-08-24',
    null, '失注時に2社目として追加される代替候補',
    date '2026-08-24', 'セキュリティ構成を提案する'
  ),
  (
    9900104,
    (select customer_id from customer where customer_name = '【予備候補】新宿ワークス株式会社' order by customer_id limit 1),
    10,
    (select deal_phase_id from deal_phase where deal_phase_name = 'ヒアリング'),
    (select deal_result_status_id from deal_result_status where status_code = 'ongoing'),
    4000000, 65, 1, 2, date '2026-07-15', null, 49, 2800000, 60,
    time '09:00', time '17:00', false, date '2026-08-28',
    null, '上位候補で不足する場合だけ使う予備案件',
    date '2026-08-28', '課題と導入人数を確認する'
  );

-- 初期画面では同じ基準案件の後続予定が並ぶ。結果入力後はこれらが消え、
-- 残目標に応じて代替候補A/Bの訪問へ自動で差し替わる。
insert into activity_plan (
  rep_id, plan_date, start_time, end_time, category, title, customer_id, deal_id,
  activity_type, priority, expected_amount, expected_probability, plan_status,
  is_ai_generated, rationale, progress_percent, memo
) values
  (
    10, date '2026-08-10', '10:00', '11:00', 'visit', '最終契約商談',
    (select customer_id from customer where customer_name = '【結果入力デモ】中央DX製作所' order by customer_id limit 1),
    9900101, '訪問', 1, 8000000, 80, 'scheduled', true,
    '月間目標1,000万円に対して期待売上640万円の中心案件です。結果確定後は残目標から後半計画を自動で組み直します。',
    80, 'デモではこの予定の「成約」または「失注」を押してください。'
  ),
  (
    10, date '2026-08-13', '10:00', '11:00', 'visit', '契約条件フォロー',
    (select customer_id from customer where customer_name = '【結果入力デモ】中央DX製作所' order by customer_id limit 1),
    9900101, '訪問', 1, 8000000, 80, 'scheduled', true,
    '8月10日の商談が継続した場合の後続予定です。成約・失注が確定すると不要になるため自動削除されます。',
    0, '結果入力前に存在し、入力後に消えることを見せる予定です。'
  ),
  (
    10, date '2026-08-17', '14:00', '15:00', 'visit', '決裁者フォロー',
    (select customer_id from customer where customer_name = '【結果入力デモ】中央DX製作所' order by customer_id limit 1),
    9900101, '訪問', 1, 8000000, 80, 'scheduled', true,
    '未確定時の追加フォローです。結果入力後は代替案件の計画に置き換わります。',
    0, '後半計画が変わることを分かりやすくする比較用予定です。'
  );

commit;

