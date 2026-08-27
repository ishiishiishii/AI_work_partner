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


def suggest_monthly_customer_portfolio(
    conn: Connection,
    *,
    rep_id: int,
    period: dict[str, Any],
    objective: dict[str, Any],
    weeks: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    selection_limit: int,
) -> list[dict[str, Any]]:
    """Ask Qwen to propose the month-level customer portfolio and week bias.

    The candidates are already scored and partially selected by the
    deterministic planner.  Qwen may only choose IDs and weeks included in
    this payload.  The route planner subsequently rebuilds the portfolio and
    checks mandatory visits, meeting capacity, customer-type diversity, and
    sales/profit coverage before accepting any part of the proposal.
    """
    if not candidates or not weeks or selection_limit <= 0:
        raise AiPlanningError("月間選定に利用できる顧客候補または週がありません。")

    user_payload = {
        "period": period,
        "objective": objective,
        "rules": {
            "selection_limit": selection_limit,
            "keep_must_visit": True,
            "daily_targets_are_soft": True,
            "period_end_targets_have_priority": True,
        },
        "weeks": weeks,
        "customer_candidates": candidates,
    }
    system_prompt = (
        "あなたはAI Work Partnerの月間顧客ポートフォリオ選定担当です。"
        "ルールベースが算出した評価値と基準案(currently_selected)を土台に、月末の"
        "期待売上・期待粗利を最大化しやすい顧客と、その顧客を重点的に訪問する週を"
        "提案してください。\n"
        "従うべきルール:\n"
        "- customer_idはcustomer_candidatesにある実在IDだけを使い、新しいIDを作らないこと\n"
        "- must_visit=trueの顧客は必ず含めること\n"
        "- 売上だけでなく期待粗利、担当者適合度、商談フェーズ、受注予定日、次アクション、"
        "必要訪問回数と移動負担を総合して選ぶこと\n"
        "- objective.policyはユーザーが選んだ収益方針であること。balancedは売上と粗利を"
        "同程度に、salesは売上を、gross_profitは粗利をより重く評価すること\n"
        "- objectiveのsales_weightとgross_profit_weightを反映し、日目標の均等達成より"
        "periodの残目標達成と月全体の成果最大化を優先すること\n"
        "- preferred_weekはweeksに存在するweek_numberから選ぶこと。期限・受注予定日・"
        "次アクションを踏まえ、特に根拠がなければ前半へ偏らせすぎないこと\n"
        "- 最大selection_limit社まで、優先度順に返すこと\n"
        "- reasonは、期待売上・期待粗利・確度・商談状況など、この顧客を月間候補に"
        "選ぶ具体的根拠を日本語で簡潔に書くこと\n"
        "- 出力は次のJSON配列のみとし、説明文やコードブロック記法を含めないこと:\n"
        '[{"customer_id": <int>, "preferred_week": <int>, "reason": "<text>"}]'
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
                "temperature": 0.1,
                "max_tokens": 5000,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=120,
        )
        response.raise_for_status()
        content = _extract_content(response)
        raw_items = _parse_plan_items(content)
    except AiPlanningError:
        log_response(
            conn,
            context="batch_monthly_customer_selection",
            prompt=prompt_json,
            response="(parse error)",
            rep_id=rep_id,
        )
        raise
    except Exception as error:
        log_response(
            conn,
            context="batch_monthly_customer_selection",
            prompt=prompt_json,
            response=f"(error) {error}",
            rep_id=rep_id,
        )
        raise AiPlanningError(f"Qwenへの接続に失敗しました: {error}") from error

    valid_customer_ids = {int(candidate["customer_id"]) for candidate in candidates}
    valid_week_numbers = {int(week["week_number"]) for week in weeks}
    seen_customer_ids: set[int] = set()
    selections: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            customer_id = int(item["customer_id"])
            preferred_week = int(item["preferred_week"])
            reason = str(item["reason"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if (
            customer_id not in valid_customer_ids
            or preferred_week not in valid_week_numbers
            or customer_id in seen_customer_ids
            or not reason
        ):
            continue
        seen_customer_ids.add(customer_id)
        selections.append(
            {
                "customer_id": customer_id,
                "preferred_week": preferred_week,
                "reason": reason,
            }
        )
        if len(selections) >= selection_limit:
            break

    log_response(
        conn,
        context="batch_monthly_customer_selection",
        prompt=prompt_json,
        response=content,
        rep_id=rep_id,
    )
    if not selections:
        raise AiPlanningError("Qwenから有効な月間顧客選定案を取得できませんでした。")
    return selections


# Fixed activity_type vocabulary, matching frontend/components/dashboard/
# ActivityPlanList.tsx's EDITABLE_ACTIVITY_TYPES -- the AI must pick from
# this list rather than invent free text, so the UI's type styling/labels
# keep working for AI-generated plans too.
_VALID_ACTIVITY_TYPES = {"訪問", "電話", "メール", "Web会議", "資料作成", "新規開拓"}
_VALID_CATEGORIES = {"visit", "task"}
_MAX_PLAN_ITEMS = 60


_SITUATION_LABELS = {
    "both_short": "売上・粗利ともに目標達成確率が低い",
    "sales_only_short": "売上目標の達成確率のみ低い",
    "profit_only_short": "粗利目標の達成確率のみ低い",
    "on_track": "売上・粗利とも目標達成確率は十分高い",
}


def generate_plan_selection(
    conn: Connection,
    *,
    rep_id: int,
    target_month: str,
    base_date: date,
    month_end: date,
    candidates: list[dict],
    sales_target: dict | None,
    situation: str = "on_track",
) -> list[dict]:
    """Ask Qwen for this month's full activity mix -- not just which deals to
    visit, but also prep/follow-up/prospecting tasks (資料作成・電話・メール・
    新規開拓) -- with date, priority, and rationale for each. Only selection/
    scheduling/rationale come from the model -- amounts and probabilities for
    deal-linked items are always re-read from the deal row by the caller,
    never trusted from model output. `situation` (from
    target_simulation.classify_gap_situation) is passed only so rationale text
    can describe *why* today's ranking looks the way it does -- the model is
    told not to use it to re-rank, since candidates already arrive pre-ranked
    for exactly that gap situation.
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
            "target_gross_profit": (
                float(sales_target["target_gross_profit"])
                if sales_target.get("target_gross_profit") is not None
                else None
            ),
        }
        if sales_target
        else None
    )
    user_payload = {
        "target_month": target_month,
        "sales_target": target_payload,
        # 順位づけには使わせない(candidate_dealsが既にこの状況を反映して並んでいる)、
        # rationaleの説明文だけをこの状況に即した内容にするための読み取り専用の文脈。
        "situation": _SITUATION_LABELS.get(situation, situation),
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
        "- candidate_deals は、今月の売上・粗利目標の達成確率(sales_target.situation)を"
        "踏まえた優先順位で既に並んでいるので、基本的にこの順番を優先すること。"
        "同程度の優先度であれば is_stale が true(長期間接点が無い)の顧客や、"
        "見込み金額(estimated_amount)が大きい商談を優先すること\n"
        "- situation は候補の並び順に既に反映済みなので、並び替えの根拠として"
        "使わないこと。rationale の文章表現を状況に合わせて説明する目的にのみ使うこと"
        "(例: situationがsales_only_shortなら「売上目標達成確率が低いため、"
        "見込み金額の大きい本案件を優先」のように説明する)\n"
        "- 訪問だけに偏らせず、商談前の資料作成、停滞している商談への電話・メール、"
        "新規開拓の時間なども適度に配置すること\n"
        "- 商談に紐づく準備・フォロー(category='task', deal_idあり)を月内で15件程度作り、"
        "提案資料の最終確認・アポイント確認を訪問直前、フォローアップメール・次回Web会議の"
        "日程調整を訪問直後に置くこと。titleには顧客名と具体的な作業を書くこと\n"
        "- deal_id=nullの新規開拓を月前半に集中して繰り返し配置すること。内容は新規開拓リスト更新、"
        "業界動向リサーチ、来月向け顧客リスト作成と架電、新規見込み先への電話を使い分けること\n"
        "- deal_id=nullの定型事務として『週次報告書の作成』『提案資料テンプレートの整備』を"
        "ほぼ毎週繰り返すこと\n"
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


def suggest_schedule_adjustments(
    conn: Connection,
    *,
    rep_id: int,
    occurrences: list[dict],
) -> list[dict]:
    """Ask Qwen whether any of the given batch-plan visits should move to a
    different date, based on each deal's next_action note, risk flags, and
    (for a must_visit deal) its deadline.

    `occurrences` is route_planning._schedule_adjustment_context's output --
    already filtered to only the visits with an actual signal (high risk, a
    next_action note, or must_visit), each carrying its own eligible_dates.
    The model may only pick a date from that occurrence's own eligible_dates
    (which, for a must_visit deal, already excludes anything past its own
    deadline); the caller (route_planning._apply_schedule_adjustments)
    re-validates every returned item against that same list before applying
    anything, so nothing here is trusted blindly -- this function only
    proposes, it never decides.
    """
    if not occurrences:
        raise AiPlanningError("調整対象の訪問がありません。")

    occurrence_payload = [
        {
            "customer_id": o["customer_id"],
            "customer_name": o["customer_name"],
            "visit_sequence": o["visit_sequence"],
            "current_date": o["current_date"].isoformat(),
            "eligible_dates": [d.isoformat() for d in o["eligible_dates"]],
            "deals": o["deals"],
            "loss_risk": o["loss_risk"],
            "delay_risk": o["delay_risk"],
            "risk_reasons": o["risk_reasons"],
            "must_visit": o["must_visit"],
            "visit_deadline": o["visit_deadline"].isoformat() if o["visit_deadline"] else None,
        }
        for o in occurrences
    ]
    user_payload = {"occurrences": occurrence_payload}

    system_prompt = (
        "あなたは営業担当者の月間訪問スケジュールを微調整するAI Work Partnerです。"
        "各訪問(occurrence)には、次のアクション(next_action)や失注/延期リスクの情報、"
        "必須訪問(must_visit)かどうかと期限(visit_deadline)が付いています。\n"
        "従うべきルール:\n"
        "- ほとんどのoccurrenceは変更不要です。next_actionの記述やリスク情報から"
        "具体的な根拠がある場合(例:『来週まで連絡しない』『見積回答待ち』のような"
        "記述がある、延期リスクが高いなど)のみ調整を提案すること。根拠が弱い、"
        "または無い場合は何も提案しないこと\n"
        "- must_visitがtrueの訪問は特に慎重に扱うこと。期限(visit_deadline)に"
        "間に合わなくなる調整は絶対に提案しないこと(eligible_datesは既に期限内に"
        "絞られているので、その中からのみ選べば自動的に守られる)。むしろ、"
        "next_actionやリスク情報から見て早めに動いた方がよい場合は、期限に余裕が"
        "あっても前倒しの日付を積極的に提案してよい\n"
        "- new_date は、そのoccurrenceの eligible_dates に含まれる日付から必ず"
        "1つ選ぶこと。eligible_dates に無い日付や、新しい日付を作ってはならない\n"
        "- customer_id と visit_sequence は occurrence のものをそのまま使うこと\n"
        "- reason は日本語で、なぜその日付に動かすのか具体的かつ簡潔に述べること\n"
        "- 変更が必要な occurrence が無ければ空配列を返すこと\n"
        "- 出力は次のJSON配列のみとし、説明文やコードブロック記法は一切含めないこと:\n"
        '[{"customer_id": <int>, "visit_sequence": <int>, "new_date": "YYYY-MM-DD", '
        '"reason": "<text>"}]'
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
                "temperature": 0.2,
                "max_tokens": 4000,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=120,
        )
        response.raise_for_status()
        content = _extract_content(response)
        raw_items = _parse_plan_items(content)
    except AiPlanningError:
        log_response(conn, context="batch_schedule_adjustment", prompt=prompt_json, response="(parse error)", rep_id=rep_id)
        raise
    except Exception as error:
        log_response(conn, context="batch_schedule_adjustment", prompt=prompt_json, response=f"(error) {error}", rep_id=rep_id)
        raise AiPlanningError(f"Qwenへの接続に失敗しました: {error}") from error

    adjustments: list[dict] = []
    for item in raw_items:
        try:
            adjustments.append(
                {
                    "customer_id": int(item["customer_id"]),
                    "visit_sequence": int(item["visit_sequence"]),
                    "new_date": str(item["new_date"]),
                    "reason": str(item["reason"]).strip(),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue

    log_response(conn, context="batch_schedule_adjustment", prompt=prompt_json, response=content, rep_id=rep_id)
    return adjustments


def revise_unreachable_day(
    conn: Connection,
    *,
    rep_id: int,
    target_date: date,
    error_message: str,
    constraints: dict[str, Any],
    objective: dict[str, Any],
    monthly_plan: dict[str, Any],
    candidates: list[dict[str, Any]],
    candidate_limit: int,
) -> list[dict[str, Any]]:
    """Ask Qwen to replace an infeasible day's candidate pool.

    The caller supplies only real candidates that remain eligible for a
    single visit in the target month.  Qwen may rank/select those candidates,
    but the caller re-validates every occurrence key and runs CP-SAT plus the
    routing solver again.  The model therefore improves the business choice;
    it never gets authority to relax working hours, fixed appointments, or
    the maximum visit count.
    """
    if not candidates:
        raise AiPlanningError("再計画に利用できる訪問候補がありません。")

    candidate_payload = [
        {
            "customer_id": candidate["customer_id"],
            "visit_sequence": candidate["visit_sequence"],
            "customer_name": candidate["customer_name"],
            "currently_assigned": candidate["currently_assigned"],
            "must_visit": candidate["must_visit"],
            "visit_deadline": candidate["visit_deadline"],
            "expected_sales": candidate["expected_sales"],
            "expected_gross_profit": candidate["expected_gross_profit"],
            "opportunity_expected_sales": candidate["opportunity_expected_sales"],
            "opportunity_expected_gross_profit": candidate[
                "opportunity_expected_gross_profit"
            ],
            "visit_duration_min": candidate["visit_duration_min"],
            "distance_from_branch_m": candidate["distance_from_branch_m"],
            "phase_names": candidate["phase_names"],
            "next_actions": candidate["next_actions"],
        }
        for candidate in candidates
    ]
    user_payload = {
        "target_date": target_date.isoformat(),
        "failure": {
            "code": "target_not_reachable",
            "message": error_message,
        },
        "hard_constraints": constraints,
        "objective": objective,
        "monthly_plan": monthly_plan,
        "candidate_limit": candidate_limit,
        "candidates": candidate_payload,
    }
    system_prompt = (
        "あなたはAI Work Partnerの月間営業ルート再計画担当です。"
        "指定日の候補セットでは勤務時間・固定予定・最大訪問数を満たせず、"
        "target_not_reachableになりました。候補を入れ替え、月全体の期待売上と"
        "期待粗利が最大になるように、再計算へ渡す訪問候補を優先順で選んでください。\n"
        "従うべきルール:\n"
        "- hard_constraintsは絶対に緩和しないこと。時刻や最大訪問数を変更する提案はしないこと\n"
        "- objective.policyはユーザーが選んだ収益方針であること。balancedは売上と粗利を"
        "同程度に、salesは売上を、gross_profitは粗利をより重く評価すること\n"
        "- objectiveのsales_weightとgross_profit_weightを使い、期待売上と期待粗利の"
        "両方を評価すること。粗利がnullの候補は粗利を確認できないため、同程度なら"
        "粗利が確認できる候補を優先すること\n"
        "- must_visit=true、期限が近い、next_actionsに当日の対応が必要な記述がある候補は"
        "機会損失も考慮すること\n"
        "- distance_from_branch_mとvisit_duration_minが大きい候補だけに偏ると再び"
        "制約違反になりやすいので、価値と実行しやすさを両立すること\n"
        "- candidatesに存在するcustomer_idとvisit_sequenceの組だけを使い、同じ組を"
        "重複させないこと。最大candidate_limit件まで選べること\n"
        "- reasonは日本語で、売上・粗利・期限・移動負担のどれを根拠にしたかを簡潔に述べること\n"
        "- 出力は次のJSON配列のみとし、説明文やコードブロック記法は一切含めないこと:\n"
        '[{"customer_id": <int>, "visit_sequence": <int>, "reason": "<text>"}]'
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
                "temperature": 0.1,
                "max_tokens": 3000,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=120,
        )
        response.raise_for_status()
        content = _extract_content(response)
        raw_items = _parse_plan_items(content)
    except AiPlanningError:
        log_response(
            conn,
            context="unreachable_day_revision",
            prompt=prompt_json,
            response="(parse error)",
            rep_id=rep_id,
        )
        raise
    except Exception as error:
        log_response(
            conn,
            context="unreachable_day_revision",
            prompt=prompt_json,
            response=f"(error) {error}",
            rep_id=rep_id,
        )
        raise AiPlanningError(f"Qwenへの接続に失敗しました: {error}") from error

    valid_keys = {
        (int(candidate["customer_id"]), int(candidate["visit_sequence"]))
        for candidate in candidates
    }
    seen: set[tuple[int, int]] = set()
    revisions: list[dict[str, Any]] = []
    for item in raw_items:
        try:
            key = (int(item["customer_id"]), int(item["visit_sequence"]))
            reason = str(item["reason"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if key not in valid_keys or key in seen or not reason:
            continue
        seen.add(key)
        revisions.append(
            {
                "customer_id": key[0],
                "visit_sequence": key[1],
                "reason": reason,
            }
        )
        if len(revisions) >= candidate_limit:
            break

    log_response(
        conn,
        context="unreachable_day_revision",
        prompt=prompt_json,
        response=content,
        rep_id=rep_id,
    )
    if not revisions:
        raise AiPlanningError("Qwenから有効な日次再計画候補を取得できませんでした。")
    return revisions


def suggest_target_gap_fill(
    conn: Connection,
    *,
    rep_id: int,
    period: dict[str, Any],
    objective: dict[str, Any],
    days: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    assignment_limit: int,
) -> list[dict[str, Any]]:
    """Ask Qwen to fill a period-end gap or repair an infeasible day.

    Daily target amounts are intentionally descriptive rather than hard
    constraints.  Qwen assigns only caller-provided reserve candidates to
    caller-provided eligible dates; the route planner validates every key and
    then re-runs the hard scheduling solvers before accepting a change.
    """
    if not days or not candidates or assignment_limit <= 0:
        raise AiPlanningError("目標補填に利用できる日付または訪問候補がありません。")

    user_payload = {
        "period": period,
        "objective": objective,
        "rules": {
            "daily_targets_are_soft": True,
            "period_end_targets_have_priority": True,
            "assignment_limit": assignment_limit,
        },
        "days": days,
        "reserve_candidates": candidates,
    }
    system_prompt = (
        "あなたはAI Work Partnerの月末目標補填・営業日程再構築担当です。"
        "既存システムが作った日別計画を変更の土台とし、期間末の期待売上・期待粗利の"
        "不足を埋めるか、実行不能になった訪問を実行可能な別日へ移す候補と日付を"
        "提案してください。\n"
        "従うべきルール:\n"
        "- period.schedule_recovery_required=trueの場合、sales_shortfallと"
        "gross_profit_shortfallが0でも再計画を止めないこと。reserve_candidatesの"
        "recovery_required=trueを優先し、failed_dates以外のeligible_datesへ再配置すること\n"
        "- 日目標はソフト目標なので、日ごとの未達は許容すること。日目標を均等に"
        "達成させることより、periodのsales_shortfallとgross_profit_shortfallを"
        "期間末までに両方0へ近づけることを優先すること\n"
        "- objective.policyはユーザーが選んだ収益方針であること。balancedは売上と粗利を"
        "同程度に、salesは売上を、gross_profitは粗利をより重く評価すること\n"
        "- objectiveの売上・粗利ウェイトを使うこと。両方不足している場合は、片方だけ"
        "大きくしてもう片方を放置せず、両目標を満たす組合せを選ぶこと\n"
        "- target_dateは候補自身のeligible_datesからだけ選ぶこと。customer_idを新しく"
        "作らず、同じ顧客を複数日に割り当てないこと\n"
        "- daysのfixed_windows、current_visit_count、max_visitsと、候補の移動距離・"
        "訪問時間を考慮すること。ただし最終的な実行可能性は後段ソルバーが再検証する\n"
        "- reasonは期待売上・期待粗利と、なぜその日に補填するかを日本語で簡潔に書くこと\n"
        "- 最大assignment_limit件まで、補填効果が高い順で返すこと\n"
        "- 出力は次のJSON配列のみとし、説明文やコードブロック記法を含めないこと:\n"
        '[{"customer_id": <int>, "target_date": "YYYY-MM-DD", "reason": "<text>"}]'
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
                "temperature": 0.1,
                "max_tokens": 4000,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=120,
        )
        response.raise_for_status()
        content = _extract_content(response)
        raw_items = _parse_plan_items(content)
    except AiPlanningError:
        log_response(
            conn,
            context="batch_target_gap_fill",
            prompt=prompt_json,
            response="(parse error)",
            rep_id=rep_id,
        )
        raise
    except Exception as error:
        log_response(
            conn,
            context="batch_target_gap_fill",
            prompt=prompt_json,
            response=f"(error) {error}",
            rep_id=rep_id,
        )
        raise AiPlanningError(f"Qwenへの接続に失敗しました: {error}") from error

    eligible_dates_by_customer = {
        int(candidate["customer_id"]): {
            date.fromisoformat(str(value)) for value in candidate["eligible_dates"]
        }
        for candidate in candidates
    }
    seen_customers: set[int] = set()
    assignments: list[dict[str, Any]] = []
    for item in raw_items:
        try:
            customer_id = int(item["customer_id"])
            target_date = date.fromisoformat(str(item["target_date"]))
            reason = str(item["reason"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if (
            customer_id in seen_customers
            or target_date not in eligible_dates_by_customer.get(customer_id, set())
            or not reason
        ):
            continue
        seen_customers.add(customer_id)
        assignments.append(
            {
                "customer_id": customer_id,
                "target_date": target_date,
                "reason": reason,
            }
        )
        if len(assignments) >= assignment_limit:
            break

    log_response(
        conn,
        context="batch_target_gap_fill",
        prompt=prompt_json,
        response=content,
        rep_id=rep_id,
    )
    if not assignments:
        raise AiPlanningError("Qwenから有効な月末目標補填案を取得できませんでした。")
    return assignments


def generate_week_narratives(
    conn: Connection,
    *,
    rep_id: int,
    weeks: list[dict],
) -> dict[int, str]:
    """Ask Qwen to write one natural-language paragraph per week of the
    batch plan (replacing the templated `focus` text), given each week's
    numbers, assigned customers, phase-progress goals, and risk flags.
    Never asked to change any number -- only to describe the week already
    decided by the deterministic scheduler.
    """
    if not weeks:
        raise AiPlanningError("対象の週がありません。")

    week_payload = [
        {
            "week_number": w["week_number"],
            "start_date": w["start_date"].isoformat(),
            "end_date": w["end_date"].isoformat(),
            "target_amount": float(w["target_amount"]),
            "expected_sales": float(w["expected_sales"]),
            "attainment_rate": w["attainment_rate"],
            "customer_names": w["customer_names"],
            "deal_progress_goals": [
                {
                    "customer_name": g["customer_name"],
                    "current_phase_name": g["current_phase_name"],
                    "target_phase_name": g["target_phase_name"],
                }
                for g in w["deal_progress_goals"]
            ],
        }
        for w in weeks
    ]
    user_payload = {"weeks": week_payload}

    system_prompt = (
        "あなたは営業担当者の月間バッチ計画の週次サマリーを書くAI Work Partnerです。"
        "各週のデータ(目標金額・期待売上・達成率・訪問予定顧客・商談進行目標)を基に、"
        "その週に何を重視すべきかを1〜2文の日本語で簡潔に説明してください。\n"
        "従うべきルール:\n"
        "- 数値(金額・達成率など)は与えられたデータをそのまま参照し、独自に計算・"
        "修正しないこと\n"
        "- deal_progress_goals があれば、どの商談をどのフェーズへ進めたいかに触れること\n"
        "- 出力は次のJSON配列のみとし、説明文やコードブロック記法は一切含めないこと:\n"
        '[{"week_number": <int>, "note": "<text>"}]'
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
                "max_tokens": 2000,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=120,
        )
        response.raise_for_status()
        content = _extract_content(response)
        raw_items = _parse_plan_items(content)
    except AiPlanningError:
        log_response(conn, context="batch_week_narrative", prompt=prompt_json, response="(parse error)", rep_id=rep_id)
        raise
    except Exception as error:
        log_response(conn, context="batch_week_narrative", prompt=prompt_json, response=f"(error) {error}", rep_id=rep_id)
        raise AiPlanningError(f"Qwenへの接続に失敗しました: {error}") from error

    valid_week_numbers = {w["week_number"] for w in weeks}
    notes: dict[int, str] = {}
    for item in raw_items:
        try:
            week_number = int(item["week_number"])
            note = str(item["note"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if week_number in valid_week_numbers and note:
            notes[week_number] = note

    log_response(conn, context="batch_week_narrative", prompt=prompt_json, response=content, rep_id=rep_id)
    if not notes:
        raise AiPlanningError("Qwenから有効な週次コメントを取得できませんでした。")
    return notes


def rank_must_visit_candidates(
    conn: Connection,
    *,
    rep_id: int,
    target_date: date,
    candidates: list[dict],
) -> list[int]:
    """Ask Qwen to rank must_visit candidates by priority for `target_date`,
    for use only when there are more of them than the day can actually hold
    (route_planning._solve_and_persist_day calls this only in that case).

    must_visit no longer force-includes every candidate (route_optimization.
    generate_portfolios' must_visit_rank turns it into a large score bonus,
    highest for rank 0) -- CP-SAT still enforces max_visits/available_min as
    hard constraints, so this ranking only decides *which* must_visit
    candidates get dropped when not all fit, never whether the day succeeds.
    Returns customer_id in priority order (index 0 = highest priority) --
    the caller re-validates this is a permutation of the given customer_ids
    and falls back to a deterministic order (nearest deadline first) on
    AiPlanningError or an invalid response, so a Qwen outage never blocks
    the day from being solved.
    """
    if len(candidates) < 2:
        raise AiPlanningError("優先順位付けが必要な必須訪問がありません。")

    candidate_payload = [
        {
            "customer_id": c["customer_id"],
            "customer_name": c["customer_name"],
            "expected_sales": float(c["expected_sales"]),
            "visit_deadline": c["visit_deadline"].isoformat() if c["visit_deadline"] else None,
            "deals": c["deals"],
        }
        for c in candidates
    ]
    user_payload = {
        "target_date": target_date.isoformat(),
        "must_visit_candidates": candidate_payload,
    }

    system_prompt = (
        "あなたは営業担当者の1日の訪問優先順位を判断するAI Work Partnerです。"
        "以下の必須訪問(must_visit)の商談は、件数または移動時間の都合で全ては"
        f"{target_date.isoformat()}に訪問できません。優先度の高い順に並べ替えて"
        "ください。\n"
        "従うべきルール:\n"
        "- visit_deadline(期限)が近いものほど優先度を上げること。期限が同程度なら"
        "expected_sales(見込み売上)が大きいものを優先すること\n"
        "- deals内のnext_action(次のアクション)に、今日訪問しないと機会損失に"
        "つながる具体的な記述があれば優先度を上げること\n"
        "- must_visit_candidatesに含まれる customer_id を過不足なく1回ずつ、"
        "優先度の高い順に並べること。新しいIDを作らないこと\n"
        "- 出力は customer_id の整数配列のみとし、説明文やコードブロック記法は"
        "一切含めないこと: [<customer_id>, <customer_id>, ...]"
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
                "temperature": 0.1,
                "max_tokens": 1000,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=60,
        )
        response.raise_for_status()
        content = _extract_content(response)
        raw_ids = _parse_plan_items(content)
    except AiPlanningError:
        log_response(conn, context="must_visit_priority", prompt=prompt_json, response="(parse error)", rep_id=rep_id)
        raise
    except Exception as error:
        log_response(conn, context="must_visit_priority", prompt=prompt_json, response=f"(error) {error}", rep_id=rep_id)
        raise AiPlanningError(f"Qwenへの接続に失敗しました: {error}") from error

    log_response(conn, context="must_visit_priority", prompt=prompt_json, response=content, rep_id=rep_id)

    try:
        ranked_ids = [int(item) for item in raw_ids]
    except (TypeError, ValueError):
        raise AiPlanningError("Qwenの応答を優先順位として解釈できませんでした。")
    expected_ids = {c["customer_id"] for c in candidates}
    if set(ranked_ids) != expected_ids or len(ranked_ids) != len(expected_ids):
        raise AiPlanningError("Qwenの応答が対象の商談と一致しませんでした。")
    return ranked_ids
