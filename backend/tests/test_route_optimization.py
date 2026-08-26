from datetime import date, time
from decimal import Decimal

import pytest

from app.services.route_optimization import (
    AffinityEvidence,
    DealEconomics,
    MatrixCell,
    Portfolio,
    RoutePlanningError,
    RoutedOption,
    VisitCandidate,
    evaluate_options,
    generate_portfolios,
    route_portfolio,
    score_candidates,
    selection_reason,
)


def candidate(
    customer_id: int,
    amount: str,
    cost: str | None,
    probability: str,
    *,
    must_visit: bool = False,
    window_start: time | None = None,
    window_end: time | None = None,
) -> VisitCandidate:
    return VisitCandidate(
        customer_id=customer_id,
        customer_name=f"顧客{customer_id}",
        latitude=35.0 + customer_id / 100,
        longitude=139.0 + customer_id / 100,
        deal_ids=[customer_id * 10],
        phase_names=["提案"],
        economics=[
            DealEconomics(
                Decimal(amount),
                Decimal(cost) if cost is not None else None,
                Decimal(probability),
            )
        ],
        visit_duration_min=60,
        must_visit=must_visit,
        window_start=window_start,
        window_end=window_end,
    )


def matrix(size: int, minutes: int = 10) -> list[list[MatrixCell]]:
    return [
        [
            MatrixCell(0, 0) if origin == destination else MatrixCell(minutes * 60, 5000)
            for destination in range(size)
        ]
        for origin in range(size)
    ]


def test_economics_uses_decimal_and_preserves_unknown_or_negative_profit() -> None:
    profitable = DealEconomics(Decimal("1001"), Decimal("501"), Decimal("33"))
    assert profitable.planned_gross_profit == Decimal("500")
    assert profitable.expected_sales == Decimal("330")
    assert profitable.expected_gross_profit == Decimal("165")
    assert profitable.gross_profit_margin == Decimal("49.95")

    unknown = DealEconomics(Decimal("1000"), None, Decimal("50"))
    assert unknown.planned_gross_profit is None
    assert unknown.expected_gross_profit is None

    loss = DealEconomics(Decimal("1000"), Decimal("1200"), Decimal("50"))
    assert loss.planned_gross_profit == Decimal("-200")
    assert loss.expected_gross_profit == Decimal("-100")


def test_probability_out_of_range_is_rejected() -> None:
    with pytest.raises(ValueError):
        DealEconomics(Decimal("100"), Decimal("50"), Decimal("101"))


def test_salesperson_affinity_changes_candidate_value_for_equal_deals() -> None:
    strong = candidate(1, "1000", "500", "50")
    weak = candidate(2, "1000", "500", "50")
    strong.affinity_evidence.append(
        AffinityEvidence(
            industry_name="製造業",
            category_name="省エネ機器",
            deal_count=10,
            won_count=7,
            win_rate=Decimal("0.7"),
            match_score=Decimal("53.85"),
        )
    )
    weak.affinity_evidence.append(
        AffinityEvidence(
            industry_name="製造業",
            category_name="省エネ機器",
            deal_count=5,
            won_count=1,
            win_rate=Decimal("0.2"),
            match_score=Decimal("12.5"),
        )
    )

    score_candidates(
        [strong, weak],
        target_date=date(2026, 8, 26),
        weights={"affinity": 100},
    )

    assert strong.value_score == Decimal("53.85")
    assert weak.value_score == Decimal("12.50")
    assert "製造業×省エネ機器" in selection_reason(strong)
    assert "過去10件中7件成約" in selection_reason(strong)


def test_cp_sat_generates_unique_sets_and_keeps_must_visit() -> None:
    candidates = [
        candidate(1, "1000", "400", "80", must_visit=True),
        candidate(2, "900", "300", "70"),
        candidate(3, "700", "500", "50"),
        candidate(4, "600", "200", "60"),
    ]
    score_candidates(
        candidates,
        target_date=date(2026, 8, 26),
        weights={"sales": 25, "gross_profit": 35, "urgency": 20, "phase": 10, "target_gap": 10},
    )
    portfolios = generate_portfolios(
        candidates,
        matrix(5),
        max_visits=3,
        available_min=480,
        min_expected_sales=Decimal("1000"),
        min_expected_gross_profit=Decimal("500"),
        limit=10,
        time_limit_sec=1,
    )
    assert portfolios
    assert len({item.candidate_indexes for item in portfolios}) == len(portfolios)
    assert all(0 in item.candidate_indexes for item in portfolios)
    assert all(len(item.candidate_indexes) <= 3 for item in portfolios)
    assert all(not item.target_constraints_relaxed for item in portfolios)


def test_unreachable_target_returns_explicit_relaxed_alternatives() -> None:
    candidates = [candidate(1, "1000", "500", "50")]
    score_candidates(
        candidates,
        target_date=date(2026, 8, 26),
        weights={"sales": 25, "gross_profit": 35, "urgency": 20, "phase": 10, "target_gap": 10},
    )
    portfolios = generate_portfolios(
        candidates,
        matrix(2),
        max_visits=1,
        available_min=480,
        min_expected_sales=Decimal("999999"),
        min_expected_gross_profit=None,
        limit=10,
        time_limit_sec=1,
    )
    assert len(portfolios) == 1
    assert portfolios[0].target_constraints_relaxed is True


def test_routing_model_obeys_work_and_visit_windows() -> None:
    candidates = [
        candidate(
            1,
            "1000",
            "500",
            "80",
            window_start=time(10, 0),
            window_end=time(12, 0),
        ),
        candidate(2, "800", "300", "60"),
    ]
    portfolio = Portfolio((0, 1), Decimal("120"), "optimal")
    routed = route_portfolio(
        candidates,
        matrix(3, minutes=15),
        portfolio,
        target_date=date(2026, 8, 26),
        work_start=time(9, 0),
        work_end=time(18, 0),
        time_limit_sec=1,
    )
    assert routed.routing_status == "feasible"
    assert len(routed.stops) == 2
    assert routed.stops[-1]["departure_at"].time() <= time(18, 0)
    timed = next(stop for stop in routed.stops if stop["customer_id"] == 1)
    assert time(10, 0) <= timed["arrival_at"].time() <= time(11, 0)


def test_evaluator_never_trades_away_required_target_condition() -> None:
    relaxed = RoutedOption(
        Portfolio((0,), Decimal("999"), "optimal", True),
        "feasible",
        [],
        5,
        1000,
        0,
        False,
        {
            "expected_gross_profit": Decimal("999999"),
            "expected_sales": Decimal("999999"),
        },
    )
    strict = RoutedOption(
        Portfolio((1,), Decimal("10"), "optimal", False),
        "feasible",
        [],
        60,
        10000,
        0,
        True,
        {
            "expected_gross_profit": Decimal("100"),
            "expected_sales": Decimal("100"),
        },
    )
    assert evaluate_options([relaxed, strict]) is strict


def test_evaluator_honors_weighted_business_value_before_raw_profit() -> None:
    high_fit = RoutedOption(
        Portfolio((0,), Decimal("90"), "optimal"),
        "feasible",
        [],
        20,
        1000,
        0,
        True,
        {
            "expected_gross_profit": Decimal("100"),
            "expected_sales": Decimal("200"),
        },
    )
    high_raw_profit = RoutedOption(
        Portfolio((1,), Decimal("40"), "optimal"),
        "feasible",
        [],
        20,
        1000,
        0,
        True,
        {
            "expected_gross_profit": Decimal("1000"),
            "expected_sales": Decimal("2000"),
        },
    )

    assert evaluate_options([high_raw_profit, high_fit]) is high_fit


def test_evaluator_rejects_all_infeasible_options() -> None:
    infeasible = RoutedOption(
        Portfolio((0,), Decimal("10"), "optimal"),
        "routing_infeasible",
        [],
        0,
        0,
        0,
        False,
        {},
    )
    with pytest.raises(RoutePlanningError) as error:
        evaluate_options([infeasible])
    assert error.value.code == "routing_infeasible"



def test_minimum_gross_profit_excludes_unknown_cost_from_strict_solution() -> None:
    candidates = [
        candidate(1, "1000", None, "100"),
        candidate(2, "1000", "100", "100"),
    ]
    score_candidates(
        candidates,
        target_date=date(2026, 8, 26),
        weights={"sales": 25, "gross_profit": 35, "urgency": 20, "phase": 10, "target_gap": 10},
    )
    portfolios = generate_portfolios(
        candidates,
        matrix(3),
        max_visits=2,
        available_min=480,
        min_expected_sales=None,
        min_expected_gross_profit=Decimal("500"),
        limit=10,
        time_limit_sec=1,
    )
    assert portfolios
    assert all(0 not in item.candidate_indexes for item in portfolios)
    assert all(not item.target_constraints_relaxed for item in portfolios)


def test_routing_model_schedules_visits_outside_existing_fixed_plan() -> None:
    candidates = [candidate(1, "1000", "500", "80")]
    routed = route_portfolio(
        candidates,
        matrix(2, minutes=15),
        Portfolio((0,), Decimal("100"), "optimal"),
        target_date=date(2026, 8, 26),
        work_start=time(9, 0),
        work_end=time(18, 0),
        blocked_windows=[(time(9, 0), time(12, 0))],
        time_limit_sec=1,
    )
    assert routed.routing_status == "feasible"
    assert routed.stops[0]["arrival_at"].time() >= time(12, 0)



def test_short_travel_penalty_prefers_closer_candidate_at_equal_value() -> None:
    candidates = [
        candidate(1, "1000", "500", "50"),
        candidate(2, "1000", "500", "50"),
    ]
    candidates[0].distance_from_branch_m = 1000
    candidates[1].distance_from_branch_m = 100000
    score_candidates(
        candidates,
        target_date=date(2026, 8, 26),
        weights={"sales": 25, "gross_profit": 35, "urgency": 20, "phase": 10, "target_gap": 10},
    )
    portfolios = generate_portfolios(
        candidates,
        matrix(3),
        max_visits=1,
        available_min=480,
        min_expected_sales=None,
        min_expected_gross_profit=None,
        limit=1,
        time_limit_sec=1,
        travel_penalty_weight=30,
    )
    assert portfolios[0].candidate_indexes == (0,)


def test_routing_model_adds_turnaround_time_between_visits() -> None:
    candidates = [
        candidate(1, "1000", "500", "80"),
        candidate(2, "900", "400", "70"),
    ]
    routed = route_portfolio(
        candidates,
        matrix(3, minutes=10),
        Portfolio((0, 1), Decimal("100"), "optimal"),
        target_date=date(2026, 8, 26),
        work_start=time(9, 0),
        work_end=time(18, 0),
        turnaround_buffer_min=20,
        time_limit_sec=1,
    )

    assert routed.routing_status == "feasible"
    first, second = routed.stops
    gap_min = int((second["arrival_at"] - first["departure_at"]).total_seconds() // 60)
    assert gap_min >= 30  # turnaround 20 minutes + travel 10 minutes
    assert routed.totals["total_turnaround_min"] == 40


def test_routing_model_supports_different_start_and_end_locations() -> None:
    candidates = [candidate(1, "1000", "500", "80")]
    custom_matrix = [
        [MatrixCell(0, 0), MatrixCell(600, 5000), MatrixCell(1800, 15000)],
        [MatrixCell(600, 5000), MatrixCell(0, 0), MatrixCell(1200, 10000)],
        [MatrixCell(1800, 15000), MatrixCell(1200, 10000), MatrixCell(0, 0)],
    ]
    routed = route_portfolio(
        candidates,
        custom_matrix,
        Portfolio((0,), Decimal("100"), "optimal"),
        target_date=date(2026, 8, 26),
        work_start=time(9, 0),
        work_end=time(18, 0),
        end_node_index=2,
        time_limit_sec=1,
    )

    assert routed.routing_status == "feasible"
    assert routed.total_travel_min == 30  # start->customer 10 + customer->end 20
    assert routed.total_distance_m == 15000
