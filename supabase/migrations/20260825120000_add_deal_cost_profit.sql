-- Adds cost/profit tracking to deal (AGENTS.md section 9: keep the model
-- normalized; derive rather than duplicate what can be computed).
--
-- cost is stored per deal (seeded in supabase/seed.sql as a random integer
-- between 50% and 95% of estimated_amount). profit is a generated column so
-- it always equals estimated_amount - cost and can never drift out of sync.
-- Existing databases can already contain deals, so add the column as nullable,
-- backfill those rows, and only then enforce NOT NULL. Fresh databases are
-- populated by seed.sql, which supplies an explicit cost for every deal.
alter table deal
  add column cost numeric;

update deal
set cost = round(estimated_amount * (0.50 + random() * 0.45))
where cost is null;

alter table deal
  alter column cost set not null,
  add column profit numeric generated always as (estimated_amount - cost) stored;
