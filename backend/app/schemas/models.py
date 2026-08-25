from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SalesRepOut(OrmModel):
    rep_id: int
    rep_name: str


class TerritoryOut(BaseModel):
    branch_name: str
    prefectures: list[str]


class IndustryOut(OrmModel):
    industry_id: int
    industry_name: str


class CompanySizeOut(OrmModel):
    company_size_id: int
    company_size_name: str


class DealPhaseOut(OrmModel):
    deal_phase_id: int
    deal_phase_name: str


class MastersOut(BaseModel):
    industries: list[IndustryOut]
    company_sizes: list[CompanySizeOut]
    deal_phases: list[DealPhaseOut]


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
    industry_name: str
    company_size_name: str
    location: str
    primary_rep_id: int | None = None
    primary_rep_name: str | None = None
    # 市区町村レベルの実座標(国土地理院APIでジオコーディング済みの場合のみ)。
    # 未ジオコーディングの間はNoneで、フロント側が都道府県+ランダムズレにフォールバックする。
    lat: float | None = None
    lng: float | None = None


class StaleCustomerOut(OrmModel):
    customer_id: int
    customer_name: str
    industry_name: str
    company_size_name: str
    location: str
    primary_rep_id: int | None = None
    primary_rep_name: str | None = None
    last_contact_date: date | None = None
    days_since_contact: int | None = None


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
    customer_name: str
    rep_id: int
    rep_name: str
    deal_phase_name: str
    deal_result_status: str
    product_name: str
    subcategory_name: str
    category_name: str
    estimated_amount: Decimal
    win_probability: Decimal
    expected_visit_count: int
    expected_effort_hours: Decimal
    deal_start_date: date
    contract_date: date | None = None
    product_id: int
    deal_phase_id: int
    cost: Decimal
    profit: Decimal


class DealUpdate(BaseModel):
    product_id: int
    deal_phase_id: int
    estimated_amount: Decimal = Field(ge=0)
    win_probability: int = Field(ge=0, le=100)
    expected_visit_count: int = Field(ge=0)
    expected_effort_hours: Decimal = Field(ge=0)


class RepAffinityOut(OrmModel):
    rep_id: int
    rep_name: str
    industry_name: str
    category_name: str
    pattern_name: str
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
    start_time: str | None = None
    end_time: str | None = None
    category: str = "visit"
    title: str | None = None
    customer_id: int | None = None
    deal_id: int | None = None
    activity_type: str
    priority: int
    expected_amount: Decimal
    expected_probability: int
    plan_status: str
    is_ai_generated: bool
    rationale: str | None = None
    product_name: str | None = None
    progress_percent: int = 0
    memo: str | None = None


class PlanCreate(BaseModel):
    rep_id: int
    plan_date: date
    category: str = Field(pattern=r"^(visit|task)$")
    activity_type: str = "visit"
    start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    title: str | None = None
    customer_id: int | None = None
    deal_id: int | None = None
    priority: int = Field(default=3, ge=1, le=5)
    expected_amount: Decimal = Field(default=Decimal("0"), ge=0)
    expected_probability: int = Field(default=0, ge=0, le=100)
    rationale: str | None = None


class PlanUpdate(BaseModel):
    start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    category: str = Field(pattern=r"^(visit|task)$")
    activity_type: str
    title: str | None = None
    product_name_override: str | None = None
    memo: str | None = None


class PlanProgressUpdate(BaseModel):
    progress_percent: int = Field(ge=0, le=100)


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

class AiChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4_000)


class AiChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)
    history: list[AiChatMessage] = Field(default_factory=list, max_length=20)
    context: dict[str, Any] = Field(default_factory=dict)


class AiChatResponse(BaseModel):
    answer: str
    model: str

