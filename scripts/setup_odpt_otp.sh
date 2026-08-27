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
  curl -fL --retry 3 --get \
    --data-urlencode "acl:consumerKey=${ODPT_ACCESS_TOKEN}" \
    "https://api.odpt.org/api/v4/files/TWR/data/TWR-Train-GTFS.zip" \
    -o "${OTP_DIR}/twr-rinkai-train-gtfs.zip"
  curl -fL --retry 3 --get \
    --data-urlencode "acl:consumerKey=${ODPT_ACCESS_TOKEN}" \
    "https://api.odpt.org/api/v4/files/MIR/data/MIR-Train-GTFS.zip" \
    -o "${OTP_DIR}/tsukuba-express-train-gtfs.zip"
  curl -fL --retry 3 --get \
    --data-urlencode "acl:consumerKey=${ODPT_ACCESS_TOKEN}" \
    "https://api.odpt.org/api/v4/files/TamaMonorail/data/TamaMonorail-Train-GTFS.zip" \
    -o "${OTP_DIR}/tama-monorail-train-gtfs.zip"
  # ODPTは横浜市営地下鉄GTFSを日付版で公開しており「最新」の固定URLがない。
  # 更新時は https://ckan.odpt.org/en/dataset/yokohama_municipal_train で最新日付を確認して置き換える。
  curl -fL --retry 3 --get \
    --data-urlencode "acl:consumerKey=${ODPT_ACCESS_TOKEN}" \
    "https://api.odpt.org/api/v4/files/odpt/YokohamaMunicipal/Train.zip?date=20251226" \
    -o "${OTP_DIR}/yokohama-municipal-train-gtfs.zip"
fi

if [[ -n "${ODPT_CHALLENGE_ACCESS_TOKEN:-}" ]]; then
  curl -fL --retry 3 --get \
    --data-urlencode "acl:consumerKey=${ODPT_CHALLENGE_ACCESS_TOKEN}" \
    "https://api-challenge.odpt.org/api/v4/files/JR-East/data/JR-East-Train-GTFS.zip" \
    -o "${OTP_DIR}/jr-east-train-gtfs.zip"
  curl -fL --retry 3 --get \
    --data-urlencode "acl:consumerKey=${ODPT_CHALLENGE_ACCESS_TOKEN}" \
    "https://api-challenge.odpt.org/api/v4/files/Sotetsu/data/Sotetsu-Train-GTFS.zip" \
    -o "${OTP_DIR}/sotetsu-train-gtfs.zip"
  curl -fL --retry 3 --get \
    --data-urlencode "acl:consumerKey=${ODPT_CHALLENGE_ACCESS_TOKEN}" \
    "https://api-challenge.odpt.org/api/v4/files/Keio/data/Keio-Train-GTFS.zip" \
    -o "${OTP_DIR}/keio-train-gtfs.zip"
  curl -fL --retry 3 --get \
    --data-urlencode "acl:consumerKey=${ODPT_CHALLENGE_ACCESS_TOKEN}" \
    "https://api-challenge.odpt.org/api/v4/files/Tobu/data/Tobu-Train-GTFS.zip" \
    -o "${OTP_DIR}/tobu-train-gtfs.zip"
fi

if [[ ! -f "${OTP_DIR}/kanto-latest.osm.pbf" ]]; then
  curl -fL --retry 3 \
    "https://download.geofabrik.de/asia/japan/kanto-latest.osm.pbf" \
    -o "${OTP_DIR}/kanto-latest.osm.pbf"
fi

cd "${PROJECT_DIR}"
docker compose run --rm otp --build --save
docker compose up -d otp api
