import json
from datetime import date

import pytest

from app.services import ai


class FakeResponse:
    def __init__(self, body: dict):
        self._body = body

    def json(self) -> dict:
        return self._body

    def raise_for_status(self) -> None:
        return None


class FakeConn:
    """Enough of psycopg's Connection interface for ai.log_response's
    insert-then-fetchone-then-commit chain, without touching a real DB --
    these tests are about JSON parsing/validation, not persistence."""

    def execute(self, *args, **kwargs):
        del args, kwargs
        return self

    def fetchone(self):
        return {
            "log_id": 1,
            "created_at": None,
            "rep_id": None,
            "context": None,
            "prompt": None,
            "response": None,
            "metadata": None,
        }

    def commit(self) -> None:
        return None


def _occurrence(customer_id: int = 1, visit_sequence: int = 1) -> dict:
    return {
        "customer_id": customer_id,
        "customer_name": "テスト商事",
        "visit_sequence": visit_sequence,
        "current_date": date(2026, 9, 1),
        "eligible_dates": [date(2026, 9, 4), date(2026, 9, 7)],
        "deals": [{"phase_name": "提案", "next_action": "見積回答待ち"}],
        "loss_risk": "low",
        "delay_risk": "high",
        "risk_reasons": ["受注予定日を5日超過している"],
        "must_visit": False,
        "visit_deadline": None,
    }


# ---------------------------------------------------------------------------
# suggest_monthly_customer_portfolio
# ---------------------------------------------------------------------------


def _monthly_candidate(customer_id: int) -> dict:
    return {
        "customer_id": customer_id,
        "customer_name": f"月間候補{customer_id}",
        "customer_type": "ongoing",
        "currently_selected": customer_id == 1,
        "must_visit": customer_id == 1,
        "remaining_visit_count": 1,
        "expected_sales": 1_000_000,
        "expected_gross_profit": 300_000,
    }


def test_suggest_monthly_customer_portfolio_validates_ids_weeks_and_duplicates(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        ai.httpx,
        "post",
        lambda *a, **k: FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                [
                                    {
                                        "customer_id": 1,
                                        "preferred_week": 1,
                                        "reason": "必須訪問かつ月間売上への貢献が高い",
                                    },
                                    {
                                        "customer_id": 999,
                                        "preferred_week": 1,
                                        "reason": "存在しない候補",
                                    },
                                    {
                                        "customer_id": 2,
                                        "preferred_week": 99,
                                        "reason": "存在しない週",
                                    },
                                    {
                                        "customer_id": 1,
                                        "preferred_week": 2,
                                        "reason": "重複",
                                    },
                                    {
                                        "customer_id": 2,
                                        "preferred_week": 2,
                                        "reason": "第2週の粗利を補う",
                                    },
                                ],
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }
        ),
    )

    result = ai.suggest_monthly_customer_portfolio(
        FakeConn(),
        rep_id=10,
        period={"start_date": "2026-09-01", "end_date": "2026-09-30"},
        objective={"sales_weight": 25, "gross_profit_weight": 25},
        weeks=[
            {"week_number": 1, "start_date": "2026-09-01", "end_date": "2026-09-04"},
            {"week_number": 2, "start_date": "2026-09-07", "end_date": "2026-09-11"},
        ],
        candidates=[_monthly_candidate(1), _monthly_candidate(2)],
        selection_limit=10,
    )

    assert result == [
        {
            "customer_id": 1,
            "preferred_week": 1,
            "reason": "必須訪問かつ月間売上への貢献が高い",
        },
        {
            "customer_id": 2,
            "preferred_week": 2,
            "reason": "第2週の粗利を補う",
        },
    ]


def test_suggest_monthly_customer_portfolio_requires_candidates() -> None:
    with pytest.raises(ai.AiPlanningError):
        ai.suggest_monthly_customer_portfolio(
            FakeConn(), rep_id=10, period={}, objective={}, weeks=[],
            candidates=[], selection_limit=0,
        )


# ---------------------------------------------------------------------------
# suggest_schedule_adjustments
# ---------------------------------------------------------------------------


def test_suggest_schedule_adjustments_returns_validated_items(monkeypatch) -> None:
    monkeypatch.setattr(
        ai.httpx,
        "post",
        lambda *a, **k: FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                [
                                    {
                                        "customer_id": 1,
                                        "visit_sequence": 1,
                                        "new_date": "2026-09-04",
                                        "reason": "見積回答待ちのため後ろ倒し",
                                    }
                                ]
                            )
                        }
                    }
                ]
            }
        ),
    )
    result = ai.suggest_schedule_adjustments(
        FakeConn(), rep_id=1, occurrences=[_occurrence()]
    )
    assert result == [
        {
            "customer_id": 1,
            "visit_sequence": 1,
            "new_date": "2026-09-04",
            "reason": "見積回答待ちのため後ろ倒し",
        }
    ]


def test_suggest_schedule_adjustments_skips_malformed_items(monkeypatch) -> None:
    monkeypatch.setattr(
        ai.httpx,
        "post",
        lambda *a, **k: FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                [
                                    {"customer_id": 1, "visit_sequence": 1},  # missing fields
                                    {
                                        "customer_id": 1,
                                        "visit_sequence": 1,
                                        "new_date": "2026-09-04",
                                        "reason": "有効な提案",
                                    },
                                ]
                            )
                        }
                    }
                ]
            }
        ),
    )
    result = ai.suggest_schedule_adjustments(
        FakeConn(), rep_id=1, occurrences=[_occurrence()]
    )
    assert result == [
        {
            "customer_id": 1,
            "visit_sequence": 1,
            "new_date": "2026-09-04",
            "reason": "有効な提案",
        }
    ]


def test_suggest_schedule_adjustments_empty_response_is_a_valid_no_op(monkeypatch) -> None:
    monkeypatch.setattr(
        ai.httpx,
        "post",
        lambda *a, **k: FakeResponse({"choices": [{"message": {"content": "[]"}}]}),
    )
    result = ai.suggest_schedule_adjustments(
        FakeConn(), rep_id=1, occurrences=[_occurrence()]
    )
    assert result == []


def test_suggest_schedule_adjustments_raises_on_connection_failure(monkeypatch) -> None:
    def fail(*args, **kwargs):
        del args, kwargs
        raise ConnectionError("boom")

    monkeypatch.setattr(ai.httpx, "post", fail)
    with pytest.raises(ai.AiPlanningError):
        ai.suggest_schedule_adjustments(FakeConn(), rep_id=1, occurrences=[_occurrence()])


def test_suggest_schedule_adjustments_raises_when_no_occurrences_given() -> None:
    with pytest.raises(ai.AiPlanningError):
        ai.suggest_schedule_adjustments(FakeConn(), rep_id=1, occurrences=[])


# ---------------------------------------------------------------------------
# revise_unreachable_day
# ---------------------------------------------------------------------------


def _revision_candidate(customer_id: int = 1, visit_sequence: int = 1) -> dict:
    return {
        "customer_id": customer_id,
        "visit_sequence": visit_sequence,
        "customer_name": f"顧客{customer_id}",
        "currently_assigned": False,
        "must_visit": False,
        "visit_deadline": None,
        "expected_sales": 1_000_000,
        "expected_gross_profit": 300_000,
        "opportunity_expected_sales": 1_000_000,
        "opportunity_expected_gross_profit": 300_000,
        "visit_duration_min": 60,
        "distance_from_branch_m": 5_000,
        "phase_names": ["提案"],
        "next_actions": ["見積を提示する"],
    }


def test_revise_unreachable_day_validates_and_limits_candidate_keys(monkeypatch) -> None:
    monkeypatch.setattr(
        ai.httpx,
        "post",
        lambda *a, **k: FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                [
                                    {
                                        "customer_id": 2,
                                        "visit_sequence": 1,
                                        "reason": "期待粗利が高く移動も短い",
                                    },
                                    {
                                        "customer_id": 999,
                                        "visit_sequence": 1,
                                        "reason": "存在しない候補",
                                    },
                                    {
                                        "customer_id": 2,
                                        "visit_sequence": 1,
                                        "reason": "重複",
                                    },
                                    {
                                        "customer_id": 1,
                                        "visit_sequence": 1,
                                        "reason": "期待売上が高い",
                                    },
                                ]
                            )
                        }
                    }
                ]
            }
        ),
    )

    result = ai.revise_unreachable_day(
        FakeConn(),
        rep_id=1,
        target_date=date(2026, 8, 28),
        error_message="候補セットがありません",
        constraints={"max_visits": 4},
        objective={"sales_weight": 50, "gross_profit_weight": 50},
        monthly_plan={"expected_sales_before_revision": 0},
        candidates=[_revision_candidate(1), _revision_candidate(2)],
        candidate_limit=2,
    )

    assert result == [
        {
            "customer_id": 2,
            "visit_sequence": 1,
            "reason": "期待粗利が高く移動も短い",
        },
        {
            "customer_id": 1,
            "visit_sequence": 1,
            "reason": "期待売上が高い",
        },
    ]


def test_revise_unreachable_day_rejects_empty_valid_response(monkeypatch) -> None:
    monkeypatch.setattr(
        ai.httpx,
        "post",
        lambda *a, **k: FakeResponse(
            {"choices": [{"message": {"content": "[]"}}]}
        ),
    )
    with pytest.raises(ai.AiPlanningError):
        ai.revise_unreachable_day(
            FakeConn(),
            rep_id=1,
            target_date=date(2026, 8, 28),
            error_message="候補セットがありません",
            constraints={"max_visits": 4},
            objective={"sales_weight": 50, "gross_profit_weight": 50},
            monthly_plan={"expected_sales_before_revision": 0},
            candidates=[_revision_candidate()],
            candidate_limit=1,
        )


# ---------------------------------------------------------------------------
# suggest_target_gap_fill
# ---------------------------------------------------------------------------


def _gap_fill_candidate(customer_id: int = 1) -> dict:
    return {
        "customer_id": customer_id,
        "customer_name": f"補填候補{customer_id}",
        "eligible_dates": ["2026-08-28", "2026-08-31"],
        "must_visit": False,
        "visit_deadline": None,
        "expected_sales": 2_000_000,
        "expected_gross_profit": 600_000,
        "visit_duration_min": 60,
        "distance_from_branch_m": 4_000,
        "phase_names": ["契約交渉"],
        "next_actions": ["契約条件を確認する"],
    }


def test_suggest_target_gap_fill_validates_customer_and_eligible_date(monkeypatch) -> None:
    monkeypatch.setattr(
        ai.httpx,
        "post",
        lambda *a, **k: FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                [
                                    {
                                        "customer_id": 1,
                                        "target_date": "2026-08-28",
                                        "reason": "売上・粗利不足を同時に補える",
                                    },
                                    {
                                        "customer_id": 2,
                                        "target_date": "2026-09-01",
                                        "reason": "候補期間外",
                                    },
                                    {
                                        "customer_id": 999,
                                        "target_date": "2026-08-31",
                                        "reason": "存在しない顧客",
                                    },
                                    {
                                        "customer_id": 1,
                                        "target_date": "2026-08-31",
                                        "reason": "重複",
                                    },
                                ]
                            )
                        }
                    }
                ]
            }
        ),
    )

    result = ai.suggest_target_gap_fill(
        FakeConn(),
        rep_id=1,
        period={"sales_shortfall": 1_000_000, "gross_profit_shortfall": 300_000},
        objective={"sales_weight": 25, "gross_profit_weight": 25},
        days=[{"target_date": "2026-08-28"}],
        candidates=[_gap_fill_candidate(1), _gap_fill_candidate(2)],
        assignment_limit=3,
    )

    assert result == [
        {
            "customer_id": 1,
            "target_date": date(2026, 8, 28),
            "reason": "売上・粗利不足を同時に補える",
        }
    ]


def test_suggest_target_gap_fill_requires_candidates() -> None:
    with pytest.raises(ai.AiPlanningError):
        ai.suggest_target_gap_fill(
            FakeConn(),
            rep_id=1,
            period={},
            objective={},
            days=[{"target_date": "2026-08-28"}],
            candidates=[],
            assignment_limit=1,
        )


# ---------------------------------------------------------------------------
# generate_week_narratives
# ---------------------------------------------------------------------------


def _week(week_number: int = 1) -> dict:
    return {
        "week_number": week_number,
        "start_date": date(2026, 9, 1),
        "end_date": date(2026, 9, 5),
        "target_amount": 1000000,
        "expected_sales": 800000,
        "attainment_rate": 0.8,
        "customer_names": ["テスト商事"],
        "deal_progress_goals": [
            {
                "customer_name": "テスト商事",
                "current_phase_name": "提案",
                "target_phase_name": "見積",
            }
        ],
    }


def test_generate_week_narratives_maps_notes_by_week_number(monkeypatch) -> None:
    monkeypatch.setattr(
        ai.httpx,
        "post",
        lambda *a, **k: FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                [{"week_number": 1, "note": "テスト商事を見積へ進めます。"}]
                            )
                        }
                    }
                ]
            }
        ),
    )
    result = ai.generate_week_narratives(FakeConn(), rep_id=1, weeks=[_week()])
    assert result == {1: "テスト商事を見積へ進めます。"}


def test_generate_week_narratives_ignores_unknown_week_numbers(monkeypatch) -> None:
    monkeypatch.setattr(
        ai.httpx,
        "post",
        lambda *a, **k: FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                [
                                    {"week_number": 1, "note": "有効なコメント"},
                                    {"week_number": 99, "note": "存在しない週"},
                                ]
                            )
                        }
                    }
                ]
            }
        ),
    )
    result = ai.generate_week_narratives(FakeConn(), rep_id=1, weeks=[_week()])
    assert result == {1: "有効なコメント"}


def test_generate_week_narratives_raises_when_nothing_usable(monkeypatch) -> None:
    monkeypatch.setattr(
        ai.httpx,
        "post",
        lambda *a, **k: FakeResponse({"choices": [{"message": {"content": "[]"}}]}),
    )
    with pytest.raises(ai.AiPlanningError):
        ai.generate_week_narratives(FakeConn(), rep_id=1, weeks=[_week()])
