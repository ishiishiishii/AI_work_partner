import json
from dataclasses import dataclass
from typing import Any

from psycopg import Connection

import httpx

from app.config import settings


@dataclass(frozen=True)
class AiPingResult:
    status: str
    message: str
    provider: str


def ping() -> AiPingResult:
    try:
        response = httpx.post(
            f"{settings.ai_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.ai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.ai_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "あなたは営業計画を支援するAI Work Partnerです。"
                            "日本語で簡潔に回答してください。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Webアプリとの接続確認として、"
                            "利用可能であることを一文で答えてください。"
                        ),
                    },
                ],
                "temperature": 0.2,
                "max_tokens": 100,
            },
            timeout=120,
        )

        response.raise_for_status()

        message = response.json()["choices"][0]["message"]
        content = (
            message.get("content")
            or message.get("reasoning_content")
            or "Qwenから応答を受信しました。"
        )

        return AiPingResult(
            status="ok",
            message=content,
            provider=f"vLLM / {settings.ai_model}",
        )

    except Exception as error:
        return AiPingResult(
            status="error",
            message=f"Qwen connection failed: {error}",
            provider="vLLM",
        )


def log_response(
    conn: Connection,
    *,
    context: str,
    response: str,
    rep_id: int | None = None,
    prompt: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict:
    """Persist one AI prompt/response pair to `ai_response_log`.

    Not called anywhere yet -- this is the landing pad for whatever calls
    the real model once one is wired in, so that integration doesn't also
    need a schema change.
    """
    row = conn.execute(
        """
        insert into ai_response_log (rep_id, context, prompt, response, metadata)
        values (%s, %s, %s, %s, %s)
        returning log_id, created_at, rep_id, context, prompt, response, metadata
        """,
        (rep_id, context, prompt, response, json.dumps(metadata) if metadata else None),
    ).fetchone()
    conn.commit()
    return dict(row)