from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SalesRepOut(OrmModel):
    rep_id: int
    rep_name: str


class TargetCreate(BaseModel):
    rep_id: int
    target_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    target_amount: Decimal = Field(ge=0)
    target_deal_count: int = Field(default=0, ge=0)


class TargetOut(OrmModel):
    rep_id: int
    target_month: str
    target_amount: Decimal
    target_deal_count: int


class CustomerCreate(BaseModel):
    customer_name: str
    industry_id: int
    company_size_id: int
    location: str
    primary_rep_id: int | None = None


class CustomerOut(OrmModel):
    customer_id: int
    customer_name: str
    industry_id: int
    company_size_id: int
    location: str
    primary_rep_id: int | None = None


class DealCreate(BaseModel):
    customer_id: int
    rep_id: int
    product_id: int
    deal_phase_id: int
    estimated_amount: Decimal = Field(ge=0)
    win_probability: int = Field(ge=0, le=100)
    expected_visit_count: int = Field(ge=0)
    expected_effort_hours: Decimal = Field(ge=0)
    deal_start_date: date | None = None


class DealOut(OrmModel):
    deal_id: int
    customer_id: int
    rep_id: int
    deal_phase_id: int
    deal_result_status_id: int
    product_id: int
    estimated_amount: Decimal
    win_probability: Decimal
    expected_visit_count: int
    expected_effort_hours: Decimal
    deal_start_date: date
    contract_date: date | None = None


class RepAffinityOut(OrmModel):
    rep_id: int
    industry_id: int
    category_id: int
    pattern_id: int
    deal_count: int
    won_count: int
    win_rate: Decimal
    avg_won_amount: Decimal
    affinity_score: Decimal
    calculated_at: datetime | None = None


class PlanOut(OrmModel):
    plan_id: int
    rep_id: int
    plan_date: date
    customer_id: int | None = None
    deal_id: int | None = None
    activity_type: str
    priority: int
    expected_amount: Decimal
    expected_probability: int
    plan_status: str
    is_ai_generated: bool
    rationale: str | None = None
    product_id: int | None = None
    product_name: str | None = None


class PlanGenerateRequest(BaseModel):
    rep_id: int
    target_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    start_date: date | None = None


class PlanGenerateResponse(BaseModel):
    plans: list[PlanOut]
    message: str


class ResultCreate(BaseModel):
    rep_id: int
    outcome: str = Field(pattern=r"^(won|lost|deferred|progress|other)$")
    result_date: date | None = None
    plan_id: int | None = None
    customer_id: int | None = None
    deal_id: int | None = None
    activity_type: str = "visit"
    outcome_note: str | None = None


class ResultOut(OrmModel):
    result_id: int
    plan_id: int | None = None
    rep_id: int
    result_date: date
    customer_id: int | None = None
    deal_id: int | None = None
    activity_type: str
    outcome: str
    outcome_note: str | None = None
    created_at: datetime | None = None


class ProductOut(OrmModel):
    product_id: int
    product_name: str
    subcategory_id: int
    subcategory_name: str
    category_id: int
    category_name: str


class ReplanRequest(BaseModel):
    rep_id: int
    target_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class ForecastOut(BaseModel):
    rep_id: int
    target_month: str
    target_amount: Decimal
    expected_amount: Decimal
    attainment_ratio: float
    open_plan_count: int
