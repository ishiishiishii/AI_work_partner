-- Adds the `branch` master table (AGENTS.md section 9 master list) and links
-- sales_rep to it, so each rep's assigned branch/office is normalized rather
-- than a free-text duplicate on sales_rep itself.
create table branch (
  branch_id serial primary key,
  branch_name text not null unique
);

alter table sales_rep
  add column branch_id int not null references branch (branch_id);

create index sales_rep_branch_id_idx on sales_rep (branch_id);
