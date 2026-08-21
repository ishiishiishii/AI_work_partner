from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.db import get_connection
from app.schemas.models import (
    CustomerCreate,
    CustomerOut,
    ForecastOut,
    PlanGenerateRequest,
    PlanGenerateResponse,
    PlanOut,
    ReplanRequest,
    ResultCreate,
    ResultOut,
    TargetCreate,
    TargetOut,
)
from app.services import planning

router = APIRouter(prefix="/api", tags=["mvp"])


@router.get("/targets", response_model=list[TargetOut])
def get_targets(rep_id: UUID | None = None) -> list[TargetOut]:
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
def get_customers(rep_id: UUID | None = None) -> list[CustomerOut]:
    with get_connection() as conn:
        rows = planning.list_customers(conn, rep_id)
    return [CustomerOut.model_validate(row) for row in rows]


@router.post("/customers", response_model=CustomerOut)
def post_customer(body: CustomerCreate) -> CustomerOut:
    with get_connection() as conn:
        try:
            row = planning.create_customer(
                conn,
                customer_name=body.customer_name,
                primary_rep_id=body.primary_rep_id,
                industry=body.industry,
                location=body.location,
                estimated_amount=body.estimated_amount,
                win_probability=body.win_probability,
                status=body.status,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CustomerOut.model_validate(row)


@router.get("/plans", response_model=list[PlanOut])
def get_plans(
    rep_id: UUID = Query(...),
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[PlanOut]:
    with get_connection() as conn:
        rows = planning.list_plans(
            conn, rep_id=rep_id, from_date=from_date, to_date=to_date
        )
    return [PlanOut.model_validate(row) for row in rows]


@router.post("/plans/generate", response_model=PlanGenerateResponse)
def post_plans_generate(body: PlanGenerateRequest) -> PlanGenerateResponse:
    with get_connection() as conn:
        plans = planning.generate_plans(
            conn,
            rep_id=body.rep_id,
            target_month=body.target_month,
            start_date=body.start_date,
        )
    return PlanGenerateResponse(
        plans=plans,
        message="Generated a skeleton plan from open deals (expected value order).",
    )


@router.post("/plans/replan", response_model=PlanGenerateResponse)
def post_plans_replan(body: ReplanRequest) -> PlanGenerateResponse:
    with get_connection() as conn:
        plans = planning.generate_plans(
            conn,
            rep_id=body.rep_id,
            target_month=body.target_month,
            start_date=date.today(),
        )
    return PlanGenerateResponse(
        plans=plans,
        message="Replanned from remaining open deals after latest outcomes.",
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


@router.get("/forecast", response_model=ForecastOut)
def get_forecast(
    rep_id: UUID = Query(...),
    target_month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
) -> ForecastOut:
    with get_connection() as conn:
        try:
            row = planning.forecast(conn, rep_id=rep_id, target_month=target_month)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ForecastOut.model_validate(row)
