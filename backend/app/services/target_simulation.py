"""Monte Carlo achievement-probability estimation and gap-aware candidate
ranking for Must-5 (月間営業計画の自動生成/目標からの逆算, AGENTS.md section 8).

Pure functions only, no DB Connection -- planning.py fetches rows, this module
computes over the resulting dicts/Decimals. Mirrors the style of
route_optimization.py's score_candidates/_normalize (also pure, also unit
tested without a DB), but is kept fully independent of that module: the two
feature areas (day-level route optimization vs month-level target planning)
are unrelated and shouldn't share private helpers.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

ONE = Decimal("1")
HUNDRED = Decimal("100")

# deal_phase has exactly 5 rows today (see supabase/seed.sql: 初回接触=1,
# ヒアリング=2, 提案=3, 見積=4, 契約交渉=5). Kept as a constant rather than a
# live query since it only changes on a schema-level edit to deal_phase's seed
# rows, not at runtime.
MAX_DEAL_PHASE_SORT_ORDER = 5

# No spec-given number; a tunable judgment call. Below this, the situation
# counts as "at risk" for that dimension (see classify_gap_situation).
_ACHIEVEMENT_PROBABILITY_THRESHOLD = 0.7


@dataclass(frozen=True)
class SimulationResult:
    trials: int
    sales_probability: float
    profit_probability: float | None  # None when no profit target is set
    joint_probability: float
    expected_sales: Decimal
    expected_profit: Decimal
    sales_gap: Decimal
    profit_gap: Decimal | None  # None when no profit target is set


def simulate_achievement(
    open_deals: list[dict],
    *,
    already_won_amount: Decimal,
    already_won_profit: Decimal,
    target_amount: Decimal,
    target_gross_profit: Decimal | None,
    trials: int = 5000,
    rng: random.Random | None = None,
) -> SimulationResult:
    """Monte Carlo estimate of the probability of clearing target_amount and
    target_gross_profit by month end, given each open deal (dict with
    estimated_amount/profit/win_probability keys, e.g. planning._candidate_deals'
    rows) independently closes with probability win_probability/100 (spec
    section 11 -- MVP treats deals as independent; correlation across deals
    is future work, not attempted here).

    expected_sales/expected_profit/sales_gap/profit_gap are closed-form exact
    expected values, not derived from the simulation -- only the probability
    of clearing a threshold needs sampling, since that depends on the whole
    outcome distribution, not just its mean.
    """
    rng = rng if rng is not None else random.Random()

    win_fractions = [Decimal(deal["win_probability"]) / HUNDRED for deal in open_deals]
    weighted_sales = sum(
        (Decimal(deal["estimated_amount"]) * fraction for deal, fraction in zip(open_deals, win_fractions)),
        Decimal("0"),
    )
    weighted_profit = sum(
        (Decimal(deal["profit"]) * fraction for deal, fraction in zip(open_deals, win_fractions)),
        Decimal("0"),
    )
    expected_sales = (already_won_amount + weighted_sales).quantize(ONE, rounding=ROUND_HALF_UP)
    expected_profit = (already_won_profit + weighted_profit).quantize(ONE, rounding=ROUND_HALF_UP)
    sales_gap = max(Decimal("0"), target_amount - expected_sales)
    profit_gap = (
        None
        if target_gross_profit is None
        else max(Decimal("0"), target_gross_profit - expected_profit)
    )

    # Hot loop: plain int/float rather than Decimal, a deliberate, narrow
    # exception to the repo's Decimal-for-money convention, scoped only to
    # this loop -- every value crossing back out is Decimal again above/below.
    already_won_amount_i = int(already_won_amount.quantize(ONE, rounding=ROUND_HALF_UP))
    already_won_profit_i = int(already_won_profit.quantize(ONE, rounding=ROUND_HALF_UP))
    amounts_i = [int(Decimal(deal["estimated_amount"]).quantize(ONE, rounding=ROUND_HALF_UP)) for deal in open_deals]
    profits_i = [int(Decimal(deal["profit"]).quantize(ONE, rounding=ROUND_HALF_UP)) for deal in open_deals]
    probabilities = [float(fraction) for fraction in win_fractions]
    target_amount_i = int(target_amount.quantize(ONE, rounding=ROUND_HALF_UP))
    target_profit_i = (
        None if target_gross_profit is None
        else int(target_gross_profit.quantize(ONE, rounding=ROUND_HALF_UP))
    )

    deal_count = len(open_deals)
    hits_sales = hits_profit = hits_joint = 0
    for _ in range(trials):
        sales = already_won_amount_i
        profit = already_won_profit_i
        for i in range(deal_count):
            if rng.random() < probabilities[i]:
                sales += amounts_i[i]
                profit += profits_i[i]
        sales_ok = sales >= target_amount_i
        # An absent profit target is unconditionally satisfied -- this is what
        # makes joint_probability collapse to sales_probability below with no
        # extra branching, and is the precise definition of "don't gate on it".
        profit_ok = target_profit_i is None or profit >= target_profit_i
        if sales_ok:
            hits_sales += 1
        if profit_ok:
            hits_profit += 1
        if sales_ok and profit_ok:
            hits_joint += 1

    return SimulationResult(
        trials=trials,
        sales_probability=hits_sales / trials,
        profit_probability=(None if target_gross_profit is None else hits_profit / trials),
        joint_probability=hits_joint / trials,
        expected_sales=expected_sales,
        expected_profit=expected_profit,
        sales_gap=sales_gap,
        profit_gap=profit_gap,
    )


def classify_gap_situation(
    *,
    sales_probability: float,
    profit_probability: float | None,
    threshold: float = _ACHIEVEMENT_PROBABILITY_THRESHOLD,
) -> str:
    """Which of spec section 10's four situations applies right now, driven
    directly by the simulation's own probabilities (not a separate amount-gap
    check) -- so the switch and the probability shown in the UI always agree.
    profit_probability=None (no profit target set) can never be "short"."""
    sales_short = sales_probability < threshold
    profit_short = profit_probability is not None and profit_probability < threshold
    if sales_short and profit_short:
        return "both_short"
    if sales_short:
        return "sales_only_short"
    if profit_short:
        return "profit_only_short"
    return "on_track"


# Six normalized-0-100 factors, weighted per spec section 10's qualitative
# switching rules. Deliberately a normalized weighted sum, not the literal
# product spec section 9.3 writes -- a raw product of six differently-scaled
# factors is numerically fragile (one near-zero factor crushes everything),
# and the spec itself immediately hedges with "単純な総合点だけで判断しない."
#
# "受注確率の上昇幅"(probability lift from today's action) and "月内計上可能性"
# aren't independently measurable -- nothing tracks win_probability history or
# an explicit in-month-close flag. win_probability (current confidence) and
# deal_phase progress (a later phase is more likely to land *this* month,
# independent of stated win_probability) are assigned to these two factors
# separately so the same number isn't double-counted under two names.
#
# 必要工数(effort) is deliberately NOT a ranking factor (no ÷effort term): a
# literal effort-divisor would make cheap/quick items systematically beat big
# strategic deals -- exactly the "小型案件への偏り" bug spec section 3 names.
_WEIGHT_PROFILES: dict[str, dict[str, int]] = {
    "both_short":        {"sales": 30, "profit_margin": 30, "win_probability": 15, "in_month_likelihood": 15, "urgency": 5,  "neglect_risk": 5},
    "sales_only_short":  {"sales": 45, "profit_margin": 10, "win_probability": 15, "in_month_likelihood": 15, "urgency": 10, "neglect_risk": 5},
    "profit_only_short": {"sales": 10, "profit_margin": 45, "win_probability": 15, "in_month_likelihood": 15, "urgency": 10, "neglect_risk": 5},
    # 既存案件の失注防止/特定案件への依存低減(spec 10)を neglect_risk 重視で表現。
    # 翌月向け商談の創出(spec 12: 新規開拓比率)はPhase 1のスコープ外。
    "on_track":          {"sales": 15, "profit_margin": 15, "win_probability": 10, "in_month_likelihood": 10, "urgency": 10, "neglect_risk": 40},
}

# Customers with no contact in this many days are graded as fully "neglected"
# (mirrors planning.STALE_THRESHOLD_DAYS's boolean is_stale, but graded 0-100
# instead of a cutoff). planning.py passes its own constant in rather than
# this module importing it, to keep the two modules decoupled.
DEFAULT_NEGLECT_THRESHOLD_DAYS = 60


# Thresholds for assess_deal_risk. No spec-given numbers; tunable judgment
# calls consistent with _ACHIEVEMENT_PROBABILITY_THRESHOLD/
# DEFAULT_NEGLECT_THRESHOLD_DAYS above -- rule-based, not learned (AGENTS.md
# section 9: "ルールベースで期待成果...と負担を計算").
_LOSS_RISK_HIGH_PROBABILITY = 30
_LOSS_RISK_MEDIUM_PROBABILITY = 50
_DELAY_RISK_APPROACHING_DAYS = 7


@dataclass(frozen=True)
class DealRisk:
    loss_risk: str  # "low" | "medium" | "high"
    delay_risk: str  # "low" | "medium" | "high"
    reasons: list[str]


def assess_deal_risk(
    *,
    win_probability: Decimal | int,
    days_since_contact: int | None,
    expected_close_date: date | None,
    today: date,
    neglect_threshold_days: int = DEFAULT_NEGLECT_THRESHOLD_DAYS,
) -> DealRisk:
    """Rule-based per-deal 失注リスク(loss_risk)/延期リスク(delay_risk), each
    "low"/"medium"/"high". Independent of score_candidates' value_score: this
    answers "is this specific deal in trouble" rather than "how much should
    today's plan favor it", so a deal can be top-ranked and still carry a
    risk flag the rationale text should mention.
    """
    reasons: list[str] = []

    stale_high = days_since_contact is not None and days_since_contact >= neglect_threshold_days
    stale_medium = (
        days_since_contact is not None
        and days_since_contact >= neglect_threshold_days // 2
    )
    if win_probability < _LOSS_RISK_HIGH_PROBABILITY or stale_high:
        loss_risk = "high"
    elif win_probability < _LOSS_RISK_MEDIUM_PROBABILITY or stale_medium:
        loss_risk = "medium"
    else:
        loss_risk = "low"
    if win_probability < _LOSS_RISK_MEDIUM_PROBABILITY:
        reasons.append(f"成約確度が{int(win_probability)}%と低い")
    if stale_medium:
        reasons.append(f"前回接点から{days_since_contact}日以上経過している")

    if expected_close_date is None:
        delay_risk = "medium"
        reasons.append("受注予定日が未設定")
    else:
        days_over = (today - expected_close_date).days
        if days_over > 0:
            delay_risk = "high"
            reasons.append(f"受注予定日を{days_over}日超過している")
        elif -days_over <= _DELAY_RISK_APPROACHING_DAYS:
            delay_risk = "medium"
            reasons.append("受注予定日が近づいている")
        else:
            delay_risk = "low"

    return DealRisk(loss_risk=loss_risk, delay_risk=delay_risk, reasons=reasons)


def _normalize(values: list[Decimal]) -> list[Decimal]:
    if not values:
        return []
    low, high = min(values), max(values)
    if low == high:
        return [Decimal("100") if high > 0 else Decimal("0") for _ in values]
    return [
        ((value - low) * HUNDRED / (high - low)).quantize(Decimal("0.01"))
        for value in values
    ]


def score_candidates(
    candidates: list[dict],
    *,
    situation: str,
    today: date,
    month_end: date,
    neglect_threshold_days: int = DEFAULT_NEGLECT_THRESHOLD_DAYS,
) -> None:
    """Mutate each candidate dict in place, adding 'value_score' (Decimal,
    0-100 weighted average) -- the ranking generate_plans uses to decide which
    open deals get this month's attention first, given the current gap
    situation from classify_gap_situation. Each candidate dict must carry
    estimated_amount/profit/win_probability/deal_phase_sort_order/
    days_since_contact (planning._candidate_deals' row shape)."""
    weights = _WEIGHT_PROFILES[situation]
    total_weight = Decimal(sum(weights.values()))

    sales_scores = _normalize([Decimal(c["estimated_amount"]) for c in candidates])
    profit_margin_scores = _normalize([
        (Decimal(c["profit"]) / Decimal(c["estimated_amount"]) * HUNDRED)
        if Decimal(c["estimated_amount"]) > 0 else Decimal("0")
        for c in candidates
    ])
    win_probability_scores = [Decimal(c["win_probability"]) for c in candidates]
    in_month_scores = [
        Decimal(c["deal_phase_sort_order"]) / Decimal(MAX_DEAL_PHASE_SORT_ORDER) * HUNDRED
        for c in candidates
    ]
    days_remaining = max(1, (month_end - today).days + 1)
    urgency_raw = [
        Decimal(max(0, MAX_DEAL_PHASE_SORT_ORDER - int(c["deal_phase_sort_order"]))) / Decimal(days_remaining)
        for c in candidates
    ]
    urgency_scores = _normalize(urgency_raw)
    neglect_scores = [
        Decimal("100")
        if c["days_since_contact"] is None
        else Decimal(min(100, int(c["days_since_contact"]) * 100 // neglect_threshold_days))
        for c in candidates
    ]

    for index, candidate in enumerate(candidates):
        components = {
            "sales": sales_scores[index],
            "profit_margin": profit_margin_scores[index],
            "win_probability": win_probability_scores[index],
            "in_month_likelihood": in_month_scores[index],
            "urgency": urgency_scores[index],
            "neglect_risk": neglect_scores[index],
        }
        candidate["value_score"] = (
            sum(components[name] * Decimal(weight) for name, weight in weights.items())
            / total_weight
        ).quantize(Decimal("0.01"))
