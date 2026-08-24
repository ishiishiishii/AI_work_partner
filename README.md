# AI Work Partner

FastAPI + Next.js + ローカル Supabase のモノレポ開発環境です。チーム全員が同じ構成で起動できるように、アプリは Docker Compose、Supabase は公式 CLI（内部で Docker）で動かします。

## 構成

| サービス | 技術 | URL |
| --- | --- | --- |
| Web | Next.js (App Router) | http://localhost:3000 |
| API | FastAPI | http://localhost:8000 / docs: http://localhost:8000/docs |
| Supabase API | Local Supabase | http://127.0.0.1:55321 |
| Postgres | Supabase 同梱 | `127.0.0.1:55322` |
| Studio | Supabase Studio | http://127.0.0.1:55323 |

AI（オープンモデル）は後から差し替えできるよう、API の `/api/ai/ping` にプレースホルダのみ置いています。

```text
Browser → web (:3000) → api (:8000)
                ↘         ↘
                 → Supabase local (API / Auth / Postgres / Studio)
```

## 前提ソフト

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)（起動済みであること）
- [Supabase CLI](https://supabase.com/docs/guides/cli)
- Git

フロント / バックはコンテナ内で動くため、ホストに Node.js や Python は必須ではありません（ローカル直接実行する場合のみ必要）。

### Supabase CLI（Windows）

```powershell
npm install -g supabase
```

Scoop を使う場合:

```powershell
scoop bucket add supabase https://github.com/supabase/scoop-bucket.git
scoop install supabase
```

> このリポジトリのローカル Supabase は、他プロジェクト／Windows 予約ポートとの衝突を避けるため  
> API `55321` / DB `55322` / Studio `55323` を使います（`supabase/config.toml`）。

## 初回セットアップ

```powershell
git clone https://github.com/ishiishiishii/AI_work_partner.git
cd AI_work_partner
copy .env.example .env
```

### 1. ローカル Supabase を起動

リポジトリルートで:

```powershell
supabase start
supabase status
```

`supabase status` に表示される次の値を `.env` に反映してください。

- `API URL` → `SUPABASE_URL` と `NEXT_PUBLIC_SUPABASE_URL`
- `anon key` → `SUPABASE_ANON_KEY` と `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `service_role key` → `SUPABASE_SERVICE_ROLE_KEY`
- `DB URL` → `DATABASE_URL`（ホストから接続する場合）

Docker 内の API / Web からホスト上の Supabase へ繋ぐため、`.env.example` の `SUPABASE_URL_DOCKER` / `DATABASE_URL_DOCKER`（`host.docker.internal`）はそのまま使えます。

### 2. アプリを起動

```powershell
docker compose up --build
```

起動後:

- フロント: http://localhost:3000
- API OpenAPI: http://localhost:8000/docs

### 3. ログイン用デモアカウント

フロントの `/login` は Supabase Auth を使っています。`sales_rep` テーブルとは別物ですが、
`api` コンテナ起動時に `scripts.seed_demo_auth_users` が自動実行されるため、
`docker compose up` するだけで担当者ごとのデモアカウント（EMP001〜EMP018、パスワードは共通で `demo1234`）が作成されます。手動での実行は不要です。

既にアカウントがある場合はスキップされるだけなので、コンテナを再起動しても安全です。手動で再実行したい場合は次のコマンドでも実行できます。

```powershell
docker compose exec api python3 -m scripts.seed_demo_auth_users
```


## 日常の起動 / 停止

```powershell
# 起動
supabase start
docker compose up

# 停止（別ターミナル）
docker compose down
supabase stop
```

## ディレクトリ

```text
.
├── backend/          # FastAPI
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── routers/
│   │   └── services/ # AI stub, Supabase client helper
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/         # Next.js
│   ├── app/
│   ├── lib/          # API / Supabase helpers
│   ├── Dockerfile
│   └── package.json
├── supabase/         # Local Supabase (config / migrations / seed)
├── docker-compose.yml
├── .env.example
└── README.md
```

## 開発メモ

- API のホットリロード: `backend/` を volume マウントしています。
- Web のホットリロード: `frontend/` を volume マウントしています（`node_modules` は名前付き volume）。
- DB スキーマ変更は `supabase/migrations/` に SQL を追加し、`supabase db reset` などで適用します。
- AI 実装を足すときは `backend/app/services/ai.py` を差し替えてください。

## トラブルシュート

- **API が Supabase に繋がらない**: Docker Desktop が起動していること、`supabase start` 済みであること、`.env` のキーが `supabase status` と一致していることを確認。
- **フロントで API が失敗する**: ブラウザからは `NEXT_PUBLIC_API_URL=http://localhost:8000` を使います（コンテナ名 `api` はブラウザから解決できません）。
- **Windows でファイル変更が検知されない**: `WATCHPACK_POLLING=true` を compose に設定済みです。
