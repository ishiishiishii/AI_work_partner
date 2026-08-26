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
        custom_weights = (
            self.sales_weight_percent,
            self.gross_profit_weight_percent,
        )
        if any(value is not None for value in custom_weights):
            if any(value is None for value in custom_weights):
                raise ValueError(
                    "sales_weight_percent and gross_profit_weight_percent must be set together"
                )
            if sum(value for value in custom_weights if value is not None) != 100:
                raise ValueError("sales and gross-profit weights must add up to 100")
        if self.work_start >= self.work_end:
            raise ValueError("work_start must be earlier than work_end")
        if self.break_enabled:
            if self.break_start >= self.break_end:
                raise ValueError("break_start must be earlier than break_end")
            if self.break_start < self.work_start or self.break_end > self.work_end:
                raise ValueError("break must be within working hours")
        work_minutes = (
            self.work_end.hour * 60 + self.work_end.minute
            - self.work_start.hour * 60 - self.work_start.minute
        )
        if self.return_buffer_min >= work_minutes:
            raise ValueError("return_buffer_min must be shorter than working hours")
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


class RoutePlanRejectOut(BaseModel):
    plan_id: int
    status: Literal["rejected"]


class GeocodingBatchOut(BaseModel):
    processed: int
    success: int
    review: int
    failed: int
