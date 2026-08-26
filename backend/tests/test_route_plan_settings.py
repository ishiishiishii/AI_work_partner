from datetime import date, datetime, time, timedelta
from decimal import Decimal

from pydantic import ValidationError
import pytest

from app.schemas.route_plans import RoutePlanPreviewRequest
from app.services.route_optimization import (
    DealEconomics,
    MatrixCell,
    Portfolio,
    RoutedOption,
    VisitCandidate,
)
from app.services.route_planning import (
    TRAVEL_MODE_CACHE_KEYS,
    _add_realistic_travel_time,
    _refine_transit_option,
)


def test_route_plan_realistic_defaults() -> None:
    request = RoutePlanPreviewRequest(target_date="2026-08-26")

    assert request.max_visits == 4
    assert request.travel_mode == "driving"
    assert request.break_enabled is True
    assert request.break_start.isoformat() == "12:00:00"
    assert request.break_end.isoformat() == "13:00:00"
    assert request.turnaround_buffer_min == 20
    assert request.travel_time_buffer_percent == 20
    assert request.access_buffer_min == 10
    assert request.return_buffer_min == 30


def test_custom_endpoint_requires_address() -> None:
    with pytest.raises(ValidationError):
        RoutePlanPreviewRequest(
            target_date="2026-08-26",
            start_location={"kind": "custom"},
        )


def test_realistic_travel_time_adds_percentage_and_access_buffer() -> None:
    adjusted = _add_realistic_travel_time(
        [
            [MatrixCell(0, 0), MatrixCell(600, 5000)],
            [MatrixCell(600, 5000), MatrixCell(0, 0)],
        ],
        buffer_percent=20,
        access_buffer_min=10,
    )

    assert adjusted[0][0].duration_sec == 0
    assert adjusted[0][1].duration_sec == 1320  # 10 min * 1.2 + 10 min
    assert adjusted[0][1].distance_m == 5000


def test_google_cache_is_separate_for_every_travel_mode() -> None:
    assert TRAVEL_MODE_CACHE_KEYS == {
        "driving": "GOOGLE_DRIVE",
        "transit": "ODPT_OTP_TRANSIT_V3",
        "walking": "GOOGLE_WALK",
        "cycling": "GOOGLE_BICYCLE",
    }


def test_transit_schedule_is_requeried_after_each_meeting() -> None:
    class TimedProvider:
        def __init__(self) -> None:
            self.departures: list[datetime] = []

        def get_itinerary(self, origin, destination, departure_at):
            del origin, destination
            self.departures.append(departure_at)
            arrival_at = departure_at + timedelta(minutes=30)
            return {
                "departure_at": departure_at.isoformat(),
                "arrival_at": arrival_at.isoformat(),
                "duration_sec": 1800,
                "distance_m": 5000,
                "walk_distance_m": 500,
                "real_time": False,
                "data_status": "時刻表ベース",
                "legs": [{"from_name": "出発地点", "to_name": "到着地点"}],
            }

    candidates = [
        VisitCandidate(
            customer_id=index,
            customer_name=f"顧客{index}",
            latitude=35.68 + index / 100,
            longitude=139.76 + index / 100,
            deal_ids=[index],
            phase_names=["提案"],
            economics=[DealEconomics(Decimal("100000"), Decimal("50000"), Decimal("0.5"))],
            visit_duration_min=60,
        )
        for index in (1, 2)
    ]
    option = RoutedOption(
        portfolio=Portfolio((0, 1), Decimal("100"), "optimal"),
        routing_status="feasible",
        stops=[{"candidate_index": 0}, {"candidate_index": 1}],
        total_travel_min=0,
        total_distance_m=0,
        total_wait_min=0,
        target_met=True,
        totals={},
    )
    provider = TimedProvider()

    _refine_transit_option(
        option,
        provider=provider,  # type: ignore[arg-type]
        candidates=candidates,
        start_location={"latitude": 35.68, "longitude": 139.76},
        end_location={"latitude": 35.68, "longitude": 139.76},
        target_date=date(2026, 8, 26),
        work_start=time(9, 0),
        work_end=time(18, 0),
        blocked_windows=[(time(12, 0), time(13, 0))],
        turnaround_buffer_min=20,
        travel_time_buffer_percent=0,
        access_buffer_min=0,
    )

    assert [value.time() for value in provider.departures] == [
        time(9, 0),
        time(10, 50),
        time(14, 20),
    ]
    assert option.stops[0]["arrival_at"].time() == time(9, 30)
    assert option.stops[1]["arrival_at"].time() == time(13, 0)
    assert option.totals["route_end_at"] == "2026-08-26T14:50:00+09:00"
