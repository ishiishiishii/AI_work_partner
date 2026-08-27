import random
from datetime import date
from decimal import Decimal

import pytest

from app.services.target_simulation import (
    classify_gap_situation,
    score_candidates,
    simulate_achievement,
)


def deal(
    amount: str,
    profit: str,
    probability: str,
    *,
    sort_order: int = 3,
    days_since_contact: int | None = 0,
) -> dict:
    return {
        "estimated_amount": Decimal(amount),
        "profit": Decimal(profit),
        "win_probability": Decimal(probability),
        "deal_phase_sort_order": sort_order,
        "days_since_contact": days_since_contact,
    }


# ---------------------------------------------------------------------------
# simulate_achievement
# ---------------------------------------------------------------------------


def test_single_deal_certain_to_win_gives_probability_one() -> None:
    result = simulate_achievement(
        [deal("1000", "0", "100")],
        already_won_amount=Decimal("0"),
        already_won_profit=Decimal("0"),
        target_amount=Decimal("1000"),
        target_gross_profit=None,
        trials=200,
        rng=random.Random(1),
    )
    assert result.sales_probability == 1.0


def test_single_deal_certain_to_lose_gives_probability_zero() -> None:
    result = simulate_achievement(
        [deal("1000", "0", "0")],
        already_won_amount=Decimal("0"),
        already_won_profit=Decimal("0"),
        target_amount=Decimal("1000"),
        target_gross_profit=None,
        trials=200,
        rng=random.Random(1),
    )
    assert result.sales_probability == 0.0


def test_already_won_amount_meeting_target_gives_probability_one_regardless_of_pipeline() -> None:
    result = simulate_achievement(
        [],
        already_won_amount=Decimal("5000000"),
        already_won_profit=Decimal("0"),
        target_amount=Decimal("5000000"),
        target_gross_profit=None,
        trials=200,
        rng=random.Random(1),
    )
    assert result.sales_probability == 1.0
    assert result.sales_gap == Decimal("0")


def test_three_deal_scenario_matches_hand_computed_probability() -> None:
    # D1 alone (3,000,000 @ 60%) is exactly enough to clear the 3,000,000 gap
    # (target 5,000,000 - already_won 2,000,000); D2/D3 alone or together
    # never clear it. So sales_probability converges to exactly P(D1 wins) =
    # 0.60, independent of D2/D3 -- a clean hand-verifiable fixture.
    open_deals = [
        deal("3000000", "1500000", "60"),
        deal("1500000", "600000", "40"),
        deal("800000", "300000", "25"),
    ]
    result = simulate_achievement(
        open_deals,
        already_won_amount=Decimal("2000000"),
        already_won_profit=Decimal("0"),
        target_amount=Decimal("5000000"),
        target_gross_profit=None,
        trials=5000,
        rng=random.Random(42),
    )
    assert result.expected_sales == Decimal("4600000")
    assert result.sales_gap == Decimal("400000")
    assert result.sales_probability == pytest.approx(0.60, abs=0.03)


def test_no_profit_target_leaves_profit_probability_none_and_joint_equals_sales() -> None:
    open_deals = [deal("1000000", "400000", "50"), deal("500000", "100000", "80")]
    result = simulate_achievement(
        open_deals,
        already_won_amount=Decimal("0"),
        already_won_profit=Decimal("0"),
        target_amount=Decimal("1000000"),
        target_gross_profit=None,
        trials=2000,
        rng=random.Random(7),
    )
    assert result.profit_probability is None
    assert result.profit_gap is None
    assert result.joint_probability == result.sales_probability
    # expected_profit is still a real number even with no target to compare it to.
    assert result.expected_profit == Decimal("280000")


# ---------------------------------------------------------------------------
# classify_gap_situation
# ---------------------------------------------------------------------------


def test_classify_gap_situation_four_quadrants() -> None:
    assert classify_gap_situation(sales_probability=0.5, profit_probability=0.5) == "both_short"
    assert classify_gap_situation(sales_probability=0.5, profit_probability=0.9) == "sales_only_short"
    assert classify_gap_situation(sales_probability=0.9, profit_probability=0.5) == "profit_only_short"
    assert classify_gap_situation(sales_probability=0.9, profit_probability=0.9) == "on_track"


def test_classify_gap_situation_no_profit_target_can_never_be_profit_short() -> None:
    assert classify_gap_situation(sales_probability=0.5, profit_probability=None) == "sales_only_short"
    assert classify_gap_situation(sales_probability=0.9, profit_probability=None) == "on_track"


def test_classify_gap_situation_threshold_is_strictly_less_than() -> None:
    # Exactly at the threshold does NOT count as short.
    assert classify_gap_situation(sales_probability=0.7, profit_probability=0.7) == "on_track"
    assert classify_gap_situation(sales_probability=0.6999, profit_probability=0.7) == "sales_only_short"


# ---------------------------------------------------------------------------
# score_candidates
# ---------------------------------------------------------------------------


def _ranked_names(candidates: list[dict]) -> list[str]:
    return [c["name"] for c in sorted(candidates, key=lambda c: c["value_score"], reverse=True)]


def _deal_a_b() -> list[dict]:
    # A: big, low-margin, high win probability, far along, freshly contacted.
    # B: small, high-margin, low win probability, early stage, neglected.
    deal_a = deal("3000000", "900000", "60", sort_order=4, days_since_contact=0)
    deal_a["name"] = "A"
    deal_b = deal("800000", "560000", "25", sort_order=2, days_since_contact=70)
    deal_b["name"] = "B"
    return [deal_a, deal_b]


@pytest.mark.parametrize("situation", ["both_short", "sales_only_short"])
def test_score_candidates_favors_large_deal_when_sales_is_short(situation: str) -> None:
    candidates = _deal_a_b()
    score_candidates(candidates, situation=situation, today=date(2026, 8, 1), month_end=date(2026, 8, 31))
    assert _ranked_names(candidates) == ["A", "B"]


def test_score_candidates_favors_high_margin_deal_when_only_profit_is_short() -> None:
    candidates = _deal_a_b()
    score_candidates(
        candidates, situation="profit_only_short", today=date(2026, 8, 1), month_end=date(2026, 8, 31)
    )
    assert _ranked_names(candidates) == ["B", "A"]


def test_score_candidates_favors_neglected_deal_when_on_track() -> None:
    candidates = _deal_a_b()
    score_candidates(candidates, situation="on_track", today=date(2026, 8, 1), month_end=date(2026, 8, 31))
    # B is the neglected (70-day-stale) deal; on_track weights neglect_risk
    # heavily (spec section 10: protect at-risk existing deals over chasing more).
    assert _ranked_names(candidates) == ["B", "A"]
