-- 月間営業スケジュールの週計算結果を「採用」前から活動計画へ下書きとして
-- 反映できるよう、activity_plan.plan_status に draft を追加する。
-- draft は list_plans の除外条件(plan_status != 'cancelled')に含まれるため、
-- 追加のSELECT変更なしで活動計画一覧に表示される。

alter table activity_plan drop constraint activity_plan_plan_status_check;

alter table activity_plan
  add constraint activity_plan_plan_status_check
  check (plan_status in ('draft', 'scheduled', 'done', 'cancelled', 'changed'));
