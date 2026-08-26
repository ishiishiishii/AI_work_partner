from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_authenticated_rep_id
from app.db import get_connection
from app.schemas.models import AiChatRequest, AiChatResponse
from app.schemas.route_plans import RoutePlanPreviewRequest
from app.services import ai, qwen_chat, route_planning

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/ai/ping")
def ai_ping() -> dict[str, str]:
    result = ai.ping()
    return {
        "status": result.status,
        "message": result.message,
        "provider": result.provider,
    }


@router.post("/api/ai/chat", response_model=AiChatResponse)
def ai_chat(
    body: AiChatRequest,
    rep_id: int = Depends(get_authenticated_rep_id),
) -> AiChatResponse:
    def create_sales_route_plan(arguments: dict) -> dict:
        request = RoutePlanPreviewRequest.model_validate(arguments)
        with get_connection() as conn:
            return route_planning.create_preview(
                conn, rep_id=rep_id, request=request
            )

    try:
        result = qwen_chat.ask(
            question=body.question,
            history=[message.model_dump() for message in body.history],
            context=body.context,
            tool_executor=create_sales_route_plan,
        )
    except qwen_chat.QwenChatError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return AiChatResponse(answer=result.answer, model=result.model)
