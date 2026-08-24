"""Recomputes rep_affinity from deal/customer/product data.

rep_affinity has no independent inputs of its own -- it is always rebuilt from
closed (won/lost) deals, so "recalculate" is delete-then-reinsert per rep
rather than an incremental update.
"""

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


def recalculate_rep_affinity(conn: Connection, rep_id: int | None = None) -> list[dict]:
    """Rebuild rep_affinity for one rep, or every rep when rep_id is None."""
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
