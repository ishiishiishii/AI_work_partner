"""Create demo Supabase Auth accounts, one per sales rep (EMP001..EMP020).

ログイン機能(フロントの /login)で使うデモアカウントを作成する。
sales_rep テーブルと違い、Supabase Auth のユーザーは supabase/seed.sql では
作れないため、このスクリプトをローカル環境ごとに1回実行する必要がある。

使い方(コンテナ内で実行すること):
    docker compose exec api python3 -m scripts.seed_demo_auth_users

必要な環境変数(.env 経由でコンテナに渡っている想定):
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

同じメールアドレスのアカウントが既にある場合はスキップするだけなので、
何度実行しても安全。
"""

import sys

import httpx

from app.config import settings

DEMO_PASSWORD = "demo1234"

REPS = [
    (1, "石川次郎"),
    (2, "村上花子"),
    (3, "小林綾子"),
    (4, "木村さゆり"),
    (5, "加藤拓也"),
    (6, "遠藤直樹"),
    (7, "近藤拓也"),
    (8, "井上愛"),
    (9, "吉田直樹"),
    (10, "高橋健二"),
    (11, "林慎一"),
    (12, "井上健太"),
    (13, "林麻衣"),
    (14, "岡田健二"),
    (15, "吉田陽子"),
    (16, "石川大輔"),
    (17, "岡本裕子"),
    (18, "後藤大輔"),
    (19, "新人太郎"),
    (20, "大重鎮重信"),
]


def main() -> None:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY が設定されていません。.env を確認してください。")
        sys.exit(1)

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }
    url = f"{settings.supabase_url}/auth/v1/admin/users"

    with httpx.Client(timeout=10) as client:
        for rep_id, rep_name in REPS:
            email = f"rep{rep_id}@aiworkpartner.local"
            employee_id = f"EMP{rep_id:03d}"
            payload = {
                "email": email,
                "password": DEMO_PASSWORD,
                "email_confirm": True,
                "app_metadata": {"rep_id": rep_id, "rep_name": rep_name},
            }
            res = client.post(url, headers=headers, json=payload)
            if res.status_code == 200:
                print(f"作成しました: {employee_id} ({rep_name})")
            elif res.status_code in (400, 422) and "already been registered" in res.text:
                print(f"既に存在します: {employee_id} ({rep_name})")
            else:
                print(f"失敗しました: {employee_id} ({rep_name}) -> {res.status_code} {res.text}")


if __name__ == "__main__":
    main()
