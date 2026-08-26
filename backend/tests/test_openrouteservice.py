from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.services import geocoding, route_optimization
from app.services.geocoding import (
    FallbackGeocoder,
    GeocodeResult,
    GsiGeocoder,
    OpenRouteServiceGeocoder,
    OtpStopGeocoder,
)
from app.services.route_optimization import (
    GoogleRoutesMatrixProvider,
    OpenTripPlannerTransitMatrixProvider,
    RouteMatrixPartialError,
    RoutePlanningError,
)


TOKYO = ZoneInfo("Asia/Tokyo")


def json_response(body: object) -> httpx.Response:
    return httpx.Response(
        200,
        json=body,
        request=httpx.Request("GET", "https://example.test"),
    )


def feature(
    *,
    confidence: float,
    region: str = "東京都",
    label: str = "東京都千代田区丸の内1丁目",
    country: str = "JPN",
    match_type: str = "exact",
    coordinates: list[float] | None = None,
) -> dict:
    return {
        "geometry": {
            "coordinates": coordinates or [139.7671, 35.6812],
        },
        "properties": {
            "confidence": confidence,
            "region": region,
            "label": label,
            "country_a": country,
            "match_type": match_type,
            "gid": "openstreetmap:address:1",
        },
    }


def test_geocoder_uses_server_side_key_and_accepts_precise_japanese_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def fake_get(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return json_response(
            {"features": [feature(confidence=0.95), feature(confidence=0.60)]}
        )

    monkeypatch.setattr(geocoding.httpx, "get", fake_get)
    provider = OpenRouteServiceGeocoder(
        api_key="free-token",
        api_url="https://example.test/geocode/search",
    )

    result = provider.geocode("東京都千代田区丸の内1丁目")

    assert result.status == "success"
    assert result.latitude == pytest.approx(35.6812)
    assert result.longitude == pytest.approx(139.7671)
    assert result.place_id == "openstreetmap:address:1"
    assert captured["headers"] == {"Authorization": "free-token"}
    assert captured["params"]["boundary.country"] == "JP"
    assert "api_key" not in captured["params"]


def test_geocoder_marks_ambiguous_or_low_confidence_results_for_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        geocoding.httpx,
        "get",
        lambda *args, **kwargs: json_response(
            {"features": [feature(confidence=0.84), feature(confidence=0.80)]}
        ),
    )
    provider = OpenRouteServiceGeocoder(
        api_key="free-token",
        api_url="https://example.test/geocode/search",
    )

    assert provider.geocode("東京都千代田区丸の内1丁目").status == "review"


def test_geocoder_rejects_missing_key() -> None:
    provider = OpenRouteServiceGeocoder(
        api_key="",
        api_url="https://example.test/geocode/search",
    )

    with pytest.raises(RoutePlanningError) as error:
        provider.geocode("東京都千代田区丸の内1丁目")

    assert error.value.code == "geocoding_api_unavailable"


def test_gsi_geocoder_accepts_same_prefecture_town_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def fake_get(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return json_response(
            [
                {
                    "geometry": {"coordinates": [140.882034, 38.259258]},
                    "properties": {"title": "宮城県仙台市青葉区中央"},
                }
            ]
        )

    monkeypatch.setattr(geocoding.httpx, "get", fake_get)
    result = GsiGeocoder(api_url="https://example.test/gsi").geocode(
        "宮城県仙台市青葉区中央6-27-7"
    )

    assert result.status == "success"
    assert result.accuracy == "town;source=gsi"
    assert result.latitude == pytest.approx(38.259258)
    assert captured["params"] == {"q": "宮城県仙台市青葉区中央6-27-7"}


def test_otp_stop_geocoder_prefers_station_match_without_external_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def fake_post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return json_response(
            {
                "data": {
                    "stops": [
                        {
                            "gtfsId": "2:0302-01",
                            "name": "東京国際クルーズターミナル駅前",
                            "lat": 35.622328,
                            "lon": 139.772184,
                        },
                        {
                            "gtfsId": "2:0965-01",
                            "name": "東京駅丸の内北口",
                            "lat": 35.682228,
                            "lon": 139.765036,
                        },
                    ]
                }
            }
        )

    monkeypatch.setattr(geocoding.httpx, "post", fake_post)
    result = OtpStopGeocoder(api_url="http://otp.test/otp/gtfs/v1").geocode(
        "東京駅"
    )

    assert result.status == "success"
    assert result.latitude == pytest.approx(35.682228)
    assert result.longitude == pytest.approx(139.765036)
    assert result.accuracy == "stop;source=otp"
    assert captured["json"]["variables"] == {"name": "東京"}


def test_fallback_geocoder_replaces_imprecise_primary_result() -> None:
    class StaticGeocoder:
        def __init__(self, result: GeocodeResult):
            self.result = result

        def geocode(self, address: str) -> GeocodeResult:
            del address
            return self.result

    provider = FallbackGeocoder(
        primary=StaticGeocoder(GeocodeResult(status="review")),
        fallback=StaticGeocoder(
            GeocodeResult(
                status="success",
                latitude=38.259258,
                longitude=140.882034,
                accuracy="town;source=gsi",
            )
        ),
    )

    assert provider.geocode("宮城県仙台市青葉区中央6-27-7").status == "success"


def test_open_trip_planner_builds_transit_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict] = []

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, **kwargs):
            requests.append({"url": url, **kwargs})
            return json_response(
                {
                    "data": {
                        "plan": {
                            "itineraries": [
                                {
                                    "duration": 1800,
                                    "walkDistance": 900.0,
                                    "legs": [
                                        {"mode": "WALK", "duration": 300, "distance": 400.0},
                                        {"mode": "SUBWAY", "duration": 1200, "distance": 8000.0},
                                        {"mode": "WALK", "duration": 300, "distance": 500.0},
                                    ],
                                }
                            ],
                            "messageStrings": [],
                        }
                    }
                }
            )

    monkeypatch.setattr(route_optimization.httpx, "Client", FakeClient)
    provider = OpenTripPlannerTransitMatrixProvider(
        api_url="http://otp.test/otp/gtfs/v1"
    )

    matrix = provider.get_matrix(
        [(35.6812, 139.7671), (35.6895, 139.6917)],
        datetime(2026, 8, 26, 9, 0, tzinfo=TOKYO),
    )

    assert len(requests) == 2
    assert requests[0]["json"]["variables"]["date"] == "2026-08-26"
    assert requests[0]["json"]["variables"]["time"] == "09:00:00"
    assert matrix[0][1].duration_sec == 1800
    assert matrix[0][1].distance_m == 8900


def test_open_trip_planner_returns_timed_japanese_transit_legs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def fake_post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return json_response(
            {
                "data": {
                    "plan": {
                        "itineraries": [
                            {
                                "duration": 1560,
                                "walkDistance": 550.0,
                                "legs": [
                                    {
                                        "mode": "WALK",
                                        "duration": 480,
                                        "distance": 300.0,
                                        "realTime": False,
                                        "headsign": None,
                                        "start": {"scheduledTime": "2026-08-26T09:00:00+09:00", "estimated": None},
                                        "end": {"scheduledTime": "2026-08-26T09:08:00+09:00", "estimated": None},
                                        "from": {"name": "Origin", "stop": None},
                                        "to": {"name": "浅草", "stop": {"gtfsId": "1:118", "name": "浅草", "platformCode": None}},
                                        "route": None,
                                        "trip": None,
                                    },
                                    {
                                        "mode": "SUBWAY",
                                        "duration": 540,
                                        "distance": 3600.0,
                                        "realTime": False,
                                        "headsign": "西馬込",
                                        "start": {"scheduledTime": "2026-08-26T09:09:00+09:00", "estimated": None},
                                        "end": {"scheduledTime": "2026-08-26T09:18:00+09:00", "estimated": None},
                                        "from": {"name": "浅草", "stop": {"gtfsId": "1:118", "name": "浅草", "platformCode": None}},
                                        "to": {"name": "日本橋", "stop": {"gtfsId": "1:113", "name": "日本橋", "platformCode": None}},
                                        "route": {"gtfsId": "1:1", "shortName": None, "longName": "浅草線"},
                                        "trip": {"gtfsId": "1:trip", "tripHeadsign": "西馬込"},
                                    },
                                    {
                                        "mode": "WALK",
                                        "duration": 540,
                                        "distance": 250.0,
                                        "realTime": False,
                                        "headsign": None,
                                        "start": {"scheduledTime": "2026-08-26T09:18:00+09:00", "estimated": None},
                                        "end": {"scheduledTime": "2026-08-26T09:27:00+09:00", "estimated": None},
                                        "from": {"name": "日本橋", "stop": {"gtfsId": "1:113", "name": "日本橋", "platformCode": None}},
                                        "to": {"name": "Destination", "stop": None},
                                        "route": None,
                                        "trip": None,
                                    },
                                ],
                            }
                        ],
                        "messageStrings": [],
                    }
                }
            }
        )

    monkeypatch.setattr(route_optimization.httpx, "post", fake_post)
    provider = OpenTripPlannerTransitMatrixProvider(api_url="http://otp.test/otp/gtfs/v1")

    itinerary = provider.get_itinerary(
        (35.7107, 139.7952),
        (35.6824, 139.7744),
        datetime(2026, 8, 26, 9, 0, tzinfo=TOKYO),
    )

    assert 'locale: "ja"' in captured["json"]["query"]
    assert itinerary["departure_at"] == "2026-08-26T09:00:00+09:00"
    assert itinerary["arrival_at"] == "2026-08-26T09:27:00+09:00"
    assert itinerary["duration_sec"] == 1620
    assert itinerary["scheduled_duration_sec"] == 1560
    assert itinerary["data_status"] == "時刻表ベース"
    subway = itinerary["legs"][1]
    assert subway["route_name"] == "浅草線"
    assert subway["headsign"] == "西馬込"
    assert subway["from_name"] == "浅草"
    assert subway["to_name"] == "日本橋"


def test_open_trip_planner_partial_matrix_only_excludes_disconnected_points() -> None:
    cell = route_optimization.MatrixCell(600, 1000)
    matrix = [
        [cell, cell, None],
        [cell, cell, None],
        [None, None, cell],
    ]
    missing = [(0, 2), (1, 2), (2, 0), (2, 1)]

    assert OpenTripPlannerTransitMatrixProvider._missing_point_indexes(matrix, missing) == {2}


def test_open_trip_planner_prefers_earliest_arriving_transit_itinerary() -> None:
    body = {
        "data": {
            "plan": {
                "itineraries": [
                    {
                        "duration": 2304,
                        "endTime": 1787704704000,
                        "walkDistance": 2793,
                        "legs": [{"mode": "WALK"}],
                    },
                    {
                        "duration": 1554,
                        "endTime": 1787705121000,
                        "walkDistance": 1078,
                        "legs": [
                            {"mode": "WALK"},
                            {"mode": "BUS"},
                            {"mode": "WALK"},
                        ],
                    },
                    {
                        "duration": 1400,
                        "endTime": 1787705300000,
                        "walkDistance": 900,
                        "legs": [
                            {"mode": "WALK"},
                            {"mode": "SUBWAY"},
                            {"mode": "WALK"},
                        ],
                    },
                ]
            }
        }
    }

    selected = OpenTripPlannerTransitMatrixProvider._best_itinerary(body)

    assert selected is not None
    assert selected["duration"] == 1554
    assert any(leg["mode"] == "BUS" for leg in selected["legs"])


def test_open_trip_planner_falls_back_to_walk_when_transit_is_unavailable() -> None:
    body = {
        "data": {
            "plan": {
                "itineraries": [
                    {
                        "duration": 900,
                        "endTime": 1787703300000,
                        "walkDistance": 1000,
                        "legs": [{"mode": "WALK"}],
                    }
                ]
            }
        }
    }

    selected = OpenTripPlannerTransitMatrixProvider._best_itinerary(body)

    assert selected is not None
    assert selected["legs"] == [{"mode": "WALK"}]


@pytest.mark.parametrize(
    ("travel_mode", "google_mode"),
    [
        ("driving", "DRIVE"),
        ("walking", "WALK"),
        ("cycling", "BICYCLE"),
    ],
)
def test_google_matrix_uses_selected_non_transit_mode(
    monkeypatch: pytest.MonkeyPatch,
    travel_mode: str,
    google_mode: str,
) -> None:
    captured: dict = {}

    def fake_post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return json_response(
            [
                {
                    "originIndex": origin,
                    "destinationIndex": destination,
                    "duration": "0s" if origin == destination else "125.4s",
                    "distanceMeters": 0 if origin == destination else 1500.2,
                    "condition": "ROUTE_EXISTS",
                    "status": {},
                }
                for origin in range(2)
                for destination in range(2)
            ]
        )

    monkeypatch.setattr(route_optimization.httpx, "post", fake_post)
    provider = GoogleRoutesMatrixProvider(
        api_key="google-token",
        api_url="https://example.test/computeRouteMatrix",
        travel_mode=travel_mode,
    )

    matrix = provider.get_matrix(
        [(35.6812, 139.7671), (35.6895, 139.6917)],
        datetime(2026, 8, 26, 9, 0, tzinfo=TOKYO),
    )

    assert captured["headers"]["X-Goog-Api-Key"] == "google-token"
    assert captured["json"]["travelMode"] == google_mode
    assert "departureTime" not in captured["json"]
    assert matrix[0][1].duration_sec == 125
    assert matrix[1][0].distance_m == 1500


def test_google_matrix_requires_key() -> None:
    provider = GoogleRoutesMatrixProvider(
        api_key="",
        api_url="https://example.test/computeRouteMatrix",
        travel_mode="driving",
    )

    with pytest.raises(RoutePlanningError) as error:
        provider.get_matrix(
            [(35.0, 139.0), (35.1, 139.1)],
            datetime(2026, 8, 26, 9, 0, tzinfo=TOKYO),
        )

    assert error.value.code == "google_routes_api_unavailable"


def test_google_partial_matrix_only_excludes_disconnected_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(url, **kwargs):
        del url
        return json_response(
            [
                {
                    "originIndex": origin,
                    "destinationIndex": destination,
                    "duration": "0s" if origin == destination else "120s",
                    "distanceMeters": 0 if origin == destination else 1000,
                    "condition": (
                        "ROUTE_NOT_FOUND"
                        if origin != destination and 2 in (origin, destination)
                        else "ROUTE_EXISTS"
                    ),
                    "status": {},
                }
                for origin in range(3)
                for destination in range(3)
            ]
        )

    monkeypatch.setattr(route_optimization.httpx, "post", fake_post)
    provider = GoogleRoutesMatrixProvider(
        api_key="google-token",
        api_url="https://example.test/computeRouteMatrix",
        travel_mode="driving",
    )

    with pytest.raises(RouteMatrixPartialError) as error:
        provider.get_matrix(
            [(35.68, 139.76), (35.69, 139.77), (35.70, 139.78)],
            datetime(2026, 8, 26, 9, 0, tzinfo=TOKYO),
        )

    assert error.value.point_indexes == {2}
