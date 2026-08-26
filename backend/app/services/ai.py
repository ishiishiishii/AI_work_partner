import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from psycopg import Connection

import httpx

from app.config import settings
from app.services.qwen_chat import _extract_content


class AiPlanningError(RuntimeError):
    """Raised when the AI planner is unreachable or returns nothing usable.

    Callers fall back to rule-based planning on this -- AGENTS.md keeps AI a
    replaceable boundary, so a Qwen outage must never block plan generation.
    """


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


def _parse_plan_items(content: str) -> list[Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text.removeprefix("json").strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise AiPlanningError("Qwenの応答からJSON配列を取り出せませんでした。")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, list):
        raise AiPlanningError("Qwenの応答がJSON配列ではありませんでした。")
    return parsed


# Fixed activity_type vocabulary, matching frontend/components/dashboard/
# ActivityPlanList.tsx's EDITABLE_ACTIVITY_TYPES -- the AI must pick from
# this list rather than invent free text, so the UI's type styling/labels
# keep working for AI-generated plans too.
_VALID_ACTIVITY_TYPES = {"訪問", "電話", "メール", "Web会議", "資料作成", "新規開拓"}
_VALID_CATEGORIES = {"visit", "task"}
_MAX_PLAN_ITEMS = 60


def generate_plan_selection(
    conn: Connection,
    *,
    rep_id: int,
    target_month: str,
    base_date: date,
    month_end: date,
    candidates: list[dict],
    sales_target: dict | None,
) -> list[dict]:
    """Ask Qwen for this month's full activity mix -- not just which deals to
    visit, but also prep/follow-up/prospecting tasks (資料作成・電話・メール・
    新規開拓) -- with date, priority, and rationale for each. Only selection/
    scheduling/rationale come from the model -- amounts and probabilities for
    deal-linked items are always re-read from the deal row by the caller,
    never trusted from model output.
    """
    candidate_payload = [
        {
            "deal_id": c["deal_id"],
            "customer_name": c["customer_name"],
            "industry_name": c["industry_name"] or "不明",
            "product_name": c["product_name"],
            "estimated_amount": float(c["estimated_amount"]),
            "win_probability": c["win_probability"],
            "last_contact_date": c["last_contact_date"].isoformat() if c["last_contact_date"] else None,
            "is_stale": c["is_stale"],
        }
        for c in candidates
    ]
    target_payload = (
        {
            "target_amount": float(sales_target["target_amount"]),
            "target_deal_count": sales_target["target_deal_count"],
        }
        if sales_target
        else None
    )
    user_payload = {
        "target_month": target_month,
        "sales_target": target_payload,
        "candidate_deals": candidate_payload,
    }

    system_prompt = (
        "あなたは営業担当者の月間活動計画を作成するAI Work Partnerです。"
        "訪問だけでなく、商談準備・電話・メール・新規開拓など、今月必要な活動全体を"
        "バランスよく計画してください。\n"
        "活動の種類:\n"
        "- category='visit'(訪問・Web会議など、顧客と直接会う/話す活動)。"
        "この場合 deal_id は candidate_deals から必ず1つ選ぶこと。\n"
        "- category='task'(資料作成・電話・メール・新規開拓など、事務作業や軽い接点)。"
        "商談に関連する場合は candidate_deals から deal_id を選び、"
        "特定の商談に紐づかない活動(週次報告書作成、新規開拓の架電リスト作成など)は"
        "deal_id を null にし、title に具体的な活動内容を日本語で書くこと。\n"
        "activity_type は次のいずれかから選ぶこと: 訪問, 電話, メール, Web会議, 資料作成, 新規開拓\n"
        "従うべきルール:\n"
        f"- plan_date は{base_date.isoformat()}〜{month_end.isoformat()}の範囲の日付にすること\n"
        "- 同じ deal_id + activity_type の組み合わせを重複させないこと\n"
        "- candidate_deals は商談ステージが進んでいる順(クロージングに近い順)に"
        "既に並んでいるので、基本的にこの順番を優先すること。"
        "同程度の優先度であれば is_stale が true(長期間接点が無い)の顧客や、"
        "見込み金額(estimated_amount)が大きい商談を優先すること\n"
        "- 訪問だけに偏らせず、商談前の資料作成、停滞している商談への電話・メール、"
        "新規開拓の時間なども適度に配置すること\n"
        "- 稼働日に1件だけ予定を置いて残りを空けたままにしないこと。"
        "訪問の前後の空き時間には、関連する資料作成・電話・メールや新規開拓を追加で配置し、"
        "1日の稼働時間(9:00〜18:00、12:00〜13:00は昼休み)をできるだけ埋めること\n"
        "- priority は1(最優先)〜5(低)の整数\n"
        "- rationale は日本語で、金額・確度・接点状況など具体的な数値を根拠に簡潔に述べること\n"
        "- 出力は次のJSON配列のみとし、説明文やコードブロック記法は一切含めないこと:\n"
        '[{"category": "visit"|"task", "activity_type": "<種別>", "deal_id": <int|null>, '
        '"title": "<text|null>", "plan_date": "YYYY-MM-DD", "priority": <int>, "rationale": "<text>"}]'
    )

    prompt_json = json.dumps(user_payload, ensure_ascii=False, default=str)
    try:
        response = httpx.post(
            f"{settings.ai_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.ai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.ai_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt_json},
                ],
                "temperature": 0.3,
                "max_tokens": 8000,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=180,
        )
        response.raise_for_status()
        content = _extract_content(response)
        raw_items = _parse_plan_items(content)
    except AiPlanningError:
        log_response(conn, context="plan_generation", prompt=prompt_json, response="(parse error)", rep_id=rep_id)
        raise
    except Exception as error:
        log_response(conn, context="plan_generation", prompt=prompt_json, response=f"(error) {error}", rep_id=rep_id)
        raise AiPlanningError(f"Qwenへの接続に失敗しました: {error}") from error

    candidates_by_id = {c["deal_id"]: c for c in candidates}
    seen: set[tuple[int, str]] = set()
    decisions: list[dict] = []
    for item in raw_items:
        try:
            category = str(item["category"]).strip()
            activity_type = str(item["activity_type"]).strip()
            raw_deal_id = item.get("deal_id")
            deal_id = int(raw_deal_id) if raw_deal_id not in (None, "") else None
            title = str(item["title"]).strip() if item.get("title") else None
            plan_date = date.fromisoformat(str(item["plan_date"]))
            priority = int(item["priority"])
            rationale = str(item["rationale"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if category not in _VALID_CATEGORIES or activity_type not in _VALID_ACTIVITY_TYPES or not rationale:
            continue
        if not (base_date <= plan_date <= month_end):
            continue
        # visit は必ず商談に紐づける。task は商談に紐づかない場合、表示名として
        # title が要る(フロントは customer_name が無いと "(顧客不明)" になる)。
        if category == "visit" and deal_id is None:
            continue
        if deal_id is not None:
            if deal_id not in candidates_by_id:
                continue
            dedup_key = (deal_id, activity_type)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
        elif not title:
            continue
        decisions.append(
            {
                "category": category,
                "activity_type": activity_type,
                "deal_id": deal_id,
                "title": title,
                "plan_date": plan_date,
                "priority": min(max(priority, 1), 5),
                "rationale": rationale,
            }
        )

    log_response(conn, context="plan_generation", prompt=prompt_json, response=content, rep_id=rep_id)

    if not decisions:
        raise AiPlanningError("Qwenから有効な計画案を取得できませんでした。")
    return decisions[:_MAX_PLAN_ITEMS]