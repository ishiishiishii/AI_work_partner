from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

import httpx
from psycopg import Connection

from app.config import settings
from app.services.route_optimization import RoutePlanningError

TOKYO = ZoneInfo("Asia/Tokyo")
PREFECTURES = (
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
)


@dataclass(frozen=True)
class GeocodeResult:
    status: str
    latitude: float | None = None
    longitude: float | None = None
    place_id: str | None = None
    accuracy: str | None = None


class Geocoder(Protocol):
    def geocode(self, address: str) -> GeocodeResult: ...


def prefecture_from_address(address: str) -> str | None:
    return next((name for name in PREFECTURES if address.startswith(name)), None)


class OpenRouteServiceGeocoder:
    def __init__(
        self,
        *,
        api_key: str,
        api_url: str,
        min_confidence: float = 0.8,
        timeout: float = 20,
    ):
        self.api_key = api_key
        self.api_url = api_url
        self.min_confidence = min_confidence
        self.timeout = timeout

    def geocode(self, address: str) -> GeocodeResult:
        if not self.api_key:
            raise RoutePlanningError(
                "geocoding_api_unavailable",
                "openrouteservice APIキーが設定されていません。",
            )
        try:
            response = httpx.get(
                self.api_url,
                headers={"Authorization": self.api_key},
                params={
                    "text": address,
                    "boundary.country": "JP",
                    "lang": "ja",
                    "size": 5,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise RoutePlanningError(
                "geocoding_api_unavailable",
                "openrouteservice Geocoding APIに接続できませんでした。",
            ) from error

        features = body.get("features", []) if isinstance(body, dict) else []
        if not isinstance(features, list):
            raise RoutePlanningError(
                "geocoding_api_invalid",
                "openrouteservice Geocoding APIの応答形式が不正です。",
            )
        if not features:
            return GeocodeResult(status="failed")

        first = features[0] if isinstance(features[0], dict) else {}
        properties = first.get("properties", {})
        coordinates = first.get("geometry", {}).get("coordinates", [])
        if (
            not isinstance(properties, dict)
            or not isinstance(coordinates, list)
            or len(coordinates) < 2
        ):
            return GeocodeResult(status="failed")
        try:
            longitude = float(coordinates[0])
            latitude = float(coordinates[1])
            confidence = float(properties.get("confidence", 0))
        except (TypeError, ValueError):
            return GeocodeResult(status="failed")

        second_confidence = 0.0
        if len(features) > 1 and isinstance(features[1], dict):
            try:
                second_confidence = float(
                    features[1].get("properties", {}).get("confidence", 0)
                )
            except (AttributeError, TypeError, ValueError):
                second_confidence = 0.0

        source_prefecture = prefecture_from_address(address)
        returned_text = f"{properties.get('region', '')} {properties.get('label', '')}"
        country_code = str(properties.get("country_a", "")).upper()
        match_type = str(
            properties.get("match_type") or properties.get("accuracy") or "unknown"
        )
        unambiguous = len(features) == 1 or confidence - second_confidence >= 0.1
        precise = confidence >= self.min_confidence and match_type != "fallback"
        same_prefecture = (
            source_prefecture is not None and source_prefecture in returned_text
        )
        in_japan = country_code in {"JP", "JPN"} or "日本" in returned_text
        status = (
            "success"
            if unambiguous and precise and same_prefecture and in_japan
            else "review"
        )
        return GeocodeResult(
            status=status,
            latitude=latitude,
            longitude=longitude,
            place_id=properties.get("gid") or properties.get("id"),
            accuracy=f"{match_type};confidence={confidence:.2f}",
        )


class GsiGeocoder:
    """Free Japanese-address fallback backed by the GSI address search."""

    def __init__(self, *, api_url: str, timeout: float = 20):
        self.api_url = api_url
        self.timeout = timeout

    def geocode(self, address: str) -> GeocodeResult:
        try:
            response = httpx.get(
                self.api_url,
                params={"q": address},
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise RoutePlanningError(
                "geocoding_api_unavailable",
                "国土地理院の住所検索APIに接続できませんでした。",
            ) from error

        if not isinstance(body, list) or not body:
            return GeocodeResult(status="failed")
        first = body[0] if isinstance(body[0], dict) else {}
        properties = first.get("properties", {})
        coordinates = first.get("geometry", {}).get("coordinates", [])
        if (
            not isinstance(properties, dict)
            or not isinstance(coordinates, list)
            or len(coordinates) < 2
        ):
            return GeocodeResult(status="failed")
        try:
            longitude = float(coordinates[0])
            latitude = float(coordinates[1])
        except (TypeError, ValueError):
            return GeocodeResult(status="failed")

        title = str(properties.get("title", ""))
        source_prefecture = prefecture_from_address(address)
        status = (
            "success"
            if source_prefecture is not None and title.startswith(source_prefecture)
            else "review"
        )
        return GeocodeResult(
            status=status,
            latitude=latitude,
            longitude=longitude,
            place_id=f"gsi:{title}" if title else None,
            # GSI commonly resolves the generated demo addresses to a town
            # representative point, so record that limitation explicitly.
            accuracy="town;source=gsi",
        )


class OtpStopGeocoder:
    """Resolve station names from the locally loaded OpenTripPlanner graph."""

    def __init__(self, *, api_url: str, timeout: float = 10):
        self.api_url = api_url
        self.timeout = timeout

    def geocode(self, address: str) -> GeocodeResult:
        target = address.strip()
        base_name = target[:-1] if target.endswith("駅") else target
        try:
            response = httpx.post(
                self.api_url,
                json={
                    "query": (
                        "query Stops($name: String!) { "
                        "stops(name: $name) { gtfsId name lat lon } }"
                    ),
                    "variables": {"name": base_name},
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise RoutePlanningError(
                "otp_api_unavailable",
                "OpenTripPlannerの駅検索APIに接続できませんでした。",
            ) from error

        stops = body.get("data", {}).get("stops", []) if isinstance(body, dict) else []
        if not isinstance(stops, list) or not stops:
            return GeocodeResult(status="failed")

        def rank(stop: dict) -> tuple[int, int, int, str]:
            name = str(stop.get("name") or "").replace(" ", "")
            if name in {target, base_name}:
                match_rank = 0
            elif name.startswith(target):
                match_rank = 1
            elif target in name:
                match_rank = 2
            elif name.startswith(base_name):
                match_rank = 3
            elif base_name in name:
                match_rank = 4
            else:
                match_rank = 5
            # 同順位なら鉄道フィードをバス停より優先し、短い名称を選ぶ。
            feed_rank = 0 if str(stop.get("gtfsId") or "").startswith("1:") else 1
            return match_rank, feed_rank, len(name), name

        valid_stops = [stop for stop in stops if isinstance(stop, dict)]
        if not valid_stops:
            return GeocodeResult(status="failed")
        best = min(valid_stops, key=rank)
        try:
            latitude = float(best["lat"])
            longitude = float(best["lon"])
        except (KeyError, TypeError, ValueError):
            return GeocodeResult(status="failed")
        return GeocodeResult(
            status="success",
            latitude=latitude,
            longitude=longitude,
            place_id=str(best.get("gtfsId") or "") or None,
            accuracy="stop;source=otp",
        )


class FallbackGeocoder:
    def __init__(self, *, primary: Geocoder, fallback: Geocoder):
        self.primary = primary
        self.fallback = fallback

    def geocode(self, address: str) -> GeocodeResult:
        try:
            primary_result = self.primary.geocode(address)
        except RoutePlanningError:
            primary_result = GeocodeResult(status="failed")
        if primary_result.status == "success":
            return primary_result

        fallback_result = self.fallback.geocode(address)
        return (
            fallback_result
            if fallback_result.status != "failed"
            else primary_result
        )


def default_geocoder() -> Geocoder:
    return FallbackGeocoder(
        # The current demo dataset contains synthetic Japanese street numbers.
        # GSI resolves their real town portion reliably and avoids spending the
        # openrouteservice quota on Pelias fallbacks; ORS remains the backup.
        primary=GsiGeocoder(api_url=settings.gsi_geocoding_api_url),
        fallback=OpenRouteServiceGeocoder(
            api_key=settings.ors_api_key,
            api_url=settings.ors_geocoding_api_url,
            min_confidence=settings.ors_geocoding_min_confidence,
        ),
    )


def geocode_pending_customers(
    conn: Connection,
    *,
    limit: int = 300,
    geocoder: Geocoder | None = None,
) -> dict[str, int]:
    geocoder = geocoder or default_geocoder()
    rows = conn.execute(
        """
        select customer_id, location
        from customer
        where geocoding_status in ('pending', 'failed')
        order by customer_id
        limit %s
        """,
        (limit,),
    ).fetchall()
    counts = {"processed": 0, "success": 0, "review": 0, "failed": 0}
    for row in rows:
        result = geocoder.geocode(row["location"])
        conn.execute(
            """
            update customer
            set latitude = %s,
                longitude = %s,
                place_id = %s,
                geocoding_status = %s,
                geocode_accuracy = %s,
                geocoded_at = %s
            where customer_id = %s
            """,
            (
                result.latitude,
                result.longitude,
                result.place_id,
                result.status,
                result.accuracy,
                datetime.now(TOKYO),
                row["customer_id"],
            ),
        )
        counts["processed"] += 1
        counts[result.status] += 1
    conn.commit()
    return counts


# The demo addresses use real prefecture/city/town names with synthetic block
# numbers. The lightweight map view stores a town-level coordinate separately
# from the stricter route-planning geocode above.
_BLOCK_NUMBER_PATTERN = re.compile(r"\d+-\d+-\d+$")
_GSI_ENDPOINT = "https://msearch.gsi.go.jp/address-search/AddressSearch"
_RATE_LIMIT_SECONDS = 0.3
DEFAULT_BACKFILL_LIMIT = 20


def strip_block_number(location: str) -> str:
    """Return the real prefecture/city/town portion of a demo address."""
    return _BLOCK_NUMBER_PATTERN.sub("", location).strip()


def geocode_address(address: str) -> tuple[float, float] | None:
    """Return (latitude, longitude), or None when GSI cannot resolve it."""
    try:
        response = httpx.get(_GSI_ENDPOINT, params={"q": address}, timeout=5)
        response.raise_for_status()
        results = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not results:
        return None
    longitude, latitude = results[0]["geometry"]["coordinates"]
    return (latitude, longitude)


def geocode_customer_location(location: str) -> tuple[float, float] | None:
    return geocode_address(strip_block_number(location))


def backfill_customer_coordinates(
    conn: Connection,
    *,
    limit: int = DEFAULT_BACKFILL_LIMIT,
) -> int:
    """Backfill town-level lat/lng used by the customer map."""
    rows = conn.execute(
        "select customer_id, location from customer where lat is null "
        "order by customer_id limit %s",
        (limit,),
    ).fetchall()
    updated = 0
    for index, row in enumerate(rows):
        coords = geocode_customer_location(row["location"])
        if coords is not None:
            latitude, longitude = coords
            conn.execute(
                "update customer set lat = %s, lng = %s where customer_id = %s",
                (latitude, longitude, row["customer_id"]),
            )
            updated += 1
        if index < len(rows) - 1:
            time.sleep(_RATE_LIMIT_SECONDS)
    conn.commit()
    return updated
