"""Recomputes rep_affinity from deal/customer/product data.

rep_affinity has no independent inputs of its own -- it is always rebuilt from
closed (won/lost) deals, so "recalculate" is delete-then-reinsert per rep
rather than an incremental update.
"""

from decimal import Decimal

from psycopg import Connection

# category_median is computed across ALL reps' closed deals so "大型/小口" is a
# stable, comparable threshold rather than relative to one rep's own history.
#
# company_deal_seq ranks a customer's deals across the WHOLE company (every rep,
# every status), so "新規開拓" means the company's first-ever contact with that
# customer -- not just this rep's first deal with them.
_AFFINITY_QUERY = """
with company_deal_seq as (
  select deal_id, customer_id,
         row_number() over (
           partition by customer_id
           order by deal_start_date, deal_id
         ) as customer_deal_seq
  from deal
),
category_median as (
  select ps.category_id,
         percentile_cont(0.5) within group (order by d.estimated_amount) as median_amount
  from deal d
  join product p on p.product_id = d.product_id
  join product_subcategory ps on ps.subcategory_id = p.subcategory_id
  join deal_result_status drs on drs.deal_result_status_id = d.deal_result_status_id
  where drs.status_code in ('won', 'lost')
  group by ps.category_id
),
rep_deals as (
  select
    d.rep_id,
    c.industry_id,
    ps.category_id,
    d.estimated_amount,
    (drs.status_code = 'won') as is_won,
    cds.customer_deal_seq
  from deal d
  join customer c on c.customer_id = d.customer_id
  join product p on p.product_id = d.product_id
  join product_subcategory ps on ps.subcategory_id = p.subcategory_id
  join deal_result_status drs on drs.deal_result_status_id = d.deal_result_status_id
  join company_deal_seq cds on cds.deal_id = d.deal_id
  where drs.status_code in ('won', 'lost')
    and (%(rep_id)s::int is null or d.rep_id = %(rep_id)s)
),
classified as (
  select
    rd.rep_id,
    rd.industry_id,
    rd.category_id,
    (case when rd.customer_deal_seq = 1 then '新規開拓' else '既存深耕' end || '・' ||
     case when rd.estimated_amount >= cm.median_amount then '大型' else '小口' end) as pattern_name,
    rd.estimated_amount,
    rd.is_won
  from rep_deals rd
  join category_median cm on cm.category_id = rd.category_id
)
select
  classified.rep_id,
  classified.industry_id,
  classified.category_id,
  dp.pattern_id,
  count(*)::int as deal_count,
  sum(classified.is_won::int)::int as won_count,
  round(sum(classified.is_won::int)::numeric / count(*), 4) as win_rate,
  coalesce(avg(classified.estimated_amount) filter (where classified.is_won), 0) as avg_won_amount,
  round(
    (sum(classified.is_won::int)::numeric / count(*))
    * coalesce(avg(classified.estimated_amount) filter (where classified.is_won), 0),
    2
  ) as affinity_score
from classified
join deal_pattern dp on dp.pattern_name = classified.pattern_name
group by classified.rep_id, classified.industry_id, classified.category_id, dp.pattern_id
"""


# estimate_win_probability の Tier0 と同じ集計を、顧客詳細ページの表示用に切り出したもの。
def customer_win_rate_summary(conn: Connection, customer_id: int) -> dict:
    row = conn.execute(
        """
        select
          count(*) filter (where drs.status_code in ('won', 'lost'))::int as closed_count,
          sum((drs.status_code = 'won')::int)::int as won_count
        from deal d
        join deal_result_status drs on drs.deal_result_status_id = d.deal_result_status_id
        where d.customer_id = %s
        """,
        (customer_id,),
    ).fetchone()
    closed_count = row["closed_count"]
    won_count = row["won_count"] or 0
    win_rate = round(won_count / closed_count * 100) if closed_count > 0 else None
    return {"customer_id": customer_id, "closed_count": closed_count, "won_count": won_count, "win_rate": win_rate}


def list_rep_affinity(conn: Connection, rep_id: int) -> list[dict]:
    rows = conn.execute(
        """
        select rep_id, rep_name, industry_name, category_name, pattern_name,
               deal_count, won_count, win_rate, avg_won_amount, affinity_score, calculated_at
        from ai.rep_affinity
        where rep_id = %s
        order by affinity_score desc
        """,
        (rep_id,),
    ).fetchall()
    return list(rows)



# Arbitrary constant key for a transaction-scoped advisory lock (auto-released on
# commit/rollback). Two callers rebuilding the same rep's rows concurrently (e.g. the
# dashboard and the affinity page both recalculating on load) would otherwise both see
# the pre-delete rows, both delete them, then race to re-insert the same primary keys --
# the loser gets a UniqueViolation once the winner commits. Serializing the whole
# delete+insert body behind this lock makes concurrent calls queue instead of racing.
_RECALCULATE_LOCK_KEY = 872346123


# 成約確率の自動算出。顧客自身の実績(Tier0) → 担当者×業界×カテゴリ×パターンの実績
# (Tier1) → 同業界×同規模企業の実績(Tier1.5) → 担当者全体の実績(Tier2) → 固定値(Tier3)
# の順にフォールバックする。Tier0を担当者×顧客ではなく顧客単位にしているのは、
# 担当者×顧客だと実績3件以上の組が全体の1.4%しかなく実用に耐えないため。
_DEFAULT_WIN_PROBABILITY = 30

_WIN_PROBABILITY_QUERY = """
with tier0 as (
  select
    sum((drs.status_code = 'won')::int)::numeric
      / nullif(count(*) filter (where drs.status_code in ('won', 'lost')), 0) as win_rate
  from deal d
  join deal_result_status drs on drs.deal_result_status_id = d.deal_result_status_id
  where d.customer_id = %(customer_id)s
    and (%(deal_id)s::int is null or d.deal_id != %(deal_id)s)
),
category_median as (
  select ps.category_id,
         percentile_cont(0.5) within group (order by d.estimated_amount) as median_amount
  from deal d
  join product p on p.product_id = d.product_id
  join product_subcategory ps on ps.subcategory_id = p.subcategory_id
  join deal_result_status drs on drs.deal_result_status_id = d.deal_result_status_id
  where drs.status_code in ('won', 'lost')
  group by ps.category_id
),
target as (
  select
    c.industry_id as industry_id,
    c.company_size_id as company_size_id,
    ps.category_id as category_id,
    (case when not exists (
        select 1 from deal d2
        where d2.customer_id = %(customer_id)s
          and (%(deal_id)s::int is null or d2.deal_id != %(deal_id)s)
      ) then '新規開拓' else '既存深耕' end
     || '・' ||
     case when %(estimated_amount)s >= coalesce(cm.median_amount, %(estimated_amount)s)
          then '大型' else '小口' end
    ) as pattern_name
  from product p
  join product_subcategory ps on ps.subcategory_id = p.subcategory_id
  cross join customer c
  left join category_median cm on cm.category_id = ps.category_id
  where p.product_id = %(product_id)s and c.customer_id = %(customer_id)s
),
tier1 as (
  select ra.win_rate
  from rep_affinity ra
  join target t on t.industry_id = ra.industry_id and t.category_id = ra.category_id
  join deal_pattern dp on dp.pattern_id = ra.pattern_id and dp.pattern_name = t.pattern_name
  where ra.rep_id = %(rep_id)s
),
tier1_5 as (
  select
    sum((drs.status_code = 'won')::int)::numeric
      / nullif(count(*) filter (where drs.status_code in ('won', 'lost')), 0) as win_rate
  from deal d
  join customer c2 on c2.customer_id = d.customer_id
  join deal_result_status drs on drs.deal_result_status_id = d.deal_result_status_id
  join target t on t.industry_id = c2.industry_id and t.company_size_id = c2.company_size_id
  where (%(deal_id)s::int is null or d.deal_id != %(deal_id)s)
),
tier2 as (
  select
    sum((drs.status_code = 'won')::int)::numeric
      / nullif(count(*) filter (where drs.status_code in ('won', 'lost')), 0) as win_rate
  from deal d
  join deal_result_status drs on drs.deal_result_status_id = d.deal_result_status_id
  where d.rep_id = %(rep_id)s
    and (%(deal_id)s::int is null or d.deal_id != %(deal_id)s)
)
select round(coalesce(
  (select win_rate from tier0),
  (select win_rate from tier1),
  (select win_rate from tier1_5),
  (select win_rate from tier2),
  %(default_win_rate)s
) * 100)::int as win_probability
"""


def estimate_win_probability(
    conn: Connection,
    *,
    rep_id: int,
    customer_id: int,
    product_id: int,
    estimated_amount: Decimal,
    deal_id: int | None = None,
) -> int:
    row = conn.execute(
        _WIN_PROBABILITY_QUERY,
        {
            "rep_id": rep_id,
            "customer_id": customer_id,
            "product_id": product_id,
            "estimated_amount": estimated_amount,
            "deal_id": deal_id,
            "default_win_rate": _DEFAULT_WIN_PROBABILITY / 100,
        },
    ).fetchone()
    return row["win_probability"]


def recalculate_rep_affinity(conn: Connection, rep_id: int | None = None) -> list[dict]:
    """Rebuild rep_affinity for one rep, or every rep when rep_id is None."""
    conn.execute("select pg_advisory_xact_lock(%s)", (_RECALCULATE_LOCK_KEY,)).fetchone()

    rows = conn.execute(_AFFINITY_QUERY, {"rep_id": rep_id}).fetchall()

    if rep_id is not None:
        conn.execute("delete from rep_affinity where rep_id = %s", (rep_id,))
    else:
        conn.execute("delete from rep_affinity")

    for row in rows:
        conn.execute(
            """
            insert into rep_affinity (
              rep_id, industry_id, category_id, pattern_id,
              deal_count, won_count, win_rate, avg_won_amount, affinity_score
            )
            values (%(rep_id)s, %(industry_id)s, %(category_id)s, %(pattern_id)s,
                    %(deal_count)s, %(won_count)s, %(win_rate)s, %(avg_won_amount)s,
                    %(affinity_score)s)
            """,
            row,
        )
    conn.commit()

    # Re-read through the AI view so the response carries resolved names
    # (rep/industry/category/pattern) rather than the raw ids just inserted.
    if rep_id is not None:
        result = conn.execute(
            """
            select rep_id, rep_name, industry_name, category_name, pattern_name,
                   deal_count, won_count, win_rate, avg_won_amount, affinity_score, calculated_at
            from ai.rep_affinity
            where rep_id = %s
            order by affinity_score desc
            """,
            (rep_id,),
        ).fetchall()
    else:
        result = conn.execute(
            """
            select rep_id, rep_name, industry_name, category_name, pattern_name,
                   deal_count, won_count, win_rate, avg_won_amount, affinity_score, calculated_at
            from ai.rep_affinity
            order by rep_id, affinity_score desc
            """
        ).fetchall()
    return list(result)
