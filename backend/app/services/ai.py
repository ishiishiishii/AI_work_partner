import json
from dataclasses import dataclass
from typing import Any

from psycopg import Connection


@dataclass(frozen=True)
class AiPingResult:
    status: str
    message: str
    provider: str


def ping() -> AiPingResult:
    """Placeholder for a future open-model / inference backend."""
    return AiPingResult(
        status="ok",
        message="AI provider is not configured yet. Replace this stub when a model is chosen.",
        provider="placeholder",
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
