from datetime import date, timedelta
from decimal import Decimal

from psycopg import Connection

from app.schemas.models import PlanOut
from app.services import affinity

# A customer counts as "stale" (churn-risk, company-wide) with no visit or
# deal in this many days. Shared by list_stale_customers and the plan
# generator's priority boost so the two stay in sync.
STALE_THRESHOLD_DAYS = 60


def _month_to_date(target_month: str) -> date:
    year, month = map(int, target_month.split("-"))
    return date(year, month, 1)


def _format_target(row: dict) -> dict:
    row = dict(row)
    row["target_month"] = row["target_month"].strftime("%Y-%m")
    return row


def list_reps(conn: Connection) -> list[dict]:
    rows = conn.execute("select rep_id, rep_name from sales_rep order by rep_id").fetchall()
    return list(rows)


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
            select distinct c.customer_id, c.customer_name, c.industry_name,
                   c.company_size_name, c.location, c.primary_rep_id, c.primary_rep_name
            from ai.customer c
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
            select customer_id, customer_name, industry_name, company_size_name,
                   location, primary_rep_id, primary_rep_name
            from ai.customer
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
    new_customer_id = conn.execute(
        """
        insert into customer (
          customer_name, industry_id, company_size_id, location, primary_rep_id
        )
        values (%s, %s, %s, %s, %s)
        returning customer_id
        """,
        (customer_name, industry_id, company_size_id, location, primary_rep_id),
    ).fetchone()["customer_id"]
    # Re-read through the AI view so the response carries resolved names
    # (industry/company size/primary rep) rather than the raw ids just inserted.
    row = conn.execute(
        """
        select customer_id, customer_name, industry_name, company_size_name,
               location, primary_rep_id, primary_rep_name
        from ai.customer
        where customer_id = %s
        """,
        (new_customer_id,),
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
        """
        select ca.customer_id, ca.customer_name, ca.industry_name, ca.company_size_name,
               ca.location, ca.primary_rep_id, ca.primary_rep_name,
               ca.last_contact_date, ca.days_since_contact
        from ai.customer_activity ca
        where (
          ca.last_contact_date is null
          or ca.last_contact_date < current_date - %(threshold_days)s * interval '1 day'
        )
        and (
          %(rep_id)s::int is null
          or ca.primary_rep_id = %(rep_id)s
          or exists (
            select 1 from deal d
            where d.customer_id = ca.customer_id and d.rep_id = %(rep_id)s
          )
        )
        order by ca.last_contact_date asc nulls first
        """,
        {"threshold_days": threshold_days, "rep_id": rep_id},
    ).fetchall()
    return list(rows)


_AI_DEAL_COLUMNS = """
    deal_id, customer_id, customer_name, rep_id, rep_name,
    deal_phase_name, deal_result_status, product_name, subcategory_name,
    category_name, estimated_amount, win_probability, expected_visit_count,
    expected_effort_hours, deal_start_date, contract_date, product_id, deal_phase_id
"""


def list_deals(conn: Connection, rep_id: int | None = None) -> list[dict]:
    if rep_id:
        rows = conn.execute(
            f"""
            select {_AI_DEAL_COLUMNS}
            from ai.deal
            where rep_id = %s
            order by deal_start_date desc, deal_id desc
            """,
            (rep_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            select {_AI_DEAL_COLUMNS}
            from ai.deal
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
    new_deal_id = conn.execute(
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
        returning deal_id
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
    ).fetchone()["deal_id"]
    # Re-read through the AI view so the response carries resolved names
    # (customer/rep/phase/status/product) rather than the raw ids just inserted.
    row = conn.execute(
        f"select {_AI_DEAL_COLUMNS} from ai.deal where deal_id = %s",
        (new_deal_id,),
    ).fetchone()
    conn.commit()
    return dict(row)


def update_deal(
    conn: Connection,
    *,
    deal_id: int,
    rep_id: int,
    product_id: int,
    deal_phase_id: int,
    estimated_amount: Decimal,
    win_probability: int,
    expected_visit_count: int,
    expected_effort_hours: Decimal,
) -> dict:
    updated = conn.execute(
        """
        update deal
        set product_id = %s,
            deal_phase_id = %s,
            estimated_amount = %s,
            win_probability = %s,
            expected_visit_count = %s,
            expected_effort_hours = %s
        where deal_id = %s and rep_id = %s
        returning deal_id
        """,
        (
            product_id,
            deal_phase_id,
            estimated_amount,
            win_probability,
            expected_visit_count,
            expected_effort_hours,
            deal_id,
            rep_id,
        ),
    ).fetchone()
    if not updated:
        raise ValueError("deal not found")
    row = conn.execute(
        f"select {_AI_DEAL_COLUMNS} from ai.deal where deal_id = %s",
        (deal_id,),
    ).fetchone()
    conn.commit()
    return dict(row)


def delete_deal(conn: Connection, *, deal_id: int, rep_id: int) -> None:
    deleted = conn.execute(
        "delete from deal where deal_id = %s and rep_id = %s returning deal_id",
        (deal_id, rep_id),
    ).fetchone()
    if not deleted:
        raise ValueError("deal not found")
    conn.commit()


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
    # cancelled plans (e.g. replaced via '対応が難しい') are intentionally excluded --
    # they're kept in the table for history, but shouldn't reappear in the active list.
    clauses = ["rep_id = %s", "plan_status != 'cancelled'"]
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
        select plan_id, rep_id, plan_date, start_time, end_time, category, title,
               customer_id, deal_id, activity_type, priority, expected_amount,
               expected_probability, plan_status, is_ai_generated, rationale, product_name
        from ai.activity_plan
        where {where}
        order by plan_date, priority
        """,
        params,
    ).fetchall()
    return list(rows)


def create_plan(
    conn: Connection,
    *,
    rep_id: int,
    plan_date: date,
    category: str,
    activity_type: str,
    start_time: str | None,
    end_time: str | None,
    title: str | None,
    customer_id: int | None,
    deal_id: int | None,
    priority: int,
    expected_amount: Decimal,
    expected_probability: int,
    rationale: str | None,
) -> dict:
    row = conn.execute(
        """
        insert into activity_plan (
          rep_id, plan_date, category, activity_type, start_time, end_time,
          title, customer_id, deal_id, priority, expected_amount, expected_probability,
          plan_status, is_ai_generated, rationale
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'scheduled', false, %s)
        returning plan_id, rep_id, plan_date, start_time, end_time, category, title,
                  customer_id, deal_id, activity_type, priority, expected_amount,
                  expected_probability, plan_status, is_ai_generated, rationale,
                  null::int as product_id, null::text as product_name
        """,
        (
            rep_id,
            plan_date,
            category,
            activity_type,
            start_time,
            end_time,
            title,
            customer_id,
            deal_id,
            priority,
            expected_amount,
            expected_probability,
            rationale,
        ),
    ).fetchone()
    conn.commit()
    return dict(row)


def cancel_plan(conn: Connection, *, plan_id: int, rep_id: int) -> dict:
    """Soft-cancel a plan (e.g. replaced via '対応が難しい') rather than hard-deleting it."""
    row = conn.execute(
        """
        update activity_plan
        set plan_status = 'cancelled'
        where plan_id = %s and rep_id = %s
        returning plan_id, rep_id, plan_date, start_time, end_time, category, title,
                  customer_id, deal_id, activity_type, priority, expected_amount,
                  expected_probability, plan_status, is_ai_generated, rationale,
                  null::int as product_id, null::text as product_name
        """,
        (plan_id, rep_id),
    ).fetchone()
    if not row:
        raise ValueError("plan not found")
    conn.commit()
    return dict(row)


def update_plan(
    conn: Connection,
    *,
    plan_id: int,
    rep_id: int,
    start_time: str | None,
    end_time: str | None,
    category: str,
    activity_type: str,
    title: str | None,
    product_name_override: str | None,
) -> dict:
    row = conn.execute(
        """
        update activity_plan ap
        set start_time = %s,
            end_time = %s,
            category = %s,
            activity_type = %s,
            title = %s,
            product_name_override = %s
        where ap.plan_id = %s and ap.rep_id = %s
        returning ap.plan_id, ap.rep_id, ap.plan_date, ap.start_time, ap.end_time,
                  ap.category, ap.title, ap.customer_id, ap.deal_id, ap.activity_type,
                  ap.priority, ap.expected_amount, ap.expected_probability, ap.plan_status,
                  ap.is_ai_generated, ap.rationale,
                  (select d.product_id from deal d where d.deal_id = ap.deal_id) as product_id,
                  coalesce(
                    ap.product_name_override,
                    (
                      select p.product_name
                      from deal d
                      join product p on p.product_id = d.product_id
                      where d.deal_id = ap.deal_id
                    )
                  ) as product_name
        """,
        (start_time, end_time, category, activity_type, title, product_name_override, plan_id, rep_id),
    ).fetchone()
    if not row:
        raise ValueError("plan not found")
    conn.commit()
    return dict(row)


def _candidate_deals(conn: Connection, rep_id: int) -> list[dict]:
    # Stale (churn-risk) customers get a priority boost within this rep's own
    # candidate list -- this only reorders the rep's own deals, it never
    # reassigns a deal to a different rep (see AGENTS.md: team-wide
    # assignment optimization is an explicit Later feature, out of MVP scope).
    return list(
        conn.execute(
            """
            select d.deal_id, d.customer_id, d.estimated_amount, d.win_probability,
                   d.customer_name, ca.industry_name, d.product_name,
                   ca.last_contact_date,
                   (
                     ca.last_contact_date is null
                     or ca.last_contact_date < current_date - %(threshold_days)s * interval '1 day'
                   ) as is_stale
            from ai.deal d
            join ai.customer_activity ca on ca.customer_id = d.customer_id
            where d.rep_id = %(rep_id)s and d.deal_result_status = 'ongoing'
            order by
              (case when (
                 ca.last_contact_date is null
                 or ca.last_contact_date < current_date - %(threshold_days)s * interval '1 day'
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
          and category = 'visit'
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
            f"（業界: {deal['industry_name'] or '未設定'}、商品: {deal['product_name']}）のため優先しています。"
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
        plan_data = dict(row)
        plan_data["product_name"] = deal["product_name"]
        created.append(PlanOut.model_validate(plan_data))

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


def delete_result(conn: Connection, *, result_id: int, rep_id: int) -> dict:
    """Undo a recorded result: mirror-image of create_result's side effects."""
    result = conn.execute(
        """
        select result_id, plan_id, rep_id, result_date, customer_id, deal_id,
               activity_type, outcome, outcome_note, created_at
        from activity_result
        where result_id = %s and rep_id = %s
        """,
        (result_id, rep_id),
    ).fetchone()
    if not result:
        raise ValueError("result not found")

    if result["deal_id"] and result["outcome"] in {"won", "lost"}:
        conn.execute(
            """
            update deal
            set deal_result_status_id = (
                  select deal_result_status_id
                  from deal_result_status
                  where status_code = 'ongoing'
                ),
                contract_date = null
            where deal_id = %s and rep_id = %s
            """,
            (result["deal_id"], rep_id),
        )
        # deal re-opened -> this rep's track record changed again.
        affinity.recalculate_rep_affinity(conn, rep_id)

    if result["plan_id"]:
        conn.execute(
            """
            update activity_plan
            set plan_status = 'scheduled'
            where plan_id = %s and rep_id = %s
            """,
            (result["plan_id"], rep_id),
        )

    conn.execute("delete from activity_result where result_id = %s", (result_id,))
    conn.commit()
    return dict(result)


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
