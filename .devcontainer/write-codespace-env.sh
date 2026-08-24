#!/usr/bin/env bash
# Codespaces postStartCommand: rewrite the browser-facing URLs in .env to use
# this Codespace's public forwarded domain instead of localhost/127.0.0.1.
#
# Why this is needed: NEXT_PUBLIC_* values are read by the browser (and by
# Supabase Auth calls made directly from the browser), not by the containers.
# Inside a Codespace, "localhost" from the *browser's* point of view is the
# developer's own machine, not the Codespace -- so it must point at the
# forwarded https://<codespace>-<port>.<domain> URL instead.
#
# Runs every time the Codespace starts (CODESPACE_NAME is stable for the life
# of a given Codespace, but the script is idempotent either way). It only
# rewrites URLs -- the anon/service_role keys still come from
# `supabase status` per the normal setup flow (see README).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -z "${CODESPACE_NAME:-}" ]; then
  echo "CODESPACE_NAME is not set -- not running in a Codespace, skipping."
  exit 0
fi

DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
WEB_URL="https://${CODESPACE_NAME}-3000.${DOMAIN}"
API_URL="https://${CODESPACE_NAME}-8000.${DOMAIN}"
SUPABASE_URL="https://${CODESPACE_NAME}-55321.${DOMAIN}"

if [ ! -f .env ]; then
  cp .env.example .env
fi

set_env() {
  local key="$1" value="$2"
  local escaped
  escaped=$(printf '%s' "$value" | sed -e 's/[\/&]/\\&/g')
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${escaped}|" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

set_env "SUPABASE_URL" "$SUPABASE_URL"
set_env "NEXT_PUBLIC_SUPABASE_URL" "$SUPABASE_URL"
set_env "NEXT_PUBLIC_API_URL" "$API_URL"
set_env "API_PUBLIC_URL" "$API_URL"
set_env "API_CORS_ORIGINS" "http://localhost:3000,${WEB_URL}"

echo ""
echo "Codespaces用に .env のURLを更新しました:"
echo "  Web:      $WEB_URL"
echo "  API:      $API_URL"
echo "  Supabase: $SUPABASE_URL"
echo ""
echo "次の手順:"
echo "  1) supabase start"
echo "  2) supabase status  (anon key / service_role key を確認し、.env の"
echo "     SUPABASE_ANON_KEY / NEXT_PUBLIC_SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY へ反映)"
echo "  3) docker compose exec api python3 -m scripts.seed_demo_auth_users"
echo "  4) docker compose up --build -d"
echo "  5) VS Code の Ports パネルで 3000 / 8000 / 55321 の Visibility を Public に変更"
echo "  6) $WEB_URL をスマホ等で開く"
