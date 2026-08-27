-- Adds a free-text memo/note field to deal, for the customer detail deal
-- detail modal (顧客詳細: 商談詳細のメモ・備考欄).
alter table deal
  add column memo text;
