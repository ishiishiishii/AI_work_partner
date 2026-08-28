import calendar
import math
import random
from datetime import date, timedelta
from decimal import Decimal

from psycopg import Connection

from app.schemas.models import PlanOut
from app.services import affinity, ai, geocoding, target_simulation

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
    rows = conn.execute(
        """
        select r.rep_id, r.rep_name, r.branch_id, b.branch_name
        from sales_rep r
        join branch b on b.branch_id = r.branch_id
        order by r.rep_id
        """
    ).fetchall()
    return list(rows)


def list_masters(conn: Connection) -> dict:
    """Industry/company size/deal phase master lists, for select-box options in
    forms that need to submit the id (customer/deal creation, deal editing).
    Frontend previously hardcoded these (see frontend/lib/mockData.ts history)
    because no API existed yet and the ids had to match seed.sql's insertion
    order."""
    industries = conn.execute(
        "select industry_id, industry_name from industry order by industry_id"
    ).fetchall()
    company_sizes = conn.execute(
        "select company_size_id, company_size_name from company_size_master order by company_size_id"
    ).fetchall()
    deal_phases = conn.execute(
        "select deal_phase_id, deal_phase_name from deal_phase order by sort_order"
    ).fetchall()
    return {
        "industries": list(industries),
        "company_sizes": list(company_sizes),
        "deal_phases": list(deal_phases),
    }


def list_targets(conn: Connection, rep_id: int | None = None) -> list[dict]:
    if rep_id:
        rows = conn.execute(
            """
            select target_id, rep_id, target_month, target_amount, target_deal_count,
                   target_gross_profit
            from sales_target
            where rep_id = %s
            order by target_month desc
            """,
            (rep_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            select target_id, rep_id, target_month, target_amount, target_deal_count,
                   target_gross_profit
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
    target_gross_profit: Decimal | None = None,
) -> dict:
    row = conn.execute(
        """
        insert into sales_target (
          rep_id, target_month, target_amount, target_deal_count, target_gross_profit
        )
        values (%s, %s, %s, %s, %s)
        on conflict (rep_id, target_month) do update
          set target_amount = excluded.target_amount,
              target_deal_count = excluded.target_deal_count,
              target_gross_profit = excluded.target_gross_profit
        returning target_id, rep_id, target_month, target_amount, target_deal_count,
                  target_gross_profit
        """,
        (rep_id, _month_to_date(target_month), target_amount, target_deal_count, target_gross_profit),
    ).fetchone()
    conn.commit()
    return _format_target(row)


def list_deadlines(conn: Connection, rep_id: int | None = None) -> list[dict]:
    if rep_id:
        rows = conn.execute(
            """
            select deadline_id, rep_id, title, due_date, customer_id, deal_id,
                   is_done, memo, created_at
            from deadline
            where rep_id = %s
            order by due_date
            """,
            (rep_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            select deadline_id, rep_id, title, due_date, customer_id, deal_id,
                   is_done, memo, created_at
            from deadline
            order by due_date
            """
        ).fetchall()
    return [dict(row) for row in rows]


def create_deadline(
    conn: Connection,
    *,
    rep_id: int,
    title: str,
    due_date: date,
    customer_id: int | None,
    deal_id: int | None,
    memo: str | None,
) -> dict:
    row = conn.execute(
        """
        insert into deadline (rep_id, title, due_date, customer_id, deal_id, memo)
        values (%s, %s, %s, %s, %s, %s)
        returning deadline_id, rep_id, title, due_date, customer_id, deal_id,
                  is_done, memo, created_at
        """,
        (rep_id, title, due_date, customer_id, deal_id, memo),
    ).fetchone()
    conn.commit()
    return dict(row)


def list_customers(conn: Connection, rep_id: int | None = None) -> list[dict]:
    if rep_id:
        # Scope candidate discovery to the rep's own territory (see
        # `prefecture`/`branch`, 20260826100000 -- same mapping
        # _customer_branch/_rep_branch use for the deal-creation check
        # below), but never hide a customer the rep already has a real
        # relationship with (assigned as primary, or an existing deal --
        # imported deal history predates branch assignment and regularly
        # crosses territory, see create_deal's comment). A customer whose
        # location doesn't match any known prefecture (p.branch_id is null)
        # can't be judged in- or out-of-territory, so it's treated as in
        # territory too. in_territory is surfaced so the frontend can call
        # out the exception cases separately (e.g. a rep transferred from
        # another branch, keeping their prior customers) rather than mixing
        # them silently into the main list. has_relationship is surfaced
        # too, so the frontend can further split the in-territory set into
        # customers the rep already has (registered/deal history) versus
        # untouched candidates in their own area.
        rows = conn.execute(
            """
            select distinct c.customer_id, c.customer_name, c.industry_name,
                   c.company_size_name, c.location, c.primary_rep_id, c.primary_rep_name,
                   c.website, c.contact_name, c.lat, c.lng,
                   (p.branch_id is null or p.branch_id = r.branch_id) as in_territory,
                   coalesce(
                     c.primary_rep_id = %s
                     or exists (
                       select 1 from deal d
                       where d.customer_id = c.customer_id and d.rep_id = %s
                     ),
                     false
                   ) as has_relationship
            from ai.customer c
            join sales_rep r on r.rep_id = %s
            left join prefecture p on starts_with(c.location, p.prefecture_name)
            where p.branch_id is null
               or p.branch_id = r.branch_id
               or c.primary_rep_id = %s
               or exists (
                 select 1 from deal d
                 where d.customer_id = c.customer_id and d.rep_id = %s
               )
            order by c.customer_name
            """,
            (rep_id, rep_id, rep_id, rep_id, rep_id),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            select customer_id, customer_name, industry_name, company_size_name,
                   location, primary_rep_id, primary_rep_name, website, contact_name,
                   lat, lng, true as in_territory, true as has_relationship
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
    website: str | None = None,
    contact_name: str | None = None,
) -> dict:
    # 1件だけなので、登録操作の一部として同期的にジオコーディングを試みる(数百ms程度)。
    # 失敗しても登録自体は止めない -- lat/lngはNULLのままになり、フロント側が
    # 都道府県+ランダムズレにフォールバックする(geocoding.py参照)。
    coords = geocoding.geocode_customer_location(location)
    lat, lng = coords if coords is not None else (None, None)

    new_customer_id = conn.execute(
        """
        insert into customer (
          customer_name, industry_id, company_size_id, location, primary_rep_id,
          website, contact_name, lat, lng
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning customer_id
        """,
        (
            customer_name,
            industry_id,
            company_size_id,
            location,
            primary_rep_id,
            website,
            contact_name,
            lat,
            lng,
        ),
    ).fetchone()["customer_id"]
    # Re-read through the AI view so the response carries resolved names
    # (industry/company size/primary rep) rather than the raw ids just
    # inserted, plus in_territory relative to the assigned primary rep (no
    # primary rep, or an unresolvable location, both default to true --
    # see list_customers' comment on the same convention).
    row = conn.execute(
        """
        select c.customer_id, c.customer_name, c.industry_name, c.company_size_name,
               c.location, c.primary_rep_id, c.primary_rep_name, c.website, c.contact_name,
               c.lat, c.lng,
               coalesce(p.branch_id is null or p.branch_id = r.branch_id, true) as in_territory,
               (c.primary_rep_id is not null) as has_relationship
        from ai.customer c
        left join sales_rep r on r.rep_id = c.primary_rep_id
        left join prefecture p on starts_with(c.location, p.prefecture_name)
        where c.customer_id = %s
        """,
        (new_customer_id,),
    ).fetchone()
    conn.commit()
    return dict(row)


# 新規顧客登録フォームの「顧客名で検索」用。territoryやhas_relationshipで絞らず
# 全担当者の登録済み顧客から名称の部分一致で探す(他の担当者がすでに登録済みの
# 顧客と気づけるようにするための重複防止機能なので、自分のエリア外・無関係でも
# ヒットさせる必要がある)。list_customersと違い業種/企業規模はid込みで返す
# (選択時にフォームのセレクトボックスへそのまま反映するため)。
def search_customers(conn: Connection, *, query: str, limit: int = 8) -> list[dict]:
    rows = conn.execute(
        """
        select c.customer_id, c.customer_name, c.industry_id, i.industry_name,
               c.company_size_id, csm.company_size_name, c.location,
               c.website, c.contact_name
        from customer c
        join industry i on i.industry_id = c.industry_id
        join company_size_master csm on csm.company_size_id = c.company_size_id
        where c.customer_name ilike %s
        order by c.customer_name
        limit %s
        """,
        (f"%{query}%", limit),
    ).fetchall()
    return list(rows)


def list_stale_customers(
    conn: Connection,
    *,
    threshold_days: int = STALE_THRESHOLD_DAYS,
    rep_id: int | None = None,
) -> list[dict]:
    """Customers with no company-wide contact in threshold_days (or ever),
    scoped to the rep's territory the same way list_customers is (with the
    same existing-relationship exception -- see list_customers' comment)."""
    rows = conn.execute(
        """
        select ca.customer_id, ca.customer_name, ca.industry_name, ca.company_size_name,
               ca.location, ca.primary_rep_id, ca.primary_rep_name,
               ca.last_contact_date, ca.days_since_contact,
               coalesce(p.branch_id is null or p.branch_id = r.branch_id, true) as in_territory,
               coalesce(
                 %(rep_id)s::int is not null
                 and (
                   ca.primary_rep_id = %(rep_id)s
                   or exists (
                     select 1 from deal d
                     where d.customer_id = ca.customer_id and d.rep_id = %(rep_id)s
                   )
                 ),
                 false
               ) as has_relationship
        from ai.customer_activity ca
        left join prefecture p on starts_with(ca.location, p.prefecture_name)
        left join sales_rep r on r.rep_id = %(rep_id)s
        where (
          ca.last_contact_date is null
          or ca.last_contact_date < current_date - %(threshold_days)s * interval '1 day'
        )
        and (
          %(rep_id)s::int is null
          or p.branch_id is null
          or p.branch_id = r.branch_id
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
    expected_effort_hours, deal_start_date, contract_date, product_id, deal_phase_id,
    cost, profit, expected_close_date, next_action, actual_amount, memo
"""


def list_deals(
    conn: Connection, rep_id: int | None = None, customer_id: int | None = None
) -> list[dict]:
    conditions = []
    params: list[int] = []
    if rep_id:
        conditions.append("rep_id = %s")
        params.append(rep_id)
    if customer_id:
        conditions.append("customer_id = %s")
        params.append(customer_id)
    where_clause = f"where {' and '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"""
        select {_AI_DEAL_COLUMNS}
        from ai.deal
        {where_clause}
        order by deal_start_date desc, deal_id desc
        """,
        tuple(params),
    ).fetchall()
    return list(rows)


def _customer_branch(conn: Connection, customer_id: int) -> str | None:
    row = conn.execute(
        """
        select b.branch_name
        from customer c
        join prefecture p on starts_with(c.location, p.prefecture_name)
        join branch b on b.branch_id = p.branch_id
        where c.customer_id = %s
        """,
        (customer_id,),
    ).fetchone()
    return row["branch_name"] if row else None


def _rep_branch(conn: Connection, rep_id: int) -> str | None:
    row = conn.execute(
        """
        select b.branch_name
        from sales_rep r
        join branch b on b.branch_id = r.branch_id
        where r.rep_id = %s
        """,
        (rep_id,),
    ).fetchone()
    return row["branch_name"] if row else None


def get_rep_territory(conn: Connection, rep_id: int) -> dict | None:
    """The rep's branch and the prefectures it covers (see `prefecture` /
    `branch` tables, 20260826100000). Used to scope the customer map to a
    rep's own territory instead of showing the whole country."""
    branch_row = conn.execute(
        """
        select b.branch_id, b.branch_name
        from sales_rep r
        join branch b on b.branch_id = r.branch_id
        where r.rep_id = %s
        """,
        (rep_id,),
    ).fetchone()
    if not branch_row:
        return None
    prefecture_rows = conn.execute(
        "select prefecture_name from prefecture where branch_id = %s order by prefecture_name",
        (branch_row["branch_id"],),
    ).fetchall()
    return {
        "branch_name": branch_row["branch_name"],
        "prefectures": [row["prefecture_name"] for row in prefecture_rows],
    }


def create_deal(
    conn: Connection,
    *,
    customer_id: int,
    rep_id: int,
    product_id: int,
    deal_phase_id: int,
    estimated_amount: Decimal,
    expected_visit_count: int,
    expected_effort_hours: Decimal,
    deal_start_date: date,
    expected_close_date: date | None = None,
    next_action: str | None = None,
    memo: str | None = None,
) -> dict:
    # New deals (unlike imported/seeded history, which predates branch
    # assignment) must be logged by a rep whose branch covers the customer's
    # location -- otherwise the AI plan/rationale layer could end up
    # suggesting a rep visit a customer far outside their territory.
    customer_branch = _customer_branch(conn, customer_id)
    rep_branch = _rep_branch(conn, rep_id)
    if customer_branch is not None and rep_branch is not None and customer_branch != rep_branch:
        raise ValueError(
            f"この顧客の所在地は{customer_branch}支店の管轄です。"
            f"{rep_branch}支店の担当者はこの顧客の商談を新規登録できません。"
        )

    # cost has no user input (same as seed.sql's demo data): a random integer
    # between 50% and 95% of estimated_amount, so profit stays meaningful.
    amount = int(estimated_amount)
    cost_low = math.ceil(amount * 0.5)
    cost_high = max(cost_low, math.floor(amount * 0.95))
    cost = random.randint(cost_low, cost_high)

    # win_probability も cost と同様にユーザー入力ではなく、担当者の実績
    # (rep_affinity、無ければ担当者全体の勝率、それも無ければ既定値)から自動算出する。
    win_probability = affinity.estimate_win_probability(
        conn,
        rep_id=rep_id,
        customer_id=customer_id,
        product_id=product_id,
        estimated_amount=estimated_amount,
    )

    # deal_id has no owning sequence (AGENTS.md: it preserves the imported CSV's
    # ids), so newly registered deals continue the max+1 by hand. New deals always
    # start 'ongoing' with no contract_date; won/lost is set later via /results,
    # which is the only place the contract_date trigger constraint is satisfied.
    new_deal_id = conn.execute(
        """
        insert into deal (
          deal_id, customer_id, rep_id, deal_phase_id, deal_result_status_id,
          product_id, estimated_amount, cost, win_probability, expected_visit_count,
          expected_effort_hours, deal_start_date, contract_date,
          expected_close_date, next_action, memo
        )
        values (
          (select coalesce(max(deal_id), 0) + 1 from deal),
          %s, %s, %s,
          (select deal_result_status_id from deal_result_status where status_code = 'ongoing'),
          %s, %s, %s, %s, %s, %s, %s, null, %s, %s, %s
        )
        returning deal_id
        """,
        (
            customer_id,
            rep_id,
            deal_phase_id,
            product_id,
            estimated_amount,
            cost,
            win_probability,
            expected_visit_count,
            expected_effort_hours,
            deal_start_date,
            expected_close_date,
            next_action,
            memo,
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
    expected_visit_count: int,
    expected_effort_hours: Decimal,
    expected_close_date: date | None = None,
    next_action: str | None = None,
    actual_amount: Decimal | None = None,
    memo: str | None = None,
) -> dict:
    existing = conn.execute(
        "select customer_id from deal where deal_id = %s and rep_id = %s",
        (deal_id, rep_id),
    ).fetchone()
    if not existing:
        raise ValueError("deal not found")

    # 商品(カテゴリ)や見込み金額が変わるとパターン分類(大型/小口等)も変わるため、
    # win_probability は編集のたびに最新の実績で再算出する(cf. create_deal)。
    win_probability = affinity.estimate_win_probability(
        conn,
        rep_id=rep_id,
        customer_id=existing["customer_id"],
        product_id=product_id,
        estimated_amount=estimated_amount,
        deal_id=deal_id,
    )

    updated = conn.execute(
        """
        update deal
        set product_id = %s,
            deal_phase_id = %s,
            estimated_amount = %s,
            win_probability = %s,
            expected_visit_count = %s,
            expected_effort_hours = %s,
            expected_close_date = %s,
            next_action = %s,
            actual_amount = coalesce(%s, actual_amount),
            memo = coalesce(%s, memo)
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
            expected_close_date,
            next_action,
            actual_amount,
            memo,
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
               pc.category_id, pc.category_name,
               p.description, p.price_min, p.price_max, p.lead_time_days, p.features
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
    clauses = ["ap.rep_id = %s", "ap.plan_status != 'cancelled'"]
    params: list[object] = [rep_id]
    if from_date:
        clauses.append("ap.plan_date >= %s")
        params.append(from_date)
    if to_date:
        clauses.append("ap.plan_date <= %s")
        params.append(to_date)
    where = " and ".join(clauses)
    rows = conn.execute(
        f"""
        select ap.plan_id, ap.rep_id, ap.plan_date, ap.start_time, ap.end_time, ap.category,
               ap.title, ap.customer_id, ap.deal_id, ap.activity_type, ap.priority,
               ap.expected_amount, ap.expected_probability, ap.plan_status, ap.is_ai_generated,
               ap.rationale, ap.product_name, ap.progress_percent, ap.memo, ar.outcome
        from ai.activity_plan ap
        left join lateral (
            select outcome
            from activity_result
            where activity_result.plan_id = ap.plan_id
            order by created_at desc
            limit 1
        ) ar on true
        where {where}
        order by ap.plan_date, ap.priority
        """,
        params,
    ).fetchall()
    # outcome (won/lost/deferred) is recorded separately in activity_result; fold it
    # into a result_status the frontend can render without a second round trip.
    outcome_to_result_status = {"won": "won", "lost": "lost", "deferred": "postponed"}
    return [
        {**dict(row), "result_status": outcome_to_result_status.get(row["outcome"])}
        for row in rows
    ]


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
    product_name_override: str | None = None,
) -> dict:
    row = conn.execute(
        """
        insert into activity_plan (
          rep_id, plan_date, category, activity_type, start_time, end_time,
          title, customer_id, deal_id, priority, expected_amount, expected_probability,
          plan_status, is_ai_generated, rationale, product_name_override
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'scheduled', false, %s, %s)
        returning plan_id, rep_id, plan_date, start_time, end_time, category, title,
                  customer_id, deal_id, activity_type, priority, expected_amount,
                  expected_probability, plan_status, is_ai_generated, rationale,
                  (select d.product_id from deal d where d.deal_id = activity_plan.deal_id) as product_id,
                  coalesce(
                    activity_plan.product_name_override,
                    (
                      select p.product_name
                      from deal d
                      join product p on p.product_id = d.product_id
                      where d.deal_id = activity_plan.deal_id
                    )
                  ) as product_name,
                  progress_percent,
                  null::text as memo
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
            product_name_override,
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
                  null::int as product_id, null::text as product_name, progress_percent, memo
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
    plan_date: date,
    start_time: str | None,
    end_time: str | None,
    category: str,
    activity_type: str,
    title: str | None,
    customer_id: int | None,
    product_name_override: str | None,
    expected_amount: Decimal,
    expected_probability: int,
    memo: str | None,
) -> dict:
    row = conn.execute(
        """
        update activity_plan ap
        set plan_date = %s,
            start_time = %s,
            end_time = %s,
            category = %s,
            activity_type = %s,
            title = %s,
            customer_id = %s,
            product_name_override = %s,
            expected_amount = %s,
            expected_probability = %s,
            memo = %s
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
                  ) as product_name,
                  ap.progress_percent,
                  ap.memo
        """,
        (
            plan_date,
            start_time,
            end_time,
            category,
            activity_type,
            title,
            customer_id,
            product_name_override,
            expected_amount,
            expected_probability,
            memo,
            plan_id,
            rep_id,
        ),
    ).fetchone()
    if not row:
        raise ValueError("plan not found")
    conn.commit()
    return dict(row)


def update_plan_progress(
    conn: Connection, *, plan_id: int, rep_id: int, progress_percent: int
) -> dict:
    row = conn.execute(
        """
        update activity_plan ap
        set progress_percent = %s
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
                  ) as product_name,
                  ap.progress_percent,
                  ap.memo
        """,
        (progress_percent, plan_id, rep_id),
    ).fetchone()
    if not row:
        raise ValueError("plan not found")
    conn.commit()
    return dict(row)


def _candidate_deals(conn: Connection, rep_id: int) -> list[dict]:
    # Base ordering here is just a stable, deterministic starting point (deal_phase
    # progress, then staleness, then amount) -- generate_plans/forecast re-rank this
    # list via target_simulation.score_candidates once a target is known. This SQL
    # order is what's used when no re-ranking happens (e.g. no sales_target row yet).
    # Only reorders the rep's own deals, never reassigns a deal to a different rep
    # (see AGENTS.md: team-wide assignment optimization is an explicit Later
    # feature, out of MVP scope).
    return list(
        conn.execute(
            """
            select d.deal_id, d.customer_id, d.estimated_amount, d.win_probability,
                   d.customer_name, ca.industry_name, d.product_name,
                   ca.last_contact_date, ca.days_since_contact,
                   d.profit, dp.sort_order as deal_phase_sort_order,
                   d.expected_effort_hours, d.expected_close_date, d.next_action,
                   (
                     ca.last_contact_date is null
                     or ca.last_contact_date < current_date - %(threshold_days)s * interval '1 day'
                   ) as is_stale
            from ai.deal d
            join ai.customer_activity ca on ca.customer_id = d.customer_id
            join deal_phase dp on dp.deal_phase_id = d.deal_phase_id
            where d.rep_id = %(rep_id)s and d.deal_result_status = 'ongoing'
            order by
              dp.sort_order desc,
              (case when (
                 ca.last_contact_date is null
                 or ca.last_contact_date < current_date - %(threshold_days)s * interval '1 day'
               ) then 1 else 0 end) desc,
              d.estimated_amount desc
            """,
            {"rep_id": rep_id, "threshold_days": STALE_THRESHOLD_DAYS},
        ).fetchall()
    )


def _won_this_month(conn: Connection, *, rep_id: int, target_month: str) -> dict:
    """Revenue/profit already closed (won, contract_date in target_month) --
    the fixed baseline that target_simulation.simulate_achievement adds to
    every trial before probabilistically summing the still-open deals."""
    row = conn.execute(
        """
        select coalesce(sum(coalesce(d.actual_amount, d.estimated_amount)), 0) as won_amount,
               coalesce(sum(d.profit), 0) as won_profit
        from ai.deal d
        where d.rep_id = %(rep_id)s
          and d.deal_result_status = 'won'
          and to_char(d.contract_date, 'YYYY-MM') = %(target_month)s
        """,
        {"rep_id": rep_id, "target_month": target_month},
    ).fetchone()
    return {"won_amount": Decimal(row["won_amount"]), "won_profit": Decimal(row["won_profit"])}


def _cap_candidates_to_target(candidates: list[dict], target_amount: Decimal | None) -> list[dict]:
    """Keep candidates in their given priority order, accumulating
    estimated_amount, and stop just before the running total would exceed
    120% of the monthly target -- so a generated plan lands in the
    100-120% achievement range instead of always pulling in every open deal."""
    if target_amount is None:
        return candidates
    # A zero/negative remaining target means this month's closed revenue has
    # already covered the goal. Returning every open deal here used to create
    # more future visits after a win, the opposite of outcome-driven replanning.
    if target_amount <= 0:
        return []
    cap = target_amount * Decimal("1.2")
    capped: list[dict] = []
    running_total = Decimal("0")
    for deal in candidates:
        amount = Decimal(deal["estimated_amount"])
        if running_total + amount > cap and capped:
            break
        capped.append(deal)
        running_total += amount
    return capped


_FALLBACK_FOLLOWUP_TYPES = ("資料作成", "電話", "メール")

# Appended to each rule-based rationale so it explains *why* this month's gap
# situation drove the ranking (target_simulation.classify_gap_situation),
# matching what the AI path is asked to describe via generate_plan_selection's
# situation payload. "on_track" gets no suffix -- nothing unusual to flag.
_SITUATION_RATIONALE_SUFFIX = {
    "both_short": "また、今月は売上・粗利ともに目標達成確率が低いため、両方に貢献する案件として優先度を上げています。",
    "sales_only_short": "また、今月は売上目標の達成確率が低いため、見込み金額の大きい案件として優先度を上げています。",
    "profit_only_short": "また、今月は粗利目標の達成確率が低いため、粗利率の高い案件として優先度を上げています。",
}


def _rule_based_plan_decisions(
    candidates: list[dict], base: date, month: int, situation: str = "on_track"
) -> list[dict]:
    """Fallback used when the AI planner is unreachable or returns nothing
    usable: same gap-aware ordering the AI is asked to reproduce (see
    generate_plans' target_simulation.score_candidates call), one visit per
    business day plus a same-day follow-up task so the day isn't left mostly
    idle after a single short visit."""
    decisions = []
    for index, deal in enumerate(candidates):
        plan_date = base + timedelta(days=index)
        if plan_date.month != month:
            break
        expected = Decimal(deal["estimated_amount"])
        probability = int(deal["win_probability"])
        rationale = (
            f"{deal['customer_name']} は見込み {expected:,.0f} 円・確度 {probability}% "
            f"（業界: {deal['industry_name'] or '未設定'}、商品: {deal['product_name']}）のため優先しています。"
        )
        rationale += _SITUATION_RATIONALE_SUFFIX.get(situation, "")
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
        risk = target_simulation.assess_deal_risk(
            win_probability=deal["win_probability"],
            days_since_contact=deal["days_since_contact"],
            expected_close_date=deal["expected_close_date"],
            today=base,
        )
        if risk.loss_risk == "high" or risk.delay_risk == "high":
            rationale += f" 注意: {'、'.join(risk.reasons)}ため、失注・延期リスクが高い状態です。"
        priority = min(index + 1, 5)
        decisions.append(
            {
                "category": "visit",
                "activity_type": "訪問",
                "deal_id": deal["deal_id"],
                "title": None,
                "plan_date": plan_date,
                "priority": priority,
                "rationale": rationale,
            }
        )
        followup_type = _FALLBACK_FOLLOWUP_TYPES[index % len(_FALLBACK_FOLLOWUP_TYPES)]
        decisions.append(
            {
                "category": "task",
                "activity_type": followup_type,
                "deal_id": deal["deal_id"],
                "title": None,
                "plan_date": plan_date,
                "priority": min(priority + 1, 5),
                "rationale": (
                    f"{deal['customer_name']}への訪問に合わせ、空き時間で{followup_type}を行い"
                    "準備・フォローを進めます。"
                ),
            }
        )
    return decisions


# Typical duration per activity_type, used to pack each day into sequential
# time blocks. The AI (and the rule-based fallback) only decide what/when
# (date)/why -- exact clock times are computed here deterministically so
# they're always valid and non-overlapping, same reasoning as never trusting
# AI-provided amounts (see generate_plan_selection's docstring).
_ACTIVITY_DURATION_MINUTES = {
    "訪問": 90,
    "Web会議": 45,
    "電話": 20,
    "メール": 15,
    "資料作成": 60,
    "新規開拓": 60,
}
_DAY_START_MINUTES = 9 * 60
_LUNCH_START_MINUTES = 12 * 60
_LUNCH_END_MINUTES = 13 * 60


def _minutes_to_hhmm(total_minutes: int) -> str:
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"


_IDLE_FILL_TARGET_MINUTES = 420
_MAX_ITEMS_PER_DAY = 5
_DEAL_SUPPORT_TASK_TARGET = 15

# The LLM is asked to create this mix as well, but these templates are the
# deterministic validation/fallback layer.  A demo must not lose the core
# story merely because the model returned too few preparation/follow-up rows.
# relative_position is consumed by _assign_time_slots so the task is placed
# directly before/after the matching visit instead of in an unrelated gap.
_DEAL_SUPPORT_TASKS = (
    {
        "activity_type": "資料作成",
        "title": "{customer_name}向け提案資料の最終チェック",
        "relative_position": "before",
        "duration_minutes": 30,
        "rationale": "訪問直前の空き時間で、提案内容と見積条件を最終確認します。",
    },
    {
        "activity_type": "電話",
        "title": "{customer_name}へアポイントメント確認",
        "relative_position": "before",
        "duration_minutes": 15,
        "rationale": "訪問前に担当者・開始時刻・当日の議題を確認します。",
    },
    {
        "activity_type": "メール",
        "title": "{customer_name}へ訪問後のフォローアップメール送信",
        "relative_position": "after",
        "duration_minutes": 20,
        "rationale": "訪問直後の空き時間で、合意事項と次のアクションを共有します。",
    },
    {
        "activity_type": "Web会議",
        "title": "{customer_name}へWeb会議の日程調整とアジェンダ共有",
        "relative_position": "after",
        "duration_minutes": 30,
        "rationale": "訪問内容を次の商談につなげるため、日程候補とアジェンダを共有します。",
    },
)

_PROSPECTING_TASKS = (
    (
        "新規開拓リストの更新",
        "来月以降の商談創出に向けて、新規開拓候補の連絡先と優先順位を更新します。",
    ),
    (
        "業界動向のリサーチ",
        "担当業界の動向を調べ、新規見込み先に使える提案仮説を整理します。",
    ),
    (
        "来月に向けた新規顧客リスト作成とアポイントメント架電",
        "月前半の空き時間を活用し、来月の商談母数を先回りして確保します。",
    ),
    (
        "新規見込み先へのアプローチ電話",
        "訪問予定のない時間帯に新規見込み先へ接点を作ります。",
    ),
)

_WEEKLY_ADMIN_TASKS = (
    (
        "週次報告書の作成",
        45,
        "週の活動実績・見込み・翌週の重点案件を定型報告としてまとめます。",
    ),
    (
        "提案資料テンプレートの整備",
        45,
        "空き時間で提案資料と見積テンプレートを整え、次の商談準備を短縮します。",
    ),
)


def _decision_duration(decision: dict) -> int:
    return int(
        decision.get("duration_minutes")
        or _ACTIVITY_DURATION_MINUTES.get(decision["activity_type"], 60)
    )


def _business_days(start: date, end: date) -> list[date]:
    return [
        start + timedelta(days=offset)
        for offset in range((end - start).days + 1)
        if (start + timedelta(days=offset)).weekday() < 5
    ]


def _can_fit(day_decisions: list[dict], duration_minutes: int) -> bool:
    return (
        len(day_decisions) < _MAX_ITEMS_PER_DAY
        and sum(_decision_duration(item) for item in day_decisions) + duration_minutes
        <= _IDLE_FILL_TARGET_MINUTES
    )


def _append_task(decisions: list[dict], by_date: dict[date, list[dict]], task: dict) -> bool:
    day_decisions = by_date.setdefault(task["plan_date"], [])
    if not _can_fit(day_decisions, _decision_duration(task)):
        return False
    decisions.append(task)
    day_decisions.append(task)
    return True


def _fill_idle_days(
    decisions: list[dict],
    candidates: list[dict],
    *,
    base: date,
    month_end: date,
) -> None:
    """Fill genuine working-time gaps with a stable, explainable task mix.

    The LLM still decides the initial monthly plan.  This post-processor
    validates and supplements that output with three product requirements:
    up to 15 deal-linked preparation/follow-up tasks beside their visits,
    repeated prospecting in the first half of the month, and recurring weekly
    administration.  Deal-less tasks never affect the revenue/profit forecast.
    """
    candidates_by_id = {candidate["deal_id"]: candidate for candidate in candidates}
    by_date: dict[date, list[dict]] = {}
    for decision in decisions:
        by_date.setdefault(decision["plan_date"], []).append(decision)

    visits = [
        decision
        for decision in decisions
        if decision["category"] == "visit"
        and decision.get("deal_id") in candidates_by_id
    ]
    visit_keys = {(visit["deal_id"], visit["plan_date"]) for visit in visits}

    # Existing LLM-generated linked tasks count only when they are on the same
    # day as their visit.  Give them a concrete customer-specific title and a
    # before/after marker so they are rendered next to that visit.
    linked_support: list[dict] = []
    for task in decisions:
        key = (task.get("deal_id"), task["plan_date"])
        if task["category"] != "task" or key not in visit_keys:
            continue
        candidate = candidates_by_id[task["deal_id"]]
        template = _DEAL_SUPPORT_TASKS[len(linked_support) % len(_DEAL_SUPPORT_TASKS)]
        task["title"] = task.get("title") or template["title"].format(
            customer_name=candidate["customer_name"]
        )
        task["relative_position"] = template["relative_position"]
        task["duration_minutes"] = min(_decision_duration(task), 45)
        linked_support.append(task)

    # Add at most two support actions per visit, alternating preparation and
    # follow-up.  With the normal eight-visit demo portfolio this creates the
    # requested 15 rows without making a single day look artificially packed.
    existing_signatures = {
        (task.get("deal_id"), task.get("title"), task["plan_date"])
        for task in linked_support
    }
    for visit_index, visit in enumerate(visits):
        if len(linked_support) >= _DEAL_SUPPORT_TASK_TARGET:
            break
        candidate = candidates_by_id[visit["deal_id"]]
        for support_offset in range(2):
            if len(linked_support) >= _DEAL_SUPPORT_TASK_TARGET:
                break
            template = _DEAL_SUPPORT_TASKS[(visit_index * 2 + support_offset) % len(_DEAL_SUPPORT_TASKS)]
            title = template["title"].format(customer_name=candidate["customer_name"])
            signature = (visit["deal_id"], title, visit["plan_date"])
            if signature in existing_signatures:
                continue
            task = {
                "category": "task",
                "activity_type": template["activity_type"],
                "deal_id": visit["deal_id"],
                "title": title,
                "plan_date": visit["plan_date"],
                "priority": visit["priority"],
                "rationale": f"{candidate['customer_name']}への{template['rationale']}",
                "relative_position": template["relative_position"],
                "duration_minutes": template["duration_minutes"],
            }
            if _append_task(decisions, by_date, task):
                linked_support.append(task)
                existing_signatures.add(signature)

    # A small portfolio may not reach 15 with two tasks per visit.  Make one
    # more pass over the remaining support templates, still respecting the
    # five-item/420-minute daily capacity, so four visits can also demonstrate
    # the full 15-item preparation/follow-up story.
    for visit in visits:
        if len(linked_support) >= _DEAL_SUPPORT_TASK_TARGET:
            break
        candidate = candidates_by_id[visit["deal_id"]]
        for template in _DEAL_SUPPORT_TASKS:
            if len(linked_support) >= _DEAL_SUPPORT_TASK_TARGET:
                break
            title = template["title"].format(customer_name=candidate["customer_name"])
            signature = (visit["deal_id"], title, visit["plan_date"])
            if signature in existing_signatures:
                continue
            task = {
                "category": "task",
                "activity_type": template["activity_type"],
                "deal_id": visit["deal_id"],
                "title": title,
                "plan_date": visit["plan_date"],
                "priority": visit["priority"],
                "rationale": f"{candidate['customer_name']}への{template['rationale']}",
                "relative_position": template["relative_position"],
                "duration_minutes": template["duration_minutes"],
            }
            if _append_task(decisions, by_date, task):
                linked_support.append(task)
                existing_signatures.add(signature)

    business_days = _business_days(base, month_end)
    if not business_days:
        return

    def add_to_first_available(task: dict, eligible_days: list[date]) -> bool:
        for plan_date in eligible_days:
            candidate_task = {**task, "plan_date": plan_date}
            existing = {
                (item.get("title"), item.get("deal_id"))
                for item in by_date.get(plan_date, [])
            }
            if (candidate_task.get("title"), candidate_task.get("deal_id")) in existing:
                continue
            if _append_task(decisions, by_date, candidate_task):
                return True
        return False

    # Concentrate prospecting in the first half of the month.  Eight repeated
    # actions make the pattern visible while still leaving capacity for visits
    # and their preparation/follow-up.
    first_half_days = [day for day in business_days if day.day <= 15]
    for index in range(min(8, len(first_half_days))):
        title, rationale = _PROSPECTING_TASKS[index % len(_PROSPECTING_TASKS)]
        preferred = first_half_days[index:] + first_half_days[:index]
        add_to_first_available(
            {
                "category": "task",
                "activity_type": "新規開拓",
                "deal_id": None,
                "title": title,
                "priority": 4,
                "rationale": rationale,
                "duration_minutes": 45,
            },
            preferred,
        )

    # Repeat the same two administrative tasks once in every ISO week.  The
    # report prefers the last business day and template upkeep the middle day;
    # capacity checks move them to another idle slot in that week if needed.
    weeks: dict[tuple[int, int], list[date]] = {}
    for day in business_days:
        iso = day.isocalendar()
        weeks.setdefault((iso.year, iso.week), []).append(day)
    for week_days in weeks.values():
        for task_index, (title, duration, rationale) in enumerate(_WEEKLY_ADMIN_TASKS):
            if any(
                item.get("title") == title
                for plan_date in week_days
                for item in by_date.get(plan_date, [])
            ):
                continue
            preferred_day = week_days[-1] if task_index == 0 else week_days[len(week_days) // 2]
            preferred = [preferred_day] + [day for day in week_days if day != preferred_day]
            add_to_first_available(
                {
                    "category": "task",
                    "activity_type": "資料作成",
                    "deal_id": None,
                    "title": title,
                    "priority": 5,
                    "rationale": rationale,
                    "duration_minutes": duration,
                },
                preferred,
            )


def _assign_time_slots(decisions: list[dict]) -> None:
    """Assign non-overlapping slots, keeping support immediately by its visit."""
    by_date: dict[date, list[dict]] = {}
    for decision in decisions:
        by_date.setdefault(decision["plan_date"], []).append(decision)

    for day_decisions in by_date.values():
        visits = [item for item in day_decisions if item["category"] == "visit"]
        visit_rank = {item.get("deal_id"): index for index, item in enumerate(visits)}

        def schedule_key(item: dict) -> tuple[int, int, int]:
            deal_id = item.get("deal_id")
            if deal_id in visit_rank:
                position = item.get("relative_position")
                position_rank = 0 if position == "before" else 2 if position == "after" else 1
                return visit_rank[deal_id], position_rank, item["priority"]
            return len(visits) + item["priority"], 1, item["priority"]

        day_decisions.sort(key=schedule_key)
        cursor = _DAY_START_MINUTES
        for decision in day_decisions:
            if _LUNCH_START_MINUTES <= cursor < _LUNCH_END_MINUTES:
                cursor = _LUNCH_END_MINUTES
            duration = _decision_duration(decision)
            decision["start_time"] = _minutes_to_hhmm(cursor)
            cursor += duration
            decision["end_time"] = _minutes_to_hhmm(cursor)


def _activity_plan_economics(decision: dict, deal: dict | None) -> tuple[Decimal, int]:
    """Keep deal value on the visit, never on its supporting work rows."""
    if decision["category"] != "visit" or deal is None:
        return Decimal("0"), 0
    return Decimal(deal["estimated_amount"]), int(deal["win_probability"])


def generate_plans(
    conn: Connection,
    *,
    rep_id: int,
    target_month: str,
    start_date: date | None = None,
) -> tuple[list[PlanOut], bool]:
    """Clear future scheduled AI plans and recreate from open deals.

    Deal selection, scheduling, priority, and rationale are asked of the AI
    planner (Qwen); if it's unreachable or returns nothing usable, falls back
    to the deterministic expected-value ordering so plan generation never
    breaks (AGENTS.md: AI stays a replaceable boundary). Returns the created
    plans plus whether the AI planner was actually used.
    """
    year, month = map(int, target_month.split("-"))
    base = start_date or date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])

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

    all_candidates = _candidate_deals(conn, rep_id)
    sales_target = conn.execute(
        """
        select target_amount, target_deal_count, target_gross_profit
        from sales_target where rep_id = %s and target_month = %s
        """,
        (rep_id, _month_to_date(target_month)),
    ).fetchone()
    target_amount = Decimal(sales_target["target_amount"]) if sales_target else None
    remaining_target_amount = target_amount
    planning_sales_target = dict(sales_target) if sales_target else None
    situation = "on_track"

    won = (
        _won_this_month(conn, rep_id=rep_id, target_month=target_month)
        if sales_target
        else {"won_amount": Decimal("0"), "won_profit": Decimal("0")}
    )
    if sales_target:
        remaining_target_amount = max(
            Decimal("0"), target_amount - won["won_amount"]
        )
        planning_sales_target["target_amount"] = remaining_target_amount
        if sales_target["target_gross_profit"] is not None:
            planning_sales_target["target_gross_profit"] = max(
                Decimal("0"),
                Decimal(sales_target["target_gross_profit"]) - won["won_profit"],
            )

    if sales_target and all_candidates:
        target_gross_profit = (
            Decimal(sales_target["target_gross_profit"])
            if sales_target["target_gross_profit"] is not None
            else None
        )
        simulation = target_simulation.simulate_achievement(
            all_candidates,
            already_won_amount=won["won_amount"],
            already_won_profit=won["won_profit"],
            target_amount=target_amount,
            target_gross_profit=target_gross_profit,
        )
        situation = target_simulation.classify_gap_situation(
            sales_probability=simulation.sales_probability,
            profit_probability=simulation.profit_probability,
        )
        # Re-rank by the gap-aware priority score (spec sections 9.3/10) instead
        # of _candidate_deals' plain SQL ORDER BY; _cap_candidates_to_target
        # below stays a generic "walk the ranked list, stop at 120% of target"
        # step regardless of how that ranking was produced.
        target_simulation.score_candidates(
            all_candidates, situation=situation, today=base, month_end=month_end,
        )
        all_candidates.sort(key=lambda deal: deal["value_score"], reverse=True)

    # all_candidates is now ranked by priority; cap it to the deals needed to
    # land the plan in the 100-120% achievement range instead of pulling in
    # every open deal.
    candidates = _cap_candidates_to_target(all_candidates, remaining_target_amount)
    candidates_by_id = {deal["deal_id"]: deal for deal in candidates}

    decisions: list[dict] = []
    used_ai = False
    if candidates:
        try:
            decisions = ai.generate_plan_selection(
                conn,
                rep_id=rep_id,
                target_month=target_month,
                base_date=base,
                month_end=month_end,
                # candidates is already capped to the target range; the extra
                # slice keeps the prompt (and latency) bounded for reps with
                # 100+ open deals without dropping the deals worth planning.
                candidates=candidates[:40],
                # The monthly target shown to Qwen is the amount still needed
                # after won deals, so a success removes surplus future visits.
                sales_target=planning_sales_target,
                situation=situation,
            )
            used_ai = True
        except ai.AiPlanningError:
            decisions = _rule_based_plan_decisions(candidates, base, month, situation)

    _fill_idle_days(decisions, candidates, base=base, month_end=month_end)
    _assign_time_slots(decisions)

    created: list[PlanOut] = []
    for decision in decisions:
        deal = candidates_by_id.get(decision["deal_id"]) if decision["deal_id"] is not None else None
        expected, probability = _activity_plan_economics(decision, deal)
        row = conn.execute(
            """
            insert into activity_plan (
              rep_id, plan_date, start_time, end_time, category, title, customer_id,
              deal_id, activity_type, priority, expected_amount, expected_probability,
              plan_status, is_ai_generated, rationale
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'scheduled', true, %s)
            returning plan_id, rep_id, plan_date, start_time, end_time, category, title,
                      customer_id, deal_id, activity_type, priority, expected_amount,
                      expected_probability, plan_status, is_ai_generated, rationale
            """,
            (
                rep_id,
                decision["plan_date"],
                decision["start_time"],
                decision["end_time"],
                decision["category"],
                decision["title"],
                deal["customer_id"] if deal else None,
                decision["deal_id"],
                decision["activity_type"],
                decision["priority"],
                expected,
                probability,
                decision["rationale"],
            ),
        ).fetchone()
        plan_data = dict(row)
        plan_data["product_name"] = deal["product_name"] if deal else None
        created.append(PlanOut.model_validate(plan_data))

    conn.commit()
    return created, used_ai


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
        # lost へ遷移する際は既存の actual_amount(過去にwon→取り消し等で入っていた値)を
        # 明示的にnullへ戻す。enforce_deal_contract_dateトリガーがwon以外での
        # actual_amount残存を拒否するため、放置すると更新自体が失敗する。
        conn.execute(
            """
            update deal
            set deal_result_status_id = (
                  select deal_result_status_id
                  from deal_result_status
                  where status_code = %s
                ),
                contract_date = %s,
                actual_amount = case when %s = 'won' then actual_amount else null end
            where deal_id = %s and rep_id = %s
            """,
            (outcome, contract_date, outcome, deal_id, rep_id),
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
                contract_date = null,
                actual_amount = null
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
        select target_amount, target_gross_profit
        from sales_target
        where rep_id = %s and target_month = %s
        """,
        (rep_id, _month_to_date(target_month)),
    ).fetchone()
    if not target:
        raise ValueError("target not found")

    # 1商談に複数のactivity_plan行(訪問+関連タスク等)が紐づき得るため、商談単位で
    # 1回だけ計上する(重複計上を避ける)。成約は実契約金額(actual_amount、未記録なら
    # estimated_amount)、失注は0円、進行中は見込み金額×確度/100。粗利も同じ考え方で
    # deal.profit(estimated_amountベースの見積り粗利)を確度按分して合算する。
    # deal_idの無い予定(次回予定作成時に参考としてコピーされただけの商品・金額など)は
    # 実体の商談が存在せず成約しようがないため、見込みには一切加算しない。
    stats = conn.execute(
        """
        with month_plans as (
          select plan_id, deal_id, plan_status
          from activity_plan
          where rep_id = %(rep_id)s
            and plan_status != 'cancelled'
            and to_char(plan_date, 'YYYY-MM') = %(target_month)s
        ),
        deal_amounts as (
          select
            d.deal_id,
            case
              when drs.status_code = 'won' then coalesce(d.actual_amount, d.estimated_amount)
              when drs.status_code = 'lost' then 0
              else d.estimated_amount * d.win_probability / 100
            end as amount,
            case
              when drs.status_code = 'lost' then 0
              when drs.status_code = 'won' then d.profit
              else d.profit * d.win_probability / 100
            end as gross_profit
          from deal d
          join deal_result_status drs on drs.deal_result_status_id = d.deal_result_status_id
          where d.deal_id in (select deal_id from month_plans where deal_id is not null)
        )
        select
          coalesce((select sum(amount) from deal_amounts), 0) as expected_amount,
          coalesce((select sum(gross_profit) from deal_amounts), 0) as expected_gross_profit,
          (select count(*) from month_plans where plan_status = 'scheduled')::int as open_plan_count
        """,
        {"rep_id": rep_id, "target_month": target_month},
    ).fetchone()

    target_amount = Decimal(target["target_amount"])
    target_gross_profit = (
        Decimal(target["target_gross_profit"]) if target["target_gross_profit"] is not None else None
    )
    expected_amount = Decimal(stats["expected_amount"])
    expected_gross_profit = Decimal(stats["expected_gross_profit"])
    ratio = float(expected_amount / target_amount) if target_amount > 0 else 0.0
    gross_profit_ratio = (
        float(expected_gross_profit / target_gross_profit)
        if target_gross_profit is not None and target_gross_profit > 0
        else None
    )

    # Distinct from expected_amount/expected_gross_profit above (which only
    # count what's already on the calendar this month): the simulation looks
    # at every open deal in the pipeline, scheduled or not, to answer "what's
    # our shot at the target by month end" (spec section 9.1/11).
    open_deals = _candidate_deals(conn, rep_id)
    won = _won_this_month(conn, rep_id=rep_id, target_month=target_month)
    simulation = target_simulation.simulate_achievement(
        open_deals,
        already_won_amount=won["won_amount"],
        already_won_profit=won["won_profit"],
        target_amount=target_amount,
        target_gross_profit=target_gross_profit,
    )

    return {
        "rep_id": rep_id,
        "target_month": target_month,
        "target_amount": target_amount,
        "expected_amount": expected_amount,
        "attainment_ratio": ratio,
        "open_plan_count": stats["open_plan_count"],
        "target_gross_profit": target_gross_profit,
        "expected_gross_profit": expected_gross_profit,
        "gross_profit_attainment_ratio": gross_profit_ratio,
        "sales_achievement_probability": simulation.sales_probability,
        "profit_achievement_probability": simulation.profit_probability,
        "joint_achievement_probability": simulation.joint_probability,
        "sales_gap_amount": simulation.sales_gap,
        "profit_gap_amount": simulation.profit_gap,
    }
