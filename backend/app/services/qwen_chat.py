import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from zoneinfo import ZoneInfo
import httpx

from app.config import settings


@dataclass(frozen=True)
class ChatResult:
    answer: str
    model: str


class QwenChatError(RuntimeError):
    """Raised when the configured Qwen endpoint cannot return an answer."""


CREATE_SALES_ROUTE_PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "create_sales_route_plan",
        "description": "指定日の営業訪問ルート案を売上予定額・予定粗利・指定した移動手段と休憩時間から作成する。",
        "parameters": {
            "type": "object",
            "properties": {
                "target_date": {
                    "type": "string",
                    "format": "date",
                    "description": "Asia/Tokyoで確定したYYYY-MM-DD",
                },
                "policy": {
                    "type": "string",
                    "enum": ["balanced", "sales", "gross_profit", "short_travel"],
                    "default": "balanced",
                },
                "max_visits": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 4,
                },
                "travel_mode": {
                    "type": "string",
                    "enum": ["driving", "transit", "walking", "cycling"],
                    "default": "driving",
                },
                "start_location": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": ["branch", "custom"]},
                        "address": {"type": "string"},
                    },
                    "required": ["kind"],
                    "additionalProperties": False,
                },
                "end_location": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": ["branch", "custom"]},
                        "address": {"type": "string"},
                    },
                    "required": ["kind"],
                    "additionalProperties": False,
                },
                "break_enabled": {"type": "boolean", "default": True},
                "break_start": {"type": "string", "format": "time", "default": "12:00"},
                "break_end": {"type": "string", "format": "time", "default": "13:00"},
                "min_expected_sales": {"type": "integer", "minimum": 0},
                "min_expected_gross_profit": {"type": "integer"},
            },
            "required": ["target_date"],
            "additionalProperties": False,
        },
    },
}


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


def _post_chat(payload: dict[str, Any]) -> httpx.Response:
    try:
        response = httpx.post(
            f"{settings.ai_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.ai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        return response
    except httpx.HTTPStatusError as error:
        raise QwenChatError(
            f"Qwen APIがエラーを返しました (HTTP {error.response.status_code})。"
        ) from error
    except httpx.RequestError as error:
        raise QwenChatError("Qwen APIに接続できませんでした。") from error


def ask(
    *,
    question: str,
    history: list[dict[str, str]],
    context: dict[str, Any],
    tool_executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> ChatResult:
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat()
    context_json = json.dumps(context, ensure_ascii=False, default=str)[:40_000]
    system_prompt = (
        "あなたは営業担当者を支援するAI Work Partnerです。"
        "必ず日本語で、結論を先に、具体的かつ簡潔に回答してください。"
        "以下のダッシュボードデータを事実情報として利用してください。"
        "データに無い事実を推測で断定せず、不足している場合はその旨を伝えてください。"
        "金額・確率・日付など、回答の根拠になる数値があれば示してください。"
        "営業ルート作成依頼では必ずcreate_sales_route_planを使い、"
        "住所・金額・順番を自分で補完しないでください。"
        "ツール結果の数値は再計算や丸め直しをせず、予定値である注記を含めてください。"
        "ツール失敗時も住所の手入力やWeb検索を提案せず、エラーコードに応じて"
        "Geocoding状態、Google Routes/ODPT経路検索設定、担当エリア、進行中商談の登録状態だけを"
        "確認するよう案内してください。"
        f"今日の日付はAsia/Tokyoで{today}です。\n"
        f"<dashboard_data>{context_json}</dashboard_data>"
    )
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-10:])
    messages.append({"role": "user", "content": question})

    payload: dict[str, Any] = {
        "model": settings.ai_model,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 10000,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if tool_executor is not None:
        payload["tools"] = [CREATE_SALES_ROUTE_PLAN_TOOL]
        payload["tool_choice"] = "auto"

    response = _post_chat(payload)
    message = response.json()["choices"][0]["message"]
    tool_calls = message.get("tool_calls") or []
    if tool_calls and tool_executor is not None:
        call = tool_calls[0]
        function = call.get("function", {})
        if function.get("name") != "create_sales_route_plan":
            raise QwenChatError("Qwenが未許可のツールを要求しました。")
        try:
            arguments = json.loads(function.get("arguments") or "{}")
            tool_result = tool_executor(arguments)
        except Exception as error:
            tool_result = {
                "status": "error",
                "code": getattr(error, "code", "tool_error"),
                "message": str(error),
            }
        messages.append(
            {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": tool_calls,
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.get("id"),
                "name": "create_sales_route_plan",
                "content": json.dumps(tool_result, ensure_ascii=False, default=str),
            }
        )
        response = _post_chat(
            {
                "model": settings.ai_model,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 10000,
                "chat_template_kwargs": {"enable_thinking": False},
            }
        )

    return ChatResult(answer=_extract_content(response), model=settings.ai_model)
