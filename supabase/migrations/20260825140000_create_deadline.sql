-- 汎用のタスク期限。ヘッダーの＋メニューからのクイック追加用で、顧客/商談との
-- 紐付けは任意(どちらもnullで単体の期限として使える)。activity_planとは別物:
-- 予定(いつ何をするか)ではなく、単に「いつまでに」を管理するリマインダー。
create table deadline (
  deadline_id serial primary key,
  rep_id int not null references sales_rep (rep_id) on delete cascade,
  title text not null,
  due_date date not null,
  customer_id int references customer (customer_id) on delete set null,
  deal_id int references deal (deal_id) on delete set null,
  is_done boolean not null default false,
  memo text,
  created_at timestamptz not null default now()
);

create index deadline_rep_due_idx on deadline (rep_id, due_date);
