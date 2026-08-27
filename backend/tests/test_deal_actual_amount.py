"""deal.actual_amount(実際の契約金額)まわりの検証。

成約(won)時にトリガーが estimated_amount から自動補完すること、未成約
(ongoing/lost)では actual_amount を持てないこと、update_deal での手動補正、
forecast() が actual_amount を estimated_amount より優先することを確認する。

テスト用の商談・担当者・顧客はid 999300番台で作成し、各テストの最後で必ず
conn.rollback() する(commit は一切呼ばない)。既存のシードデータには触れない。
"""

from datetime import date as _date
from decimal import Decimal

import pytest

from app.db import get_connection
from app.services import planning

_BRANCH_ID = 1
_DEAL_PHASE_ID = 1
_PRODUCT_ID = 1


def _status_id(conn, status_code: str) -> int:
    return conn.execute(
        "select deal_result_status_id from deal_result_status where status_code = %s",
        (status_code,),
    ).fetchone()["deal_result_status_id"]


def _insert_rep(conn, rep_id: int) -> None:
    conn.execute(
        "insert into sales_rep (rep_id, rep_name, branch_id) values (%s, %s, %s)",
        (rep_id, f"test rep {rep_id}", _BRANCH_ID),
    )


def _insert_customer(conn, customer_id: int) -> None:
    conn.execute(
        """
        insert into customer (customer_id, customer_name, industry_id, company_size_id, location)
        values (%s, %s, 1, 1, %s)
        """,
        (customer_id, f"test customer {customer_id}", "テスト県テスト市1-1-1"),
    )


def _insert_deal(
    conn,
    deal_id: int,
    *,
    customer_id: int,
    rep_id: int,
    estimated_amount: Decimal,
    status_code: str,
    actual_amount: Decimal | None = None,
) -> None:
    contract_date = "2026-01-01" if status_code == "won" else None
    conn.execute(
        """
        insert into deal (
          deal_id, customer_id, rep_id, deal_phase_id, deal_result_status_id,
          product_id, estimated_amount, cost, win_probability, expected_visit_count,
          expected_effort_hours, deal_start_date, contract_date, actual_amount
        ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            deal_id, customer_id, rep_id, _DEAL_PHASE_ID, _status_id(conn, status_code),
            _PRODUCT_ID, estimated_amount, estimated_amount // 2, 50, 1,
            Decimal("1"), "2026-01-01", contract_date, actual_amount,
        ),
    )


def test_won_deal_auto_fills_actual_amount_from_estimate():
    with get_connection() as conn:
        try:
            _insert_rep(conn, 999300)
            _insert_customer(conn, 999300)
            _insert_deal(
                conn, 999300, customer_id=999300, rep_id=999300,
                estimated_amount=Decimal("500000"), status_code="won",
            )
            row = conn.execute(
                "select estimated_amount, actual_amount from deal where deal_id = 999300"
            ).fetchone()
            assert row["actual_amount"] == row["estimated_amount"] == Decimal("500000")
        finally:
            conn.rollback()


def test_won_deal_keeps_explicit_actual_amount():
    with get_connection() as conn:
        try:
            _insert_rep(conn, 999301)
            _insert_customer(conn, 999301)
            _insert_deal(
                conn, 999301, customer_id=999301, rep_id=999301,
                estimated_amount=Decimal("500000"), status_code="won",
                actual_amount=Decimal("470000"),
            )
            row = conn.execute(
                "select estimated_amount, actual_amount from deal where deal_id = 999301"
            ).fetchone()
            assert row["estimated_amount"] == Decimal("500000")
            assert row["actual_amount"] == Decimal("470000")
        finally:
            conn.rollback()


def test_non_won_deal_rejects_actual_amount():
    with get_connection() as conn:
        try:
            _insert_rep(conn, 999302)
            _insert_customer(conn, 999302)
            with pytest.raises(Exception, match="actual_amount must be null"):
                _insert_deal(
                    conn, 999302, customer_id=999302, rep_id=999302,
                    estimated_amount=Decimal("500000"), status_code="ongoing",
                    actual_amount=Decimal("470000"),
                )
        finally:
            conn.rollback()


def test_update_deal_corrects_actual_amount_without_touching_estimate():
    # planning.update_deal は内部で conn.commit() するため(create_deal と同様)、
    # rollback() では後始末できない。他のテストと違い、必ず明示的に削除する。
    with get_connection() as conn:
        try:
            _insert_rep(conn, 999303)
            _insert_customer(conn, 999303)
            _insert_deal(
                conn, 999303, customer_id=999303, rep_id=999303,
                estimated_amount=Decimal("500000"), status_code="won",
            )
            conn.commit()

            planning.update_deal(
                conn,
                deal_id=999303,
                rep_id=999303,
                product_id=_PRODUCT_ID,
                deal_phase_id=_DEAL_PHASE_ID,
                estimated_amount=Decimal("500000"),
                expected_visit_count=1,
                expected_effort_hours=Decimal("1"),
                actual_amount=Decimal("470000"),
            )
            row = conn.execute(
                "select estimated_amount, actual_amount from deal where deal_id = 999303"
            ).fetchone()
            assert row["estimated_amount"] == Decimal("500000")
            assert row["actual_amount"] == Decimal("470000")

            # actual_amountを省略した更新では、既存の値を上書きしない(coalesce)
            planning.update_deal(
                conn,
                deal_id=999303,
                rep_id=999303,
                product_id=_PRODUCT_ID,
                deal_phase_id=_DEAL_PHASE_ID,
                estimated_amount=Decimal("500000"),
                expected_visit_count=2,
                expected_effort_hours=Decimal("1"),
            )
            row = conn.execute(
                "select actual_amount from deal where deal_id = 999303"
            ).fetchone()
            assert row["actual_amount"] == Decimal("470000")
        finally:
            conn.execute("delete from deal where deal_id = 999303")
            conn.execute("delete from customer where customer_id = 999303")
            conn.execute("delete from sales_rep where rep_id = 999303")
            conn.commit()


def test_undoing_a_won_result_clears_actual_amount():
    # create_result / delete_result はどちらも内部で conn.commit() するため、
    # update_deal のテストと同様に明示的な削除で後始末する。
    with get_connection() as conn:
        try:
            _insert_rep(conn, 999305)
            _insert_customer(conn, 999305)
            _insert_deal(
                conn, 999305, customer_id=999305, rep_id=999305,
                estimated_amount=Decimal("500000"), status_code="ongoing",
            )
            conn.commit()

            result = planning.create_result(
                conn, rep_id=999305, outcome="won", result_date=_date(2026, 1, 10),
                plan_id=None, customer_id=999305, deal_id=999305,
                activity_type="visit", outcome_note=None,
            )
            row = conn.execute(
                "select deal_result_status_id, actual_amount from deal where deal_id = 999305"
            ).fetchone()
            assert row["actual_amount"] == Decimal("500000")

            # 成約を取り消すと、ongoingに戻ると同時にactual_amountもクリアされる
            # (クリアしないと、次のUPDATEでトリガーの「非成約でactual_amountは
            # 必ずnull」という制約に違反して例外になる)
            planning.delete_result(conn, result_id=result["result_id"], rep_id=999305)
            row = conn.execute(
                "select deal_result_status_id, actual_amount, contract_date from deal where deal_id = 999305"
            ).fetchone()
            assert row["actual_amount"] is None
            assert row["contract_date"] is None
            assert row["deal_result_status_id"] == _status_id(conn, "ongoing")
        finally:
            conn.execute("delete from activity_result where deal_id = 999305")
            conn.execute("delete from deal where deal_id = 999305")
            conn.execute("delete from customer where customer_id = 999305")
            conn.execute("delete from sales_rep where rep_id = 999305")
            conn.commit()


def test_forecast_prefers_actual_amount_over_estimate_for_won_deals():
    with get_connection() as conn:
        try:
            _insert_rep(conn, 999304)
            _insert_customer(conn, 999304)
            _insert_deal(
                conn, 999304, customer_id=999304, rep_id=999304,
                estimated_amount=Decimal("500000"), status_code="won",
                actual_amount=Decimal("470000"),
            )
            conn.execute(
                "insert into sales_target (rep_id, target_month, target_amount) "
                "values (999304, '2026-01-01', 1000000)"
            )
            conn.execute(
                """
                insert into activity_plan (
                  rep_id, plan_date, category, title, customer_id, deal_id,
                  activity_type, priority, expected_amount, expected_probability,
                  plan_status, is_ai_generated
                ) values (999304, '2026-01-05', 'visit', 'test', 999304, 999304,
                          'visit', 1, 500000, 50, 'scheduled', false)
                """
            )

            result = planning.forecast(conn, rep_id=999304, target_month="2026-01")
            assert result["expected_amount"] == Decimal("470000")
        finally:
            conn.rollback()
