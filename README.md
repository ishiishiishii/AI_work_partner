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

QwenはOpenAI互換API経由で接続し、営業ルート依頼ではFastAPIの専用最適化ツールだけを呼び出します。

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

`/login` はSupabase Authで認証します。社員IDは `EMP001`〜`EMP050`、
パスワードは共通で `demo1234` です。デモユーザーは `supabase/seed.sql` が作成し、
Bearer JWTの改ざんできない `app_metadata.rep_id` から本人を特定します。

### 4. 営業ルート計画の初期化

1. Google CloudでRoutes APIを有効化し、請求先を設定して、`.env` の
   `GOOGLE_MAPS_API_KEY` へAPIキーを設定します。
2. 公共交通用のODPTデータとOpenTripPlannerを初期化します（初回は約500 MBの
   OpenStreetMapデータを取得し、経路グラフを作るため数分かかります）。

```powershell
./scripts/setup_odpt_otp.sh
```

   トークンなしでも都営地下鉄・都営バスを利用できます。東京メトロも含める場合は、
   公共交通オープンデータセンターの無料開発者登録後、`.env` の`ODPT_ACCESS_TOKEN`へ
   トークンを設定して再実行します。JR東日本を含める場合は公共交通オープンデータ
   チャレンジ2026のトークンを`ODPT_CHALLENGE_ACCESS_TOKEN`へ設定します。
3. APIキーやトークンは`NEXT_PUBLIC_*`にせず、サーバー側だけに保存してください。
4. 既存DBには `supabase migration up` でPostGIS・ルート計画テーブルを適用します。
5. 顧客住所を一度だけ座標化します。

```powershell
docker compose exec api python scripts/geocode_customers.py --limit 300
```

`success` の顧客だけが自動候補になります。`review` は都道府県不一致・候補の曖昧さ・
信頼度不足を確認してから修正してください。通常の計画作成ではGeocodingを再実行しません。

車・徒歩・自転車の移動時間行列はGoogle Routes APIを利用します。公共交通は、日本の
Google Routes APIでは乗換経路を取得できないため、ODPTのGTFSデータとローカルで動く
OpenTripPlannerで「出発地から駅までの徒歩＋鉄道・地下鉄・バス＋駅から訪問先までの徒歩」を一括計算します。
Google Compute Route Matrixはリクエスト数ではなく、出発地数×目的地数の要素数で利用量が決まります。
移動行列は24時間キャッシュし、同じ条件での再作成ではAPI消費を抑えます。
公共交通は計算時間を抑えるため、評価上位8候補から計画します。
住所検索は国土地理院を優先し、必要なら任意設定の`ORS_API_KEY`をフォールバックに使います。

ダッシュボードの「1日の営業ルート計画」で案を作成できます。プレビュー時点では
`activity_plan` を変更せず、「この計画を採用」を押したときだけ競合を再確認して保存します。

### テスト

```powershell
docker compose exec api pytest -q
docker compose exec web npm run build
```

## GitHub Codespaces でスマホ等の別端末から確認する

同じLANに繋げない端末（スマホ等）で `/login` などを確認したい場合、`.devcontainer` を使って
GitHub Codespaces 上でこの一式を起動できます。`localhost`/`127.0.0.1` は端末自身を指してしまい
LAN外からは繋がらないため、Codespaces のポート転送URLを使う方式です。

1. GitHub上でこのリポジトリの Codespace を作成（`.devcontainer` の設定で Supabase CLI が自動インストールされ、`.env` の URL がこの Codespace 用に自動書き換えされます）
2. Codespace のターミナルで通常通りセットアップ
   ```bash
   supabase start
   supabase status   # anon key / service_role key を .env に反映
   supabase db reset   # fresh Codespaceでmigration・seed・デモAuthユーザーを反映
   docker compose up --build -d
   ```
3. VS Code の **Ports** パネルで `3000` / `8000` / `55321` の **Visibility** を `Public` に変更
   （デフォルトは Private = GitHubログインが必要なため、スマホ等からそのまま開けません）
4. `3000` の転送URL（`https://<codespace名>-3000.app.github.dev` 形式）をスマホ等で開く

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
- Qwen連携は `backend/app/services/qwen_chat.py`、数値計算と最適化はFastAPIサービス側に分離しています。

## トラブルシュート

- **API が Supabase に繋がらない**: Docker Desktop が起動していること、`supabase start` 済みであること、`.env` のキーが `supabase status` と一致していることを確認。
- **フロントで API が失敗する**: ブラウザからは `NEXT_PUBLIC_API_URL=http://localhost:8000` を使います（コンテナ名 `api` はブラウザから解決できません）。
- **Windows でファイル変更が検知されない**: `WATCHPACK_POLLING=true` を compose に設定済みです。
- **訪問候補が0件になる**: Geocoding CLI実行後、顧客の `geocoding_status` が `success` か確認します。
- **ルートAPIが503になる**: 車・徒歩・自転車は`GOOGLE_MAPS_API_KEY`とRoutes APIの設定を、
  公共交通は`docker compose ps otp`と`docker compose logs otp`でOpenTripPlannerの起動状態を確認します。
