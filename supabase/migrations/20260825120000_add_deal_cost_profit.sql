-- Adds cost/profit tracking to deal (AGENTS.md section 9: keep the model
-- normalized; derive rather than duplicate what can be computed).
--
-- cost is stored per deal (seeded in supabase/seed.sql as a random integer
-- between 50% and 95% of estimated_amount). profit is a generated column so
-- it always equals estimated_amount - cost and can never drift out of sync.
alter table deal
  add column cost numeric not null,
  add column profit numeric generated always as (estimated_amount - cost) stored;
