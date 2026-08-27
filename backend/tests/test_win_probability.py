"""estimate_win_probability の各段階(顧客自身の実績 → 担当者×業界×カテゴリ×パターン
→ 同業界×同規模企業 → 担当者全体 → 固定値)が、それぞれ正しく使われることを検証する。

テスト用の商談・担当者・顧客はid 999000番台で作成し、各テストの最後で必ず
conn.rollback() する(commit は一切呼ばない)。既存のシードデータには触れない。
"""

from decimal import Decimal

from app.db import get_connection
from app.services import affinity

_BRANCH_ID = 1
_DEAL_PHASE_ID = 1
_PRODUCT_ID = 1
_CATEGORY_ID = 1


def _status_id(conn, status_code: str) -> int:
    return conn.execute(
        "select deal_result_status_id from deal_result_status where status_code = %s",
        (status_code,),
    ).fetchone()["deal_result_status_id"]


def _insert_customer(conn, customer_id: int, *, industry_id: int, company_size_id: int) -> None:
    conn.execute(
        """
        insert into customer (customer_id, customer_name, industry_id, company_size_id, location)
        values (%s, %s, %s, %s, %s)
        """,
        (customer_id, f"test customer {customer_id}", industry_id, company_size_id, "テスト県テスト市1-1-1"),
    )


def _insert_rep(conn, rep_id: int) -> None:
    conn.execute(
        "insert into sales_rep (rep_id, rep_name, branch_id) values (%s, %s, %s)",
        (rep_id, f"test rep {rep_id}", _BRANCH_ID),
    )


def _insert_deal(conn, deal_id: int, *, customer_id: int, rep_id: int, estimated_amount, status_code: str) -> None:
    contract_date = "2026-01-01" if status_code == "won" else None
    conn.execute(
        """
        insert into deal (
          deal_id, customer_id, rep_id, deal_phase_id, deal_result_status_id,
          product_id, estimated_amount, cost, win_probability, expected_visit_count,
          expected_effort_hours, deal_start_date, contract_date
        ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            deal_id, customer_id, rep_id, _DEAL_PHASE_ID, _status_id(conn, status_code),
            _PRODUCT_ID, estimated_amount, estimated_amount // 2, 50, 1,
            Decimal("1"), "2026-01-01", contract_date,
        ),
    )


def test_uses_customer_own_history_when_available():
    with get_connection() as conn:
        try:
            any_rep = conn.execute("select rep_id from sales_rep limit 1").fetchone()["rep_id"]
            _insert_customer(conn, 999001, industry_id=1, company_size_id=1)
            for index, status in enumerate(["won", "won", "won", "won", "lost"]):
                _insert_deal(
                    conn, 999100 + index,
                    customer_id=999001, rep_id=any_rep, estimated_amount=100000, status_code=status,
                )

            result = affinity.estimate_win_probability(
                conn, rep_id=any_rep, customer_id=999001, product_id=_PRODUCT_ID,
                estimated_amount=Decimal("100000"),
            )
            assert result == 80
        finally:
            conn.rollback()


def test_falls_back_to_rep_pattern_affinity_when_customer_is_new():
    with get_connection() as conn:
        try:
            _insert_rep(conn, 999002)
            _insert_customer(conn, 999002, industry_id=1, company_size_id=1)

            median = conn.execute(
                """
                select percentile_cont(0.5) within group (order by d.estimated_amount) as m
                from deal d
                join product p on p.product_id = d.product_id
                join product_subcategory ps on ps.subcategory_id = p.subcategory_id
                join deal_result_status drs on drs.deal_result_status_id = d.deal_result_status_id
                where drs.status_code in ('won', 'lost') and ps.category_id = %s
                """,
                (_CATEGORY_ID,),
            ).fetchone()["m"]
            small_amount = Decimal(median) / 2  # 中央値未満 = 小口
            pattern_id = conn.execute(
                "select pattern_id from deal_pattern where pattern_name = '新規開拓・小口'"
            ).fetchone()["pattern_id"]
            conn.execute(
                """
                insert into rep_affinity (
                  rep_id, industry_id, category_id, pattern_id,
                  deal_count, won_count, win_rate, avg_won_amount, affinity_score
                ) values (999002, 1, %s, %s, 10, 6, 0.6, 100000, 60000)
                """,
                (_CATEGORY_ID, pattern_id),
            )

            result = affinity.estimate_win_probability(
                conn, rep_id=999002, customer_id=999002, product_id=_PRODUCT_ID,
                estimated_amount=small_amount,
            )
            assert result == 60
        finally:
            conn.rollback()


def test_falls_back_to_industry_and_company_size_peers():
    with get_connection() as conn:
        try:
            _insert_rep(conn, 999003)
            _insert_customer(conn, 999003, industry_id=1, company_size_id=1)

            expected = conn.execute(
                """
                select round(
                  sum((drs.status_code = 'won')::int)::numeric
                    / nullif(count(*) filter (where drs.status_code in ('won', 'lost')), 0)
                  * 100
                ) as rate
                from deal d
                join customer c on c.customer_id = d.customer_id
                join deal_result_status drs on drs.deal_result_status_id = d.deal_result_status_id
                where c.industry_id = 1 and c.company_size_id = 1
                """
            ).fetchone()["rate"]

            result = affinity.estimate_win_probability(
                conn, rep_id=999003, customer_id=999003, product_id=_PRODUCT_ID,
                estimated_amount=Decimal("100000"),
            )
            assert result == int(expected)
        finally:
            conn.rollback()


def test_falls_back_to_rep_overall_then_to_fixed_default():
    with get_connection() as conn:
        try:
            _insert_rep(conn, 999004)
            _insert_customer(conn, 999004, industry_id=1, company_size_id=1)
            _insert_customer(conn, 999005, industry_id=2, company_size_id=1)

            # 同業界×同規模企業の実績を一時的に消し、tier1.5(似た企業)を発火させない
            # 状態を作る。conn.rollback()するので既存データは元に戻る。
            conn.execute(
                "delete from deal where customer_id in "
                "(select customer_id from customer where industry_id = 1 and company_size_id = 1)"
            )

            # 担当者自身にも実績が無い時点では固定値になる
            default_result = affinity.estimate_win_probability(
                conn, rep_id=999004, customer_id=999004, product_id=_PRODUCT_ID,
                estimated_amount=Decimal("100000"),
            )
            assert default_result == affinity._DEFAULT_WIN_PROBABILITY

            # 担当者自身の実績(対象顧客とは別の顧客との商談)を持たせるとそちらが使われる
            for index, status in enumerate(["won", "won", "won", "lost", "lost"]):
                _insert_deal(
                    conn, 999200 + index,
                    customer_id=999005, rep_id=999004, estimated_amount=100000, status_code=status,
                )
            rep_overall_result = affinity.estimate_win_probability(
                conn, rep_id=999004, customer_id=999004, product_id=_PRODUCT_ID,
                estimated_amount=Decimal("100000"),
            )
            assert rep_overall_result == 60
        finally:
            conn.rollback()
