import threading
from datetime import date

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.db import get_connection
from app.schemas.models import (
    CustomerCreate,
    CustomerOut,
    CustomerSuggestionOut,
    CustomerWinRateOut,
    DeadlineCreate,
    DeadlineOut,
    DealCreate,
    DealOut,
    DealUpdate,
    ForecastOut,
    MastersOut,
    PlanCreate,
    PlanGenerateRequest,
    PlanGenerateResponse,
    PlanOut,
    PlanProgressUpdate,
    PlanUpdate,
    ProductOut,
    RepAffinityOut,
    ReplanRequest,
    ResultCreate,
    ResultOut,
    SalesRepOut,
    StaleCustomerOut,
    TargetCreate,
    TargetOut,
    TerritoryOut,
)
from app.services import affinity, geocoding, planning

router = APIRouter(prefix="/api", tags=["mvp"])


@router.get("/reps", response_model=list[SalesRepOut])
def get_reps() -> list[SalesRepOut]:
    with get_connection() as conn:
        rows = planning.list_reps(conn)
    return [SalesRepOut.model_validate(row) for row in rows]


@router.get("/reps/{rep_id}/territory", response_model=TerritoryOut)
def get_rep_territory(rep_id: int) -> TerritoryOut:
    with get_connection() as conn:
        row = planning.get_rep_territory(conn, rep_id)
    if not row:
        raise HTTPException(status_code=404, detail="rep not found")
    return TerritoryOut.model_validate(row)


@router.get("/masters", response_model=MastersOut)
def get_masters() -> MastersOut:
    with get_connection() as conn:
        return MastersOut.model_validate(planning.list_masters(conn))


@router.get("/targets", response_model=list[TargetOut])
def get_targets(rep_id: int | None = None) -> list[TargetOut]:
    with get_connection() as conn:
        rows = planning.list_targets(conn, rep_id)
    return [TargetOut.model_validate(row) for row in rows]


@router.post("/targets", response_model=TargetOut)
def post_target(body: TargetCreate) -> TargetOut:
    with get_connection() as conn:
        row = planning.upsert_target(
            conn,
            rep_id=body.rep_id,
            target_month=body.target_month,
            target_amount=body.target_amount,
            target_deal_count=body.target_deal_count,
        )
    return TargetOut.model_validate(row)


@router.get("/customers", response_model=list[CustomerOut])
def get_customers(background_tasks: BackgroundTasks, rep_id: int | None = None) -> list[CustomerOut]:
    with get_connection() as conn:
        rows = planning.list_customers(conn, rep_id)
    # 未ジオコーディングの顧客を少しずつ埋める(レスポンスは待たせない)。db resetのたびに
    # lat/lngは消えるが、api再起動有無に関わらず通常のアクセスが続けば自然に埋まっていく
    # -- コンテナ再起動タイミングに賭けた仕組みにはしない(過去のログイン問題と同じ轍を踏まない)。
    background_tasks.add_task(_backfill_customer_coordinates)
    return [CustomerOut.model_validate(row) for row in rows]


# 複数の担当者がほぼ同時にダッシュボードを開くと、リクエストごとに積み上がった
# バックフィルが接続プール(max_size=5)を食いつぶし、他の担当者の通常リクエストが
# プールのタイムアウト(30秒)まで固まる不具合があった。同時に1つしか走らせない
# ようにするだけで直る問題であり、「レスポンスは待たせず少しずつ埋める」という
# 元の設計自体は変えない(取れなければ今回はスキップし、次のアクセスでまた試みる)。
_backfill_lock = threading.Lock()


def _backfill_customer_coordinates() -> None:
    if not _backfill_lock.acquire(blocking=False):
        return
    try:
        with get_connection() as conn:
            geocoding.backfill_customer_coordinates(conn)
    finally:
        _backfill_lock.release()


@router.post("/customers", response_model=CustomerOut)
def post_customer(body: CustomerCreate) -> CustomerOut:
    with get_connection() as conn:
        try:
            row = planning.create_customer(
                conn,
                customer_name=body.customer_name,
                industry_id=body.industry_id,
                company_size_id=body.company_size_id,
                location=body.location,
                primary_rep_id=body.primary_rep_id,
                website=body.website,
                contact_name=body.contact_name,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CustomerOut.model_validate(row)


# 新規顧客登録フォームの「顧客名で検索」候補用。担当エリアやhas_relationshipで
# 絞らず、全担当者の登録済み顧客から部分一致で探す(重複登録に気づけるように)。
@router.get("/customers/search", response_model=list[CustomerSuggestionOut])
def get_customer_search(q: str = Query(min_length=1)) -> list[CustomerSuggestionOut]:
    with get_connection() as conn:
        rows = planning.search_customers(conn, query=q)
    return [CustomerSuggestionOut.model_validate(row) for row in rows]


@router.get("/customers/stale", response_model=list[StaleCustomerOut])
def get_stale_customers(
    threshold_days: int = Query(planning.STALE_THRESHOLD_DAYS, ge=1),
    rep_id: int | None = None,
) -> list[StaleCustomerOut]:
    with get_connection() as conn:
        rows = planning.list_stale_customers(
            conn, threshold_days=threshold_days, rep_id=rep_id
        )
    return [StaleCustomerOut.model_validate(row) for row in rows]


@router.get("/customers/{customer_id}/win-rate", response_model=CustomerWinRateOut)
def get_customer_win_rate(customer_id: int) -> CustomerWinRateOut:
    with get_connection() as conn:
        row = affinity.customer_win_rate_summary(conn, customer_id)
    return CustomerWinRateOut.model_validate(row)


@router.get("/deadlines", response_model=list[DeadlineOut])
def get_deadlines(rep_id: int | None = None) -> list[DeadlineOut]:
    with get_connection() as conn:
        rows = planning.list_deadlines(conn, rep_id)
    return [DeadlineOut.model_validate(row) for row in rows]


@router.post("/deadlines", response_model=DeadlineOut)
def post_deadline(body: DeadlineCreate) -> DeadlineOut:
    with get_connection() as conn:
        try:
            row = planning.create_deadline(
                conn,
                rep_id=body.rep_id,
                title=body.title,
                due_date=body.due_date,
                customer_id=body.customer_id,
                deal_id=body.deal_id,
                memo=body.memo,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DeadlineOut.model_validate(row)


@router.get("/deals", response_model=list[DealOut])
def get_deals(rep_id: int | None = None) -> list[DealOut]:
    with get_connection() as conn:
        rows = planning.list_deals(conn, rep_id)
    return [DealOut.model_validate(row) for row in rows]


@router.post("/deals", response_model=DealOut)
def post_deal(body: DealCreate) -> DealOut:
    with get_connection() as conn:
        try:
            row = planning.create_deal(
                conn,
                customer_id=body.customer_id,
                rep_id=body.rep_id,
                product_id=body.product_id,
                deal_phase_id=body.deal_phase_id,
                estimated_amount=body.estimated_amount,
                expected_visit_count=body.expected_visit_count,
                expected_effort_hours=body.expected_effort_hours,
                deal_start_date=body.deal_start_date or date.today(),
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DealOut.model_validate(row)


@router.patch("/deals/{deal_id}", response_model=DealOut)
def patch_deal(deal_id: int, body: DealUpdate, rep_id: int = Query(...)) -> DealOut:
    with get_connection() as conn:
        try:
            row = planning.update_deal(
                conn,
                deal_id=deal_id,
                rep_id=rep_id,
                product_id=body.product_id,
                deal_phase_id=body.deal_phase_id,
                estimated_amount=body.estimated_amount,
                expected_visit_count=body.expected_visit_count,
                expected_effort_hours=body.expected_effort_hours,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DealOut.model_validate(row)


@router.delete("/deals/{deal_id}", status_code=204)
def delete_deal(deal_id: int, rep_id: int = Query(...)) -> None:
    with get_connection() as conn:
        try:
            planning.delete_deal(conn, deal_id=deal_id, rep_id=rep_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/reps/{rep_id}/affinity", response_model=list[RepAffinityOut])
def get_rep_affinity(rep_id: int) -> list[RepAffinityOut]:
    with get_connection() as conn:
        rows = affinity.list_rep_affinity(conn, rep_id)
    return [RepAffinityOut.model_validate(row) for row in rows]


@router.post("/reps/affinity/recalculate", response_model=list[RepAffinityOut])
def post_rep_affinity_recalculate(rep_id: int | None = None) -> list[RepAffinityOut]:
    with get_connection() as conn:
        rows = affinity.recalculate_rep_affinity(conn, rep_id)
    return [RepAffinityOut.model_validate(row) for row in rows]


@router.get("/products", response_model=list[ProductOut])
def get_products(name: str | None = None) -> list[ProductOut]:
    with get_connection() as conn:
        rows = planning.search_products(conn, name)
    return [ProductOut.model_validate(row) for row in rows]


@router.get("/plans", response_model=list[PlanOut])
def get_plans(
    rep_id: int = Query(...),
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[PlanOut]:
    with get_connection() as conn:
        rows = planning.list_plans(
            conn, rep_id=rep_id, from_date=from_date, to_date=to_date
        )
    return [PlanOut.model_validate(row) for row in rows]


@router.post("/plans", response_model=PlanOut)
def post_plan(body: PlanCreate) -> PlanOut:
    with get_connection() as conn:
        row = planning.create_plan(
            conn,
            rep_id=body.rep_id,
            plan_date=body.plan_date,
            category=body.category,
            activity_type=body.activity_type,
            start_time=body.start_time,
            end_time=body.end_time,
            title=body.title,
            customer_id=body.customer_id,
            deal_id=body.deal_id,
            priority=body.priority,
            expected_amount=body.expected_amount,
            expected_probability=body.expected_probability,
            rationale=body.rationale,
        )
    return PlanOut.model_validate(row)


@router.delete("/plans/{plan_id}", response_model=PlanOut)
def delete_plan(plan_id: int, rep_id: int = Query(...)) -> PlanOut:
    """Soft-cancel (plan_status='cancelled'), e.g. when '対応が難しい' replaces it."""
    with get_connection() as conn:
        try:
            row = planning.cancel_plan(conn, plan_id=plan_id, rep_id=rep_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlanOut.model_validate(row)


@router.patch("/plans/{plan_id}", response_model=PlanOut)
def patch_plan(plan_id: int, body: PlanUpdate, rep_id: int = Query(...)) -> PlanOut:
    with get_connection() as conn:
        try:
            row = planning.update_plan(
                conn,
                plan_id=plan_id,
                rep_id=rep_id,
                start_time=body.start_time,
                end_time=body.end_time,
                category=body.category,
                activity_type=body.activity_type,
                title=body.title,
                product_name_override=body.product_name_override,
                memo=body.memo,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlanOut.model_validate(row)


@router.patch("/plans/{plan_id}/progress", response_model=PlanOut)
def patch_plan_progress(
    plan_id: int, body: PlanProgressUpdate, rep_id: int = Query(...)
) -> PlanOut:
    with get_connection() as conn:
        try:
            row = planning.update_plan_progress(
                conn,
                plan_id=plan_id,
                rep_id=rep_id,
                progress_percent=body.progress_percent,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlanOut.model_validate(row)


@router.post("/plans/generate", response_model=PlanGenerateResponse)
def post_plans_generate(body: PlanGenerateRequest) -> PlanGenerateResponse:
    with get_connection() as conn:
        plans, used_ai = planning.generate_plans(
            conn,
            rep_id=body.rep_id,
            target_month=body.target_month,
            start_date=body.start_date,
        )
    return PlanGenerateResponse(
        plans=plans,
        message="AIが商談候補から計画を生成しました。"
        if used_ai
        else "AIに接続できなかったため、簡易ロジックで計画を生成しました。",
    )


@router.post("/plans/replan", response_model=PlanGenerateResponse)
def post_plans_replan(body: ReplanRequest) -> PlanGenerateResponse:
    with get_connection() as conn:
        plans, used_ai = planning.generate_plans(
            conn,
            rep_id=body.rep_id,
            target_month=body.target_month,
            start_date=date.today(),
        )
    return PlanGenerateResponse(
        plans=plans,
        message="AIが直近の結果を踏まえて再計画しました。"
        if used_ai
        else "AIに接続できなかったため、簡易ロジックで再計画しました。",
    )


@router.post("/results", response_model=ResultOut)
def post_result(body: ResultCreate) -> ResultOut:
    with get_connection() as conn:
        row = planning.create_result(
            conn,
            rep_id=body.rep_id,
            outcome=body.outcome,
            result_date=body.result_date or date.today(),
            plan_id=body.plan_id,
            customer_id=body.customer_id,
            deal_id=body.deal_id,
            activity_type=body.activity_type,
            outcome_note=body.outcome_note,
        )
    return ResultOut.model_validate(row)


@router.delete("/results/{result_id}", response_model=ResultOut)
def delete_result(result_id: int, rep_id: int = Query(...)) -> ResultOut:
    with get_connection() as conn:
        try:
            row = planning.delete_result(conn, result_id=result_id, rep_id=rep_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ResultOut.model_validate(row)


@router.get("/forecast", response_model=ForecastOut)
def get_forecast(
    rep_id: int = Query(...),
    target_month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
) -> ForecastOut:
    with get_connection() as conn:
        try:
            row = planning.forecast(conn, rep_id=rep_id, target_month=target_month)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ForecastOut.model_validate(row)
