-- Landing pad for AI-generated output, ahead of the real model being wired in
-- (backend/app/services/ai.py is still a placeholder). Once a model is
-- connected, its calls can log prompt/response pairs here for later review,
-- without needing a schema change at that point.
create table ai_response_log (
  log_id serial primary key,
  created_at timestamptz not null default now(),
  rep_id int references sales_rep (rep_id) on delete set null,
  context text not null,
  prompt text,
  response text not null,
  metadata jsonb
);

create index ai_response_log_rep_id_idx on ai_response_log (rep_id);
create index ai_response_log_created_at_idx on ai_response_log (created_at);
