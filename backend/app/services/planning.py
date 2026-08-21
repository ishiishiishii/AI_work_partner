from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from psycopg import Connection

from app.schemas.models import PlanOut


def list_targets(conn: Connection, rep_id: UUID | None = None) -> list[dict]:
    if rep_id:
        rows = conn.execute(
            """
            select rep_id, target_month, target_amount, target_deal_count
            from sales_target
            where rep_id = %s
            order by target_month desc
            """,
            (rep_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            select rep_id, target_month, target_amount, target_deal_count
            from sales_target
            order by target_month desc
            """
        ).fetchall()
    return list(rows)


def upsert_target(
    conn: Connection,
    *,
    rep_id: UUID,
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
        returning rep_id, target_month, target_amount, target_deal_count
        """,
        (rep_id, target_month, target_amount, target_deal_count),
    ).fetchone()
    conn.commit()
    return dict(row)


def list_customers(conn: Connection, rep_id: UUID | None = None) -> list[dict]:
    if rep_id:
        rows = conn.execute(
            """
            select customer_id, customer_name, industry, location,
                   estimated_amount, win_probability, primary_rep_id, status
            from customer
            where primary_rep_id = %s
            order by customer_name
            """,
            (rep_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            select customer_id, customer_name, industry, location,
                   estimated_amount, win_probability, primary_rep_id, status
            from customer
            order by customer_name
            """
        ).fetchall()
    return list(rows)


def create_customer(
    conn: Connection,
    *,
    customer_name: str,
    primary_rep_id: UUID,
    industry: str | None,
    location: str | None,
    estimated_amount: Decimal,
    win_probability: int,
    status: str,
) -> dict:
    row = conn.execute(
        """
        insert into customer (
          customer_name, primary_rep_id, industry, location,
          estimated_amount, win_probability, status
        )
        values (%s, %s, %s, %s, %s, %s, %s)
        returning customer_id, customer_name, industry, location,
                  estimated_amount, win_probability, primary_rep_id, status
        """,
        (
            customer_name,
            primary_rep_id,
            industry,
            location,
            estimated_amount,
            win_probability,
            status,
        ),
    ).fetchone()
    conn.commit()
    return dict(row)


def list_plans(
    conn: Connection,
    *,
    rep_id: UUID,
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


def _candidate_deals(conn: Connection, rep_id: UUID) -> list[dict]:
    return list(
        conn.execute(
            """
            select d.deal_id, d.customer_id, d.estimated_amount, d.win_probability,
                   c.customer_name, c.industry
            from deal d
            join customer c on c.customer_id = d.customer_id
            where d.rep_id = %s and d.result_status = 'open'
            order by (d.estimated_amount * d.win_probability) desc
            """,
            (rep_id,),
        ).fetchall()
    )


def generate_plans(
    conn: Connection,
    *,
    rep_id: UUID,
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
            f"（業界: {deal['industry'] or '未設定'}）のため優先しています。"
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
    rep_id: UUID,
    outcome: str,
    result_date: date,
    plan_id: UUID | None,
    customer_id: UUID | None,
    deal_id: UUID | None,
    activity_type: str,
    outcome_note: str | None,
) -> dict:
    if deal_id and outcome in {"won", "lost", "deferred"}:
        status_map = {"won": "won", "lost": "lost", "deferred": "deferred"}
        conn.execute(
            """
            update deal
            set result_status = %s
            where deal_id = %s and rep_id = %s
            """,
            (status_map[outcome], deal_id, rep_id),
        )

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


def forecast(conn: Connection, *, rep_id: UUID, target_month: str) -> dict:
    target = conn.execute(
        """
        select target_amount
        from sales_target
        where rep_id = %s and target_month = %s
        """,
        (rep_id, target_month),
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
