from fastapi import APIRouter

from app.db import get_connection
from app.services import ai

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    database = "ok"
    try:
        with get_connection() as conn:
            # industry がある = 現行マイグレーション適用済み。古い UUID スキーマだと失敗する。
            conn.execute("select 1 from industry limit 1")
    except Exception:
        database = "unavailable"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
    }


@router.get("/api/ai/ping")
def ai_ping() -> dict[str, str]:
    result = ai.ping()
    return {
        "status": result.status,
        "message": result.message,
        "provider": result.provider,
    }
