from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _business_week_number(plan_date: date) -> int:
    """月内の月曜始まり週を、その月の最初の営業日から連番で数える。
    route_planning.py の _business_weeks と同じ週の区切り方だが、activity_plan には
    week_number を永続化していないため plan_date から都度算出する。"""
    first_of_month = plan_date.replace(day=1)
    first_business_day = first_of_month
    while first_business_day.weekday() >= 5:
        first_business_day += timedelta(days=1)
    monday_of_date = plan_date - timedelta(days=plan_date.weekday())
    monday_of_first = first_business_day - timedelta(days=first_business_day.weekday())
    diff_days = (monday_of_date - monday_of_first).days
    return max(1, diff_days // 7 + 1)


class SalesRepOut(OrmModel):
    rep_id: int
    rep_name: str
    branch_id: int
    branch_name: str


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
    # None = 粗利目標を設定しない(0円目標という意味ではない)。上流のUI/DBどちらでも
    # NULLと0円を混同しないこと。
    target_gross_profit: Decimal | None = Field(default=None, ge=0)


class TargetOut(OrmModel):
    rep_id: int
    target_month: str
    target_amount: Decimal
    target_deal_count: int
    target_gross_profit: Decimal | None = None


class CustomerCreate(BaseModel):
    customer_name: str
    industry_id: int
    company_size_id: int
    location: str
    primary_rep_id: int | None = None
    website: str | None = None
    contact_name: str | None = None


class CustomerOut(OrmModel):
    customer_id: int
    customer_name: str
    industry_name: str
    company_size_name: str
    location: str
    primary_rep_id: int | None = None
    primary_rep_name: str | None = None
    in_territory: bool = True
    has_relationship: bool = True
    website: str | None = None
    contact_name: str | None = None
    # 市区町村レベルの実座標(国土地理院APIでジオコーディング済みの場合のみ)。
    # 未ジオコーディングの間はNoneで、フロント側が都道府県+ランダムズレにフォールバックする。
    lat: float | None = None
    lng: float | None = None


# 新規顧客登録フォームの「顧客名で検索」用。他の担当者が登録済みの同名顧客が
# あれば候補として出し、選択時に業種/企業規模/所在地などを丸ごと流用できるよう
# id・name両方を持たせている(CustomerOutはid.を持たないため、選択後にフォームの
# セレクトボックスへ反映するにはidが要る)。
class CustomerSuggestionOut(OrmModel):
    customer_id: int
    customer_name: str
    industry_id: int
    industry_name: str
    company_size_id: int
    company_size_name: str
    location: str
    website: str | None = None
    contact_name: str | None = None


class StaleCustomerOut(OrmModel):
    customer_id: int
    customer_name: str
    industry_name: str
    company_size_name: str
    location: str
    primary_rep_id: int | None = None
    primary_rep_name: str | None = None
    in_territory: bool = True
    has_relationship: bool = True
    last_contact_date: date | None = None
    days_since_contact: int | None = None


class DealCreate(BaseModel):
    customer_id: int
    rep_id: int
    product_id: int
    deal_phase_id: int
    estimated_amount: Decimal = Field(ge=0)
    expected_visit_count: int = Field(ge=0)
    expected_effort_hours: Decimal = Field(ge=0)
    deal_start_date: date | None = None
    expected_close_date: date | None = None
    next_action: str | None = None
    memo: str | None = None


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
    expected_close_date: date | None = None
    next_action: str | None = None
    actual_amount: Decimal | None = None
    memo: str | None = None


class DealUpdate(BaseModel):
    product_id: int
    deal_phase_id: int
    estimated_amount: Decimal = Field(ge=0)
    expected_visit_count: int = Field(ge=0)
    expected_effort_hours: Decimal = Field(ge=0)
    expected_close_date: date | None = None
    next_action: str | None = None
    # 成約(won)済みの商談のみ有効。未成約に送っても保存時のトリガーで拒否される
    actual_amount: Decimal | None = Field(default=None, ge=0)
    memo: str | None = None


class CustomerWinRateOut(OrmModel):
    customer_id: int
    closed_count: int
    won_count: int
    win_rate: int | None = None


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


class AdminTaskTypeOut(OrmModel):
    task_type_id: int
    task_name: str
    is_default: bool


class AdminTaskTypeCreate(BaseModel):
    task_name: str


class RepHomeOfficeDayOut(OrmModel):
    day_of_week: int
    is_home_available: bool


class HomeOfficeAvailabilityUpdate(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    is_home_available: bool


class RepAdminTaskDurationOut(OrmModel):
    task_type_id: int
    task_name: str
    duration_minutes: int | None = None
    updated_at: datetime | None = None


class AdminTaskDurationUpdate(BaseModel):
    duration_minutes: int = Field(ge=0)


class RepProfileOut(BaseModel):
    rep_id: int
    home_office: list[RepHomeOfficeDayOut]
    task_durations: list[RepAdminTaskDurationOut]


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
    result_status: str | None = None

    @computed_field
    @property
    def week_number(self) -> int:
        return _business_week_number(self.plan_date)


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
    product_name_override: str | None = None


class PlanUpdate(BaseModel):
    plan_date: date
    start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    category: str = Field(pattern=r"^(visit|task)$")
    activity_type: str
    title: str | None = None
    customer_id: int | None = None
    product_name_override: str | None = None
    expected_amount: Decimal = Field(default=Decimal("0"), ge=0)
    expected_probability: int = Field(default=0, ge=0, le=100)
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
    description: str
    price_min: int
    price_max: int
    lead_time_days: int
    features: list[str]


class ReplanRequest(BaseModel):
    rep_id: int
    target_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    # 結果を入力した予定日から将来計画を組み直せるよう、画面側が基準日を渡す。
    # 未指定の既存クライアントは従来どおりAPI実行日を基準にする。
    start_date: date | None = None


class ForecastOut(BaseModel):
    rep_id: int
    target_month: str
    target_amount: Decimal
    expected_amount: Decimal
    attainment_ratio: float
    open_plan_count: int
    # 粗利・達成確率まわりは目標に粗利設定が無ければNone(0%達成という意味ではない)。
    target_gross_profit: Decimal | None = None
    expected_gross_profit: Decimal = Decimal("0")
    gross_profit_attainment_ratio: float | None = None
    sales_achievement_probability: float = 0.0
    profit_achievement_probability: float | None = None
    joint_achievement_probability: float = 0.0
    sales_gap_amount: Decimal = Decimal("0")
    profit_gap_amount: Decimal | None = None

class DeadlineCreate(BaseModel):
    rep_id: int
    title: str = Field(min_length=1)
    due_date: date
    customer_id: int | None = None
    deal_id: int | None = None
    memo: str | None = None


class DeadlineOut(OrmModel):
    deadline_id: int
    rep_id: int
    title: str
    due_date: date
    customer_id: int | None = None
    deal_id: int | None = None
    is_done: bool = False
    memo: str | None = None
    created_at: datetime | None = None


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
