from fastapi import Header, HTTPException

from app.services.supabase_client import get_supabase_client


def get_authenticated_rep_id(
    authorization: str | None = Header(default=None),
) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="認証が必要です。")
    token = authorization.removeprefix("Bearer ").strip()
    client = get_supabase_client()
    if client is None:
        raise HTTPException(status_code=503, detail="認証サービスが設定されていません。")
    try:
        response = client.auth.get_user(token)
        user = response.user
        rep_id = (user.app_metadata or {}).get("rep_id") if user else None
    except Exception as error:
        raise HTTPException(status_code=401, detail="認証トークンが無効です。") from error
    if not isinstance(rep_id, int) or rep_id < 1:
        raise HTTPException(status_code=403, detail="営業担当者との紐付けがありません。")
    return rep_id
