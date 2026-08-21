from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SalesRepOut(OrmModel):
    rep_id: UUID
    rep_name: str
    coverage_area: str | None = None


class TargetCreate(BaseModel):
    rep_id: UUID
    target_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    target_amount: Decimal = Field(ge=0)
    target_deal_count: int = Field(default=0, ge=0)


class TargetOut(OrmModel):
    rep_id: UUID
    target_month: str
    target_amount: Decimal
    target_deal_count: int


class CustomerCreate(BaseModel):
    customer_name: str
    primary_rep_id: UUID
    industry: str | None = None
    location: str | None = None
    estimated_amount: Decimal = Field(default=Decimal("0"), ge=0)
    win_probability: int = Field(default=50, ge=0, le=100)
    status: str = Field(default="prospect")


class CustomerOut(OrmModel):
    customer_id: UUID
    customer_name: str
    industry: str | None = None
    location: str | None = None
    estimated_amount: Decimal
    win_probability: int
    primary_rep_id: UUID
    status: str


class PlanOut(OrmModel):
    plan_id: UUID
    rep_id: UUID
    plan_date: date
    customer_id: UUID | None = None
    deal_id: UUID | None = None
    activity_type: str
    priority: int
    expected_amount: Decimal
    expected_probability: int
    plan_status: str
    is_ai_generated: bool
    rationale: str | None = None


class PlanGenerateRequest(BaseModel):
    rep_id: UUID
    target_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    start_date: date | None = None


class PlanGenerateResponse(BaseModel):
    plans: list[PlanOut]
    message: str


class ResultCreate(BaseModel):
    rep_id: UUID
    outcome: str = Field(pattern=r"^(won|lost|deferred|progress|other)$")
    result_date: date | None = None
    plan_id: UUID | None = None
    customer_id: UUID | None = None
    deal_id: UUID | None = None
    activity_type: str = "visit"
    outcome_note: str | None = None


class ResultOut(OrmModel):
    result_id: UUID
    plan_id: UUID | None = None
    rep_id: UUID
    result_date: date
    customer_id: UUID | None = None
    deal_id: UUID | None = None
    activity_type: str
    outcome: str
    outcome_note: str | None = None
    created_at: datetime | None = None


class ReplanRequest(BaseModel):
    rep_id: UUID
    target_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class ForecastOut(BaseModel):
    rep_id: UUID
    target_month: str
    target_amount: Decimal
    expected_amount: Decimal
    attainment_ratio: float
    open_plan_count: int
