from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_authenticated_rep_id
from app.db import get_connection
from app.schemas.route_plans import (
    RoutePlanApproveOut,
    RoutePlanBatchPreviewOut,
    RoutePlanBatchPreviewRequest,
    RoutePlanPreviewOut,
    RoutePlanPreviewRequest,
    RoutePlanRejectOut,
)
from app.services import route_planning
from app.services.route_optimization import RoutePlanningError

router = APIRouter(prefix="/api", tags=["sales-route-plans"])


def _raise_http(error: RoutePlanningError) -> None:
    status = 422
    if error.code in {
        "routes_api_unavailable",
        "google_routes_api_unavailable",
        "otp_api_unavailable",
    }:
        status = 503
    elif error.code in {"plan_not_found", "rep_not_found"}:
        status = 404
    elif error.code in {
        "schedule_conflict",
        "invalid_plan_status",
        "coarse_plan_not_approvable",
    }:
        status = 409
    raise HTTPException(
        status_code=status,
        detail={"code": error.code, "message": str(error)},
    ) from error


@router.post("/route-plans/preview", response_model=RoutePlanPreviewOut)
def preview_route_plan(
    body: RoutePlanPreviewRequest,
    rep_id: int = Depends(get_authenticated_rep_id),
) -> RoutePlanPreviewOut:
    with get_connection() as conn:
        try:
            result = route_planning.create_preview(conn, rep_id=rep_id, request=body)
        except RoutePlanningError as error:
            _raise_http(error)
    return RoutePlanPreviewOut.model_validate(result)


@router.post("/route-plans/batch-preview", response_model=RoutePlanBatchPreviewOut)
def preview_route_plan_batch(
    body: RoutePlanBatchPreviewRequest,
    rep_id: int = Depends(get_authenticated_rep_id),
) -> RoutePlanBatchPreviewOut:
    with get_connection() as conn:
        try:
            result = route_planning.create_batch_preview(conn, rep_id=rep_id, request=body)
        except RoutePlanningError as error:
            _raise_http(error)
    return RoutePlanBatchPreviewOut.model_validate(result)


@router.post("/route-plans/{plan_id}/approve", response_model=RoutePlanApproveOut)
def approve_route_plan(
    plan_id: int,
    rep_id: int = Depends(get_authenticated_rep_id),
) -> RoutePlanApproveOut:
    with get_connection() as conn:
        try:
            result = route_planning.approve_plan(conn, plan_id=plan_id, rep_id=rep_id)
        except RoutePlanningError as error:
            _raise_http(error)
    return RoutePlanApproveOut.model_validate(result)


@router.post("/route-plans/{plan_id}/reject", response_model=RoutePlanRejectOut)
def reject_route_plan(
    plan_id: int,
    rep_id: int = Depends(get_authenticated_rep_id),
) -> RoutePlanRejectOut:
    with get_connection() as conn:
        try:
            result = route_planning.reject_plan(conn, plan_id=plan_id, rep_id=rep_id)
        except RoutePlanningError as error:
            _raise_http(error)
    return RoutePlanRejectOut.model_validate(result)
