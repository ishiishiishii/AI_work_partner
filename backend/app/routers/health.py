from fastapi import APIRouter

from app.services import ai

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
