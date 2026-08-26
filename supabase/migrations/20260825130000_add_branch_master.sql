-- Adds the `branch` master table (AGENTS.md section 9 master list) and links
-- sales_rep to it, so each rep's assigned branch/office is normalized rather
-- than a free-text duplicate on sales_rep itself.
create table branch (
  branch_id serial primary key,
  branch_name text not null unique
);

-- Seed the normalized master here as well as in seed.sql so an existing local
-- database has valid branches before sales_rep.branch_id becomes NOT NULL.
insert into branch (branch_name) values
  ('札幌'),
  ('仙台'),
  ('東京'),
  ('中部'),
  ('神戸'),
  ('広島'),
  ('九州')
on conflict (branch_name) do nothing;

alter table sales_rep
  add column branch_id int references branch (branch_id);

with numbered_branches as (
  select branch_id, row_number() over (order by branch_id) as branch_number
  from branch
)
update sales_rep as rep
set branch_id = branch.branch_id
from numbered_branches as branch
where branch.branch_number = ((rep.rep_id - 1) % 7) + 1;

alter table sales_rep
  alter column branch_id set not null;

create index sales_rep_branch_id_idx on sales_rep (branch_id);
