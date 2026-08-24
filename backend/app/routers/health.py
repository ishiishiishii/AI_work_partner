from fastapi import APIRouter, HTTPException

from app.schemas.models import AiChatRequest, AiChatResponse
from app.services import ai, qwen_chat

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
def ai_chat(body: AiChatRequest) -> AiChatResponse:
    try:
        result = qwen_chat.ask(
            question=body.question,
            history=[message.model_dump() for message in body.history],
            context=body.context,
        )
    except qwen_chat.QwenChatError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return AiChatResponse(answer=result.answer, model=result.model)
