-- Adds an optional monthly gross-profit target alongside the existing revenue
-- target (AGENTS.md section 8 Must-5; the goal-based backward-calculation spec
-- requires simultaneously satisfying BOTH a monthly revenue target and a
-- monthly gross-profit target by month end).
--
-- Nullable, and stays nullable: "no profit target set" is a valid, permanent
-- state (unlike deal.cost's nullable->backfill->NOT NULL migration), not
-- bootstrapping debt. Every reader must treat NULL as "don't gate on profit"
-- and never coerce it to 0 (which would mean "profit target is zero").
alter table sales_target
  add column target_gross_profit numeric;

alter table sales_target
  add constraint sales_target_gross_profit_non_negative
  check (target_gross_profit is null or target_gross_profit >= 0);
