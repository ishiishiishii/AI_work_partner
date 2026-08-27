import calendar
import math
import random
from datetime import date, timedelta
from decimal import Decimal

from psycopg import Connection

from app.schemas.models import PlanOut
from app.services import affinity, ai, geocoding

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
    cost, profit, actual_amount
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
          expected_effort_hours, deal_start_date, contract_date
        )
        values (
          (select coalesce(max(deal_id), 0) + 1 from deal),
          %s, %s, %s,
          (select deal_result_status_id from deal_result_status where status_code = 'ongoing'),
          %s, %s, %s, %s, %s, %s, %s, null
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
    actual_amount: Decimal | None = None,
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
            actual_amount = coalesce(%s, actual_amount)
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
            actual_amount,
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
               expected_probability, plan_status, is_ai_generated, rationale, product_name,
               progress_percent, memo
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
                  null::int as product_id, null::text as product_name, progress_percent,
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
    start_time: str | None,
    end_time: str | None,
    category: str,
    activity_type: str,
    title: str | None,
    product_name_override: str | None,
    memo: str | None,
) -> dict:
    row = conn.execute(
        """
        update activity_plan ap
        set start_time = %s,
            end_time = %s,
            category = %s,
            activity_type = %s,
            title = %s,
            product_name_override = %s,
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
            start_time,
            end_time,
            category,
            activity_type,
            title,
            product_name_override,
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
    # Priority order: how far along the deal is (deal_phase.sort_order, closer
    # to close first), then stale (churn-risk) customers within the same
    # phase -- this only reorders the rep's own deals, it never reassigns a
    # deal to a different rep (see AGENTS.md: team-wide assignment
    # optimization is an explicit Later feature, out of MVP scope).
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


def _cap_candidates_to_target(candidates: list[dict], target_amount: Decimal | None) -> list[dict]:
    """Keep candidates in their given priority order, accumulating
    estimated_amount, and stop just before the running total would exceed
    120% of the monthly target -- so a generated plan lands in the
    100-120% achievement range instead of always pulling in every open deal."""
    if not target_amount or target_amount <= 0:
        return candidates
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


def _rule_based_plan_decisions(candidates: list[dict], base: date, month: int) -> list[dict]:
    """Fallback used when the AI planner is unreachable or returns nothing
    usable: same expected-value ordering the AI is asked to reproduce, one
    visit per business day plus a same-day follow-up task so the day isn't
    left mostly idle after a single short visit."""
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
_FILLER_ACTIVITY_TYPES = ("資料作成", "電話", "メール", "新規開拓")

# Deal-less busywork used once the target-capped candidate pool (see
# _cap_candidates_to_target) runs out. These carry no deal_id, so they add
# nothing to expected_amount/forecast -- filling idle time must never pull in
# deals beyond what's needed to hit the target just to look busy.
_GENERIC_FILLER_TASKS = (
    ("資料作成", "週次報告書の作成", "報告・数字管理の事務作業として、空き時間に週次報告書を作成します。"),
    ("新規開拓", "新規開拓リストの更新", "来月以降の商談創出に向けて、空き時間で新規開拓リストを整理します。"),
    ("資料作成", "提案資料テンプレートの整備", "既存の提案資料・見積テンプレートを見直し、次の商談ですぐ使えるよう整備します。"),
    ("新規開拓", "業界動向のリサーチ", "担当業界の最新動向を調べ、新規開拓や既存提案のネタとして整理します。"),
)


def _fill_idle_days(decisions: list[dict], candidates: list[dict]) -> None:
    """Top up days that already have at least one activity but still leave
    most of the working day idle (a single 1-hour item followed by an empty
    day is exactly what made the day view hard to read). Doesn't invent
    brand-new active days -- only shrinks gaps within days already in use.
    Prefers deals left over from the target-capped candidate list; once
    those run out, falls back to deal-less busywork so idle-filling never
    overshoots the month's target."""
    used_deal_ids = {d["deal_id"] for d in decisions if d["deal_id"] is not None}
    leftover = [c for c in candidates if c["deal_id"] not in used_deal_ids]

    by_date: dict[date, list[dict]] = {}
    for decision in decisions:
        by_date.setdefault(decision["plan_date"], []).append(decision)
    if not by_date:
        return

    leftover_index = 0
    for plan_date, day_decisions in by_date.items():
        total_minutes = sum(
            _ACTIVITY_DURATION_MINUTES.get(d["activity_type"], 60) for d in day_decisions
        )
        # Each generic filler may appear at most once per day -- repeating the
        # exact same task title on one day looks like a bug, not a fuller
        # schedule, so a day stops filling once its unique options run out
        # rather than duplicating one.
        used_generic_today: set[int] = set()
        while total_minutes < _IDLE_FILL_TARGET_MINUTES and len(day_decisions) < _MAX_ITEMS_PER_DAY:
            if leftover_index < len(leftover):
                deal = leftover[leftover_index]
                leftover_index += 1
                activity_type = _FILLER_ACTIVITY_TYPES[len(day_decisions) % len(_FILLER_ACTIVITY_TYPES)]
                new_decision = {
                    "category": "task",
                    "activity_type": activity_type,
                    "deal_id": deal["deal_id"],
                    "title": None,
                    "plan_date": plan_date,
                    "priority": 5,
                    "rationale": (
                        f"{deal['customer_name']}は見込み {Decimal(deal['estimated_amount']):,.0f} 円・"
                        f"確度 {deal['win_probability']}% の商談があるため、空き時間を使って"
                        f"{activity_type}を進めます。"
                    ),
                }
                used_deal_ids.add(deal["deal_id"])
            else:
                available = [i for i in range(len(_GENERIC_FILLER_TASKS)) if i not in used_generic_today]
                if not available:
                    break
                generic_index = available[0]
                used_generic_today.add(generic_index)
                activity_type, title, rationale = _GENERIC_FILLER_TASKS[generic_index]
                new_decision = {
                    "category": "task",
                    "activity_type": activity_type,
                    "deal_id": None,
                    "title": title,
                    "plan_date": plan_date,
                    "priority": 5,
                    "rationale": rationale,
                }
            decisions.append(new_decision)
            day_decisions.append(new_decision)
            total_minutes += _ACTIVITY_DURATION_MINUTES.get(new_decision["activity_type"], 60)


def _assign_time_slots(decisions: list[dict]) -> None:
    """Mutate each decision in place, adding start_time/end_time: pack same-day
    activities back-to-back from 09:00 in priority order, skipping lunch."""
    by_date: dict[date, list[dict]] = {}
    for decision in decisions:
        by_date.setdefault(decision["plan_date"], []).append(decision)

    for day_decisions in by_date.values():
        day_decisions.sort(key=lambda d: d["priority"])
        cursor = _DAY_START_MINUTES
        for decision in day_decisions:
            if _LUNCH_START_MINUTES <= cursor < _LUNCH_END_MINUTES:
                cursor = _LUNCH_END_MINUTES
            duration = _ACTIVITY_DURATION_MINUTES.get(decision["activity_type"], 60)
            decision["start_time"] = _minutes_to_hhmm(cursor)
            cursor += duration
            decision["end_time"] = _minutes_to_hhmm(cursor)


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
        "select target_amount, target_deal_count from sales_target where rep_id = %s and target_month = %s",
        (rep_id, _month_to_date(target_month)),
    ).fetchone()
    target_amount = Decimal(sales_target["target_amount"]) if sales_target else None
    # all_candidates is already ranked by priority (deal_phase progress, then
    # stale/amount); cap it to the deals needed to land the plan in the
    # 100-120% achievement range instead of pulling in every open deal.
    candidates = _cap_candidates_to_target(all_candidates, target_amount)
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
                sales_target=sales_target,
            )
            used_ai = True
        except ai.AiPlanningError:
            decisions = _rule_based_plan_decisions(candidates, base, month)

    _fill_idle_days(decisions, candidates)
    _assign_time_slots(decisions)

    created: list[PlanOut] = []
    for decision in decisions:
        deal = candidates_by_id.get(decision["deal_id"]) if decision["deal_id"] is not None else None
        expected = Decimal(deal["estimated_amount"]) if deal else Decimal("0")
        probability = int(deal["win_probability"]) if deal else 0
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
        select target_amount
        from sales_target
        where rep_id = %s and target_month = %s
        """,
        (rep_id, _month_to_date(target_month)),
    ).fetchone()
    if not target:
        raise ValueError("target not found")

    # 1商談に複数のactivity_plan行(訪問+関連タスク等)が紐づき得るため、商談単位で
    # 1回だけ計上する。成約は実契約金額(未記録ならestimated_amount)、失注は0円、
    # 進行中は見込み金額×確度/100。
    stats = conn.execute(
        """
        with month_plans as (
          select plan_id, deal_id, expected_amount, plan_status
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
            end as amount
          from deal d
          join deal_result_status drs on drs.deal_result_status_id = d.deal_result_status_id
          where d.deal_id in (select deal_id from month_plans where deal_id is not null)
        )
        select
          coalesce((select sum(amount) from deal_amounts), 0)
            + coalesce((select sum(expected_amount) from month_plans where deal_id is null), 0)
            as expected_amount,
          (select count(*) from month_plans where plan_status = 'scheduled')::int as open_plan_count
        """,
        {"rep_id": rep_id, "target_month": target_month},
    ).fetchone()

    target_amount = Decimal(target["target_amount"])
    expected_amount = Decimal(stats["expected_amount"])
    ratio = float(expected_amount / target_amount) if target_amount > 0 else 0.0
    return {
        "rep_id": rep_id,
        "target_month": target_month,
        "target_amount": target_amount,
        "expected_amount": expected_amount,
        "attainment_ratio": ratio,
        "open_plan_count": stats["open_plan_count"],
    }
