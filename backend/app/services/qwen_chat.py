import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings


@dataclass(frozen=True)
class ChatResult:
    answer: str
    model: str


class QwenChatError(RuntimeError):
    """Raised when the configured Qwen endpoint cannot return an answer."""


def _extract_content(response: httpx.Response) -> str:
    try:
        message = response.json()["choices"][0]["message"]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise QwenChatError("Qwenから不正な形式の応答を受信しました。") from error

    content = message.get("content") or message.get("reasoning_content")
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    if not isinstance(content, str) or not content.strip():
        raise QwenChatError("Qwenから空の応答を受信しました。")
    return content.strip()


def ask(
    *,
    question: str,
    history: list[dict[str, str]],
    context: dict[str, Any],
) -> ChatResult:
    context_json = json.dumps(context, ensure_ascii=False, default=str)[:40_000]
    system_prompt = (
        "あなたは営業担当者を支援するAI Work Partnerです。"
        "必ず日本語で、結論を先に、具体的かつ簡潔に回答してください。"
        "以下のダッシュボードデータを事実情報として利用してください。"
        "データに無い事実を推測で断定せず、不足している場合はその旨を伝えてください。"
        "金額・確率・日付など、回答の根拠になる数値があれば示してください。\n"
        f"<dashboard_data>{context_json}</dashboard_data>"
    )
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-10:])
    messages.append({"role": "user", "content": question})

    try:
        response = httpx.post(
            f"{settings.ai_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.ai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.ai_model,
                "messages": messages,
                "temperature": 0.4,
                "max_tokens": 10000,
                # 回答本文だけを返し、モデルの思考過程は画面に表示しない。
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=120,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise QwenChatError(
            f"Qwen APIがエラーを返しました (HTTP {error.response.status_code})。"
        ) from error
    except httpx.RequestError as error:
        raise QwenChatError("Qwen APIに接続できませんでした。") from error

    return ChatResult(answer=_extract_content(response), model=settings.ai_model)
