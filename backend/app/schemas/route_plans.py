from datetime import date, time
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class RouteEndpointInput(BaseModel):
    kind: Literal["branch", "custom"] = "branch"
    address: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_custom_address(self) -> "RouteEndpointInput":
        if self.kind == "custom" and not (self.address or "").strip():
            raise ValueError("custom endpoint requires an address")
        return self


class RouteSearchAreaInput(BaseModel):
    kind: Literal["auto", "custom"] = "auto"
    query: str | None = Field(default=None, max_length=200)
    radius_km: int = Field(default=5, ge=1, le=50)

    @model_validator(mode="after")
    def validate_custom_query(self) -> "RouteSearchAreaInput":
        if self.kind == "custom" and not (self.query or "").strip():
            raise ValueError("custom search area requires a query")
        return self


def _validate_common_route_settings(model: BaseModel) -> None:
    """Shared by RoutePlanPreviewRequest and RoutePlanBatchPreviewRequest,
    which duplicate the same work-hours/weight/break fields for a single day
    vs. a whole horizon respectively."""
    custom_weights = (
        model.sales_weight_percent,
        model.gross_profit_weight_percent,
    )
    if any(value is not None for value in custom_weights):
        if any(value is None for value in custom_weights):
            raise ValueError(
                "sales_weight_percent and gross_profit_weight_percent must be set together"
            )
        if sum(value for value in custom_weights if value is not None) != 100:
            raise ValueError("sales and gross-profit weights must add up to 100")
    if model.work_start >= model.work_end:
        raise ValueError("work_start must be earlier than work_end")
    if model.break_enabled:
        if model.break_start >= model.break_end:
            raise ValueError("break_start must be earlier than break_end")
        if model.break_start < model.work_start or model.break_end > model.work_end:
            raise ValueError("break must be within working hours")
    work_minutes = (
        model.work_end.hour * 60 + model.work_end.minute
        - model.work_start.hour * 60 - model.work_start.minute
    )
    if model.return_buffer_min >= work_minutes:
        raise ValueError("return_buffer_min must be shorter than working hours")


class RoutePlanPreviewRequest(BaseModel):
    target_date: date
    policy: Literal["balanced", "sales", "gross_profit", "short_travel"] = "balanced"
    sales_weight_percent: int | None = Field(default=None, ge=0, le=100)
    gross_profit_weight_percent: int | None = Field(default=None, ge=0, le=100)
    max_visits: int = Field(default=4, ge=1, le=10)
    work_start: time = time(9, 0)
    work_end: time = time(18, 0)
    travel_mode: Literal["driving", "transit", "walking", "cycling"] = "driving"
    start_location: RouteEndpointInput = Field(default_factory=RouteEndpointInput)
    end_location: RouteEndpointInput = Field(default_factory=RouteEndpointInput)
    search_area: RouteSearchAreaInput = Field(default_factory=RouteSearchAreaInput)
    break_enabled: bool = True
    break_start: time = time(12, 0)
    break_end: time = time(13, 0)
    turnaround_buffer_min: int = Field(default=20, ge=0, le=60)
    travel_time_buffer_percent: int = Field(default=20, ge=0, le=100)
    access_buffer_min: int = Field(default=10, ge=0, le=60)
    return_buffer_min: int = Field(default=30, ge=0, le=120)
    min_expected_sales: Decimal | None = Field(default=None, ge=0)
    min_expected_gross_profit: Decimal | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> "RoutePlanPreviewRequest":
        _validate_common_route_settings(self)
        return self


class RoutePlanPortfolioAssignmentInput(BaseModel):
    """One month-outline customer allocation carried into a weekly solve."""

    customer_id: int
    visit_count: int = Field(ge=1, le=31)


class RoutePlanBatchPreviewRequest(BaseModel):
    """Month-to-week-to-day integrated planning request.

    ``horizon=week`` remains available for API compatibility, while the
    dashboard keeps a month-wide objective and uses ``detailed_days`` to run
    the expensive single-day route solver only for the next business week.
    Later business days remain coarse until the plan is regenerated.
    """

    start_date: date
    horizon: Literal["week", "month"] = "week"
    # outline_only creates the month portfolio/week allocation without running
    # any daily CP-SAT/routing solver. The UI then sends each week's portfolio
    # back in portfolio_assignments for a bounded detailed solve.
    outline_only: bool = False
    end_date: date | None = None
    detailed_days: int | None = Field(default=None, ge=0, le=31)
    portfolio_assignments: list[RoutePlanPortfolioAssignmentInput] = Field(
        default_factory=list
    )
    target_amount_override: Decimal | None = Field(default=None, ge=0)
    target_gross_profit_override: Decimal | None = Field(default=None, ge=0)
    policy: Literal["balanced", "sales", "gross_profit", "short_travel"] = "balanced"
    sales_weight_percent: int | None = Field(default=None, ge=0, le=100)
    gross_profit_weight_percent: int | None = Field(default=None, ge=0, le=100)
    max_visits: int = Field(default=4, ge=1, le=10)
    work_start: time = time(9, 0)
    work_end: time = time(18, 0)
    travel_mode: Literal["driving", "transit", "walking", "cycling"] = "driving"
    start_location: RouteEndpointInput = Field(default_factory=RouteEndpointInput)
    end_location: RouteEndpointInput = Field(default_factory=RouteEndpointInput)
    search_area: RouteSearchAreaInput = Field(default_factory=RouteSearchAreaInput)
    break_enabled: bool = True
    break_start: time = time(12, 0)
    break_end: time = time(13, 0)
    turnaround_buffer_min: int = Field(default=20, ge=0, le=60)
    travel_time_buffer_percent: int = Field(default=20, ge=0, le=100)
    access_buffer_min: int = Field(default=10, ge=0, le=60)
    return_buffer_min: int = Field(default=30, ge=0, le=120)
    min_expected_sales: Decimal | None = Field(default=None, ge=0)
    min_expected_gross_profit: Decimal | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> "RoutePlanBatchPreviewRequest":
        _validate_common_route_settings(self)
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if self.outline_only and self.horizon != "month":
            raise ValueError("outline_only requires horizon=month")
        return self


class RoutePlanStopOut(BaseModel):
    visit_order: int
    customer_id: int
    customer_name: str
    deal_ids: list[int]
    phase_names: list[str]
    arrival_at: str
    departure_at: str
    visit_duration_min: int
    turnaround_buffer_min: int
    leg_travel_min: int
    leg_distance_m: int
    leg_details: dict[str, Any] = Field(default_factory=dict)
    economics: dict[str, Any]
    selection_reason: str
    latitude: float
    longitude: float
    estimated: bool = False


class RoutePlanOptionOut(BaseModel):
    rank: int
    selected: bool
    cp_sat_status: str
    routing_status: str
    business_value: Decimal
    totals: dict[str, Any]
    rejection_reason: str | None = None


class RoutePlanPreviewOut(BaseModel):
    plan_id: int
    status: Literal["proposed", "failed"]
    rep_id: int
    rep_name: str
    target_date: date
    branch: dict[str, Any]
    start_location: dict[str, Any]
    end_location: dict[str, Any]
    search_area: dict[str, Any]
    travel_mode: str
    break_time: dict[str, time] | None
    realism: dict[str, int]
    policy: str
    weights: dict[str, int]
    work_start: time
    work_end: time
    target_met: bool
    shortfalls: dict[str, Decimal]
    totals: dict[str, Any]
    stops: list[RoutePlanStopOut]
    return_leg: dict[str, Any] | None = None
    options: list[RoutePlanOptionOut]
    selection_reason: str
    excluded_reasons: list[str]
    warnings: list[str]
    solver: dict[str, Any]


class RoutePlanApproveOut(BaseModel):
    plan_id: int
    status: Literal["approved"]
    activity_plan_ids: list[int]


class RoutePlanIdleDayApproveRequest(BaseModel):
    batch_id: int = Field(gt=0)
    target_date: date


class RoutePlanIdleDayApproveOut(BaseModel):
    target_date: date
    status: Literal["approved"]
    activity_plan_ids: list[int]
    summary: str


class RoutePlanRejectOut(BaseModel):
    plan_id: int
    status: Literal["rejected"]


class RoutePlanWeekAlternativeRequest(BaseModel):
    plan_ids: list[int] = Field(min_length=1, max_length=7)
    minimum_economic_ratio: float = Field(default=0.9, ge=0.5, le=1.0)

    @model_validator(mode="after")
    def validate_unique_plan_ids(self) -> "RoutePlanWeekAlternativeRequest":
        if len(set(self.plan_ids)) != len(self.plan_ids):
            raise ValueError("plan_ids must be unique")
        return self


class RoutePlanAlternativeChangeOut(BaseModel):
    plan_id: int
    target_date: date
    option_rank: int
    totals: dict[str, Any]
    stops: list[RoutePlanStopOut]


class RoutePlanWeekAlternativeOut(BaseModel):
    reason: str
    change: RoutePlanAlternativeChangeOut


class RoutePlanBatchDayOut(BaseModel):
    plan_id: int | None
    target_date: date
    detail_level: Literal["detailed", "coarse"]
    status: Literal["proposed", "failed"]
    target_amount: Decimal = Decimal("0")
    shortfall_amount: Decimal = Decimal("0")
    attainment_rate: float = 0
    existing_visit_count: int = Field(default=0, ge=0)
    # 0円 = 粗利目標が未設定/その日への配分が無いという意味(月全体で
    # 粗利目標がnullなら常に0)。売上のtarget_amountと同じ配分ロジックを流用。
    target_gross_profit: Decimal = Decimal("0")
    totals: dict[str, Any]
    stops: list[RoutePlanStopOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    solver: dict[str, Any] = Field(default_factory=dict)


class WeekDealProgressGoalOut(BaseModel):
    customer_id: int
    # None for a "new" (新規開拓) prospect, which has no deal yet.
    deal_id: int | None = None
    customer_name: str
    current_phase_name: str
    target_phase_name: str
    rationale: str


class RoutePlanWeekOut(BaseModel):
    week_number: int
    start_date: date
    end_date: date
    target_amount: Decimal
    expected_sales: Decimal
    shortfall_amount: Decimal
    attainment_rate: float
    target_gross_profit: Decimal = Decimal("0")
    expected_gross_profit: Decimal = Decimal("0")
    visit_count: int
    customer_names: list[str] = Field(default_factory=list)
    focus: str
    focus_is_ai_generated: bool = False
    deal_progress_goals: list[WeekDealProgressGoalOut] = Field(default_factory=list)
    days: list[RoutePlanBatchDayOut] = Field(default_factory=list)


class RoutePlanPortfolioCustomerOut(BaseModel):
    customer_id: int
    customer_name: str
    customer_type: Literal["new", "ongoing"] = "ongoing"
    planned_sales: Decimal
    expected_sales: Decimal
    expected_gross_profit: Decimal | None = None
    salesperson_fit_score: Decimal
    required_visit_count: int = 1
    completed_visit_count: int = 0
    scheduled_visit_count: int = 0
    remaining_visit_count: int = 1
    planned_visit_count: int = 1
    visit_count_source: str = "deal.expected_visit_count"
    assigned_date: date
    assigned_dates: list[date] = Field(default_factory=list)
    selection_reason: str
    loss_risk: Literal["low", "medium", "high"] = "low"
    delay_risk: Literal["low", "medium", "high"] = "low"
    risk_reasons: list[str] = Field(default_factory=list)


class RoutePlanBatchPreviewOut(BaseModel):
    batch_id: int
    rep_id: int
    rep_name: str
    horizon: Literal["week", "month"]
    start_date: date
    end_date: date
    detailed_days: int
    branch: dict[str, Any]
    policy: str
    weights: dict[str, int]
    days: list[RoutePlanBatchDayOut]
    weeks: list[RoutePlanWeekOut] = Field(default_factory=list)
    selected_customers: list[RoutePlanPortfolioCustomerOut] = Field(default_factory=list)
    totals: dict[str, Any]
    monthly_target_amount: Decimal | None = None
    achieved_amount: Decimal = Decimal("0")
    remaining_target_amount: Decimal | None = None
    planning_target_amount: Decimal | None = None
    existing_plan_expected_sales: Decimal = Decimal("0")
    portfolio_expected_sales: Decimal = Decimal("0")
    portfolio_coverage_rate: float = 0
    # 粗利目標(sales_target.target_gross_profit)が未設定ならNone(0円目標ではない)。
    monthly_target_gross_profit: Decimal | None = None
    achieved_gross_profit: Decimal = Decimal("0")
    existing_plan_expected_gross_profit: Decimal = Decimal("0")
    # モンテカルロシミュレーションによる月末達成確率(0-1)。planning.forecast()
    # (backend/app/services/target_simulation.py)と同じエンジン・同じ意味。
    sales_achievement_probability: float = 0
    profit_achievement_probability: float | None = None
    joint_achievement_probability: float = 0
    warnings: list[str]


class GeocodingBatchOut(BaseModel):
    processed: int
    success: int
    review: int
    failed: int
