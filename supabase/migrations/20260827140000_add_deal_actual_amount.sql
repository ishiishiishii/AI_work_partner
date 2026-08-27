-- Records the real contracted amount separately from estimated_amount, so the
-- original estimate is never overwritten and "見積もり精度" stays checkable later.
-- Mirrors contract_date's design: only meaningful once a deal is won, enforced
-- by extending the existing trigger (same before-insert-or-update hook).
alter table deal
  add column actual_amount numeric;

create or replace function enforce_deal_contract_date()
returns trigger as $$
declare
  v_status text;
begin
  select status_code into v_status
  from deal_result_status
  where deal_result_status_id = new.deal_result_status_id;

  if v_status = 'won' then
    if new.contract_date is null then
      raise exception 'contract_date is required when deal_result_status is won';
    end if;
    -- Auto-fill from estimated_amount on first transition to won, so existing
    -- callers that don't pass actual_amount explicitly (e.g. the win/lose
    -- buttons) still end up with a value. Callers can correct it afterward.
    if new.actual_amount is null then
      new.actual_amount := new.estimated_amount;
    end if;
  else
    if new.contract_date is not null then
      raise exception 'contract_date must be null unless deal_result_status is won';
    end if;
    if new.actual_amount is not null then
      raise exception 'actual_amount must be null unless deal_result_status is won';
    end if;
  end if;

  return new;
end;
$$ language plpgsql;

-- Append-only per the established pattern (see 20260825120100) so the
-- existing column order stays intact for anything already selecting by name.
create or replace view ai.deal as
select
  d.deal_id,
  d.customer_id,
  c.customer_name,
  d.rep_id,
  r.rep_name,
  dp.deal_phase_name,
  drs.status_code as deal_result_status,
  p.product_name,
  ps.subcategory_name,
  pc.category_name,
  d.estimated_amount,
  d.win_probability,
  d.expected_visit_count,
  d.expected_effort_hours,
  d.deal_start_date,
  d.contract_date,
  d.product_id,
  d.deal_phase_id,
  d.cost,
  d.profit,
  d.actual_amount
from deal d
join customer c on c.customer_id = d.customer_id
join sales_rep r on r.rep_id = d.rep_id
join deal_phase dp on dp.deal_phase_id = d.deal_phase_id
join deal_result_status drs on drs.deal_result_status_id = d.deal_result_status_id
join product p on p.product_id = d.product_id
join product_subcategory ps on ps.subcategory_id = p.subcategory_id
join product_category pc on pc.category_id = ps.category_id;
