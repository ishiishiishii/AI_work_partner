# AI Work Partner

FastAPI + Next.js + ローカル Supabase のモノレポ開発環境です。チーム全員が同じ構成で起動できるように、アプリは Docker Compose、Supabase は公式 CLI（内部で Docker）で動かします。

## 構成

| サービス | 技術 | URL |
| --- | --- | --- |
| Web | Next.js (App Router) | http://localhost:3000 （ダッシュボード: http://localhost:3000/dashboard） |
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

## いちばん簡単な起動（Windows）

Docker Desktop を起動した状態で、リポジトリのルートで:

```powershell
copy .env.example .env   # 初回だけ
.\start-dev.cmd
```

スクリプトが Supabase（DB）と `api` / `web` を起動します。表が古い場合は自動で `supabase db reset` します。

起動後にブラウザで開くもの:

- 営業ダッシュボード: http://localhost:3000/dashboard
- 疎通確認: http://localhost:3000
- API OpenAPI: http://localhost:8000/docs

## 初回セットアップ（手動）

```powershell
git clone https://github.com/ishiishiishii/AI_work_partner.git
cd AI_work_partner
copy .env.example .env
```

`.env.example` にはローカル Supabase の公開デモ JWT が入っています。`jwt_secret` を変えたときだけ `supabase status` の値で上書きしてください。

Docker 内の API / Web からホスト上の Supabase へ繋ぐため、`.env.example` の `SUPABASE_URL_DOCKER` / `DATABASE_URL_DOCKER`（`host.docker.internal`）はそのまま使えます。

### 1. ローカル Supabase を起動

```powershell
supabase start
```

スキーマを最新のマイグレーション＋シードに揃える（既存のローカルデータは消えます）:

```powershell
supabase db reset --yes --local
```

### 2. アプリを起動

```powershell
docker compose up --build
```

## 日常の起動 / 停止

```powershell
# 起動（推奨）
.\start-dev.cmd

# または手動
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
├── start-dev.cmd      # Windows: DB + アプリをまとめて起動
├── start-dev.ps1
├── .env.example
└── README.md
```

## 開発メモ

- API のホットリロード: `backend/` を volume マウントしています。
- Web のホットリロード: `frontend/` を volume マウントしています（`node_modules` は名前付き volume）。
- DB スキーマ変更は `supabase/migrations/` に SQL を追加し、`supabase db reset` などで適用します。
- AI 実装を足すときは `backend/app/services/ai.py` を差し替えてください。

## トラブルシュート

- **ダッシュボードが「データの取得に失敗」になる / API が 500**: コンテナ不足ではなく、**DB の表がコードより古い**ことが多いです。ホストで `supabase db reset --yes --local` のあと、`docker compose restart api` してください。
- **コンテナに入らないと動かない？**: 入りません。`docker compose exec` は pytest などの作業用です。アプリはブラウザの URL で使います。
- **API が Supabase に繋がらない**: Docker Desktop が起動していること、`supabase start` 済みであること、`.env` のキーが `supabase status` と一致していることを確認。
- **フロントで API が失敗する**: ブラウザからは `NEXT_PUBLIC_API_URL=http://localhost:8000` を使います（コンテナ名 `api` はブラウザから解決できません）。
- **Windows でファイル変更が検知されない**: `WATCHPACK_POLLING=true` を compose に設定済みです。
