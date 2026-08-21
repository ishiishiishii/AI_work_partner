# Start local Supabase + the api/web containers for local development.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=== AI Work Partner を起動します ==="
Write-Host "ブラウザで http://localhost:3000/dashboard を開いてください。"
Write-Host "コンテナの中に入る必要はありません。"
Write-Host ""

try {
    docker info | Out-Null
} catch {
    Write-Host "Docker Desktop が起動していません。起動してから再実行してください。"
    exit 1
}

if (-not (Get-Command supabase -ErrorAction SilentlyContinue)) {
    Write-Host "Supabase CLI が見つかりません。次を実行してから再実行してください:"
    Write-Host "  npm install -g supabase"
    exit 1
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ".env を .env.example から作成しました。"
}

Write-Host "[1/3] ローカル Supabase (DB) を起動しています..."
supabase start

function Test-CurrentSchema {
    $dbContainer = "supabase_db_ai_work_partner"
    $running = docker ps --format "{{.Names}}" | Where-Object { $_ -eq $dbContainer }
    if (-not $running) {
        return $false
    }
    $name = docker exec $dbContainer psql -U postgres -d postgres -tAc "select to_regclass('public.industry')"
    return ($name.Trim() -eq "industry")
}

if (-not (Test-CurrentSchema)) {
    Write-Host "[2/3] DB の表が古い（または未作成）ので、マイグレーションとサンプルデータを入れ直します..."
    supabase db reset --yes --local
} else {
    Write-Host "[2/3] DB スキーマは現行です。reset はスキップします。"
}

Write-Host "[3/3] アプリ (api / web) を起動しています..."
docker compose up --build
