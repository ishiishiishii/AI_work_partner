from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_connection
from app.main import app
from app.schemas.route_plans import RoutePlanBatchPreviewOut, RoutePlanBatchPreviewRequest
from app.services.route_optimization import (
    DealEconomics,
    MatrixCell,
    RoutePlanningError,
    VisitCandidate,
)
from app.services.route_planning import (
    _allocate_target_amounts,
    _assign_target_customers_to_days,
    _business_days,
    _business_weeks,
    _expand_visit_occurrences,
    _select_target_customers,
    approve_plan,
    create_batch_preview,
)

TOKYO = ZoneInfo("Asia/Tokyo")
BATCH_START_DATE = date(2099, 3, 2)  # a Monday, far from any other test's dates


def test_batch_preview_requires_bearer_authentication() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/route-plans/batch-preview",
            json={"start_date": BATCH_START_DATE.isoformat(), "horizon": "week"},
        )
    assert response.status_code == 401


def test_business_days_week_horizon_gives_five_weekdays() -> None:
    days = _business_days(date(2026, 8, 26), "week")  # Wednesday
    assert len(days) == 5
    assert all(day.weekday() < 5 for day in days)
    assert days[0] == date(2026, 8, 26)


def test_business_days_skips_weekend_start() -> None:
    days = _business_days(date(2026, 8, 29), "week")  # Saturday
    assert days[0] == date(2026, 8, 31)  # rolls forward to Monday


def test_business_days_month_horizon_stops_at_month_end() -> None:
    days = _business_days(date(2026, 8, 20), "month")
    assert days[-1] == date(2026, 8, 31)
    assert all(day.weekday() < 5 for day in days)


def test_target_amount_is_allocated_exactly_across_weeks_and_days() -> None:
    days = _business_days(date(2026, 9, 1), "month")
    weeks = _business_weeks(days)
    weekly = _allocate_target_amounts(Decimal("10000003"), [len(week) for week in weeks])

    assert sum(weekly) == Decimal("10000003")
    daily = [
        amount
        for week, week_amount in zip(weeks, weekly)
        for amount in _allocate_target_amounts(week_amount, [1] * len(week))
    ]
    assert len(daily) == len(days)
    assert sum(daily) == Decimal("10000003")


def _candidate(customer_id: int, expected_sales: int, score: int) -> VisitCandidate:
    candidate = VisitCandidate(
        customer_id=customer_id,
        customer_name=f"顧客{customer_id}",
        latitude=35.0,
        longitude=139.0,
        deal_ids=[customer_id],
        phase_names=["提案"],
        economics=[
            DealEconomics(
                estimated_amount=Decimal(expected_sales),
                cost=Decimal("0"),
                win_probability=Decimal("100"),
            )
        ],
    )
    candidate.value_score = Decimal(score)
    return candidate


def test_month_customer_selection_stops_after_risk_buffer() -> None:
    selected = _select_target_customers(
        [
            _candidate(1, 600, 100),
            _candidate(2, 500, 90),
            _candidate(3, 400, 80),
        ],
        planning_target=Decimal("1000"),
        capacity=10,
    )

    assert [candidate.customer_id for candidate in selected] == [1, 2]
    assert sum(candidate.expected_sales for candidate in selected) == Decimal("1100")


def test_month_customer_selection_mixes_new_and_ongoing_and_consumes_visit_capacity() -> None:
    ongoing = _candidate(1, 800, 100)
    ongoing.customer_type = "ongoing"
    ongoing.remaining_visit_count = 2
    new = _candidate(2, 600, 90)
    new.customer_type = "new"
    new.required_visit_count = 3
    new.remaining_visit_count = 3

    selected = _select_target_customers(
        [ongoing, new],
        planning_target=Decimal("500"),
        capacity=5,
        max_visits_per_customer=5,
    )

    assert {candidate.customer_type for candidate in selected} == {"new", "ongoing"}
    assert sum(candidate.planned_visit_count for candidate in selected) == 5


def test_required_meetings_expand_to_distinct_days_without_double_counting_sales() -> None:
    candidate = _candidate(1, 1000, 100)
    candidate.remaining_visit_count = 3
    candidate.planned_visit_count = 3
    occurrences = _expand_visit_occurrences([candidate])
    business_days = _business_days(date(2026, 9, 1), "week")
    assigned = _assign_target_customers_to_days(
        occurrences,
        business_days=business_days,
        day_targets={day: Decimal("200") for day in business_days},
        max_visits=2,
    )

    assigned_dates = [
        day
        for day, day_candidates in assigned.items()
        if any(item.customer_id == candidate.customer_id for item in day_candidates)
    ]
    assert len(assigned_dates) == 3
    assert len(set(assigned_dates)) == 3
    assert [item.expected_sales for item in occurrences] == [
        Decimal("0"), Decimal("0"), Decimal("1000")
    ]
    assert all(
        item.opportunity_expected_sales == Decimal("1000")
        for item in occurrences
    )
    assert sum(item.expected_sales for item in occurrences) == Decimal("1000")


class _AlwaysSucceedsMatrixProvider:
    def get_matrix(self, points, departure_at):
        del departure_at
        size = len(points)
        return [
            [
                MatrixCell(0, 0)
                if origin == destination
                else MatrixCell(
                    600 + abs(origin - destination) * 60,
                    4000 + abs(origin - destination) * 500,
                )
                for destination in range(size)
            ]
            for origin in range(size)
        ]


def test_batch_preview_details_near_days_and_estimates_the_rest(monkeypatch) -> None:
    monkeypatch.setattr(settings, "route_portfolio_limit", 2)
    monkeypatch.setattr(settings, "route_solver_time_limit_sec", 1)
    batch_id: int | None = None
    activity_ids: list[int] = []
    originals: list[dict] = []
    rep_id: int | None = None
    target_created = False
    blocking_plan_id: int | None = None
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
                having count(distinct c.customer_id) >= 5
                order by count(distinct c.customer_id) desc
                limit 1
                """
            ).fetchone()
            assert rep
            rep_id = rep["rep_id"]
            conn.execute(
                """
                insert into sales_target (rep_id, target_month, target_amount)
                values (%s, %s, %s)
                """,
                (rep_id, date(2099, 3, 1), Decimal("1000000")),
            )
            target_created = True
            blocking_plan_id = conn.execute(
                """
                insert into activity_plan (
                  rep_id, plan_date, start_time, end_time, category, title,
                  activity_type, plan_status, is_ai_generated
                )
                values (%s, %s, '10:00', '10:30', 'task', %s,
                        '電話', 'scheduled', false)
                returning plan_id
                """,
                (rep_id, BATCH_START_DATE, "ルート計画の時刻型テスト"),
            ).fetchone()["plan_id"]
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
                limit 6
                """,
                (rep["branch_id"], rep_id),
            ).fetchall()
            originals = [dict(row) for row in customer_rows]
            assert len(originals) >= 5
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

            preview = create_batch_preview(
                conn,
                rep_id=rep_id,
                request=RoutePlanBatchPreviewRequest(
                    start_date=BATCH_START_DATE,
                    horizon="week",
                    detailed_days=1,
                    policy="balanced",
                    max_visits=2,
                    work_start=time(9, 0),
                    work_end=time(18, 0),
                ),
                matrix_provider=_AlwaysSucceedsMatrixProvider(),
            )
            batch_id = preview["batch_id"]
            RoutePlanBatchPreviewOut.model_validate(preview)

            business_days = _business_days(BATCH_START_DATE, "week")
            assert [d["target_date"] for d in preview["days"]] == business_days
            assert [
                day["target_date"]
                for week in preview["weeks"]
                for day in week["days"]
            ] == business_days
            assert sum(
                (week["target_amount"] for week in preview["weeks"]),
                Decimal("0"),
            ) == (preview["planning_target_amount"] or Decimal("0"))
            assert preview["monthly_target_amount"] == Decimal("1000000")
            assert preview["remaining_target_amount"] == Decimal("1000000")
            assert sum(
                (day["target_amount"] for day in preview["days"]),
                Decimal("0"),
            ) == preview["planning_target_amount"]
            assert preview["detailed_days"] == 1

            detailed_day = preview["days"][0]
            coarse_days = preview["days"][1:]
            assert detailed_day["detail_level"] == "detailed"
            assert all(day["detail_level"] == "coarse" for day in coarse_days)

            # A coarse day's stops (if any were assigned) must be flagged as
            # estimates, never presented with the same confidence as a routed stop.
            for day in coarse_days:
                for stop in day["stops"]:
                    assert stop["estimated"] is True

            db_detail_levels = conn.execute(
                "select detail_level from route_plan where batch_id = %s order by target_date",
                (batch_id,),
            ).fetchall()
            assert [row["detail_level"] for row in db_detail_levels] == [
                d["detail_level"] for d in preview["days"] if d["plan_id"] is not None
            ]

            # Approving a coarse day must be refused -- no routed order/time exists yet.
            coarse_with_plan = next(
                (day for day in coarse_days if day["plan_id"] is not None), None
            )
            if coarse_with_plan is not None:
                try:
                    approve_plan(conn, plan_id=coarse_with_plan["plan_id"], rep_id=rep_id)
                    raise AssertionError("coarse plan approval should have been rejected")
                except RoutePlanningError as error:
                    assert error.code == "coarse_plan_not_approvable"

            # The detailed day behaves like a normal single-day plan: approvable,
            # and only then does activity_plan gain rows.
            if detailed_day["plan_id"] is not None:
                before_count = conn.execute(
                    "select count(*)::int as count from activity_plan where rep_id = %s",
                    (rep_id,),
                ).fetchone()["count"]
                approved = approve_plan(
                    conn, plan_id=detailed_day["plan_id"], rep_id=rep_id
                )
                activity_ids = approved["activity_plan_ids"]
                after_count = conn.execute(
                    "select count(*)::int as count from activity_plan where rep_id = %s",
                    (rep_id,),
                ).fetchone()["count"]
                assert after_count == before_count + len(activity_ids)
    finally:
        with get_connection() as conn:
            if activity_ids:
                conn.execute(
                    "delete from activity_plan where plan_id = any(%s)", (activity_ids,)
                )
            if blocking_plan_id is not None:
                conn.execute(
                    "delete from activity_plan where plan_id = %s", (blocking_plan_id,)
                )
            if batch_id is not None:
                conn.execute(
                    "delete from route_plan_batch where batch_id = %s", (batch_id,)
                )
            if target_created and rep_id is not None:
                conn.execute(
                    "delete from sales_target where rep_id = %s and target_month = %s",
                    (rep_id, date(2099, 3, 1)),
                )
            conn.execute(
                "delete from route_matrix_cache where departure_bucket = %s",
                (datetime.combine(BATCH_START_DATE, time(9, 0), TOKYO),),
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
