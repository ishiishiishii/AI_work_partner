-- Maps each prefecture to the branch whose territory it falls under, so the
-- app can tell whether a rep's branch matches a customer's location. Used
-- only by newly-created deals (backend/app/services/planning.py::create_deal)
-- -- imported/seeded deal history predates branch assignment entirely and is
-- intentionally left as-is, so this is not enforced via a table trigger.
create table prefecture (
  prefecture_name text primary key,
  branch_id int not null references branch (branch_id)
);
