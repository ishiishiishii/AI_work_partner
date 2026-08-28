from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_connection
from app.main import app
from app.schemas.route_plans import RoutePlanBatchPreviewOut, RoutePlanBatchPreviewRequest
from app.services import ai
from app.services.route_optimization import (
    DealEconomics,
    MatrixCell,
    RoutePlanningError,
    VisitCandidate,
)
from app.services.route_planning import (
    DEFAULT_MIN_REVISIT_GAP_BUSINESS_DAYS,
    _allocate_target_amounts,
    _apply_unreachable_day_revision,
    _period_deferred_day_result,
    _apply_target_gap_fill_assignments,
    _apply_schedule_adjustments,
    _assign_target_customers_to_days,
    _business_days,
    _business_weeks,
    _cluster_candidates_by_region,
    _expand_visit_occurrences,
    _apply_monthly_ai_selection,
    _monthly_ai_candidate_options,
    _monthly_target_context,
    _round_trip_matrix,
    _schedule_adjustment_context,
    _select_target_customers,
    _target_gap_fill_options,
    _target_gap_fill_ai_payload,
    _target_gap_improved,
    _target_gap_shortfalls,
    _unreachable_day_ai_payload,
    _unreachable_day_revision_options,
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


def test_monthly_target_context_counts_only_contracts_before_plan_start() -> None:
    class _Result:
        @staticmethod
        def fetchone() -> dict:
            return {
                "target_amount": Decimal("40000000"),
                "target_gross_profit": Decimal("10000000"),
                "achieved": Decimal("0"),
                "achieved_profit": Decimal("0"),
            }

    class _Connection:
        query = ""
        params: tuple = ()

        def execute(self, query: str, params: tuple) -> _Result:
            self.query = query
            self.params = params
            return _Result()

    conn = _Connection()
    month_start = date(2026, 9, 1)

    context = _monthly_target_context(conn, rep_id=10, target_date=month_start)

    assert "d.contract_date < %s::date" in conn.query
    assert "coalesce(d.actual_amount, d.estimated_amount)" in conn.query
    assert conn.params == (month_start, 10, month_start)
    assert context["achieved_amount"] == Decimal("0")
    assert context["achieved_gross_profit"] == Decimal("0")
    assert context["remaining_target_amount"] == Decimal("40000000")
    assert context["remaining_target_gross_profit"] == Decimal("10000000")


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
            _candidate(4, 300, 70),
        ],
        planning_target=Decimal("1000"),
        capacity=10,
    )

    # 1+2+3 = 1500, already >= target*1.20 (1200), so 4 is excluded.
    assert [candidate.customer_id for candidate in selected] == [1, 2, 3]
    assert sum(candidate.expected_sales for candidate in selected) == Decimal("1500")


def test_month_customer_selection_keeps_prospecting_share_before_stopping() -> None:
    ongoing_a = _candidate(1, 700, 100)
    ongoing_b = _candidate(2, 700, 90)
    new = _candidate(3, 100, 20)
    new.customer_type = "new"

    selected = _select_target_customers(
        [ongoing_a, ongoing_b, new],
        planning_target=Decimal("1000"),
        capacity=10,
    )

    assert {candidate.customer_id for candidate in selected} == {1, 2, 3}
    new_visits = sum(
        candidate.planned_visit_count
        for candidate in selected
        if candidate.customer_type == "new"
    )
    total_visits = sum(candidate.planned_visit_count for candidate in selected)
    assert Decimal(new_visits) / Decimal(total_visits) >= Decimal("0.30")


def test_month_customer_selection_requires_sales_and_profit_safety_margin() -> None:
    high_sales_low_profit = _candidate(1, 1500, 100)
    high_sales_low_profit.economics = [
        DealEconomics(
            estimated_amount=Decimal("1500"),
            cost=Decimal("1400"),
            win_probability=Decimal("100"),
        )
    ]
    profit_fill = _candidate(2, 1000, 90)

    selected = _select_target_customers(
        [high_sales_low_profit, profit_fill],
        planning_target=Decimal("1000"),
        planning_target_gross_profit=Decimal("800"),
        capacity=10,
    )

    assert [candidate.customer_id for candidate in selected] == [1, 2]
    assert sum(
        candidate.expected_gross_profit or Decimal("0") for candidate in selected
    ) >= Decimal("960")


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


def test_monthly_ai_selection_can_improve_baseline_but_keeps_safety_seeds() -> None:
    mandatory = _candidate(1, 1000, 100)
    mandatory.must_visit = True
    new = _candidate(2, 500, 60)
    new.customer_type = "new"
    baseline_optional = _candidate(3, 700, 70)
    ai_replacement = _candidate(4, 900, 90)
    baseline = [mandatory, new, baseline_optional]

    options = _monthly_ai_candidate_options(
        [mandatory, new, baseline_optional, ai_replacement], baseline, limit=4
    )
    selected, reasons, preferred_weeks, applied = _apply_monthly_ai_selection(
        options,
        baseline,
        [
            {"customer_id": 1, "preferred_week": 1, "reason": "期限が近い"},
            {"customer_id": 4, "preferred_week": 2, "reason": "売上と粗利が高い"},
        ],
        capacity=3,
        planning_target=Decimal("2000"),
        planning_target_gross_profit=Decimal("1500"),
        max_visits_per_customer=5,
    )

    assert {candidate.customer_id for candidate in selected} == {1, 2, 4}
    assert mandatory in selected
    assert new in selected
    assert sum(candidate.expected_sales for candidate in selected) == Decimal("2400")
    assert reasons == {1: "期限が近い", 4: "売上と粗利が高い"}
    assert preferred_weeks == {1: 1, 4: 2}
    assert applied is True


def test_monthly_ai_selection_falls_back_when_monthly_coverage_drops() -> None:
    mandatory = _candidate(1, 1000, 100)
    mandatory.must_visit = True
    new = _candidate(2, 500, 60)
    new.customer_type = "new"
    high_value = _candidate(3, 2000, 90)
    low_value = _candidate(4, 100, 20)
    baseline = [mandatory, new, high_value]

    selected, reasons, preferred_weeks, applied = _apply_monthly_ai_selection(
        [mandatory, new, high_value, low_value],
        baseline,
        [{"customer_id": 4, "preferred_week": 1, "reason": "根拠が弱い提案"}],
        capacity=3,
        planning_target=Decimal("3000"),
        planning_target_gross_profit=Decimal("2500"),
        max_visits_per_customer=5,
    )

    assert selected == baseline
    assert reasons == {}
    assert preferred_weeks == {}
    assert applied is False


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


def test_required_meetings_are_spaced_by_the_minimum_gap_when_the_horizon_allows_it() -> None:
    candidate = _candidate(1, 1000, 100)
    candidate.remaining_visit_count = 3
    candidate.planned_visit_count = 3
    occurrences = _expand_visit_occurrences([candidate])
    business_days = _business_days(date(2026, 9, 1), "month")  # ~21 business days

    assigned = _assign_target_customers_to_days(
        occurrences,
        business_days=business_days,
        day_targets={day: Decimal("200") for day in business_days},
        max_visits=2,
    )

    assigned_dates = sorted(
        day
        for day, day_candidates in assigned.items()
        if any(item.customer_id == candidate.customer_id for item in day_candidates)
    )
    assert len(assigned_dates) == 3
    day_index = {day: index for index, day in enumerate(business_days)}
    gaps = [day_index[b] - day_index[a] for a, b in zip(assigned_dates, assigned_dates[1:])]
    assert all(gap >= DEFAULT_MIN_REVISIT_GAP_BUSINESS_DAYS for gap in gaps)


def test_required_meetings_relax_the_gap_rather_than_drop_a_visit_when_horizon_is_short() -> None:
    # 4 meetings in a 5-business-day week cannot all be >=3 business days
    # apart -- the visit must still be scheduled somewhere, never dropped.
    candidate = _candidate(1, 1000, 100)
    candidate.remaining_visit_count = 4
    candidate.planned_visit_count = 4
    occurrences = _expand_visit_occurrences([candidate])
    business_days = _business_days(date(2026, 9, 1), "week")

    assigned = _assign_target_customers_to_days(
        occurrences,
        business_days=business_days,
        day_targets={day: Decimal("200") for day in business_days},
        max_visits=1,
    )

    assigned_dates = [
        day
        for day, day_candidates in assigned.items()
        if any(item.customer_id == candidate.customer_id for item in day_candidates)
    ]
    assert len(assigned_dates) == 4
    assert len(set(assigned_dates)) == 4


def test_daily_cadence_takes_priority_over_monthly_ai_preferred_week() -> None:
    candidate = _candidate(1, 1000, 100)
    business_days = _business_days(date(2026, 9, 1), "month")
    business_weeks = _business_weeks(business_days)
    week_number_by_day = {
        day: week_number
        for week_number, week_days in enumerate(business_weeks, start=1)
        for day in week_days
    }

    assigned = _assign_target_customers_to_days(
        [candidate],
        business_days=business_days,
        day_targets={day: Decimal("200") for day in business_days},
        max_visits=2,
        week_number_by_day=week_number_by_day,
        preferred_week_by_customer={candidate.customer_id: 2},
    )

    assigned_day = next(day for day, values in assigned.items() if candidate in values)
    # A preferred week is a soft tie-break. The operational requirement to
    # build an adoptable cadence from the earliest business day wins first.
    assert assigned_day == business_days[0]


def test_apply_schedule_adjustments_moves_only_validated_suggestions() -> None:
    business_days = _business_days(date(2026, 9, 1), "week")
    a = _candidate(1, 1000, 100)
    a.visit_sequence = 1
    b = _candidate(2, 500, 90)
    b.visit_sequence = 1
    day_pools = {day: [] for day in business_days}
    day_pools[business_days[0]] = [a]
    day_pools[business_days[1]] = [b]

    context = _schedule_adjustment_context(
        day_pools,
        business_days=business_days,
        max_visits=1,
        min_gap_business_days=1,
        today=business_days[0],
    )
    # Neither candidate has risk or a next_action note, so nothing is flagged
    # for adjustment -- the LLM is never even asked about them.
    assert context == []

    # Manually construct a context entry as if a's occurrence had a signal,
    # to test the validation/application logic in isolation from risk rules.
    fake_context = [
        {
            "customer_id": a.customer_id,
            "visit_sequence": a.visit_sequence,
            "current_date": business_days[0],
            "eligible_dates": [business_days[2], business_days[3]],
        }
    ]

    # A valid suggestion (date is in eligible_dates) is applied.
    updated_pools, reasons = _apply_schedule_adjustments(
        day_pools,
        [
            {
                "customer_id": a.customer_id,
                "visit_sequence": a.visit_sequence,
                "new_date": business_days[2].isoformat(),
                "reason": "見積回答待ちのため後ろ倒し",
            }
        ],
        fake_context,
        max_visits=1,
    )
    assert a not in updated_pools[business_days[0]]
    assert a in updated_pools[business_days[2]]
    assert reasons[(business_days[2], a.customer_id)] == "見積回答待ちのため後ろ倒し"

    # An out-of-range date (not in eligible_dates) is ignored entirely.
    unchanged_pools, unchanged_reasons = _apply_schedule_adjustments(
        day_pools,
        [
            {
                "customer_id": a.customer_id,
                "visit_sequence": a.visit_sequence,
                "new_date": business_days[4].isoformat(),
                "reason": "根拠なしの変更",
            }
        ],
        fake_context,
        max_visits=1,
    )
    assert a in unchanged_pools[business_days[0]]
    assert unchanged_reasons == {}


def test_unreachable_day_revision_uses_only_unscheduled_single_visit_reserves() -> None:
    day_candidate = _candidate(1, 100, 10)
    already_scheduled_elsewhere = _candidate(2, 9_000, 100)
    multi_visit_reserve = _candidate(3, 8_000, 90)
    multi_visit_reserve.remaining_visit_count = 2
    valid_reserve = _candidate(4, 7_000, 80)

    options = _unreachable_day_revision_options(
        day_candidates=[day_candidate],
        all_candidates=[
            day_candidate,
            already_scheduled_elsewhere,
            multi_visit_reserve,
            valid_reserve,
        ],
        selected_customer_ids={1, 2},
        target_date=date(2026, 8, 28),
        weights={
            "sales": 25,
            "gross_profit": 25,
            "affinity": 15,
            "urgency": 15,
            "phase": 10,
            "target_gap": 10,
        },
        target_gap_ratio=Decimal("0.5"),
        max_visits=4,
    )

    assert [candidate.customer_id for candidate in options] == [1, 4]
    assert options[1].planned_visit_count == 1
    assert options[1].visit_sequence == 1
    assert options[1].expected_sales == Decimal("7000")


def test_unreachable_day_ai_revision_is_resolved_to_trusted_candidates() -> None:
    a = _candidate(1, 1000, 100)
    b = _candidate(2, 800, 80)
    payload = _unreachable_day_ai_payload(
        [a, b], originally_assigned_keys={(a.customer_id, a.visit_sequence)}
    )

    assert payload[0]["currently_assigned"] is True
    assert payload[1]["currently_assigned"] is False
    selected, reasons = _apply_unreachable_day_revision(
        [a, b],
        [
            {
                "customer_id": b.customer_id,
                "visit_sequence": b.visit_sequence,
                "reason": "期待粗利と移動負担のバランスが良い",
            },
            {
                "customer_id": 999,
                "visit_sequence": 1,
                "reason": "LLMが作った存在しない候補",
            },
        ],
    )

    assert selected == [b]
    assert reasons == {b.customer_id: "期待粗利と移動負担のバランスが良い"}


def test_period_end_shortfall_is_independent_of_each_daily_target() -> None:
    shortfalls = _target_gap_shortfalls(
        {
            "expected_sales": Decimal("950"),
            "expected_gross_profit": Decimal("310"),
        },
        target_sales=Decimal("1000"),
        target_gross_profit=Decimal("300"),
    )

    assert shortfalls == {
        "expected_sales": Decimal("50"),
        "expected_gross_profit": Decimal("0"),
    }


def test_routing_infeasible_day_is_deferred_without_raw_error() -> None:
    result = _period_deferred_day_result(
        date(2026, 8, 28), "detailed", error_code="routing_infeasible"
    )

    assert result["status"] == "proposed"
    assert result["plan_id"] is None
    assert result["solver"] == {
        "fallback": "deferred_to_period_gap_fill",
        "original_error": "routing_infeasible",
    }
    assert "routing_infeasible" not in result["warnings"][0]
    assert "週内または月内の別日で補填" in result["warnings"][0]


def test_target_gap_fill_options_include_pipeline_building_first_visits() -> None:
    scheduled = _candidate(1, 5_000, 100)
    multi_visit = _candidate(2, 4_000, 90)
    multi_visit.remaining_visit_count = 2
    reserve = _candidate(3, 3_000, 80)

    options = _target_gap_fill_options(
        all_candidates=[scheduled, multi_visit, reserve],
        scheduled_customer_ids={scheduled.customer_id},
        eligible_dates=[date(2026, 8, 28), date(2026, 8, 31)],
        weights={
            "sales": 25,
            "gross_profit": 25,
            "affinity": 15,
            "urgency": 15,
            "phase": 10,
            "target_gap": 10,
        },
        target_gap_ratio=Decimal("0.5"),
        max_visits=4,
    )

    assert [candidate.customer_id for candidate in options] == [2, 3]
    assert options[0].planned_visit_count == 2
    assert options[0].visit_sequence == 1
    assert options[0].expected_sales == Decimal("0")
    assert options[0].opportunity_expected_sales == Decimal("4000")
    assert options[1].planned_visit_count == 1
    assert options[1].expected_sales == Decimal("3000")


def test_recovery_payload_excludes_the_failed_day_and_marks_priority() -> None:
    candidate = _candidate(3, 3_000, 80)
    payload = _target_gap_fill_ai_payload(
        [candidate],
        eligible_dates=[date(2026, 8, 27), date(2026, 8, 28)],
        recovery_context_by_customer={
            candidate.customer_id: {
                "failed_dates": {date(2026, 8, 28)},
                "failure_codes": {"routing_infeasible"},
            }
        },
    )

    assert payload[0]["recovery_required"] is True
    assert payload[0]["eligible_dates"] == ["2026-08-27"]
    assert payload[0]["failed_dates"] == ["2026-08-28"]
    assert payload[0]["failure_codes"] == ["routing_infeasible"]


def test_target_gap_fill_assignments_and_improvement_are_revalidated() -> None:
    reserve = _candidate(3, 3_000, 80)
    assigned, reasons = _apply_target_gap_fill_assignments(
        [reserve],
        [
            {
                "customer_id": reserve.customer_id,
                "target_date": date(2026, 8, 28),
                "reason": "月末売上と粗利を補う",
            },
            {
                "customer_id": 999,
                "target_date": date(2026, 8, 31),
                "reason": "存在しない候補",
            },
        ],
        eligible_dates={date(2026, 8, 28), date(2026, 8, 31)},
    )

    assert assigned == {date(2026, 8, 28): [reserve]}
    assert reasons == {
        (date(2026, 8, 28), reserve.customer_id): "月末売上と粗利を補う"
    }
    assert _target_gap_improved(
        {
            "expected_sales": Decimal("100"),
            "expected_gross_profit": Decimal("50"),
        },
        {
            "expected_sales": Decimal("0"),
            "expected_gross_profit": Decimal("25"),
        },
        weights={"sales": 25, "gross_profit": 25},
    )
    assert not _target_gap_improved(
        {
            "expected_sales": Decimal("0"),
            "expected_gross_profit": Decimal("50"),
        },
        {
            "expected_sales": Decimal("10"),
            "expected_gross_profit": Decimal("0"),
        },
        weights={"sales": 25, "gross_profit": 25},
    )


def test_round_trip_matrix_uses_real_distance_between_candidates_not_branch_sum() -> None:
    # Both far from the branch (Tokyo) but close to each other (Yokohama):
    # the old branch_distances[i]+branch_distances[j] formula would estimate
    # roughly 2x their real ~3km separation.
    near_tokyo = _candidate(1, 1000, 100)
    near_tokyo.latitude, near_tokyo.longitude = 35.4437, 139.6380
    near_tokyo.distance_from_branch_m = 27000
    near_yokohama = _candidate(2, 1000, 100)
    near_yokohama.latitude, near_yokohama.longitude = 35.4657, 139.6222
    near_yokohama.distance_from_branch_m = 27500

    result = _round_trip_matrix([near_tokyo, near_yokohama], speed_kmh=25)

    inter_candidate_distance_m = result[1][2].distance_m
    assert inter_candidate_distance_m < 5000  # real separation is ~3km
    assert inter_candidate_distance_m < (
        near_tokyo.distance_from_branch_m + near_yokohama.distance_from_branch_m
    )
    # Branch<->candidate legs are unchanged (still distance_from_branch_m).
    assert result[0][1].distance_m == 27000
    assert result[2][0].distance_m == 27500


def test_cluster_candidates_by_region_groups_nearby_customers_together() -> None:
    tokyo_a = _candidate(1, 1000, 100)
    tokyo_a.latitude, tokyo_a.longitude = 35.681, 139.767
    tokyo_b = _candidate(2, 1000, 100)
    tokyo_b.latitude, tokyo_b.longitude = 35.690, 139.700
    osaka_a = _candidate(3, 1000, 100)
    osaka_a.latitude, osaka_a.longitude = 34.693, 135.502
    osaka_b = _candidate(4, 1000, 100)
    osaka_b.latitude, osaka_b.longitude = 34.702, 135.495

    regions = _cluster_candidates_by_region(
        [tokyo_a, tokyo_b, osaka_a, osaka_b], num_clusters=2
    )

    assert regions[1] == regions[2]
    assert regions[3] == regions[4]
    assert regions[1] != regions[3]


def test_cluster_candidates_by_region_single_cluster_when_fewer_customers_than_clusters() -> None:
    a = _candidate(1, 1000, 100)
    regions = _cluster_candidates_by_region([a], num_clusters=5)
    assert regions == {1: 0}


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
    monkeypatch.setattr(
        ai,
        "suggest_monthly_customer_portfolio",
        lambda *args, **kwargs: (_ for _ in ()).throw(ai.AiPlanningError("offline")),
    )
    batch_id: int | None = None
    outline_batch_id: int | None = None
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

            outline = create_batch_preview(
                conn,
                rep_id=rep_id,
                request=RoutePlanBatchPreviewRequest(
                    start_date=date(2099, 3, 1),
                    horizon="month",
                    outline_only=True,
                    detailed_days=0,
                    policy="balanced",
                    max_visits=2,
                ),
            )
            outline_batch_id = outline["batch_id"]
            RoutePlanBatchPreviewOut.model_validate(outline)
            assert outline["detailed_days"] == 0
            assert len(outline["weeks"]) == 5
            assert all(day["plan_id"] is None for day in outline["days"])
            assert all(day["detail_level"] == "coarse" for day in outline["days"])
            assert conn.execute(
                "select count(*)::int as count from route_plan where batch_id = %s",
                (outline_batch_id,),
            ).fetchone()["count"] == 0
            first_outline_week = outline["weeks"][0]
            weekly_assignments = [
                {
                    "customer_id": customer["customer_id"],
                    "visit_count": sum(
                        first_outline_week["start_date"]
                        <= assigned_date
                        <= first_outline_week["end_date"]
                        for assigned_date in customer["assigned_dates"]
                    ),
                }
                for customer in outline["selected_customers"]
            ]
            weekly_assignments = [
                assignment
                for assignment in weekly_assignments
                if assignment["visit_count"] > 0
            ]
            assert weekly_assignments

            preview = create_batch_preview(
                conn,
                rep_id=rep_id,
                request=RoutePlanBatchPreviewRequest(
                    start_date=BATCH_START_DATE,
                    end_date=first_outline_week["end_date"],
                    horizon="week",
                    detailed_days=1,
                    portfolio_assignments=weekly_assignments,
                    target_amount_override=first_outline_week["target_amount"],
                    target_gross_profit_override=first_outline_week[
                        "target_gross_profit"
                    ],
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
            assert {
                customer["customer_id"] for customer in preview["selected_customers"]
            } == {
                assignment["customer_id"] for assignment in weekly_assignments
            }

            assert preview["selected_customers"], "expected at least one selected customer"
            ongoing_customers = [
                c for c in preview["selected_customers"] if c["customer_type"] == "ongoing"
            ]
            assert ongoing_customers, "expected at least one ongoing-deal customer"
            for customer in preview["selected_customers"]:
                assert customer["loss_risk"] in ("low", "medium", "high")
                assert customer["delay_risk"] in ("low", "medium", "high")
                # This DB is shared with other concurrent activity, so deals
                # may or may not have expected_close_date set -- only check
                # internal consistency, not a specific global risk level.
                if customer["delay_risk"] == "low":
                    assert "受注予定日が未設定" not in customer["risk_reasons"]

            progress_goals = [
                goal for week in preview["weeks"] for goal in week["deal_progress_goals"]
            ]
            assert progress_goals, "expected at least one weekly deal-progress goal"
            for goal in progress_goals:
                assert goal["current_phase_name"]
                assert goal["target_phase_name"]
                assert goal["current_phase_name"] != goal["target_phase_name"]
                assert goal["rationale"]

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
            if outline_batch_id is not None:
                conn.execute(
                    "delete from route_plan_batch where batch_id = %s",
                    (outline_batch_id,),
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
