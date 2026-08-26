from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.config import settings
from app.schemas.route_plans import (
    RouteEndpointInput,
    RoutePlanPreviewRequest,
    RouteSearchAreaInput,
)
from app.services.geocoding import (
    GeocodeResult,
    OpenRouteServiceGeocoder,
    OtpStopGeocoder,
    default_geocoder,
    prefecture_from_address,
)
from app.services.route_optimization import (
    AffinityEvidence,
    DealEconomics,
    GoogleRoutesMatrixProvider,
    OpenTripPlannerTransitMatrixProvider,
    MatrixCell,
    MatrixProvider,
    RoutePlanningError,
    RouteMatrixPartialError,
    RoutedOption,
    VisitCandidate,
    evaluate_options,
    generate_portfolios,
    route_portfolio,
    score_candidates,
)

TOKYO = ZoneInfo("Asia/Tokyo")
TRAVEL_MODE_CACHE_KEYS = {
    "driving": "GOOGLE_DRIVE",
    "transit": "ODPT_OTP_TRANSIT_V3",
    "walking": "GOOGLE_WALK",
    "cycling": "GOOGLE_BICYCLE",
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral() else float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def policy_weights(
    policy: str,
    *,
    sales_weight_percent: int | None = None,
    gross_profit_weight_percent: int | None = None,
) -> dict[str, int]:
    if policy == "sales":
        weights = {
            "sales": 40,
            "gross_profit": 25,
            "affinity": settings.route_affinity_weight,
            "urgency": 10,
            "phase": 5,
            "target_gap": 5,
        }
    elif policy == "gross_profit":
        weights = {
            "sales": 20,
            "gross_profit": 45,
            "affinity": settings.route_affinity_weight,
            "urgency": 10,
            "phase": 5,
            "target_gap": 5,
        }
    elif policy == "short_travel":
        weights = {
            "sales": 15,
            "gross_profit": 20,
            "affinity": settings.route_affinity_weight,
            "urgency": 20,
            "phase": 15,
            "target_gap": 15,
        }
    else:
        weights = {
            "sales": settings.route_sales_weight,
            "gross_profit": settings.route_gross_profit_weight,
            "affinity": settings.route_affinity_weight,
            "urgency": settings.route_urgency_weight,
            "phase": settings.route_phase_weight,
            "target_gap": settings.route_target_gap_weight,
        }

    if sales_weight_percent is not None and gross_profit_weight_percent is not None:
        economics_total = weights["sales"] + weights["gross_profit"]
        sales_weight = (economics_total * sales_weight_percent + 50) // 100
        weights["sales"] = sales_weight
        weights["gross_profit"] = economics_total - sales_weight
    return weights


def _rep_branch(conn: Connection, rep_id: int) -> dict:
    row = conn.execute(
        """
        select sr.rep_id, sr.rep_name, b.branch_id, b.branch_name, b.location,
               b.latitude, b.longitude
        from sales_rep sr
        join branch b on b.branch_id = sr.branch_id
        where sr.rep_id = %s
        """,
        (rep_id,),
    ).fetchone()
    if not row:
        raise RoutePlanningError("rep_not_found", "営業担当者が見つかりません。")
    if row["latitude"] is None or row["longitude"] is None:
        raise RoutePlanningError("branch_geocoding_missing", "所属営業所の座標がありません。")
    return dict(row)


def _resolve_endpoint(
    branch: dict,
    endpoint: RouteEndpointInput,
    *,
    label: str,
) -> dict[str, Any]:
    if endpoint.kind == "branch":
        return {
            "kind": "branch",
            "label": f"{branch['branch_name']}営業所",
            "address": branch["location"],
            "latitude": float(branch["latitude"]),
            "longitude": float(branch["longitude"]),
            "cache_key": f"branch:{branch['branch_id']}",
        }

    address = (endpoint.address or "").strip()
    result = default_geocoder().geocode(address)
    if result.status != "success" or result.latitude is None or result.longitude is None:
        raise RoutePlanningError(
            "endpoint_geocoding_failed",
            f"{label}の住所を十分な精度で座標化できませんでした。住所を確認してください。",
        )
    return {
        "kind": "custom",
        "label": address,
        "address": address,
        "latitude": result.latitude,
        "longitude": result.longitude,
        "cache_key": f"custom:{result.latitude:.6f},{result.longitude:.6f}",
        "geocode_accuracy": result.accuracy,
    }


def _resolve_search_area(
    branch: dict,
    area: RouteSearchAreaInput,
    *,
    start_location: dict[str, Any],
    conn: Connection | None = None,
) -> dict[str, Any]:
    if area.kind == "auto":
        return {
            "kind": "auto",
            "label": "出発地点周辺（自動探索）",
            "query": None,
            "latitude": float(start_location["latitude"]),
            "longitude": float(start_location["longitude"]),
            "radius_km": None,
        }

    raw_query = (area.query or "").strip()
    normalized_query = re.sub(r"(?:周辺|付近)$", "", raw_query).strip()
    branch_prefecture = prefecture_from_address(str(branch.get("location") or ""))
    contextual_query = normalized_query
    # 「新宿区」のような区名だけは所属都道府県で曖昧さを減らす。
    # 「横浜市」まで東京都で補完すると別地点になるため、市町村を含む入力には追加しない。
    is_bare_ward = normalized_query.endswith("区") and not any(
        marker in normalized_query[:-1] for marker in ("都", "道", "府", "県", "市", "町", "村")
    )
    if (
        branch_prefecture
        and prefecture_from_address(normalized_query) is None
        and is_bare_ward
    ):
        contextual_query = f"{branch_prefecture}{normalized_query}"

    # 国土地理院の住所検索は区市町村に強い一方、「東京駅」を
    # 「東京都東久留米市」と解釈することがある。駅名はローカルのOTPを優先し、
    # 収録外の駅だけPOIを扱えるORSへフォールバックする。
    if normalized_query.endswith("駅"):
        try:
            result = OtpStopGeocoder(api_url=settings.otp_api_url).geocode(
                normalized_query
            )
        except RoutePlanningError:
            result = GeocodeResult(status="failed")
        if result.latitude is None or result.longitude is None:
            try:
                result = OpenRouteServiceGeocoder(
                    api_key=settings.ors_api_key,
                    api_url=settings.ors_geocoding_api_url,
                    min_confidence=settings.ors_geocoding_min_confidence,
                ).geocode(normalized_query)
            except RoutePlanningError:
                result = GeocodeResult(status="failed")
        if str(result.accuracy or "").startswith("fallback"):
            result = GeocodeResult(status="failed")
    else:
        result = GeocodeResult(status="failed")
        if conn is not None:
            local_center = conn.execute(
                """
                select avg(c.latitude)::float8 as latitude,
                       avg(c.longitude)::float8 as longitude
                from customer c
                join prefecture_branch pb
                  on c.location like pb.prefecture_name || '%%'
                 and pb.branch_id = %s
                where c.geocoding_status = 'success'
                  and c.latitude is not null and c.longitude is not null
                  and c.location ilike %s
                """,
                (branch["branch_id"], f"%{normalized_query}%"),
            ).fetchone()
            if local_center and local_center["latitude"] is not None:
                result = GeocodeResult(
                    status="success",
                    latitude=float(local_center["latitude"]),
                    longitude=float(local_center["longitude"]),
                    accuracy="customer-centroid;source=database",
                )
        if result.latitude is None or result.longitude is None:
            try:
                result = default_geocoder().geocode(contextual_query)
            except RoutePlanningError:
                result = GeocodeResult(status="failed")

    if result.latitude is None or result.longitude is None:
        raise RoutePlanningError(
            "search_area_geocoding_failed",
            "訪問エリアを特定できませんでした。都道府県を含む区名、または駅名を確認してください。",
        )
    if not (20 <= result.latitude <= 50 and 120 <= result.longitude <= 155):
        raise RoutePlanningError(
            "search_area_outside_japan",
            "訪問エリアを日本国内の地点として特定できませんでした。入力内容を確認してください。",
        )
    return {
        "kind": "custom",
        "label": f"{raw_query} 周辺（半径{area.radius_km}km）",
        "query": raw_query,
        "latitude": result.latitude,
        "longitude": result.longitude,
        "radius_km": area.radius_km,
        "geocode_accuracy": result.accuracy,
    }


def _exclusion_stats(conn: Connection, *, rep_id: int, branch_id: int) -> dict[str, int]:
    row = conn.execute(
        """
        select
          count(*)::int as ongoing_deals,
          count(*) filter (where c.geocoding_status <> 'success')::int as bad_geocoding,
          count(*) filter (
            where pb.branch_id is null or pb.branch_id <> %s
          )::int as outside_area,
          count(*) filter (where d.cost is null)::int as missing_cost
        from deal d
        join deal_result_status drs
          on drs.deal_result_status_id = d.deal_result_status_id
        join customer c on c.customer_id = d.customer_id
        left join prefecture_branch pb
          on c.location like pb.prefecture_name || '%%'
        where d.rep_id = %s and drs.status_code = 'ongoing'
        """,
        (branch_id, rep_id),
    ).fetchone()
    return dict(row)


def _candidate_rows(
    conn: Connection,
    *,
    rep_id: int,
    branch_id: int,
    target_date: date,
    radius_m: int,
    limit: int,
    origin_latitude: float,
    origin_longitude: float,
    include_mandatory_anchors: bool = True,
    enforce_branch_territory: bool = True,
) -> list[dict]:
    rows = conn.execute(
        """
        with origin as (
          select st_setsrid(
            st_makepoint(%(origin_longitude)s, %(origin_latitude)s), 4326
          )::geography as geo_point
        ),
        mandatory_anchor as (
          select distinct c.geo_point
          from deal d
          join deal_result_status drs
            on drs.deal_result_status_id = d.deal_result_status_id
           and drs.status_code = 'ongoing'
          join customer c on c.customer_id = d.customer_id
          left join prefecture_branch pb
            on c.location like pb.prefecture_name || '%%'
          where d.rep_id = %(rep_id)s
            and d.must_visit
            and (
              not %(enforce_branch_territory)s
              or pb.branch_id = %(branch_id)s
            )
            and c.geocoding_status = 'success'
            and c.geo_point is not null
            and not exists (
              select 1 from activity_plan ap
              where ap.rep_id = %(rep_id)s
                and ap.plan_date = %(target_date)s
                and ap.deal_id = d.deal_id
                and ap.plan_status = 'scheduled'
            )
        ),
        eligible_customer as (
          select c.customer_id,
                 min(st_distance(
                   c.geo_point,
                   origin.geo_point
                 ))::int as branch_distance_m,
                 min(least(
                   st_distance(c.geo_point, origin.geo_point),
                   coalesce(
                     (
                       select min(st_distance(c.geo_point, anchor.geo_point))
                       from mandatory_anchor anchor
                     ),
                     st_distance(c.geo_point, origin.geo_point)
                   )
                 ))::int as area_distance_m,
                 bool_or(d.must_visit) as any_must_visit,
                 min(d.visit_deadline) as nearest_deadline
          from sales_rep sr
          join branch b on b.branch_id = sr.branch_id
          join deal d on d.rep_id = sr.rep_id
          join deal_result_status drs
            on drs.deal_result_status_id = d.deal_result_status_id
           and drs.status_code = 'ongoing'
          join customer c on c.customer_id = d.customer_id
          left join prefecture_branch pb
            on c.location like pb.prefecture_name || '%%'
          cross join origin
          where sr.rep_id = %(rep_id)s
            and sr.branch_id = %(branch_id)s
            and c.geocoding_status = 'success'
            and c.geo_point is not null
            and (
              not %(enforce_branch_territory)s
              or pb.branch_id = sr.branch_id
            )
            and (
              d.must_visit
              or st_dwithin(
                c.geo_point,
                origin.geo_point,
                %(radius_m)s
              )
              or exists (
                select 1
                from mandatory_anchor anchor
                where %(include_mandatory_anchors)s
                  and st_dwithin(c.geo_point, anchor.geo_point, %(radius_m)s)
              )
            )
            and not exists (
              select 1 from activity_plan ap
              where ap.rep_id = %(rep_id)s
                and ap.plan_date = %(target_date)s
                and ap.deal_id = d.deal_id
                and ap.plan_status = 'scheduled'
            )
          group by c.customer_id
        ),
        selected_customer as (
          select *
          from eligible_customer
          order by any_must_visit desc, nearest_deadline asc nulls last,
                   area_distance_m asc
          limit %(limit)s
        )
        select c.customer_id, c.customer_name, c.latitude, c.longitude,
               selected.branch_distance_m, selected.area_distance_m,
               d.deal_id, d.estimated_amount, d.cost, d.win_probability,
               d.visit_duration_min, d.visit_window_start, d.visit_window_end,
               d.must_visit, d.visit_deadline,
               dp.deal_phase_name,
               i.industry_name, pc.category_name,
               coalesce(fit.deal_count, 0) as affinity_deal_count,
               coalesce(fit.won_count, 0) as affinity_won_count,
               coalesce(fit.win_rate, 0) as affinity_win_rate
        from selected_customer selected
        join customer c on c.customer_id = selected.customer_id
        join deal d on d.customer_id = c.customer_id and d.rep_id = %(rep_id)s
        join deal_result_status drs
          on drs.deal_result_status_id = d.deal_result_status_id
         and drs.status_code = 'ongoing'
        join deal_phase dp on dp.deal_phase_id = d.deal_phase_id
        join industry i on i.industry_id = c.industry_id
        join product p on p.product_id = d.product_id
        join product_subcategory ps on ps.subcategory_id = p.subcategory_id
        join product_category pc on pc.category_id = ps.category_id
        left join lateral (
          select
            sum(ra.deal_count)::int as deal_count,
            sum(ra.won_count)::int as won_count,
            case
              when sum(ra.deal_count) > 0
              then sum(ra.won_count)::numeric / sum(ra.deal_count)
              else 0
            end as win_rate
          from rep_affinity ra
          where ra.rep_id = %(rep_id)s
            and ra.industry_id = c.industry_id
            and ra.category_id = ps.category_id
        ) fit on true
        where not exists (
          select 1 from activity_plan ap
          where ap.rep_id = %(rep_id)s
            and ap.plan_date = %(target_date)s
            and ap.deal_id = d.deal_id
            and ap.plan_status = 'scheduled'
        )
        order by selected.any_must_visit desc, selected.area_distance_m,
                 c.customer_id, d.deal_id
        """,
        {
            "rep_id": rep_id,
            "branch_id": branch_id,
            "target_date": target_date,
            "radius_m": radius_m,
            "limit": limit,
            "origin_latitude": origin_latitude,
            "origin_longitude": origin_longitude,
            "include_mandatory_anchors": include_mandatory_anchors,
            "enforce_branch_territory": enforce_branch_territory,
        },
    ).fetchall()
    return list(rows)


def _group_candidates(rows: list[dict]) -> list[VisitCandidate]:
    grouped: dict[int, VisitCandidate] = {}
    window_starts: dict[int, list[time]] = {}
    window_ends: dict[int, list[time]] = {}
    for row in rows:
        customer_id = row["customer_id"]
        if customer_id not in grouped:
            grouped[customer_id] = VisitCandidate(
                customer_id=customer_id,
                customer_name=row["customer_name"],
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                deal_ids=[],
                phase_names=[],
                economics=[],
                distance_from_branch_m=row["branch_distance_m"],
            )
            window_starts[customer_id] = []
            window_ends[customer_id] = []
        candidate = grouped[customer_id]
        candidate.deal_ids.append(row["deal_id"])
        candidate.phase_names.append(row["deal_phase_name"])
        candidate.economics.append(
            DealEconomics(
                estimated_amount=Decimal(row["estimated_amount"]),
                cost=Decimal(row["cost"]) if row["cost"] is not None else None,
                win_probability=Decimal(row["win_probability"]),
            )
        )
        affinity_deal_count = int(row["affinity_deal_count"] or 0)
        affinity_key = (row["industry_name"], row["category_name"])
        if affinity_deal_count > 0 and not any(
            (evidence.industry_name, evidence.category_name) == affinity_key
            for evidence in candidate.affinity_evidence
        ):
            affinity_win_rate = Decimal(row["affinity_win_rate"] or 0)
            reliability = Decimal(affinity_deal_count) / Decimal(
                affinity_deal_count + 3
            )
            candidate.affinity_evidence.append(
                AffinityEvidence(
                    industry_name=row["industry_name"],
                    category_name=row["category_name"],
                    deal_count=affinity_deal_count,
                    won_count=int(row["affinity_won_count"] or 0),
                    win_rate=affinity_win_rate,
                    match_score=(
                        affinity_win_rate * Decimal("100") * reliability
                    ).quantize(Decimal("0.01")),
                )
            )
        candidate.visit_duration_min = max(
            candidate.visit_duration_min, row["visit_duration_min"]
        )
        candidate.must_visit = candidate.must_visit or row["must_visit"]
        if row["visit_deadline"] is not None:
            candidate.visit_deadline = min(
                filter(
                    lambda value: value is not None,
                    (candidate.visit_deadline, row["visit_deadline"]),
                )
            )
        if row["visit_window_start"] is not None:
            window_starts[customer_id].append(row["visit_window_start"])
        if row["visit_window_end"] is not None:
            window_ends[customer_id].append(row["visit_window_end"])
    for customer_id, candidate in grouped.items():
        if window_starts[customer_id]:
            candidate.window_start = max(window_starts[customer_id])
        if window_ends[customer_id]:
            candidate.window_end = min(window_ends[customer_id])
    return list(grouped.values())


def load_candidates(
    conn: Connection,
    *,
    rep_id: int,
    branch_id: int,
    target_date: date,
    origin: dict[str, Any],
    fixed_radius_km: int | None = None,
    include_mandatory_anchors: bool = True,
    enforce_branch_territory: bool = True,
) -> tuple[list[VisitCandidate], list[str], dict[str, int]]:
    stats = _exclusion_stats(conn, rep_id=rep_id, branch_id=branch_id)
    radius_km = fixed_radius_km or settings.route_search_radius_km
    prefilter_limit = min(100, max(
        settings.route_candidate_limit,
        settings.route_candidate_limit * 3,
    ))
    candidates: list[VisitCandidate] = []
    while True:
        candidates = _group_candidates(
            _candidate_rows(
                conn,
                rep_id=rep_id,
                branch_id=branch_id,
                target_date=target_date,
                radius_m=radius_km * 1000,
                limit=prefilter_limit,
                origin_latitude=float(origin["latitude"]),
                origin_longitude=float(origin["longitude"]),
                include_mandatory_anchors=include_mandatory_anchors,
                enforce_branch_territory=enforce_branch_territory,
            )
        )
        if (
            fixed_radius_km is not None
            or len(candidates) >= settings.route_candidate_limit
            or radius_km >= settings.route_max_search_radius_km
        ):
            break
        radius_km = min(radius_km * 2, settings.route_max_search_radius_km)

    warnings: list[str] = []
    if stats["bad_geocoding"]:
        warnings.append(
            f"座標未確定または精度不足の商談{stats['bad_geocoding']}件を除外しました。"
        )
    if stats["outside_area"] and enforce_branch_territory:
        warnings.append(f"担当エリア外の商談{stats['outside_area']}件を除外しました。")
    if stats["missing_cost"]:
        warnings.append(
            f"原価未登録の商談{stats['missing_cost']}件は粗利評価不可として扱いました。"
        )
    if fixed_radius_km is not None:
        warnings.append(
            f"指定した中心地点から半径{fixed_radius_km}km以内の訪問候補を対象にしました。"
        )
    elif len(candidates) < settings.route_candidate_limit:
        warnings.append(
            f"検索半径を最大{settings.route_max_search_radius_km}kmまで広げ、"
            f"{len(candidates)}社を候補にしました。"
        )
    return candidates, warnings, stats


def _limit_scored_candidates(
    candidates: list[VisitCandidate],
    *,
    limit: int,
) -> list[VisitCandidate]:
    mandatory = [candidate for candidate in candidates if candidate.must_visit]
    if len(mandatory) > limit:
        raise RoutePlanningError(
            "too_many_mandatory_visits",
            f"必須訪問が{len(mandatory)}件あり、候補上限{limit}件を超えています。",
        )
    optional = sorted(
        (candidate for candidate in candidates if not candidate.must_visit),
        key=lambda candidate: (
            candidate.value_score,
            candidate.expected_gross_profit
            if candidate.expected_gross_profit is not None
            else Decimal("-Infinity"),
            candidate.expected_sales,
            -candidate.distance_from_branch_m,
        ),
        reverse=True,
    )
    selected = mandatory + optional[: max(0, limit - len(mandatory))]
    return sorted(
        selected,
        key=lambda candidate: (candidate.must_visit, candidate.value_score),
        reverse=True,
    )


def _blocked_windows(conn: Connection, *, rep_id: int, target_date: date) -> list[tuple[time, time]]:
    rows = conn.execute(
        """
        select start_time, end_time
        from activity_plan
        where rep_id = %s and plan_date = %s and plan_status = 'scheduled'
          and start_time is not null and end_time is not null
        order by start_time
        """,
        (rep_id, target_date),
    ).fetchall()
    return [(row["start_time"], row["end_time"]) for row in rows]


def _merge_windows(windows: list[tuple[time, time]]) -> list[tuple[time, time]]:
    if not windows:
        return []
    ordered = sorted(windows)
    merged: list[tuple[time, time]] = [ordered[0]]
    for start, end in ordered[1:]:
        previous_start, previous_end = merged[-1]
        if start <= previous_end:
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged


def _target_gap_ratio(conn: Connection, *, rep_id: int, target_date: date) -> Decimal:
    row = conn.execute(
        """
        select st.target_amount,
               coalesce(sum(d.estimated_amount) filter (where drs.status_code = 'won'), 0) as won
        from sales_target st
        left join deal d on d.rep_id = st.rep_id
          and d.contract_date >= date_trunc('month', st.target_month)
          and d.contract_date < date_trunc('month', st.target_month) + interval '1 month'
        left join deal_result_status drs
          on drs.deal_result_status_id = d.deal_result_status_id
        where st.rep_id = %s
          and st.target_month = date_trunc('month', %s::date)::date
        group by st.target_amount
        """,
        (rep_id, target_date),
    ).fetchone()
    if not row or Decimal(row["target_amount"]) <= 0:
        return Decimal("0")
    target = Decimal(row["target_amount"])
    return max(Decimal("0"), (target - Decimal(row["won"])) / target)


def get_route_matrix(
    conn: Connection,
    *,
    start_location: dict[str, Any],
    end_location: dict[str, Any],
    candidates: list[VisitCandidate],
    departure_at: datetime,
    provider: MatrixProvider,
    travel_mode: str,
) -> tuple[list[list[MatrixCell]], int]:
    keys = [start_location["cache_key"]] + [
        f"customer:{candidate.customer_id}" for candidate in candidates
    ]
    points = [
        (float(start_location["latitude"]), float(start_location["longitude"]))
    ] + [(candidate.latitude, candidate.longitude) for candidate in candidates]
    if end_location["cache_key"] == start_location["cache_key"]:
        end_node_index = 0
    else:
        end_node_index = len(keys)
        keys.append(end_location["cache_key"])
        points.append(
            (float(end_location["latitude"]), float(end_location["longitude"]))
        )
    cache_mode = TRAVEL_MODE_CACHE_KEYS[travel_mode]
    bucket = departure_at.replace(minute=0, second=0, microsecond=0)
    rows = conn.execute(
        """
        select origin_key, destination_key, duration_sec, distance_m
        from route_matrix_cache
        where origin_key = any(%s)
          and destination_key = any(%s)
          and travel_mode = %s
          and departure_bucket = %s
          and expires_at > now()
        """,
        (keys, keys, cache_mode, bucket),
    ).fetchall()
    cache = {
        (row["origin_key"], row["destination_key"]): MatrixCell(
            row["duration_sec"], row["distance_m"]
        )
        for row in rows
    }
    if len(cache) == len(keys) * len(keys):
        return (
            [[cache[(origin, destination)] for destination in keys] for origin in keys],
            end_node_index,
        )

    matrix = provider.get_matrix(points, departure_at)
    if len(matrix) != len(points) or any(len(row) != len(points) for row in matrix):
        raise RoutePlanningError("routes_api_invalid", "移動行列の地点数が一致しません。")
    for origin_index, origin in enumerate(keys):
        for destination_index, destination in enumerate(keys):
            cell = matrix[origin_index][destination_index]
            conn.execute(
                """
                insert into route_matrix_cache (
                  origin_key, destination_key, travel_mode, departure_bucket,
                  duration_sec, distance_m, expires_at
                )
                values (%s, %s, %s, %s, %s, %s, %s + interval '24 hours')
                on conflict (origin_key, destination_key, travel_mode, departure_bucket)
                do update set duration_sec = excluded.duration_sec,
                              distance_m = excluded.distance_m,
                              expires_at = excluded.expires_at
                """,
                (
                    origin,
                    destination,
                    cache_mode,
                    bucket,
                    cell.duration_sec,
                    cell.distance_m,
                    bucket,
                ),
            )
    conn.commit()
    return matrix, end_node_index


def _add_realistic_travel_time(
    matrix: list[list[MatrixCell]],
    *,
    buffer_percent: int,
    access_buffer_min: int,
) -> list[list[MatrixCell]]:
    multiplier = 1 + buffer_percent / 100
    return [
        [
            cell
            if origin == destination
            else MatrixCell(
                duration_sec=math.ceil(cell.duration_sec * multiplier)
                + access_buffer_min * 60,
                distance_m=cell.distance_m,
            )
            for destination, cell in enumerate(row)
        ]
        for origin, row in enumerate(matrix)
    ]


def _time_on_date(target_date: date, value: time) -> datetime:
    return datetime.combine(target_date, value, TOKYO)


def _query_transit_around_blocked_time(
    provider: OpenTripPlannerTransitMatrixProvider,
    *,
    origin: tuple[float, float],
    destination: tuple[float, float],
    departure_at: datetime,
    target_date: date,
    blocked_windows: list[tuple[time, time]],
    travel_time_buffer_percent: int,
    access_buffer_min: int,
) -> dict:
    """Re-query after a break when the proposed journey would overlap it."""
    query_at = departure_at
    for _ in range(len(blocked_windows) + 2):
        itinerary = provider.get_itinerary(origin, destination, query_at)
        journey_start = datetime.fromisoformat(itinerary["departure_at"])
        journey_end = datetime.fromisoformat(itinerary["arrival_at"])
        contingency_sec = (
            math.ceil(itinerary["duration_sec"] * travel_time_buffer_percent / 100)
            + access_buffer_min * 60
        )
        protected_journey_end = journey_end + timedelta(seconds=contingency_sec)
        overlapping_ends = [
            _time_on_date(target_date, blocked_end)
            for blocked_start, blocked_end in blocked_windows
            if journey_start < _time_on_date(target_date, blocked_end)
            and protected_journey_end > _time_on_date(target_date, blocked_start)
        ]
        if not overlapping_ends:
            return itinerary
        query_at = max(overlapping_ends)
    raise RoutePlanningError(
        "transit_schedule_infeasible",
        "休憩・固定予定と重ならない公共交通経路がありません。",
    )


def _appointment_after_blocked_time(
    arrival_at: datetime,
    *,
    duration_min: int,
    target_date: date,
    blocked_windows: list[tuple[time, time]],
) -> datetime:
    adjusted = arrival_at
    for _ in range(len(blocked_windows) + 1):
        departure_at = adjusted + timedelta(minutes=duration_min)
        overlapping_ends = [
            _time_on_date(target_date, blocked_end)
            for blocked_start, blocked_end in blocked_windows
            if adjusted < _time_on_date(target_date, blocked_end)
            and departure_at > _time_on_date(target_date, blocked_start)
        ]
        if not overlapping_ends:
            return adjusted
        adjusted = max(overlapping_ends)
    return adjusted


def _refine_transit_option(
    option: RoutedOption,
    *,
    provider: OpenTripPlannerTransitMatrixProvider,
    candidates: list[VisitCandidate],
    start_location: dict[str, Any],
    end_location: dict[str, Any],
    target_date: date,
    work_start: time,
    work_end: time,
    blocked_windows: list[tuple[time, time]],
    turnaround_buffer_min: int,
    travel_time_buffer_percent: int,
    access_buffer_min: int,
) -> None:
    """Replace the approximate matrix schedule with chained, time-specific journeys."""
    current_location = (
        float(start_location["latitude"]),
        float(start_location["longitude"]),
    )
    current_label = str(start_location.get("label") or "出発地点")
    ready_at = _time_on_date(target_date, work_start)
    total_travel_sec = 0
    total_distance_m = 0
    total_wait_sec = 0

    for stop in option.stops:
        candidate = candidates[stop["candidate_index"]]
        itinerary = _query_transit_around_blocked_time(
            provider,
            origin=current_location,
            destination=(candidate.latitude, candidate.longitude),
            departure_at=ready_at,
            target_date=target_date,
            blocked_windows=blocked_windows,
            travel_time_buffer_percent=travel_time_buffer_percent,
            access_buffer_min=access_buffer_min,
        )
        itinerary["legs"][0]["from_name"] = current_label
        itinerary["legs"][-1]["to_name"] = candidate.customer_name
        timetable_arrival = datetime.fromisoformat(itinerary["arrival_at"])
        contingency_sec = (
            math.ceil(itinerary["duration_sec"] * travel_time_buffer_percent / 100)
            + access_buffer_min * 60
        )
        earliest_arrival = timetable_arrival + timedelta(seconds=contingency_sec)
        arrival_at = earliest_arrival
        if candidate.window_start is not None:
            arrival_at = max(arrival_at, _time_on_date(target_date, candidate.window_start))
        arrival_at = _appointment_after_blocked_time(
            arrival_at,
            duration_min=candidate.visit_duration_min,
            target_date=target_date,
            blocked_windows=blocked_windows,
        )
        departure_at = arrival_at + timedelta(minutes=candidate.visit_duration_min)
        if (
            candidate.window_end is not None
            and departure_at > _time_on_date(target_date, candidate.window_end)
        ):
            raise RoutePlanningError(
                "transit_schedule_infeasible",
                f"{candidate.customer_name}の訪問可能時間に間に合う公共交通経路がありません。",
            )

        travel_sec = max(0, int((earliest_arrival - ready_at).total_seconds()))
        wait_sec = max(0, int((arrival_at - earliest_arrival).total_seconds()))
        itinerary.update(
            requested_departure_at=ready_at.isoformat(),
            planned_arrival_at=arrival_at.isoformat(),
            contingency_buffer_min=math.ceil(contingency_sec / 60),
            appointment_wait_min=math.ceil(wait_sec / 60),
        )
        stop.update(
            arrival_at=arrival_at,
            departure_at=departure_at,
            leg_travel_min=math.ceil(travel_sec / 60),
            leg_distance_m=itinerary["distance_m"],
            leg_details=itinerary,
        )
        total_travel_sec += travel_sec
        total_distance_m += itinerary["distance_m"]
        total_wait_sec += wait_sec
        ready_at = departure_at + timedelta(minutes=turnaround_buffer_min)
        current_location = (candidate.latitude, candidate.longitude)
        current_label = candidate.customer_name

    return_itinerary = _query_transit_around_blocked_time(
        provider,
        origin=current_location,
        destination=(
            float(end_location["latitude"]),
            float(end_location["longitude"]),
        ),
        departure_at=ready_at,
        target_date=target_date,
        blocked_windows=blocked_windows,
        travel_time_buffer_percent=travel_time_buffer_percent,
        access_buffer_min=access_buffer_min,
    )
    return_itinerary["legs"][0]["from_name"] = current_label
    return_itinerary["legs"][-1]["to_name"] = str(
        end_location.get("label") or "帰着地点"
    )
    return_timetable_arrival = datetime.fromisoformat(return_itinerary["arrival_at"])
    return_contingency_sec = (
        math.ceil(return_itinerary["duration_sec"] * travel_time_buffer_percent / 100)
        + access_buffer_min * 60
    )
    route_end_at = return_timetable_arrival + timedelta(seconds=return_contingency_sec)
    if route_end_at > _time_on_date(target_date, work_end):
        raise RoutePlanningError(
            "transit_schedule_infeasible",
            "実際の公共交通時刻で再計算すると帰着可能時刻を超えます。",
        )
    return_travel_sec = max(0, int((route_end_at - ready_at).total_seconds()))
    return_itinerary.update(
        requested_departure_at=ready_at.isoformat(),
        planned_arrival_at=route_end_at.isoformat(),
        contingency_buffer_min=math.ceil(return_contingency_sec / 60),
        appointment_wait_min=0,
    )
    total_travel_sec += return_travel_sec
    total_distance_m += return_itinerary["distance_m"]
    option.return_leg = return_itinerary
    option.total_travel_min = math.ceil(total_travel_sec / 60)
    option.total_distance_m = total_distance_m
    option.total_wait_min = math.ceil(total_wait_sec / 60)
    option.totals.update(
        total_travel_min=option.total_travel_min,
        total_distance_m=total_distance_m,
        total_wait_min=option.total_wait_min,
        total_turnaround_min=turnaround_buffer_min * len(option.stops),
        visit_count=len(option.stops),
        route_end_at=route_end_at.isoformat(),
    )


def _shortfalls(
    selected: RoutedOption,
    request: RoutePlanPreviewRequest,
) -> dict[str, Decimal]:
    sales = Decimal(selected.totals["expected_sales"])
    gross = selected.totals["expected_gross_profit"]
    return {
        "expected_sales": max(
            Decimal("0"), (request.min_expected_sales or Decimal("0")) - sales
        ),
        "expected_gross_profit": max(
            Decimal("0"),
            (request.min_expected_gross_profit or Decimal("0"))
            - (Decimal(gross) if gross is not None else Decimal("0")),
        ),
    }


def _persist_preview(
    conn: Connection,
    *,
    rep_id: int,
    branch: dict,
    start_location: dict[str, Any],
    end_location: dict[str, Any],
    search_area: dict[str, Any],
    request: RoutePlanPreviewRequest,
    weights: dict[str, int],
    options: list[RoutedOption],
    selected: RoutedOption,
    warnings: list[str],
) -> tuple[int, list[dict]]:
    totals = _jsonable(selected.totals)
    plan = conn.execute(
        """
        insert into route_plan (
          rep_id, target_date, branch_id, status, policy, work_start, work_end,
          max_visits, min_expected_sales, min_expected_gross_profit,
          weights, constraints, solver_metadata, totals, selection_reason,
          warnings, qwen_model
        )
        values (%s, %s, %s, 'proposed', %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s)
        returning route_plan_id
        """,
        (
            rep_id,
            request.target_date,
            branch["branch_id"],
            request.policy,
            request.work_start,
            request.work_end,
            request.max_visits,
            request.min_expected_sales,
            request.min_expected_gross_profit,
            Jsonb(weights),
            Jsonb({
                "mandatory_constraints_satisfied": True,
                "travel_mode": request.travel_mode,
                "start_location": _jsonable(start_location),
                "end_location": _jsonable(end_location),
                "search_area": _jsonable(search_area),
                "break": (
                    {
                        "start": request.break_start.isoformat(),
                        "end": request.break_end.isoformat(),
                    }
                    if request.break_enabled
                    else None
                ),
                "turnaround_buffer_min": request.turnaround_buffer_min,
                "travel_time_buffer_percent": request.travel_time_buffer_percent,
                "access_buffer_min": request.access_buffer_min,
                "return_buffer_min": request.return_buffer_min,
                "return_leg": _jsonable(selected.return_leg),
            }),
            Jsonb({
                "cp_sat_portfolios": len(options),
                "routing_first_solution": "PARALLEL_CHEAPEST_INSERTION",
                "routing_local_search": "GUIDED_LOCAL_SEARCH",
                "time_limit_sec": settings.route_solver_time_limit_sec,
            }),
            Jsonb(totals),
            "必須条件を満たす案を、期待粗利、期待売上、移動時間の順に比較しました。",
            Jsonb(warnings),
            settings.ai_model,
        ),
    ).fetchone()
    plan_id = plan["route_plan_id"]
    response_options: list[dict] = []
    for rank, option in enumerate(options, start=1):
        is_selected = option is selected
        rejection_reason = option.rejection_reason
        if not is_selected and rejection_reason is None:
            rejection_reason = (
                "採用案と比べ、期待粗利・期待売上・移動時間の辞書式評価が下位でした。"
            )
        option_row = conn.execute(
            """
            insert into route_plan_option (
              route_plan_id, rank, selected, cp_sat_status, routing_status,
              business_value, totals, rejection_reason
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s)
            returning option_id
            """,
            (
                plan_id,
                rank,
                is_selected,
                option.portfolio.cp_sat_status,
                option.routing_status,
                option.portfolio.business_value,
                Jsonb(_jsonable(option.totals)),
                rejection_reason,
            ),
        ).fetchone()
        option_id = option_row["option_id"]
        for stop in option.stops:
            conn.execute(
                """
                insert into route_plan_stop (
                  route_plan_id, option_id, visit_order, customer_id, deal_ids,
                  arrival_at, departure_at, visit_duration_min, leg_travel_min,
                  leg_distance_m, leg_details, economics, selection_reason
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    plan_id,
                    option_id,
                    stop["visit_order"],
                    stop["customer_id"],
                    stop["deal_ids"],
                    stop["arrival_at"],
                    stop["departure_at"],
                    stop["visit_duration_min"],
                    stop["leg_travel_min"],
                    stop["leg_distance_m"],
                    Jsonb(_jsonable(stop.get("leg_details", {}))),
                    Jsonb(_jsonable(stop["economics"])),
                    stop["selection_reason"],
                ),
            )
        response_options.append(
            {
                "rank": rank,
                "selected": is_selected,
                "cp_sat_status": option.portfolio.cp_sat_status,
                "routing_status": option.routing_status,
                "business_value": option.portfolio.business_value,
                "totals": _jsonable(option.totals),
                "rejection_reason": rejection_reason,
            }
        )
    conn.commit()
    return plan_id, response_options


def create_preview(
    conn: Connection,
    *,
    rep_id: int,
    request: RoutePlanPreviewRequest,
    matrix_provider: MatrixProvider | None = None,
) -> dict:
    branch = _rep_branch(conn, rep_id)
    start_location = _resolve_endpoint(
        branch, request.start_location, label="出発地点"
    )
    end_location = _resolve_endpoint(
        branch, request.end_location, label="帰着地点"
    )
    search_area = _resolve_search_area(
        branch,
        request.search_area,
        start_location=start_location,
        conn=conn,
    )
    candidates, warnings, stats = load_candidates(
        conn,
        rep_id=rep_id,
        branch_id=branch["branch_id"],
        target_date=request.target_date,
        origin=search_area,
        fixed_radius_km=(
            request.search_area.radius_km
            if request.search_area.kind == "custom"
            else None
        ),
        include_mandatory_anchors=request.search_area.kind == "auto",
        enforce_branch_territory=request.search_area.kind == "auto",
    )
    if not candidates:
        if request.search_area.kind == "custom":
            raise RoutePlanningError(
                "no_candidates",
                f"{search_area['label']}内に、座標確定済みの進行中商談がありません。"
                "半径を広げるか、商談と顧客住所の登録状態を確認してください。",
            )
        raise RoutePlanningError(
            "no_candidates",
            "座標・担当エリア・進行中商談の条件を満たす訪問候補がありません。",
        )
    weights = policy_weights(
        request.policy,
        sales_weight_percent=request.sales_weight_percent,
        gross_profit_weight_percent=request.gross_profit_weight_percent,
    )
    score_candidates(
        candidates,
        target_date=request.target_date,
        weights=weights,
        target_gap_ratio=_target_gap_ratio(
            conn, rep_id=rep_id, target_date=request.target_date
        ),
    )
    if len(candidates) > settings.route_candidate_limit:
        area_candidate_count = len(candidates)
        candidates = _limit_scored_candidates(
            candidates,
            limit=settings.route_candidate_limit,
        )
        score_candidates(
            candidates,
            target_date=request.target_date,
            weights=weights,
            target_gap_ratio=_target_gap_ratio(
                conn, rep_id=rep_id, target_date=request.target_date
            ),
        )
        warnings.append(
            f"候補エリア内の{area_candidate_count}社から、売上・粗利・担当者適合度などの"
            f"評価上位{len(candidates)}社を経路計算対象にしました。"
        )
    if (
        request.travel_mode == "transit"
        and len(candidates) > settings.route_transit_candidate_limit
    ):
        candidates = _limit_scored_candidates(
            candidates,
            limit=settings.route_transit_candidate_limit,
        )
        score_candidates(
            candidates,
            target_date=request.target_date,
            weights=weights,
            target_gap_ratio=_target_gap_ratio(
                conn, rep_id=rep_id, target_date=request.target_date
            ),
        )
        warnings.append(
            "公共交通はAPI利用量を抑えるため、評価上位"
            f"{settings.route_transit_candidate_limit}件から計画しています。"
        )
    departure_at = datetime.combine(request.target_date, request.work_start, TOKYO)
    if matrix_provider is not None:
        provider = matrix_provider
    elif request.travel_mode == "transit":
        provider = OpenTripPlannerTransitMatrixProvider(
            api_url=settings.otp_api_url,
        )
    else:
        provider = GoogleRoutesMatrixProvider(
            api_key=settings.google_maps_api_key,
            api_url=settings.google_routes_matrix_api_url,
            travel_mode=request.travel_mode,
        )
    end_node_index = 0
    route_kind_label = (
        "公共交通経路" if request.travel_mode == "transit" else "道路経路"
    )
    while True:
        try:
            raw_matrix, end_node_index = get_route_matrix(
                conn,
                start_location=start_location,
                end_location=end_location,
                candidates=candidates,
                departure_at=departure_at,
                provider=provider,
                travel_mode=request.travel_mode,
            )
            break
        except RouteMatrixPartialError as error:
            expected_end_index = (
                0
                if end_location["cache_key"] == start_location["cache_key"]
                else len(candidates) + 1
            )
            if 0 in error.point_indexes or expected_end_index in error.point_indexes:
                raise RoutePlanningError(
                    "routes_api_unavailable",
                    f"指定した出発地点または帰着地点への{route_kind_label}を取得できませんでした。",
                ) from error
            excluded = [
                candidate
                for index, candidate in enumerate(candidates, start=1)
                if index in error.point_indexes
            ]
            if not excluded:
                raise RoutePlanningError(
                    "routes_api_unavailable",
                    f"営業所を含む{route_kind_label}を取得できませんでした。",
                ) from error
            excluded_ids = {candidate.customer_id for candidate in excluded}
            candidates = [
                candidate
                for candidate in candidates
                if candidate.customer_id not in excluded_ids
            ]
            warnings.append(
                f"{route_kind_label}を取得できない候補{len(excluded)}社を除外して再計算しました。"
            )
            if not candidates:
                message = f"すべての候補で{route_kind_label}を取得できませんでした。"
                if request.travel_mode == "transit":
                    message += (
                        "OpenTripPlannerに対象地域へ接続する鉄道・バスGTFSが"
                        "登録されているか確認してください。"
                    )
                raise RoutePlanningError(
                    "routes_api_unavailable",
                    message,
                ) from error
            score_candidates(
                candidates,
                target_date=request.target_date,
                weights=weights,
                target_gap_ratio=_target_gap_ratio(
                    conn, rep_id=rep_id, target_date=request.target_date
                ),
            )
    matrix = _add_realistic_travel_time(
        raw_matrix,
        buffer_percent=request.travel_time_buffer_percent,
        access_buffer_min=request.access_buffer_min,
    )
    effective_work_end_dt = (
        datetime.combine(request.target_date, request.work_end, TOKYO)
        - timedelta(minutes=request.return_buffer_min)
    )
    work_start_dt = datetime.combine(request.target_date, request.work_start, TOKYO)
    if effective_work_end_dt <= work_start_dt:
        raise RoutePlanningError(
            "invalid_work_window",
            "帰着後の事務処理時間を含めると訪問可能時間が残りません。",
        )
    effective_work_end = effective_work_end_dt.time()
    work_min = int(
        (effective_work_end_dt - work_start_dt).total_seconds()
        // 60
    )
    blocked = _blocked_windows(conn, rep_id=rep_id, target_date=request.target_date)
    if request.break_enabled:
        blocked.append((request.break_start, request.break_end))
    blocked = _merge_windows(blocked)
    blocked_min = sum(
        max(
            0,
            int(
                (
                    min(datetime.combine(request.target_date, end, TOKYO), effective_work_end_dt)
                    - max(datetime.combine(request.target_date, start, TOKYO), work_start_dt)
                ).total_seconds()
                // 60
            ),
        )
        for start, end in blocked
    )
    if blocked_min >= work_min:
        raise RoutePlanningError(
            "fixed_schedule_overflow",
            "固定予定だけで勤務可能時間を超えています。",
        )
    portfolios = generate_portfolios(
        candidates,
        matrix,
        max_visits=request.max_visits,
        available_min=work_min - blocked_min,
        min_expected_sales=request.min_expected_sales,
        min_expected_gross_profit=request.min_expected_gross_profit,
        limit=settings.route_portfolio_limit,
        time_limit_sec=settings.route_solver_time_limit_sec,
        travel_penalty_weight=30 if request.policy == "short_travel" else 0,
        end_node_index=end_node_index,
        turnaround_buffer_min=request.turnaround_buffer_min,
    )
    if not portfolios:
        raise RoutePlanningError(
            "target_not_reachable",
            "必須訪問・勤務時間・最大訪問数を満たす訪問先セットがありません。",
        )
    options = [
        route_portfolio(
            candidates,
            matrix,
            portfolio,
            target_date=request.target_date,
            work_start=request.work_start,
            work_end=effective_work_end,
            blocked_windows=blocked,
            time_limit_sec=settings.route_solver_time_limit_sec,
            end_node_index=end_node_index,
            turnaround_buffer_min=request.turnaround_buffer_min,
        )
        for portfolio in portfolios
    ]
    if request.travel_mode == "transit" and isinstance(
        provider, OpenTripPlannerTransitMatrixProvider
    ):
        for option in options:
            if option.routing_status != "feasible":
                continue
            try:
                _refine_transit_option(
                    option,
                    provider=provider,
                    candidates=candidates,
                    start_location=start_location,
                    end_location=end_location,
                    target_date=request.target_date,
                    work_start=request.work_start,
                    work_end=effective_work_end,
                    blocked_windows=blocked,
                    turnaround_buffer_min=request.turnaround_buffer_min,
                    travel_time_buffer_percent=request.travel_time_buffer_percent,
                    access_buffer_min=request.access_buffer_min,
                )
            except RoutePlanningError as error:
                if error.code == "otp_api_unavailable":
                    raise
                option.routing_status = "routing_infeasible"
                option.rejection_reason = str(error)
    selected = evaluate_options(options)
    shortfalls = _shortfalls(selected, request)
    if not selected.target_met:
        warnings.append(
            "最低期待売上または最低期待粗利を満たせないため、条件緩和した代替案です。"
        )
    long_legs = [
        stop for stop in selected.stops if stop["leg_travel_min"] > 60
    ]
    if long_legs:
        warnings.append(
            f"60分を超える移動が{len(long_legs)}区間あります。出発・帰着地点や候補範囲を確認してください。"
        )
    mode_label = {
        "driving": "車",
        "transit": "公共交通（徒歩＋電車・バス）",
        "walking": "徒歩",
        "cycling": "自転車",
    }[request.travel_mode]
    warnings.append(
        f"移動手段は{mode_label}です。移動時間に{request.travel_time_buffer_percent}%と"
        f"各区間{request.access_buffer_min}分の余裕を含めています。"
    )
    if request.travel_mode == "transit":
        warnings.append(
            "公共交通を含む候補の中から、待ち時間込みで最も早く到着する経路を採用します。"
            "利用可能な公共交通経路がない区間だけ徒歩経路を使用します。"
        )
    warnings.append("表示金額は予定値であり、確定した実売上・実粗利ではありません。")
    plan_id, response_options = _persist_preview(
        conn,
        rep_id=rep_id,
        branch=branch,
        start_location=start_location,
        end_location=end_location,
        search_area=search_area,
        request=request,
        weights=weights,
        options=options,
        selected=selected,
        warnings=warnings,
    )
    excluded = [
        message for message in warnings
        if "除外" in message or "評価不可" in message
    ]
    stops = [
        {
            **_jsonable(stop),
            "arrival_at": stop["arrival_at"].isoformat(),
            "departure_at": stop["departure_at"].isoformat(),
        }
        for stop in selected.stops
    ]
    return {
        "plan_id": plan_id,
        "status": "proposed",
        "rep_id": rep_id,
        "rep_name": branch["rep_name"],
        "target_date": request.target_date,
        "branch": {
            "branch_id": branch["branch_id"],
            "branch_name": branch["branch_name"],
            "location": branch["location"],
            "latitude": float(branch["latitude"]),
            "longitude": float(branch["longitude"]),
        },
        "start_location": {
            key: value for key, value in start_location.items() if key != "cache_key"
        },
        "end_location": {
            key: value for key, value in end_location.items() if key != "cache_key"
        },
        "search_area": search_area,
        "travel_mode": request.travel_mode,
        "break_time": (
            {"start": request.break_start, "end": request.break_end}
            if request.break_enabled
            else None
        ),
        "realism": {
            "turnaround_buffer_min": request.turnaround_buffer_min,
            "travel_time_buffer_percent": request.travel_time_buffer_percent,
            "access_buffer_min": request.access_buffer_min,
            "return_buffer_min": request.return_buffer_min,
        },
        "policy": request.policy,
        "weights": weights,
        "work_start": request.work_start,
        "work_end": request.work_end,
        "target_met": selected.target_met,
        "shortfalls": shortfalls,
        "totals": _jsonable(selected.totals),
        "stops": stops,
        "return_leg": _jsonable(selected.return_leg),
        "options": response_options,
        "selection_reason": (
            "勤務時間・固定予定・最低条件を先に判定し、実行可能案の中から"
            "指定した売上・粗利比率、担当者適合度、期限、商談フェーズを総合評価し、"
            "最後に移動時間も比較して選定しました。"
        ),
        "excluded_reasons": excluded,
        "warnings": warnings,
        "solver": {
            "cp_sat": selected.portfolio.cp_sat_status,
            "routing": selected.routing_status,
            "portfolio_count": len(portfolios),
            "first_solution": "PARALLEL_CHEAPEST_INSERTION",
            "local_search": "GUIDED_LOCAL_SEARCH",
        },
    }


def approve_plan(conn: Connection, *, plan_id: int, rep_id: int) -> dict:
    try:
        plan = conn.execute(
            """
            select route_plan_id, rep_id, target_date, status, constraints
            from route_plan
            where route_plan_id = %s
            for update
            """,
            (plan_id,),
        ).fetchone()
        if not plan or plan["rep_id"] != rep_id:
            raise RoutePlanningError("plan_not_found", "本人の計画案が見つかりません。")
        if plan["status"] == "approved":
            ids = conn.execute(
                """
                select activity_plan_id from route_plan_activity
                where route_plan_id = %s order by activity_plan_id
                """,
                (plan_id,),
            ).fetchall()
            conn.commit()
            return {
                "plan_id": plan_id,
                "status": "approved",
                "activity_plan_ids": [row["activity_plan_id"] for row in ids],
            }
        if plan["status"] != "proposed":
            raise RoutePlanningError("invalid_plan_status", "提案中の計画だけ承認できます。")

        turnaround_buffer_min = plan["constraints"]["turnaround_buffer_min"]

        stops = conn.execute(
            """
            select rps.stop_id, rps.customer_id, rps.deal_ids,
                   rps.arrival_at, rps.departure_at, rps.leg_travel_min, rps.economics,
                   rps.selection_reason, rps.visit_order, c.customer_name
            from route_plan_stop rps
            join route_plan_option rpo on rpo.option_id = rps.option_id
            join customer c on c.customer_id = rps.customer_id
            where rps.route_plan_id = %s and rpo.selected = true
            order by rps.visit_order
            """,
            (plan_id,),
        ).fetchall()
        activity_ids: list[int] = []
        for stop in stops:
            conflict = conn.execute(
                """
                select 1
                from activity_plan
                where rep_id = %s and plan_date = %s and plan_status = 'scheduled'
                  and start_time is not null and end_time is not null
                  and start_time::time < (%s::timestamptz at time zone 'Asia/Tokyo')::time
                  and end_time::time > (%s::timestamptz at time zone 'Asia/Tokyo')::time
                limit 1
                """,
                (
                    rep_id,
                    plan["target_date"],
                    stop["departure_at"],
                    stop["arrival_at"],
                ),
            ).fetchone()
            if conflict:
                raise RoutePlanningError(
                    "schedule_conflict",
                    "承認時に既存予定との競合が見つかりました。再計画してください。",
                )
            economics = stop["economics"]
            planned_sales = Decimal(str(economics["planned_sales"]))
            expected_sales = Decimal(str(economics["expected_sales"]))
            probability = (
                int((expected_sales / planned_sales * Decimal("100")).quantize(Decimal("1")))
                if planned_sales > 0 else 0
            )
            priority = min(stop["visit_order"], 5)
            travel_start_at = stop["arrival_at"] - timedelta(minutes=stop["leg_travel_min"])
            turnaround_end_at = stop["departure_at"] + timedelta(minutes=turnaround_buffer_min)
            travel_activity = conn.execute(
                """
                insert into activity_plan (
                  rep_id, plan_date, start_time, end_time, category, title,
                  customer_id, activity_type, priority, expected_amount,
                  expected_probability, plan_status, is_ai_generated, rationale
                )
                values (
                  %s, %s,
                  to_char(%s::timestamptz at time zone 'Asia/Tokyo', 'HH24:MI'),
                  to_char(%s::timestamptz at time zone 'Asia/Tokyo', 'HH24:MI'),
                  'task', %s, %s, '移動', %s, 0, 0, 'scheduled', true, %s
                )
                returning plan_id
                """,
                (
                    rep_id,
                    plan["target_date"],
                    travel_start_at,
                    stop["arrival_at"],
                    f"{stop['customer_name']}へ移動",
                    stop["customer_id"],
                    priority,
                    f"移動時間 {stop['leg_travel_min']}分(AI生成の営業ルートに基づく)。",
                ),
            ).fetchone()
            activity = conn.execute(
                """
                insert into activity_plan (
                  rep_id, plan_date, start_time, end_time, category, title,
                  customer_id, deal_id, activity_type, priority, expected_amount,
                  expected_probability, plan_status, is_ai_generated, rationale
                )
                values (
                  %s, %s,
                  to_char(%s::timestamptz at time zone 'Asia/Tokyo', 'HH24:MI'),
                  to_char(%s::timestamptz at time zone 'Asia/Tokyo', 'HH24:MI'),
                  'visit', %s, %s, %s, 'visit', %s, %s, %s,
                  'scheduled', true, %s
                )
                returning plan_id
                """,
                (
                    rep_id,
                    plan["target_date"],
                    stop["arrival_at"],
                    stop["departure_at"],
                    stop["customer_name"],
                    stop["customer_id"],
                    stop["deal_ids"][0] if stop["deal_ids"] else None,
                    priority,
                    planned_sales,
                    max(0, min(100, probability)),
                    stop["selection_reason"],
                ),
            ).fetchone()
            prep_activity = conn.execute(
                """
                insert into activity_plan (
                  rep_id, plan_date, start_time, end_time, category, title,
                  customer_id, activity_type, priority, expected_amount,
                  expected_probability, plan_status, is_ai_generated, rationale
                )
                values (
                  %s, %s,
                  to_char(%s::timestamptz at time zone 'Asia/Tokyo', 'HH24:MI'),
                  to_char(%s::timestamptz at time zone 'Asia/Tokyo', 'HH24:MI'),
                  'task', %s, %s, '準備・記録', %s, 0, 0, 'scheduled', true, %s
                )
                returning plan_id
                """,
                (
                    rep_id,
                    plan["target_date"],
                    stop["departure_at"],
                    turnaround_end_at,
                    f"{stop['customer_name']} 準備・記録",
                    stop["customer_id"],
                    priority,
                    f"商談後の準備・記録時間 {turnaround_buffer_min}分(AI生成の営業ルートに基づく)。",
                ),
            ).fetchone()
            activity_ids.append(travel_activity["plan_id"])
            activity_ids.append(activity["plan_id"])
            activity_ids.append(prep_activity["plan_id"])
            for related_id in (travel_activity["plan_id"], activity["plan_id"], prep_activity["plan_id"]):
                conn.execute(
                    """
                    insert into route_plan_activity(route_plan_id, stop_id, activity_plan_id)
                    values (%s, %s, %s)
                    """,
                    (plan_id, stop["stop_id"], related_id),
                )
        conn.execute(
            """
            update route_plan
            set status = 'approved', approved_at = now()
            where route_plan_id = %s
            """,
            (plan_id,),
        )
        conn.commit()
        return {
            "plan_id": plan_id,
            "status": "approved",
            "activity_plan_ids": activity_ids,
        }
    except Exception:
        conn.rollback()
        raise


def reject_plan(conn: Connection, *, plan_id: int, rep_id: int) -> dict:
    row = conn.execute(
        """
        update route_plan
        set status = 'rejected'
        where route_plan_id = %s and rep_id = %s and status = 'proposed'
        returning route_plan_id
        """,
        (plan_id, rep_id),
    ).fetchone()
    if not row:
        conn.rollback()
        raise RoutePlanningError(
            "plan_not_found", "本人の提案中の計画案が見つかりません。"
        )
    conn.commit()
    return {"plan_id": plan_id, "status": "rejected"}
