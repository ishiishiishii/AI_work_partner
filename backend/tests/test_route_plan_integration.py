from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.db import get_connection
from app.config import settings
from app.schemas.route_plans import RoutePlanPreviewOut, RoutePlanPreviewRequest
from app.main import app
from app.services.route_optimization import (
    MatrixCell,
    RouteMatrixPartialError,
    RoutePlanningError,
)
from app.services.route_planning import (
    _candidate_rows,
    _prospect_candidates,
    approve_plan,
    create_preview,
)

TOKYO = ZoneInfo("Asia/Tokyo")
TEST_DATE = date(2099, 1, 15)


def test_route_preview_requires_bearer_authentication() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/route-plans/preview",
            json={"target_date": TEST_DATE.isoformat()},
        )
    assert response.status_code == 401


def test_prospect_candidates_estimate_required_visits_from_completed_history() -> None:
    with get_connection() as conn:
        rep = conn.execute(
            """
            select sr.rep_id, sr.branch_id, b.latitude, b.longitude
            from sales_rep sr
            join branch b on b.branch_id = sr.branch_id
            where exists (
              select 1
              from customer c
              join prefecture_branch pb
                on c.location like pb.prefecture_name || '%%'
               and pb.branch_id = sr.branch_id
              where c.primary_rep_id is null
                and c.geocoding_status = 'success'
                and c.geo_point is not null
                and not exists (
                  select 1 from deal d
                  where d.customer_id = c.customer_id and d.rep_id = sr.rep_id
                )
            )
            order by sr.rep_id
            limit 1
            """
        ).fetchone()
        assert rep
        prospects = _prospect_candidates(
            conn,
            rep_id=rep["rep_id"],
            branch_id=rep["branch_id"],
            target_date=TEST_DATE,
            radius_m=2_000_000,
            limit=20,
            origin_latitude=float(rep["latitude"]),
            origin_longitude=float(rep["longitude"]),
        )

    assert prospects
    assert all(candidate.customer_type == "new" for candidate in prospects)
    assert all(not candidate.deal_ids for candidate in prospects)
    assert all(candidate.required_visit_count >= 1 for candidate in prospects)
    assert all(candidate.visit_count_history_size > 0 for candidate in prospects)


def test_ongoing_candidate_remaining_visits_subtract_completed_results() -> None:
    result_id: int | None = None
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                select d.rep_id, sr.branch_id, d.deal_id, d.customer_id,
                       d.expected_visit_count, d.must_visit,
                       c.latitude, c.longitude
                from deal d
                join sales_rep sr on sr.rep_id = d.rep_id
                join deal_result_status s
                  on s.deal_result_status_id = d.deal_result_status_id
                 and s.status_code = 'ongoing'
                join customer c on c.customer_id = d.customer_id
                join prefecture_branch pb
                  on c.location like pb.prefecture_name || '%%'
                 and pb.branch_id = sr.branch_id
                where d.expected_visit_count >= 2
                  and c.geocoding_status = 'success'
                  and c.geo_point is not null
                order by d.deal_id
                limit 1
                """
            ).fetchone()
            assert row
            result_id = conn.execute(
                """
                insert into activity_result (
                  rep_id, result_date, customer_id, deal_id,
                  activity_type, outcome, outcome_note
                ) values (%s, %s, %s, %s, 'visit', 'progress', %s)
                returning result_id
                """,
                (
                    row["rep_id"], TEST_DATE - timedelta(days=1),
                    row["customer_id"], row["deal_id"],
                    "残り商談回数のテスト",
                ),
            ).fetchone()["result_id"]
            candidate_rows = _candidate_rows(
                conn,
                rep_id=row["rep_id"],
                branch_id=row["branch_id"],
                target_date=TEST_DATE,
                radius_m=1_000,
                limit=20,
                origin_latitude=float(row["latitude"]),
                origin_longitude=float(row["longitude"]),
                include_mandatory_anchors=False,
            )
            candidate = next(
                item for item in candidate_rows if item["deal_id"] == row["deal_id"]
            )
            assert candidate["completed_visit_count"] >= 1
            assert candidate["remaining_visit_count"] == max(
                candidate["required_visit_count"]
                - candidate["completed_visit_count"]
                - candidate["scheduled_visit_count"],
                1 if row["must_visit"] else 0,
            )
            conn.rollback()
            result_id = None
    finally:
        if result_id is not None:
            with get_connection() as conn:
                conn.execute(
                    "delete from activity_result where result_id = %s", (result_id,)
                )
                conn.commit()


def test_candidate_area_also_expands_around_mandatory_appointments() -> None:
    originals: list[dict] = []
    deal_originals: list[dict] = []
    try:
        with get_connection() as conn:
            rows = conn.execute(
                """
                select d.rep_id, sr.branch_id, d.deal_id, d.must_visit,
                       c.customer_id, c.latitude, c.longitude,
                       c.geocoding_status
                from deal d
                join sales_rep sr on sr.rep_id = d.rep_id
                join deal_result_status s
                  on s.deal_result_status_id = d.deal_result_status_id
                 and s.status_code = 'ongoing'
                join customer c on c.customer_id = d.customer_id
                join prefecture_branch pb
                  on c.location like pb.prefecture_name || '%%'
                 and pb.branch_id = sr.branch_id
                where not exists (
                  select 1 from activity_plan ap
                  where ap.rep_id = d.rep_id
                    and ap.plan_date = %s
                    and ap.deal_id = d.deal_id
                    and ap.plan_status = 'scheduled'
                )
                order by d.rep_id, c.customer_id, d.deal_id
                """,
                (TEST_DATE,),
            ).fetchall()
            pair: tuple[dict, dict] | None = None
            for first in rows:
                second = next(
                    (
                        row
                        for row in rows
                        if row["rep_id"] == first["rep_id"]
                        and row["customer_id"] != first["customer_id"]
                    ),
                    None,
                )
                if second is not None:
                    pair = (dict(first), dict(second))
                    break
            assert pair is not None
            mandatory, nearby = pair
            originals = [mandatory, nearby]
            deal_originals = [
                {"deal_id": row["deal_id"], "must_visit": row["must_visit"]}
                for row in originals
            ]

            conn.execute(
                """
                update customer
                set latitude = 35.000000, longitude = 139.000000,
                    geocoding_status = 'success'
                where customer_id = %s
                """,
                (mandatory["customer_id"],),
            )
            conn.execute(
                """
                update customer
                set latitude = 35.001000, longitude = 139.001000,
                    geocoding_status = 'success'
                where customer_id = %s
                """,
                (nearby["customer_id"],),
            )
            conn.execute(
                "update deal set must_visit = (deal_id = %s) where deal_id = any(%s)",
                (mandatory["deal_id"], [row["deal_id"] for row in originals]),
            )

            candidates = _candidate_rows(
                conn,
                rep_id=mandatory["rep_id"],
                branch_id=mandatory["branch_id"],
                target_date=TEST_DATE,
                radius_m=5_000,
                limit=20,
                origin_latitude=34.0,
                origin_longitude=138.0,
            )
            customer_ids = {row["customer_id"] for row in candidates}
            assert mandatory["customer_id"] in customer_ids
            assert nearby["customer_id"] in customer_ids

            fixed_area_candidates = _candidate_rows(
                conn,
                rep_id=mandatory["rep_id"],
                branch_id=mandatory["branch_id"],
                target_date=TEST_DATE,
                radius_m=5_000,
                limit=20,
                origin_latitude=34.0,
                origin_longitude=138.0,
                include_mandatory_anchors=False,
            )
            fixed_area_customer_ids = {
                row["customer_id"] for row in fixed_area_candidates
            }
            assert mandatory["customer_id"] in fixed_area_customer_ids
            assert nearby["customer_id"] not in fixed_area_customer_ids
    finally:
        if originals:
            with get_connection() as conn:
                for row in originals:
                    conn.execute(
                        """
                        update customer
                        set latitude = %s, longitude = %s, geocoding_status = %s
                        where customer_id = %s
                        """,
                        (
                            row["latitude"],
                            row["longitude"],
                            row["geocoding_status"],
                            row["customer_id"],
                        ),
                    )
                for row in deal_originals:
                    conn.execute(
                        "update deal set must_visit = %s where deal_id = %s",
                        (row["must_visit"], row["deal_id"]),
                    )
                conn.commit()


def _create_proposal(conn, *, rep_id: int, customer_id: int, deal_id: int) -> int:
    branch_id = conn.execute(
        "select branch_id from sales_rep where rep_id = %s", (rep_id,)
    ).fetchone()["branch_id"]
    plan_id = conn.execute(
        """
        insert into route_plan (
          rep_id, target_date, branch_id, status, policy, work_start, work_end,
          max_visits, weights, constraints, totals
        )
        values (%s, %s, %s, 'proposed', 'balanced', '09:00', '18:00', 5, %s, %s, %s)
        returning route_plan_id
        """,
        (
            rep_id,
            TEST_DATE,
            branch_id,
            Jsonb({}),
            Jsonb({"turnaround_buffer_min": 20}),
            Jsonb({}),
        ),
    ).fetchone()["route_plan_id"]
    option_id = conn.execute(
        """
        insert into route_plan_option (
          route_plan_id, rank, selected, cp_sat_status, routing_status,
          business_value, totals
        )
        values (%s, 1, true, 'optimal', 'feasible', 100, %s)
        returning option_id
        """,
        (plan_id, Jsonb({})),
    ).fetchone()["option_id"]
    conn.execute(
        """
        insert into route_plan_stop (
          route_plan_id, option_id, visit_order, customer_id, deal_ids,
          arrival_at, departure_at, visit_duration_min, leg_travel_min,
          leg_distance_m, economics
        )
        values (%s, %s, 1, %s, %s, %s, %s, 60, 10, 5000, %s)
        """,
        (
            plan_id,
            option_id,
            customer_id,
            [deal_id],
            datetime(2099, 1, 15, 9, 0, tzinfo=TOKYO),
            datetime(2099, 1, 15, 10, 0, tzinfo=TOKYO),
            Jsonb({"planned_sales": 100000, "expected_sales": 50000}),
        ),
    )
    conn.commit()
    return plan_id


@pytest.fixture
def owned_deal() -> tuple[int, int, int]:
    with get_connection() as conn:
        row = conn.execute(
            """
            select d.rep_id, d.customer_id, d.deal_id
            from deal d
            join deal_result_status s
              on s.deal_result_status_id = d.deal_result_status_id
            where s.status_code = 'ongoing'
            order by d.deal_id
            limit 1
            """
        ).fetchone()
    assert row
    return row["rep_id"], row["customer_id"], row["deal_id"]


def test_approval_is_transactional_and_idempotent(owned_deal: tuple[int, int, int]) -> None:
    rep_id, customer_id, deal_id = owned_deal
    plan_id: int | None = None
    activity_ids: list[int] = []
    try:
        with get_connection() as conn:
            plan_id = _create_proposal(
                conn, rep_id=rep_id, customer_id=customer_id, deal_id=deal_id
            )
            first = approve_plan(conn, plan_id=plan_id, rep_id=rep_id)
            activity_ids = first["activity_plan_ids"]
            second = approve_plan(conn, plan_id=plan_id, rep_id=rep_id)
            assert second["activity_plan_ids"] == activity_ids
            # 1 stop -> 移動 + 訪問 + 準備・記録 の3件
            assert len(activity_ids) == 3
            count = conn.execute(
                "select count(*)::int as count from activity_plan where plan_id = any(%s)",
                (activity_ids,),
            ).fetchone()["count"]
            assert count == 3
    finally:
        if plan_id is not None:
            with get_connection() as conn:
                if activity_ids:
                    conn.execute(
                        "delete from activity_plan where plan_id = any(%s)", (activity_ids,)
                    )
                conn.execute("delete from route_plan where route_plan_id = %s", (plan_id,))
                conn.commit()


def test_approval_conflict_rolls_back_without_partial_activity(
    owned_deal: tuple[int, int, int],
) -> None:
    rep_id, customer_id, deal_id = owned_deal
    plan_id: int | None = None
    blocker_id: int | None = None
    try:
        with get_connection() as conn:
            blocker_id = conn.execute(
                """
                insert into activity_plan (
                  rep_id, plan_date, start_time, end_time, category, title,
                  activity_type, plan_status, is_ai_generated
                )
                values (%s, %s, '09:30', '10:30', 'task', '競合テスト',
                        'task', 'scheduled', false)
                returning plan_id
                """,
                (rep_id, TEST_DATE),
            ).fetchone()["plan_id"]
            conn.commit()
            plan_id = _create_proposal(
                conn, rep_id=rep_id, customer_id=customer_id, deal_id=deal_id
            )
            with pytest.raises(RoutePlanningError) as error:
                approve_plan(conn, plan_id=plan_id, rep_id=rep_id)
            assert error.value.code == "schedule_conflict"
            linked = conn.execute(
                "select count(*)::int as count from route_plan_activity where route_plan_id = %s",
                (plan_id,),
            ).fetchone()["count"]
            assert linked == 0
            status = conn.execute(
                "select status from route_plan where route_plan_id = %s", (plan_id,)
            ).fetchone()["status"]
            assert status == "proposed"
    finally:
        with get_connection() as conn:
            if blocker_id is not None:
                conn.execute("delete from activity_plan where plan_id = %s", (blocker_id,))
            if plan_id is not None:
                conn.execute("delete from route_plan where route_plan_id = %s", (plan_id,))
            conn.commit()


def test_approval_rejects_second_visit_to_same_customer_on_same_day(
    owned_deal: tuple[int, int, int],
) -> None:
    rep_id, customer_id, deal_id = owned_deal
    plan_id: int | None = None
    existing_visit_id: int | None = None
    try:
        with get_connection() as conn:
            existing_visit_id = conn.execute(
                """
                insert into activity_plan (
                  rep_id, plan_date, start_time, end_time, category, title,
                  customer_id, deal_id, activity_type, plan_status, is_ai_generated
                )
                values (%s, %s, '15:00', '16:00', 'visit', '同日訪問テスト',
                        %s, %s, 'visit', 'scheduled', false)
                returning plan_id
                """,
                (rep_id, TEST_DATE, customer_id, deal_id),
            ).fetchone()["plan_id"]
            conn.commit()
            plan_id = _create_proposal(
                conn, rep_id=rep_id, customer_id=customer_id, deal_id=deal_id
            )

            with pytest.raises(RoutePlanningError) as error:
                approve_plan(conn, plan_id=plan_id, rep_id=rep_id)

            assert error.value.code == "duplicate_customer_visit"
            linked = conn.execute(
                "select count(*)::int as count from route_plan_activity where route_plan_id = %s",
                (plan_id,),
            ).fetchone()["count"]
            assert linked == 0
    finally:
        with get_connection() as conn:
            if existing_visit_id is not None:
                conn.execute(
                    "delete from activity_plan where plan_id = %s", (existing_visit_id,)
                )
            if plan_id is not None:
                conn.execute("delete from route_plan where route_plan_id = %s", (plan_id,))
            conn.commit()



class DeterministicMatrixProvider:
    def __init__(self) -> None:
        self.calls = 0

    def get_matrix(self, points, departure_at):
        del departure_at
        self.calls += 1
        if self.calls == 1:
            raise RouteMatrixPartialError({len(points) - 1})
        return [
            [
                MatrixCell(0, 0)
                if origin == destination
                else MatrixCell(
                    600 + abs(origin - destination) * 60,
                    4000 + abs(origin - destination) * 500,
                )
                for destination in range(len(points))
            ]
            for origin in range(len(points))
        ]


def test_full_preview_to_approval_flow_does_not_save_before_approval(monkeypatch) -> None:
    route_plan_id: int | None = None
    monkeypatch.setattr(settings, "route_portfolio_limit", 3)
    monkeypatch.setattr(settings, "route_solver_time_limit_sec", 1)
    activity_ids: list[int] = []
    originals: list[dict] = []
    rep_id: int | None = None
    try:
        with get_connection() as conn:
            rep = conn.execute(
                """
                select sr.rep_id, sr.branch_id, b.latitude, b.longitude
                from sales_rep sr
                join branch b on b.branch_id = sr.branch_id
                join deal d on d.rep_id = sr.rep_id
                join deal_result_status s
                  on s.deal_result_status_id = d.deal_result_status_id
                 and s.status_code = 'ongoing'
                join customer c on c.customer_id = d.customer_id
                join prefecture_branch pb
                  on c.location like pb.prefecture_name || '%%'
                 and pb.branch_id = sr.branch_id
                group by sr.rep_id, sr.branch_id, b.latitude, b.longitude
                having count(distinct c.customer_id) >= 3
                order by count(distinct c.customer_id) desc
                limit 1
                """
            ).fetchone()
            assert rep
            rep_id = rep["rep_id"]
            customer_rows = conn.execute(
                """
                select distinct on (c.customer_id)
                       c.customer_id, c.latitude, c.longitude, c.place_id,
                       c.geocoding_status, c.geocode_accuracy, c.geocoded_at
                from deal d
                join deal_result_status s
                  on s.deal_result_status_id = d.deal_result_status_id
                 and s.status_code = 'ongoing'
                join customer c on c.customer_id = d.customer_id
                join prefecture_branch pb
                  on c.location like pb.prefecture_name || '%%'
                 and pb.branch_id = %s
                where d.rep_id = %s
                order by c.customer_id
                limit 5
                """,
                (rep["branch_id"], rep_id),
            ).fetchall()
            originals = [dict(row) for row in customer_rows]
            assert len(originals) >= 3
            conn.execute(
                "delete from route_matrix_cache where departure_bucket = %s",
                (datetime(2099, 1, 15, 9, 0, tzinfo=TOKYO),),
            )
            for index, row in enumerate(originals):
                conn.execute(
                    """
                    update customer
                    set latitude = %s, longitude = %s,
                        geocoding_status = 'success',
                        geocode_accuracy = 'ROOFTOP',
                        geocoded_at = now()
                    where customer_id = %s
                    """,
                    (
                        Decimal(rep["latitude"]) + Decimal(index + 1) / Decimal("100"),
                        Decimal(rep["longitude"]) + Decimal(index + 1) / Decimal("100"),
                        row["customer_id"],
                    ),
                )
            conn.commit()
            before_count = conn.execute(
                """
                select count(*)::int as count from activity_plan
                where rep_id = %s and plan_date = %s and plan_status = 'scheduled'
                """,
                (rep_id, TEST_DATE),
            ).fetchone()["count"]
            preview = create_preview(
                conn,
                rep_id=rep_id,
                request=RoutePlanPreviewRequest(
                    target_date=TEST_DATE,
                    policy="balanced",
                    sales_weight_percent=70,
                    gross_profit_weight_percent=30,
                    max_visits=3,
                    work_start=time(9, 0),
                    work_end=time(18, 0),
                ),
                matrix_provider=DeterministicMatrixProvider(),
            )
            route_plan_id = preview["plan_id"]
            assert preview["status"] == "proposed"
            assert preview["search_area"]["kind"] == "auto"
            economic_weight = (
                preview["weights"]["sales"] + preview["weights"]["gross_profit"]
            )
            assert preview["weights"]["sales"] == round(economic_weight * 0.7)
            assert all(
                "salesperson_fit_score" in stop["economics"]
                for stop in preview["stops"]
            )
            RoutePlanPreviewOut.model_validate(preview)
            assert 1 <= len(preview["stops"]) <= 3
            assert 1 <= preview["solver"]["portfolio_count"] <= 10
            assert any(
                "道路経路を取得できない候補" in warning for warning in preview["warnings"]
            )
            after_preview_count = conn.execute(
                """
                select count(*)::int as count from activity_plan
                where rep_id = %s and plan_date = %s and plan_status = 'scheduled'
                """,
                (rep_id, TEST_DATE),
            ).fetchone()["count"]
            assert after_preview_count == before_count

            approved = approve_plan(conn, plan_id=route_plan_id, rep_id=rep_id)
            activity_ids = approved["activity_plan_ids"]
            # 各stopにつき 移動 + 訪問 + 準備・記録 の3件が作成される
            assert len(activity_ids) == len(preview["stops"]) * 3
            after_approval_count = conn.execute(
                """
                select count(*)::int as count from activity_plan
                where rep_id = %s and plan_date = %s and plan_status = 'scheduled'
                """,
                (rep_id, TEST_DATE),
            ).fetchone()["count"]
            assert after_approval_count == before_count + len(activity_ids)
    finally:
        with get_connection() as conn:
            if activity_ids:
                conn.execute(
                    "delete from activity_plan where plan_id = any(%s)", (activity_ids,)
                )
            if route_plan_id is not None:
                conn.execute(
                    "delete from route_plan where route_plan_id = %s", (route_plan_id,)
                )
            conn.execute(
                "delete from route_matrix_cache where departure_bucket = %s",
                (datetime(2099, 1, 15, 9, 0, tzinfo=TOKYO),),
            )
            for row in originals:
                conn.execute(
                    """
                    update customer
                    set latitude = %s, longitude = %s, place_id = %s,
                        geocoding_status = %s, geocode_accuracy = %s,
                        geocoded_at = %s
                    where customer_id = %s
                    """,
                    (
                        row["latitude"],
                        row["longitude"],
                        row["place_id"],
                        row["geocoding_status"],
                        row["geocode_accuracy"],
                        row["geocoded_at"],
                        row["customer_id"],
                    ),
                )
            conn.commit()
