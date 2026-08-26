alter table route_plan_stop
  add column if not exists leg_details jsonb not null default '{}'::jsonb;

grant select, insert, update, delete on route_plan_stop to service_role;
