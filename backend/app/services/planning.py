from datetime import date, timedelta
from decimal import Decimal

from psycopg import Connection

from app.schemas.models import PlanOut
from app.services import affinity

# A customer counts as "stale" (churn-risk, company-wide) with no visit or
# deal in this many days. Shared by list_stale_customers and the plan
# generator's priority boost so the two stay in sync.
STALE_THRESHOLD_DAYS = 60

# Company-wide last contact per customer: any rep's deal start, or any logged
# activity_result -- so imported historical deals (no activity_result rows)
# still count.
_LAST_CONTACT_CTE = """
with last_contact as (
  select customer_id, max(contact_date) as last_contact_date
  from (
    select customer_id, deal_start_date as contact_date from deal
    union all
    select customer_id, result_date as contact_date
    from activity_result
    where customer_id is not null
  ) contacts
  group by customer_id
)
"""


def _month_to_date(target_month: str) -> date:
    year, month = map(int, target_month.split("-"))
    return date(year, month, 1)


def _format_target(row: dict) -> dict:
    row = dict(row)
    row["target_month"] = row["target_month"].strftime("%Y-%m")
    return row


def list_targets(conn: Connection, rep_id: int | None = None) -> list[dict]:
    if rep_id:
        rows = conn.execute(
            """
            select target_id, rep_id, target_month, target_amount, target_deal_count
            from sales_target
            where rep_id = %s
            order by target_month desc
            """,
            (rep_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            select target_id, rep_id, target_month, target_amount, target_deal_count
            from sales_target
            order by target_month desc
            """
        ).fetchall()
    return [_format_target(row) for row in rows]


def upsert_target(
    conn: Connection,
    *,
    rep_id: int,
    target_month: str,
    target_amount: Decimal,
    target_deal_count: int,
) -> dict:
    row = conn.execute(
        """
        insert into sales_target (rep_id, target_month, target_amount, target_deal_count)
        values (%s, %s, %s, %s)
        on conflict (rep_id, target_month) do update
          set target_amount = excluded.target_amount,
              target_deal_count = excluded.target_deal_count
        returning target_id, rep_id, target_month, target_amount, target_deal_count
        """,
        (rep_id, _month_to_date(target_month), target_amount, target_deal_count),
    ).fetchone()
    conn.commit()
    return _format_target(row)


def list_customers(conn: Connection, rep_id: int | None = None) -> list[dict]:
    if rep_id:
        # primary_rep_id is rarely set in the imported dataset, so a rep's
        # customers are the ones they actually have deals with.
        rows = conn.execute(
            """
            select distinct c.customer_id, c.customer_name, c.industry_id,
                   c.company_size_id, c.location, c.primary_rep_id
            from customer c
            where c.primary_rep_id = %s
               or exists (
                 select 1 from deal d
                 where d.customer_id = c.customer_id and d.rep_id = %s
               )
            order by c.customer_name
            """,
            (rep_id, rep_id),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            select customer_id, customer_name, industry_id, company_size_id,
                   location, primary_rep_id
            from customer
            order by customer_name
            """
        ).fetchall()
    return list(rows)


def create_customer(
    conn: Connection,
    *,
    customer_name: str,
    industry_id: int,
    company_size_id: int,
    location: str,
    primary_rep_id: int | None,
) -> dict:
    row = conn.execute(
        """
        insert into customer (
          customer_name, industry_id, company_size_id, location, primary_rep_id
        )
        values (%s, %s, %s, %s, %s)
        returning customer_id, customer_name, industry_id, company_size_id,
                  location, primary_rep_id
        """,
        (customer_name, industry_id, company_size_id, location, primary_rep_id),
    ).fetchone()
    conn.commit()
    return dict(row)


def list_stale_customers(
    conn: Connection,
    *,
    threshold_days: int = STALE_THRESHOLD_DAYS,
    rep_id: int | None = None,
) -> list[dict]:
    """Customers with no company-wide contact in threshold_days (or ever)."""
    rows = conn.execute(
        _LAST_CONTACT_CTE
        + """
        select c.customer_id, c.customer_name, c.industry_id, c.company_size_id,
               c.location, c.primary_rep_id,
               lc.last_contact_date,
               (current_date - lc.last_contact_date) as days_since_contact
        from customer c
        left join last_contact lc on lc.customer_id = c.customer_id
        where (
          lc.last_contact_date is null
          or lc.last_contact_date < current_date - %(threshold_days)s * interval '1 day'
        )
        and (
          %(rep_id)s::int is null
          or c.primary_rep_id = %(rep_id)s
          or exists (
            select 1 from deal d
            where d.customer_id = c.customer_id and d.rep_id = %(rep_id)s
          )
        )
        order by lc.last_contact_date asc nulls first
        """,
        {"threshold_days": threshold_days, "rep_id": rep_id},
    ).fetchall()
    return list(rows)


def list_deals(conn: Connection, rep_id: int | None = None) -> list[dict]:
    if rep_id:
        rows = conn.execute(
            """
            select deal_id, customer_id, rep_id, deal_phase_id, deal_result_status_id,
                   product_id, estimated_amount, win_probability, expected_visit_count,
                   expected_effort_hours, deal_start_date, contract_date
            from deal
            where rep_id = %s
            order by deal_start_date desc, deal_id desc
            """,
            (rep_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            select deal_id, customer_id, rep_id, deal_phase_id, deal_result_status_id,
                   product_id, estimated_amount, win_probability, expected_visit_count,
                   expected_effort_hours, deal_start_date, contract_date
            from deal
            order by deal_start_date desc, deal_id desc
            """
        ).fetchall()
    return list(rows)


def create_deal(
    conn: Connection,
    *,
    customer_id: int,
    rep_id: int,
    product_id: int,
    deal_phase_id: int,
    estimated_amount: Decimal,
    win_probability: int,
    expected_visit_count: int,
    expected_effort_hours: Decimal,
    deal_start_date: date,
) -> dict:
    # deal_id has no owning sequence (AGENTS.md: it preserves the imported CSV's
    # ids), so newly registered deals continue the max+1 by hand. New deals always
    # start 'ongoing' with no contract_date; won/lost is set later via /results,
    # which is the only place the contract_date trigger constraint is satisfied.
    row = conn.execute(
        """
        insert into deal (
          deal_id, customer_id, rep_id, deal_phase_id, deal_result_status_id,
          product_id, estimated_amount, win_probability, expected_visit_count,
          expected_effort_hours, deal_start_date, contract_date
        )
        values (
          (select coalesce(max(deal_id), 0) + 1 from deal),
          %s, %s, %s,
          (select deal_result_status_id from deal_result_status where status_code = 'ongoing'),
          %s, %s, %s, %s, %s, %s, null
        )
        returning deal_id, customer_id, rep_id, deal_phase_id, deal_result_status_id,
                  product_id, estimated_amount, win_probability, expected_visit_count,
                  expected_effort_hours, deal_start_date, contract_date
        """,
        (
            customer_id,
            rep_id,
            deal_phase_id,
            product_id,
            estimated_amount,
            win_probability,
            expected_visit_count,
            expected_effort_hours,
            deal_start_date,
        ),
    ).fetchone()
    conn.commit()
    return dict(row)


def search_products(conn: Connection, name: str | None = None) -> list[dict]:
    where = "where p.product_name ilike %s" if name else ""
    params = (f"%{name}%",) if name else ()
    rows = conn.execute(
        f"""
        select p.product_id, p.product_name,
               ps.subcategory_id, ps.subcategory_name,
               pc.category_id, pc.category_name
        from product p
        join product_subcategory ps on ps.subcategory_id = p.subcategory_id
        join product_category pc on pc.category_id = ps.category_id
        {where}
        order by p.product_name
        """,
        params,
    ).fetchall()
    return list(rows)


def list_plans(
    conn: Connection,
    *,
    rep_id: int,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict]:
    clauses = ["rep_id = %s"]
    params: list[object] = [rep_id]
    if from_date:
        clauses.append("plan_date >= %s")
        params.append(from_date)
    if to_date:
        clauses.append("plan_date <= %s")
        params.append(to_date)
    where = " and ".join(clauses)
    rows = conn.execute(
        f"""
        select plan_id, rep_id, plan_date, customer_id, deal_id, activity_type,
               priority, expected_amount, expected_probability, plan_status,
               is_ai_generated, rationale
        from activity_plan
        where {where}
        order by plan_date, priority
        """,
        params,
    ).fetchall()
    return list(rows)


def _candidate_deals(conn: Connection, rep_id: int) -> list[dict]:
    # Stale (churn-risk) customers get a priority boost within this rep's own
    # candidate list -- this only reorders the rep's own deals, it never
    # reassigns a deal to a different rep (see AGENTS.md: team-wide
    # assignment optimization is an explicit Later feature, out of MVP scope).
    return list(
        conn.execute(
            _LAST_CONTACT_CTE
            + """
            select d.deal_id, d.customer_id, d.estimated_amount, d.win_probability,
                   c.customer_name, i.industry_name, lc.last_contact_date,
                   (
                     lc.last_contact_date is null
                     or lc.last_contact_date < current_date - %(threshold_days)s * interval '1 day'
                   ) as is_stale
            from deal d
            join customer c on c.customer_id = d.customer_id
            join industry i on i.industry_id = c.industry_id
            join deal_result_status drs
              on drs.deal_result_status_id = d.deal_result_status_id
            left join last_contact lc on lc.customer_id = d.customer_id
            where d.rep_id = %(rep_id)s and drs.status_code = 'ongoing'
            order by
              (case when (
                 lc.last_contact_date is null
                 or lc.last_contact_date < current_date - %(threshold_days)s * interval '1 day'
               ) then 1.5 else 1.0 end)
              * (d.estimated_amount * d.win_probability) desc
            """,
            {"rep_id": rep_id, "threshold_days": STALE_THRESHOLD_DAYS},
        ).fetchall()
    )


def generate_plans(
    conn: Connection,
    *,
    rep_id: int,
    target_month: str,
    start_date: date | None = None,
) -> list[PlanOut]:
    """Skeleton planner: clear future scheduled AI plans and recreate from open deals."""
    year, month = map(int, target_month.split("-"))
    base = start_date or date(year, month, 1)

    conn.execute(
        """
        delete from activity_plan
        where rep_id = %s
          and is_ai_generated = true
          and plan_status = 'scheduled'
          and plan_date >= %s
          and to_char(plan_date, 'YYYY-MM') = %s
        """,
        (rep_id, base, target_month),
    )

    candidates = _candidate_deals(conn, rep_id)
    created: list[PlanOut] = []
    for index, deal in enumerate(candidates):
        plan_date = base + timedelta(days=index * 2)
        if plan_date.month != month:
            break
        expected = Decimal(deal["estimated_amount"])
        probability = int(deal["win_probability"])
        rationale = (
            f"{deal['customer_name']} は見込み {expected:,.0f} 円・確度 {probability}% "
            f"（業界: {deal['industry_name'] or '未設定'}）のため優先しています。"
        )
        if deal["is_stale"]:
            if deal["last_contact_date"]:
                rationale += (
                    f" また、前回接点から{STALE_THRESHOLD_DAYS}日以上経過しており"
                    f"（前回: {deal['last_contact_date']}）、顧客流出リスクの観点からも優先度を上げています。"
                )
            else:
                rationale += (
                    " また、これまで接点の記録がなく、顧客流出リスクの観点からも優先度を上げています。"
                )
        row = conn.execute(
            """
            insert into activity_plan (
              rep_id, plan_date, customer_id, deal_id, activity_type, priority,
              expected_amount, expected_probability, plan_status,
              is_ai_generated, rationale
            )
            values (%s, %s, %s, %s, 'visit', %s, %s, %s, 'scheduled', true, %s)
            returning plan_id, rep_id, plan_date, customer_id, deal_id, activity_type,
                      priority, expected_amount, expected_probability, plan_status,
                      is_ai_generated, rationale
            """,
            (
                rep_id,
                plan_date,
                deal["customer_id"],
                deal["deal_id"],
                min(index + 1, 5),
                expected,
                probability,
                rationale,
            ),
        ).fetchone()
        created.append(PlanOut.model_validate(dict(row)))

    conn.commit()
    return created


def create_result(
    conn: Connection,
    *,
    rep_id: int,
    outcome: str,
    result_date: date,
    plan_id: int | None,
    customer_id: int | None,
    deal_id: int | None,
    activity_type: str,
    outcome_note: str | None,
) -> dict:
    # deal_result_status only models progressing / won / lost (AGENTS.md section 9);
    # "deferred" / "progress" / "other" outcomes are recorded on activity_result
    # without closing the deal, so it stays a candidate for future plans.
    if deal_id and outcome in {"won", "lost"}:
        contract_date = result_date if outcome == "won" else None
        conn.execute(
            """
            update deal
            set deal_result_status_id = (
                  select deal_result_status_id
                  from deal_result_status
                  where status_code = %s
                ),
                contract_date = %s
            where deal_id = %s and rep_id = %s
            """,
            (outcome, contract_date, deal_id, rep_id),
        )
        # deal just closed (won/lost) -> this rep's track record changed.
        affinity.recalculate_rep_affinity(conn, rep_id)

    if plan_id:
        conn.execute(
            """
            update activity_plan
            set plan_status = 'done'
            where plan_id = %s and rep_id = %s
            """,
            (plan_id, rep_id),
        )

    row = conn.execute(
        """
        insert into activity_result (
          plan_id, rep_id, result_date, customer_id, deal_id,
          activity_type, outcome, outcome_note
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        returning result_id, plan_id, rep_id, result_date, customer_id, deal_id,
                  activity_type, outcome, outcome_note, created_at
        """,
        (
            plan_id,
            rep_id,
            result_date,
            customer_id,
            deal_id,
            activity_type,
            outcome,
            outcome_note,
        ),
    ).fetchone()
    conn.commit()
    return dict(row)


def forecast(conn: Connection, *, rep_id: int, target_month: str) -> dict:
    target = conn.execute(
        """
        select target_amount
        from sales_target
        where rep_id = %s and target_month = %s
        """,
        (rep_id, _month_to_date(target_month)),
    ).fetchone()
    if not target:
        raise ValueError("target not found")

    plan_stats = conn.execute(
        """
        select
          coalesce(sum(expected_amount * expected_probability / 100.0), 0) as expected_amount,
          count(*)::int as open_plan_count
        from activity_plan
        where rep_id = %s
          and plan_status = 'scheduled'
          and to_char(plan_date, 'YYYY-MM') = %s
        """,
        (rep_id, target_month),
    ).fetchone()

    target_amount = Decimal(target["target_amount"])
    expected_amount = Decimal(plan_stats["expected_amount"])
    ratio = float(expected_amount / target_amount) if target_amount > 0 else 0.0
    return {
        "rep_id": rep_id,
        "target_month": target_month,
        "target_amount": target_amount,
        "expected_amount": expected_amount,
        "attainment_ratio": ratio,
        "open_plan_count": plan_stats["open_plan_count"],
    }
