from datetime import date
from decimal import Decimal

from app.services import planning


def _candidate(index: int) -> dict:
    return {
        "deal_id": 1000 + index,
        "customer_id": 2000 + index,
        "customer_name": f"テスト企業{index}",
        "estimated_amount": Decimal("500000"),
        "win_probability": 40,
    }


def test_idle_fill_adds_deal_support_prospecting_and_weekly_admin() -> None:
    base = date(2026, 8, 1)
    month_end = date(2026, 8, 31)
    business_days = planning._business_days(base, month_end)
    candidates = [_candidate(index) for index in range(8)]
    decisions = [
        {
            "category": "visit",
            "activity_type": "訪問",
            "deal_id": candidate["deal_id"],
            "title": None,
            "plan_date": business_days[index],
            "priority": min(index + 1, 5),
            "rationale": "テスト訪問",
        }
        for index, candidate in enumerate(candidates)
    ]

    planning._fill_idle_days(decisions, candidates, base=base, month_end=month_end)
    planning._assign_time_slots(decisions)

    visits_by_deal = {
        item["deal_id"]: item
        for item in decisions
        if item["category"] == "visit"
    }
    linked_support = [
        item
        for item in decisions
        if item["category"] == "task" and item["deal_id"] is not None
    ]
    assert len(linked_support) == 15
    assert all(item["deal_id"] in visits_by_deal for item in linked_support)
    assert all(
        item["plan_date"] == visits_by_deal[item["deal_id"]]["plan_date"]
        for item in linked_support
    )
    assert all(
        str(item["deal_id"] - 1000) in item["title"]
        for item in linked_support
    )
    assert {item["relative_position"] for item in linked_support} == {"before", "after"}

    prospecting = [
        item
        for item in decisions
        if item["deal_id"] is None and item["activity_type"] == "新規開拓"
    ]
    assert len(prospecting) == 8
    assert all(item["plan_date"].day <= 15 for item in prospecting)
    assert len({item["title"] for item in prospecting}) == 4

    week_keys = {(day.isocalendar().year, day.isocalendar().week) for day in business_days}
    for title in ("週次報告書の作成", "提案資料テンプレートの整備"):
        tasks = [item for item in decisions if item.get("title") == title]
        assert len(tasks) == len(week_keys)
        assert {(item["plan_date"].isocalendar().year, item["plan_date"].isocalendar().week) for item in tasks} == week_keys
        assert all(item["deal_id"] is None for item in tasks)

    by_date: dict[date, list[dict]] = {}
    for item in decisions:
        by_date.setdefault(item["plan_date"], []).append(item)
    for day_items in by_date.values():
        ordered = sorted(day_items, key=lambda item: item["start_time"])
        assert len(ordered) <= planning._MAX_ITEMS_PER_DAY
        assert sum(planning._decision_duration(item) for item in ordered) <= planning._IDLE_FILL_TARGET_MINUTES
        assert all(first["end_time"] <= second["start_time"] for first, second in zip(ordered, ordered[1:]))


def test_idle_fill_still_creates_dealless_work_when_no_visit_is_needed() -> None:
    decisions: list[dict] = []
    planning._fill_idle_days(
        decisions,
        [],
        base=date(2026, 8, 1),
        month_end=date(2026, 8, 31),
    )

    assert decisions
    assert all(item["category"] == "task" for item in decisions)
    assert all(item["deal_id"] is None for item in decisions)
    assert any(item["activity_type"] == "新規開拓" for item in decisions)
    assert any(item["title"] == "週次報告書の作成" for item in decisions)


def test_only_visit_rows_carry_deal_economics() -> None:
    deal = {"estimated_amount": Decimal("500000"), "win_probability": 40}

    assert planning._activity_plan_economics({"category": "visit"}, deal) == (
        Decimal("500000"),
        40,
    )
    assert planning._activity_plan_economics({"category": "task"}, deal) == (
        Decimal("0"),
        0,
    )
