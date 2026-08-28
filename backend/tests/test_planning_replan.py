from contextlib import contextmanager
from datetime import date
from decimal import Decimal

from app.routers import mvp
from app.schemas.models import ReplanRequest
from app.services.planning import _cap_candidates_to_target


def _deal(deal_id: int, amount: int) -> dict:
    return {"deal_id": deal_id, "estimated_amount": Decimal(amount)}


def test_replan_selects_no_more_sales_deals_when_wins_cover_remaining_target() -> None:
    candidates = [_deal(1, 800), _deal(2, 600)]

    assert _cap_candidates_to_target(candidates, Decimal("0")) == []


def test_replan_keeps_open_candidates_when_no_monthly_target_is_configured() -> None:
    candidates = [_deal(1, 800), _deal(2, 600)]

    assert _cap_candidates_to_target(candidates, None) == candidates


def test_replan_caps_replacement_deals_against_remaining_target() -> None:
    candidates = [_deal(1, 600), _deal(2, 400), _deal(3, 300)]

    selected = _cap_candidates_to_target(candidates, Decimal("900"))

    assert [deal["deal_id"] for deal in selected] == [1, 2]
    assert sum(deal["estimated_amount"] for deal in selected) == Decimal("1000")


def test_replan_request_accepts_plan_date_as_start_date() -> None:
    request = ReplanRequest(
        rep_id=10,
        target_month="2026-08",
        start_date="2026-08-10",
    )

    assert request.start_date == date(2026, 8, 10)


def test_replan_endpoint_uses_requested_start_date(monkeypatch) -> None:
    connection = object()
    captured: dict = {}

    @contextmanager
    def fake_get_connection():
        yield connection

    def fake_generate_plans(conn, **kwargs):
        captured["conn"] = conn
        captured.update(kwargs)
        return [], False

    monkeypatch.setattr(mvp, "get_connection", fake_get_connection)
    monkeypatch.setattr(mvp.planning, "generate_plans", fake_generate_plans)

    mvp.post_plans_replan(
        ReplanRequest(
            rep_id=10,
            target_month="2026-08",
            start_date="2026-08-10",
        )
    )

    assert captured == {
        "conn": connection,
        "rep_id": 10,
        "target_month": "2026-08",
        "start_date": date(2026, 8, 10),
    }
