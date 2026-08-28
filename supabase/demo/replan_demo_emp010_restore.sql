-- replan_demo_emp010.sqlの初回実行前に退避したEMP010のコアデータを復元する。
-- デモ中に生成されたルート計画履歴は残るが、商談・活動計画・活動結果・期限・
-- 8月目標・自己分析と、元のactivity_planに対するroute_plan_activityリンクは戻る。

begin;

create schema if not exists demo_backup;

do $$
begin
  if to_regclass('demo_backup.emp010_snapshot') is null then
    raise exception 'EMP010の退避データがありません。先にreplan_demo_emp010.sqlを実行してください。';
  end if;
  if not exists (
    select 1
    from demo_backup.emp010_snapshot
    where snapshot_key = 'before_replan_demo'
  ) then
    raise exception 'EMP010の退避データがありません。先にreplan_demo_emp010.sqlを実行してください。';
  end if;
end $$;

delete from activity_result where rep_id = 10;
delete from activity_plan where rep_id = 10;
delete from deadline where rep_id = 10;
delete from rep_affinity where rep_id = 10;
delete from deal where rep_id = 10;
delete from sales_target where rep_id = 10 and target_month = date '2026-08-01';

insert into deal (
  deal_id, customer_id, rep_id, deal_phase_id, deal_result_status_id,
  estimated_amount, win_probability, expected_visit_count, expected_effort_hours,
  deal_start_date, contract_date, product_id, cost, visit_duration_min,
  visit_window_start, visit_window_end, must_visit, visit_deadline,
  actual_amount, memo, expected_close_date, next_action
)
select
  deal_id, customer_id, rep_id, deal_phase_id, deal_result_status_id,
  estimated_amount, win_probability, expected_visit_count, expected_effort_hours,
  deal_start_date, contract_date, product_id, cost, visit_duration_min,
  visit_window_start, visit_window_end, must_visit, visit_deadline,
  actual_amount, memo, expected_close_date, next_action
from demo_backup.emp010_deal;

insert into activity_plan (
  plan_id, rep_id, plan_date, customer_id, deal_id, activity_type, priority,
  expected_amount, expected_probability, plan_status, is_ai_generated, rationale,
  created_at, start_time, end_time, category, title, product_name_override,
  progress_percent, memo
)
select
  plan_id, rep_id, plan_date, customer_id, deal_id, activity_type, priority,
  expected_amount, expected_probability, plan_status, is_ai_generated, rationale,
  created_at, start_time, end_time, category, title, product_name_override,
  progress_percent, memo
from demo_backup.emp010_activity_plan;

insert into activity_result (
  result_id, plan_id, rep_id, result_date, customer_id, deal_id, activity_type,
  outcome, outcome_note, created_at
)
select
  result_id, plan_id, rep_id, result_date, customer_id, deal_id, activity_type,
  outcome, outcome_note, created_at
from demo_backup.emp010_activity_result;

insert into deadline (
  deadline_id, rep_id, title, due_date, customer_id, deal_id, is_done, memo, created_at
)
select
  deadline_id, rep_id, title, due_date, customer_id, deal_id, is_done, memo, created_at
from demo_backup.emp010_deadline;

insert into sales_target (
  target_id, rep_id, target_month, target_amount, target_deal_count, target_gross_profit
)
select
  target_id, rep_id, target_month, target_amount, target_deal_count, target_gross_profit
from demo_backup.emp010_sales_target;

insert into rep_affinity (
  rep_id, industry_id, category_id, pattern_id, deal_count, won_count,
  win_rate, avg_won_amount, affinity_score, calculated_at
)
select
  rep_id, industry_id, category_id, pattern_id, deal_count, won_count,
  win_rate, avg_won_amount, affinity_score, calculated_at
from demo_backup.emp010_rep_affinity;

insert into route_plan_activity (route_plan_id, stop_id, activity_plan_id)
select backup.route_plan_id, backup.stop_id, backup.activity_plan_id
from demo_backup.emp010_route_plan_activity backup
join route_plan rp on rp.route_plan_id = backup.route_plan_id
join route_plan_stop rps on rps.stop_id = backup.stop_id
join activity_plan ap on ap.plan_id = backup.activity_plan_id
on conflict do nothing;

select setval('activity_plan_plan_id_seq', greatest(1, (select max(plan_id) from activity_plan)));
select setval('activity_result_result_id_seq', greatest(1, (select max(result_id) from activity_result)));
select setval('deadline_deadline_id_seq', greatest(1, (select max(deadline_id) from deadline)));
select setval('sales_target_target_id_seq', greatest(1, (select max(target_id) from sales_target)));

commit;
