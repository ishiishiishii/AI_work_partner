import json

from app.services import qwen_chat


class FakeResponse:
    def __init__(self, body: dict):
        self._body = body
        self.status_code = 200

    def json(self) -> dict:
        return self._body

    def raise_for_status(self) -> None:
        return None


def test_qwen_route_tool_call_executes_once_and_explains_exact_result(monkeypatch) -> None:
    requests: list[dict] = []
    responses = [
        FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "create_sales_route_plan",
                                        "arguments": json.dumps(
                                            {
                                                "target_date": "2026-08-26",
                                                "policy": "balanced",
                                                "max_visits": 5,
                                            }
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        ),
        FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "計画ID42、期待売上500,000円の案です。金額は予定値です。",
                        }
                    }
                ]
            }
        ),
    ]

    def fake_post(*args, **kwargs):
        del args
        requests.append(kwargs["json"])
        return responses.pop(0)

    executed: list[dict] = []

    def execute(arguments: dict) -> dict:
        executed.append(arguments)
        return {
            "plan_id": 42,
            "totals": {"expected_sales": 500000},
            "warnings": ["表示金額は予定値です。"],
        }

    monkeypatch.setattr(qwen_chat.httpx, "post", fake_post)
    result = qwen_chat.ask(
        question="明日の営業計画を作って",
        history=[],
        context={},
        tool_executor=execute,
    )

    assert executed == [
        {"target_date": "2026-08-26", "policy": "balanced", "max_visits": 5}
    ]
    assert requests[0]["tools"][0]["function"]["name"] == "create_sales_route_plan"
    assert requests[0]["tool_choice"] == "auto"
    tool_message = requests[1]["messages"][-1]
    assert tool_message["role"] == "tool"
    assert json.loads(tool_message["content"])["plan_id"] == 42
    assert result.answer == "計画ID42、期待売上500,000円の案です。金額は予定値です。"
