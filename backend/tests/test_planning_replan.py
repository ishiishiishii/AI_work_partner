from decimal import Decimal

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
