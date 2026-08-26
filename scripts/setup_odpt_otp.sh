#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OTP_DIR="${PROJECT_DIR}/otp"

if [[ -f "${PROJECT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${PROJECT_DIR}/.env"
  set +a
fi

mkdir -p "${OTP_DIR}"

curl -fL --retry 3 \
  "https://api-public.odpt.org/api/v4/files/Toei/data/Toei-Train-GTFS.zip" \
  -o "${OTP_DIR}/toei-train-gtfs.zip"
curl -fL --retry 3 \
  "https://api-public.odpt.org/api/v4/files/Toei/data/ToeiBus-GTFS.zip" \
  -o "${OTP_DIR}/toei-bus-gtfs.zip"

if [[ -n "${ODPT_ACCESS_TOKEN:-}" ]]; then
  curl -fL --retry 3 --get \
    --data-urlencode "acl:consumerKey=${ODPT_ACCESS_TOKEN}" \
    "https://api.odpt.org/api/v4/files/TokyoMetro/data/TokyoMetro-Train-GTFS.zip" \
    -o "${OTP_DIR}/tokyo-metro-train-gtfs.zip"
fi

if [[ -n "${ODPT_CHALLENGE_ACCESS_TOKEN:-}" ]]; then
  curl -fL --retry 3 --get \
    --data-urlencode "acl:consumerKey=${ODPT_CHALLENGE_ACCESS_TOKEN}" \
    "https://api-challenge.odpt.org/api/v4/files/JR-East/data/JR-East-Train-GTFS.zip" \
    -o "${OTP_DIR}/jr-east-train-gtfs.zip"
fi

if [[ ! -f "${OTP_DIR}/kanto-latest.osm.pbf" ]]; then
  curl -fL --retry 3 \
    "https://download.geofabrik.de/asia/japan/kanto-latest.osm.pbf" \
    -o "${OTP_DIR}/kanto-latest.osm.pbf"
fi

cd "${PROJECT_DIR}"
docker compose run --rm otp --build --save
docker compose up -d otp api
