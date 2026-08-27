from fastapi import APIRouter

from app.db import get_connection
from app.schemas.models import (
    AdminTaskDurationUpdate,
    AdminTaskTypeCreate,
    AdminTaskTypeOut,
    HomeOfficeAvailabilityUpdate,
    RepAdminTaskDurationOut,
    RepHomeOfficeDayOut,
    RepProfileOut,
)
from app.services import profile

router = APIRouter(prefix="/api", tags=["profile"])


@router.get("/admin-task-types", response_model=list[AdminTaskTypeOut])
def get_admin_task_types() -> list[AdminTaskTypeOut]:
    with get_connection() as conn:
        rows = profile.list_admin_task_types(conn)
    return [AdminTaskTypeOut.model_validate(row) for row in rows]


@router.post("/admin-task-types", response_model=AdminTaskTypeOut)
def post_admin_task_type(body: AdminTaskTypeCreate) -> AdminTaskTypeOut:
    with get_connection() as conn:
        row = profile.create_admin_task_type(conn, body.task_name)
    return AdminTaskTypeOut.model_validate(row)


@router.get("/reps/{rep_id}/profile", response_model=RepProfileOut)
def get_rep_profile(rep_id: int) -> RepProfileOut:
    with get_connection() as conn:
        data = profile.get_rep_profile(conn, rep_id)
    return RepProfileOut.model_validate(data)


@router.put("/reps/{rep_id}/home-office", response_model=RepHomeOfficeDayOut)
def put_rep_home_office(rep_id: int, body: HomeOfficeAvailabilityUpdate) -> RepHomeOfficeDayOut:
    with get_connection() as conn:
        row = profile.set_home_office_availability(
            conn, rep_id, body.day_of_week, body.is_home_available
        )
    return RepHomeOfficeDayOut.model_validate(row)


@router.put(
    "/reps/{rep_id}/task-durations/{task_type_id}",
    response_model=RepAdminTaskDurationOut,
)
def put_rep_task_duration(
    rep_id: int, task_type_id: int, body: AdminTaskDurationUpdate
) -> RepAdminTaskDurationOut:
    with get_connection() as conn:
        row = profile.set_admin_task_duration(
            conn, rep_id, task_type_id, body.duration_minutes
        )
    return RepAdminTaskDurationOut.model_validate(row)
