from __future__ import annotations

import calendar
import json
import math
import re
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.config import settings
from app.schemas.route_plans import (
    RouteEndpointInput,
    RoutePlanBatchPreviewRequest,
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
    candidate_economics_dict,
    evaluate_options,
    generate_portfolios,
    route_portfolio,
    score_candidates,
    selection_reason,
    sum_totals,
)
from app.services import target_simulation

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
    until_date: date | None = None,
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
               greatest(coalesce(d.expected_visit_count, 1), 1)::int
                 as required_visit_count,
               progress.completed_visit_count,
               progress.scheduled_visit_count,
               greatest(
                 greatest(coalesce(d.expected_visit_count, 1), 1)
                   - progress.completed_visit_count
                   - progress.scheduled_visit_count,
                 case when d.must_visit then 1 else 0 end
               )::int as remaining_visit_count,
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
        left join lateral (
          select
            (
              select count(*)::int
              from activity_result ar
              where ar.rep_id = %(rep_id)s
                and ar.customer_id = c.customer_id
                and ar.result_date >= d.deal_start_date
                and ar.activity_type in ('visit', '訪問', '商談')
            ) as completed_visit_count,
            (
              select count(*)::int
              from activity_plan ap
              where ap.rep_id = %(rep_id)s
                and ap.customer_id = c.customer_id
                and ap.plan_status = 'scheduled'
                and ap.plan_date >= %(target_date)s
                and ap.activity_type in ('visit', '訪問', '商談')
            ) as scheduled_visit_count
        ) progress on true
        where greatest(
          greatest(coalesce(d.expected_visit_count, 1), 1)
            - progress.completed_visit_count
            - progress.scheduled_visit_count,
          case when d.must_visit then 1 else 0 end
        ) > 0
        order by selected.any_must_visit desc, selected.area_distance_m,
                 c.customer_id, d.deal_id
        """,
        {
            "rep_id": rep_id,
            "branch_id": branch_id,
            "target_date": target_date,
            "until_date": until_date or target_date,
            "radius_m": radius_m,
            "limit": limit,
            "origin_latitude": origin_latitude,
            "origin_longitude": origin_longitude,
            "include_mandatory_anchors": include_mandatory_anchors,
            "enforce_branch_territory": enforce_branch_territory,
        },
    ).fetchall()
    return list(rows)


def _prospect_candidates(
    conn: Connection,
    *,
    rep_id: int,
    branch_id: int,
    target_date: date,
    radius_m: int,
    limit: int,
    origin_latitude: float,
    origin_longitude: float,
    enforce_branch_territory: bool = True,
) -> list[VisitCandidate]:
    """Load untouched customers and estimate their first deal from history.

    A prospect has no primary rep and no deal history with this rep.  Since it
    has no rep-owned deal yet, amount, win probability and required meetings
    are estimated from completed deals for the same industry/company size,
    falling back to industry-wide and then company-wide history.
    """
    rows = conn.execute(
        """
        with origin as (
          select st_setsrid(
            st_makepoint(%(origin_longitude)s, %(origin_latitude)s), 4326
          )::geography as geo_point
        ),
        global_history as (
          select count(*)::int as deal_count,
                 count(*) filter (where drs.status_code = 'won')::int as won_count,
                 avg(d.estimated_amount) as avg_amount,
                 avg(d.cost) as avg_cost,
                 avg(greatest(coalesce(d.expected_visit_count, 1), 1))
                   as avg_visit_count,
                 avg(greatest(coalesce(d.visit_duration_min, 60), 15))
                   as avg_visit_duration
          from deal d
          join deal_result_status drs
            on drs.deal_result_status_id = d.deal_result_status_id
           and drs.status_code in ('won', 'lost')
        ),
        eligible as (
          select c.customer_id,
                 st_distance(c.geo_point, origin.geo_point)::int
                   as branch_distance_m
          from customer c
          join sales_rep sr on sr.rep_id = %(rep_id)s
          left join prefecture_branch pb
            on c.location like pb.prefecture_name || '%%'
          cross join origin
          where sr.branch_id = %(branch_id)s
            and c.primary_rep_id is null
            and not exists (
              select 1 from deal owned
              where owned.customer_id = c.customer_id
                and owned.rep_id = %(rep_id)s
            )
            and c.geocoding_status = 'success'
            and c.geo_point is not null
            and (
              not %(enforce_branch_territory)s
              or pb.branch_id = sr.branch_id
            )
            and st_dwithin(c.geo_point, origin.geo_point, %(radius_m)s)
          order by branch_distance_m
          limit %(limit)s
        )
        select c.customer_id, c.customer_name, c.latitude, c.longitude,
               eligible.branch_distance_m,
               i.industry_name,
               coalesce(fit.category_name, '商品未定') as category_name,
               coalesce(fit.deal_count, 0)::int as affinity_deal_count,
               coalesce(fit.won_count, 0)::int as affinity_won_count,
               coalesce(fit.win_rate, 0) as affinity_win_rate,
               round(coalesce(
                 history.exact_avg_amount,
                 history.industry_avg_amount,
                 global_history.avg_amount,
                 0
               )) as estimated_amount,
               round(coalesce(
                 history.exact_avg_cost,
                 history.industry_avg_cost,
                 global_history.avg_cost
               )) as cost,
               round(100 * coalesce(
                 history.exact_won_count::numeric
                   / nullif(history.exact_count, 0),
                 history.industry_won_count::numeric
                   / nullif(history.industry_count, 0),
                 global_history.won_count::numeric
                   / nullif(global_history.deal_count, 0),
                 0
               )) as win_probability,
               greatest(1, round(coalesce(
                 history.exact_avg_visit_count,
                 history.industry_avg_visit_count,
                 global_history.avg_visit_count,
                 1
               )))::int as required_visit_count,
               greatest(15, round(coalesce(
                 history.exact_avg_visit_duration,
                 history.industry_avg_visit_duration,
                 global_history.avg_visit_duration,
                 60
               )))::int as visit_duration_min,
               case when history.exact_count > 0
                    then history.exact_count
                    else coalesce(history.industry_count, global_history.deal_count, 0)
               end::int as visit_count_history_size,
               progress.completed_visit_count,
               progress.scheduled_visit_count
        from eligible
        join customer c on c.customer_id = eligible.customer_id
        join industry i on i.industry_id = c.industry_id
        cross join global_history
        left join lateral (
          select
            count(*) filter (
              where hc.company_size_id = c.company_size_id
            )::int as exact_count,
            count(*) filter (
              where hc.company_size_id = c.company_size_id
                and hdrs.status_code = 'won'
            )::int as exact_won_count,
            avg(hd.estimated_amount) filter (
              where hc.company_size_id = c.company_size_id
            ) as exact_avg_amount,
            avg(hd.cost) filter (
              where hc.company_size_id = c.company_size_id
            ) as exact_avg_cost,
            avg(greatest(coalesce(hd.expected_visit_count, 1), 1)) filter (
              where hc.company_size_id = c.company_size_id
            ) as exact_avg_visit_count,
            avg(greatest(coalesce(hd.visit_duration_min, 60), 15)) filter (
              where hc.company_size_id = c.company_size_id
            ) as exact_avg_visit_duration,
            count(*)::int as industry_count,
            count(*) filter (where hdrs.status_code = 'won')::int
              as industry_won_count,
            avg(hd.estimated_amount) as industry_avg_amount,
            avg(hd.cost) as industry_avg_cost,
            avg(greatest(coalesce(hd.expected_visit_count, 1), 1))
              as industry_avg_visit_count,
            avg(greatest(coalesce(hd.visit_duration_min, 60), 15))
              as industry_avg_visit_duration
          from deal hd
          join customer hc on hc.customer_id = hd.customer_id
          join deal_result_status hdrs
            on hdrs.deal_result_status_id = hd.deal_result_status_id
           and hdrs.status_code in ('won', 'lost')
          where hc.industry_id = c.industry_id
            and hc.customer_id <> c.customer_id
        ) history on true
        left join lateral (
          select pc.category_name,
                 sum(ra.deal_count)::int as deal_count,
                 sum(ra.won_count)::int as won_count,
                 sum(ra.won_count)::numeric / nullif(sum(ra.deal_count), 0)
                   as win_rate
          from rep_affinity ra
          join product_category pc on pc.category_id = ra.category_id
          where ra.rep_id = %(rep_id)s
            and ra.industry_id = c.industry_id
          group by pc.category_id, pc.category_name
          order by
            (sum(ra.won_count)::numeric / nullif(sum(ra.deal_count), 0))
              * (sum(ra.deal_count)::numeric / (sum(ra.deal_count) + 3)) desc,
            sum(ra.deal_count) desc
          limit 1
        ) fit on true
        left join lateral (
          select
            (
              select count(*)::int
              from activity_result ar
              where ar.rep_id = %(rep_id)s
                and ar.customer_id = c.customer_id
                and ar.deal_id is null
                and ar.activity_type in ('visit', '訪問', '商談')
            ) as completed_visit_count,
            (
              select count(*)::int
              from activity_plan ap
              where ap.rep_id = %(rep_id)s
                and ap.customer_id = c.customer_id
                and ap.deal_id is null
                and ap.plan_status = 'scheduled'
                and ap.plan_date >= %(target_date)s
                and ap.activity_type in ('visit', '訪問', '商談')
            ) as scheduled_visit_count
        ) progress on true
        order by eligible.branch_distance_m, c.customer_id
        """,
        {
            "rep_id": rep_id,
            "branch_id": branch_id,
            "target_date": target_date,
            "radius_m": radius_m,
            "limit": limit,
            "origin_latitude": origin_latitude,
            "origin_longitude": origin_longitude,
            "enforce_branch_territory": enforce_branch_territory,
        },
    ).fetchall()

    candidates: list[VisitCandidate] = []
    for row in rows:
        required = int(row["required_visit_count"] or 1)
        completed = int(row["completed_visit_count"] or 0)
        scheduled = int(row["scheduled_visit_count"] or 0)
        remaining = max(0, required - completed - scheduled)
        if remaining <= 0:
            continue
        affinity_count = int(row["affinity_deal_count"] or 0)
        evidence: list[AffinityEvidence] = []
        if affinity_count > 0:
            win_rate = Decimal(row["affinity_win_rate"] or 0)
            reliability = Decimal(affinity_count) / Decimal(affinity_count + 3)
            evidence.append(
                AffinityEvidence(
                    industry_name=row["industry_name"],
                    category_name=row["category_name"],
                    deal_count=affinity_count,
                    won_count=int(row["affinity_won_count"] or 0),
                    win_rate=win_rate,
                    match_score=(
                        win_rate * Decimal("100") * reliability
                    ).quantize(Decimal("0.01")),
                )
            )
        candidates.append(
            VisitCandidate(
                customer_id=row["customer_id"],
                customer_name=row["customer_name"],
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                deal_ids=[],
                phase_names=["新規開拓"],
                economics=[
                    DealEconomics(
                        estimated_amount=Decimal(row["estimated_amount"] or 0),
                        cost=(Decimal(row["cost"]) if row["cost"] is not None else None),
                        win_probability=Decimal(row["win_probability"] or 0),
                    )
                ],
                visit_duration_min=int(row["visit_duration_min"] or 60),
                distance_from_branch_m=int(row["branch_distance_m"] or 0),
                affinity_evidence=evidence,
                customer_type="new",
                required_visit_count=required,
                completed_visit_count=completed,
                scheduled_visit_count=scheduled,
                remaining_visit_count=remaining,
                visit_count_source="historical_industry_company_size_average",
                visit_count_history_size=int(row["visit_count_history_size"] or 0),
            )
        )
    return candidates


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
                customer_type="ongoing",
                required_visit_count=0,
                completed_visit_count=0,
                scheduled_visit_count=0,
                remaining_visit_count=0,
                visit_count_source="deal.expected_visit_count",
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
        candidate.required_visit_count = max(
            candidate.required_visit_count, int(row["required_visit_count"] or 1)
        )
        candidate.completed_visit_count = max(
            candidate.completed_visit_count, int(row["completed_visit_count"] or 0)
        )
        candidate.scheduled_visit_count = max(
            candidate.scheduled_visit_count, int(row["scheduled_visit_count"] or 0)
        )
        candidate.remaining_visit_count = max(
            candidate.remaining_visit_count, int(row["remaining_visit_count"] or 0)
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
    until_date: date | None = None,
    limit_override: int | None = None,
    enough_threshold: int | None = None,
) -> tuple[list[VisitCandidate], list[str], dict[str, int]]:
    stats = _exclusion_stats(conn, rep_id=rep_id, branch_id=branch_id)
    radius_km = fixed_radius_km or settings.route_search_radius_km
    prefilter_limit = limit_override or min(100, max(
        settings.route_candidate_limit,
        settings.route_candidate_limit * 3,
    ))
    enough = enough_threshold or settings.route_candidate_limit
    candidates: list[VisitCandidate] = []
    while True:
        ongoing_candidates = _group_candidates(
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
                until_date=until_date,
            )
        )
        prospect_candidates = _prospect_candidates(
            conn,
            rep_id=rep_id,
            branch_id=branch_id,
            target_date=target_date,
            radius_m=radius_km * 1000,
            limit=prefilter_limit,
            origin_latitude=float(origin["latitude"]),
            origin_longitude=float(origin["longitude"]),
            enforce_branch_territory=enforce_branch_territory,
        )
        candidates = ongoing_candidates + prospect_candidates
        if (
            fixed_radius_km is not None
            or len(candidates) >= enough
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
    elif len(candidates) < enough:
        warnings.append(
            f"検索半径を最大{settings.route_max_search_radius_km}kmまで広げ、"
            f"{len(candidates)}社を候補にしました。"
        )
    ongoing_count = sum(
        candidate.customer_type == "ongoing" for candidate in candidates
    )
    prospect_count = len(candidates) - ongoing_count
    warnings.append(
        f"商談中{ongoing_count}社と新規{prospect_count}社を同じ基準で評価しました。"
        "新規の必要商談回数・金額・確度は同業・同規模の過去実績による推定です。"
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
            candidate.value_score / max(1, candidate.remaining_visit_count),
            candidate.expected_sales / max(1, candidate.remaining_visit_count),
            candidate.value_score,
            candidate.expected_gross_profit
            if candidate.expected_gross_profit is not None
            else Decimal("-Infinity"),
            candidate.expected_sales,
            -candidate.distance_from_branch_m,
        ),
        reverse=True,
    )
    optional_slots = max(0, limit - len(mandatory))
    selected_optional: list[VisitCandidate] = []
    present_types = {candidate.customer_type for candidate in mandatory}
    if optional_slots:
        available_types = {candidate.customer_type for candidate in optional}
        for customer_type in ("ongoing", "new"):
            if customer_type in present_types or customer_type not in available_types:
                continue
            candidate = next(
                item for item in optional if item.customer_type == customer_type
            )
            selected_optional.append(candidate)
            present_types.add(customer_type)
            if len(selected_optional) >= optional_slots:
                break
    selected_optional_ids = {candidate.customer_id for candidate in selected_optional}
    selected_optional.extend(
        candidate
        for candidate in optional
        if candidate.customer_id not in selected_optional_ids
    )
    selected = mandatory + selected_optional[:optional_slots]
    return sorted(
        selected,
        key=lambda candidate: (candidate.must_visit, candidate.value_score),
        reverse=True,
    )


def _blocked_windows(conn: Connection, *, rep_id: int, target_date: date) -> list[tuple[time, time]]:
    rows = conn.execute(
        """
        select start_time::time as start_time, end_time::time as end_time
        from activity_plan
        where rep_id = %s and plan_date = %s and plan_status = 'scheduled'
          and start_time is not null and end_time is not null
        order by start_time
        """,
        (rep_id, target_date),
    ).fetchall()
    return [(row["start_time"], row["end_time"]) for row in rows]


def _route_time(value: time | str) -> time:
    if isinstance(value, time):
        return value
    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise RoutePlanningError(
            "invalid_schedule_time",
            f"既存予定の時刻形式が不正です: {value}",
        ) from error


def _merge_windows(
    windows: list[tuple[time | str, time | str]],
) -> list[tuple[time, time]]:
    if not windows:
        return []
    ordered = sorted(
        (_route_time(start), _route_time(end)) for start, end in windows
    )
    merged: list[tuple[time, time]] = [ordered[0]]
    for start, end in ordered[1:]:
        previous_start, previous_end = merged[-1]
        if start <= previous_end:
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged


def _ongoing_deal_economics(conn: Connection, *, rep_id: int) -> list[dict]:
    """Minimal columns target_simulation.simulate_achievement needs -- a
    lighter, separate query from planning.py's _candidate_deals (which also
    carries ranking-only columns route_planning has no use for), to keep the
    two planning paths' DB access independent of each other."""
    return list(
        conn.execute(
            """
            select d.estimated_amount, d.profit, d.win_probability
            from ai.deal d
            where d.rep_id = %s and d.deal_result_status = 'ongoing'
            """,
            (rep_id,),
        ).fetchall()
    )


def _target_gap_ratio(conn: Connection, *, rep_id: int, target_date: date) -> Decimal:
    """How far behind this month's target(s) the rep currently is, as a
    single 0-1 scalar fed into score_candidates' target_gap component
    (route_optimization.py) -- higher means further behind/more urgent.

    Derived from target_simulation's Monte Carlo dual-target achievement
    probability (see backend/app/services/planning.py's forecast(), which
    uses the same engine) rather than a flat linear revenue ratio, so this
    route-level candidate scoring reflects the same probability-based
    urgency planning.forecast() reports -- not two different, disagreeing
    notions of "how urgent is the gap" for the same rep/month.
    """
    context = _monthly_target_context(conn, rep_id=rep_id, target_date=target_date)
    target_amount = context["target_amount"]
    if target_amount is None or target_amount <= 0:
        return Decimal("0")
    simulation = target_simulation.simulate_achievement(
        _ongoing_deal_economics(conn, rep_id=rep_id),
        already_won_amount=context["achieved_amount"],
        already_won_profit=context["achieved_gross_profit"],
        target_amount=target_amount,
        target_gross_profit=context["target_gross_profit"],
    )
    return Decimal(str(1 - simulation.joint_probability))


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
    batch_id: int | None = None,
    detail_level: str = "detailed",
) -> tuple[int, list[dict]]:
    totals = _jsonable(selected.totals)
    plan = conn.execute(
        """
        insert into route_plan (
          rep_id, target_date, branch_id, status, policy, work_start, work_end,
          max_visits, min_expected_sales, min_expected_gross_profit,
          weights, constraints, solver_metadata, totals, selection_reason,
          warnings, qwen_model, batch_id, detail_level
        )
        values (%s, %s, %s, 'proposed', %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            batch_id,
            detail_level,
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
                  leg_distance_m, leg_details, economics, selection_reason, estimated
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    stop.get("estimated", False),
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
                f"{search_area['label']}内に、座標確定済みの新規・商談中候補がありません。"
                "半径を広げるか、顧客住所の登録状態を確認してください。",
            )
        raise RoutePlanningError(
            "no_candidates",
            "座標・担当エリアの条件を満たす新規・商談中の訪問候補がありません。",
        )
    weights = policy_weights(
        request.policy,
        sales_weight_percent=request.sales_weight_percent,
        gross_profit_weight_percent=request.gross_profit_weight_percent,
    )
    return _solve_and_persist_day(
        conn,
        rep_id=rep_id,
        branch=branch,
        start_location=start_location,
        end_location=end_location,
        search_area=search_area,
        candidates=candidates,
        weights=weights,
        request=request,
        matrix_provider=matrix_provider,
        warnings=warnings,
    )


def _solve_and_persist_day(
    conn: Connection,
    *,
    rep_id: int,
    branch: dict,
    start_location: dict[str, Any],
    end_location: dict[str, Any],
    search_area: dict[str, Any],
    candidates: list[VisitCandidate],
    weights: dict[str, int],
    request: RoutePlanPreviewRequest,
    matrix_provider: MatrixProvider | None,
    warnings: list[str],
    batch_id: int | None = None,
    detail_level: str = "detailed",
) -> dict:
    """Scores an already-resolved candidate pool, fetches the travel-time
    matrix, runs CP-SAT + RoutingModel, and persists the result for one
    calendar day. Shared by the single-day preview (create_preview, one call)
    and each detailed day inside a week/month batch (create_batch_preview,
    one call per near-term day) -- the two differ only in how that day's
    candidate pool was assembled beforehand."""
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
        batch_id=batch_id,
        detail_level=detail_level,
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
        "detail_level": detail_level,
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


def _business_days(start_date: date, horizon: str) -> list[date]:
    cursor = start_date
    while cursor.weekday() >= 5:
        cursor += timedelta(days=1)
    if horizon == "week":
        days: list[date] = []
        while len(days) < 5:
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor += timedelta(days=1)
        return days
    month_end = date(
        cursor.year, cursor.month, calendar.monthrange(cursor.year, cursor.month)[1]
    )
    days = []
    while cursor <= month_end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _business_weeks(business_days: list[date]) -> list[list[date]]:
    """Split ordered business days into Monday-based calendar weeks."""
    weeks: list[list[date]] = []
    current_monday: date | None = None
    for day in business_days:
        monday = day - timedelta(days=day.weekday())
        if monday != current_monday:
            weeks.append([])
            current_monday = monday
        weeks[-1].append(day)
    return weeks


def _allocate_target_amounts(
    total: Decimal | None,
    weights: list[int],
) -> list[Decimal]:
    """Allocate an amount exactly, leaving rounding remainder in the last slot."""
    if not weights:
        return []
    if total is None or total <= 0 or sum(weights) <= 0:
        return [Decimal("0") for _ in weights]
    rounded_total = total.quantize(Decimal("1"))
    allocated: list[Decimal] = []
    running = Decimal("0")
    weight_total = Decimal(sum(weights))
    for index, weight in enumerate(weights):
        if index == len(weights) - 1:
            amount = rounded_total - running
        else:
            amount = (rounded_total * Decimal(weight) / weight_total).quantize(
                Decimal("1")
            )
            running += amount
        allocated.append(amount)
    return allocated


def _monthly_target_context(
    conn: Connection,
    *,
    rep_id: int,
    target_date: date,
) -> dict[str, Decimal | None]:
    row = conn.execute(
        """
        select st.target_amount, st.target_gross_profit,
               coalesce(sum(d.estimated_amount) filter (where drs.status_code = 'won'), 0) as achieved,
               coalesce(sum(d.profit) filter (where drs.status_code = 'won'), 0) as achieved_profit
        from sales_target st
        left join deal d on d.rep_id = st.rep_id
          and d.contract_date >= date_trunc('month', st.target_month)
          and d.contract_date < date_trunc('month', st.target_month) + interval '1 month'
        left join deal_result_status drs
          on drs.deal_result_status_id = d.deal_result_status_id
        where st.rep_id = %s
          and st.target_month = date_trunc('month', %s::date)::date
        group by st.target_amount, st.target_gross_profit
        """,
        (rep_id, target_date),
    ).fetchone()
    if not row:
        return {
            "target_amount": None,
            "achieved_amount": Decimal("0"),
            "remaining_target_amount": None,
            "target_gross_profit": None,
            "achieved_gross_profit": Decimal("0"),
            "remaining_target_gross_profit": None,
        }
    target = Decimal(row["target_amount"])
    achieved = Decimal(row["achieved"])
    target_gross_profit = (
        Decimal(row["target_gross_profit"]) if row["target_gross_profit"] is not None else None
    )
    achieved_profit = Decimal(row["achieved_profit"])
    return {
        "target_amount": target,
        "achieved_amount": achieved,
        "remaining_target_amount": max(Decimal("0"), target - achieved),
        "target_gross_profit": target_gross_profit,
        "achieved_gross_profit": achieved_profit,
        "remaining_target_gross_profit": (
            None if target_gross_profit is None
            else max(Decimal("0"), target_gross_profit - achieved_profit)
        ),
    }


def _horizon_target_amount(
    remaining: Decimal | None,
    *,
    business_days: list[date],
    horizon: str,
) -> Decimal | None:
    """Prorate a month's remaining target (revenue or gross profit -- caller
    picks which) down to the requested horizon. Takes the raw remaining
    amount rather than the whole _monthly_target_context dict so the same
    proration logic can be reused for both dimensions."""
    if remaining is None or horizon == "month":
        return remaining
    # Pre-existing bug fixed in passing: this must count *all* business days
    # in business_days[0]'s month, not "from business_days[0] to month end"
    # (which _business_days(business_days[0], "month") actually computes --
    # correct for the top-level month-horizon case, wrong here). Anchoring to
    # business_days[0] alone made a week horizon starting near month-end
    # (e.g. the last business day of August) prorate against a 1-day "month"
    # and inflate the result by up to ~5x -- caught while adding the parallel
    # gross-profit target, which made an already-wrong ratio visibly wrong.
    month_days = _business_days(business_days[0].replace(day=1), "month")
    if not month_days:
        return remaining
    return (
        remaining * Decimal(len(business_days)) / Decimal(len(month_days))
    ).quantize(Decimal("1"))


def _select_target_customers(
    candidates: list[VisitCandidate],
    *,
    planning_target: Decimal | None,
    capacity: int,
    max_visits_per_customer: int | None = None,
) -> list[VisitCandidate]:
    """Build the month-level customer portfolio before assigning dates.

    Capacity is measured in meetings, not companies.  A selected customer
    consumes the deal's remaining required meetings (or the historical
    estimate for a new prospect), so a high-value opportunity that needs five
    more conversations is not treated as a one-visit shortcut to the target.
    """
    mandatory = sorted(
        (candidate for candidate in candidates if candidate.must_visit),
        key=lambda candidate: (candidate.visit_deadline or date.max, -candidate.value_score),
    )
    optional = sorted(
        (candidate for candidate in candidates if not candidate.must_visit),
        key=lambda candidate: (
            candidate.value_score / max(1, candidate.remaining_visit_count),
            candidate.expected_sales / max(1, candidate.remaining_visit_count),
            candidate.value_score,
            candidate.salesperson_fit_score,
            -candidate.distance_from_branch_m,
        ),
        reverse=True,
    )
    selected: list[VisitCandidate] = []
    used_capacity = 0

    def demand(candidate: VisitCandidate) -> int:
        visits = max(1, candidate.remaining_visit_count)
        if max_visits_per_customer is not None:
            visits = min(visits, max_visits_per_customer)
        return visits

    for candidate in mandatory:
        available = max(0, capacity - used_capacity)
        if available <= 0:
            break
        candidate.planned_visit_count = min(demand(candidate), available)
        selected.append(candidate)
        used_capacity += candidate.planned_visit_count

    expected = sum((candidate.expected_sales for candidate in selected), Decimal("0"))
    if planning_target is not None and planning_target <= 0:
        return selected

    # When both pools exist, reserve room for at least one of each.  This keeps
    # a target-driven plan from collapsing into only mature deals or only cheap
    # prospecting visits merely because one group wins a close score tie.
    seeded_ids = {candidate.customer_id for candidate in selected}
    for customer_type in ("ongoing", "new"):
        if any(candidate.customer_type == customer_type for candidate in selected):
            continue
        candidate = next(
            (
                item
                for item in optional
                if item.customer_type == customer_type
                and item.customer_id not in seeded_ids
                and used_capacity + demand(item) <= capacity
            ),
            None,
        )
        if candidate is None:
            continue
        candidate.planned_visit_count = demand(candidate)
        selected.append(candidate)
        seeded_ids.add(candidate.customer_id)
        used_capacity += candidate.planned_visit_count
        expected += candidate.expected_sales

    buffered_target = (
        Decimal("Infinity")
        if planning_target is None
        else planning_target * Decimal("1.10")
    )
    for candidate in optional:
        if candidate.customer_id in seeded_ids:
            continue
        if used_capacity >= capacity or (selected and expected >= buffered_target):
            break
        required_capacity = demand(candidate)
        if used_capacity + required_capacity > capacity:
            continue
        candidate.planned_visit_count = required_capacity
        selected.append(candidate)
        seeded_ids.add(candidate.customer_id)
        used_capacity += required_capacity
        expected += candidate.expected_sales
    return selected


def _expand_visit_occurrences(
    candidates: list[VisitCandidate],
) -> list[VisitCandidate]:
    """Expand each selected customer into the meetings needed this horizon.

    Opportunity value remains available to the visit scorer on every meeting,
    while revenue/expected revenue is recognized only on the final planned
    meeting. This prevents intermediate negotiations from being ignored as
    zero-value visits without counting one deal's revenue multiple times.
    """
    occurrences: list[VisitCandidate] = []
    for candidate in candidates:
        planned = max(1, candidate.planned_visit_count)
        credit = Decimal("1") / Decimal(planned)
        for sequence in range(1, planned + 1):
            occurrences.append(
                replace(
                    candidate,
                    score_components=dict(candidate.score_components),
                    planned_visit_count=planned,
                    visit_sequence=sequence,
                    sales_credit_fraction=credit,
                )
            )
    return occurrences


def _assign_target_customers_to_days(
    candidates: list[VisitCandidate],
    *,
    business_days: list[date],
    day_targets: dict[date, Decimal],
    max_visits: int,
) -> dict[date, list[VisitCandidate]]:
    """Distribute the month portfolio according to each day's target.

    A customer can appear on multiple dates when more meetings are required,
    but never twice on the same date.  The least-covered eligible day is
    filled first while preserving meeting order.
    """
    assigned: dict[date, list[VisitCandidate]] = {day: [] for day in business_days}
    assigned_sales = {day: Decimal("0") for day in business_days}
    grouped: dict[int, list[VisitCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.customer_id, []).append(candidate)
    customer_order = sorted(
        grouped,
        key=lambda customer_id: (
            not grouped[customer_id][0].must_visit,
            grouped[customer_id][0].visit_deadline or date.max,
            -grouped[customer_id][0].value_score,
            -grouped[customer_id][0].expected_sales,
        ),
    )
    ordered = [
        occurrence
        for customer_id in customer_order
        for occurrence in sorted(
            grouped[customer_id], key=lambda candidate: candidate.visit_sequence
        )
    ]
    day_index = {day: index for index, day in enumerate(business_days)}
    last_assigned: dict[int, date] = {}
    for candidate in ordered:
        remaining_after = candidate.planned_visit_count - candidate.visit_sequence
        eligible = [
            day
            for day in business_days
            if len(assigned[day]) < max_visits
            and day > last_assigned.get(candidate.customer_id, date.min)
            and all(
                existing.customer_id != candidate.customer_id
                for existing in assigned[day]
            )
            and (candidate.visit_deadline is None or day <= candidate.visit_deadline)
            and day_index[day] <= len(business_days) - remaining_after - 1
        ]
        if not eligible:
            eligible = [
                day
                for day in business_days
                if len(assigned[day]) < max_visits
                and day > last_assigned.get(candidate.customer_id, date.min)
                and all(
                    existing.customer_id != candidate.customer_id
                    for existing in assigned[day]
                )
            ]
        if not eligible:
            continue

        def coverage(day: date) -> tuple[Decimal, int, date]:
            target = day_targets.get(day, Decimal("0"))
            ratio = (
                assigned_sales[day] / target
                if target > 0
                else Decimal(len(assigned[day]))
            )
            return ratio, len(assigned[day]), day

        chosen_day = min(eligible, key=coverage)
        assigned[chosen_day].append(candidate)
        assigned_sales[chosen_day] += candidate.expected_sales
        last_assigned[candidate.customer_id] = chosen_day
    return assigned


def _day_pool_capacity(max_visits: int) -> int:
    return max(max_visits * settings.route_batch_pool_multiplier, max_visits + 2)


def _assign_must_visit_days(
    candidates: list[VisitCandidate],
    business_days: list[date],
) -> dict[date, list[VisitCandidate]]:
    assigned: dict[date, list[VisitCandidate]] = {day: [] for day in business_days}
    for candidate in candidates:
        deadline = candidate.visit_deadline
        target_day = next(
            (day for day in business_days if deadline is None or day <= deadline),
            business_days[-1],
        )
        assigned[target_day].append(candidate)
    return assigned


def _cluster_optional_candidates_by_day(
    conn: Connection,
    *,
    candidates: list[VisitCandidate],
    business_days: list[date],
) -> dict[date, list[VisitCandidate]]:
    """Groups non-fixed candidates into geographically compact pools, one per
    business day, using PostGIS k-means so each day's later CP-SAT/RoutingModel
    step only has to consider a nearby subset instead of the whole territory.
    Clusters that carry an earlier deadline are handed to the earliest days,
    so the soft urgency scoring inside score_candidates still has calendar
    room to prioritize them."""
    assigned: dict[date, list[VisitCandidate]] = {day: [] for day in business_days}
    by_customer = {candidate.customer_id: candidate for candidate in candidates}
    if not by_customer:
        return assigned
    k = min(len(business_days), len(by_customer))
    rows = conn.execute(
        """
        select customer_id,
               ST_ClusterKMeans(geo_point::geometry, %(k)s) over () as cluster_id
        from customer
        where customer_id = any(%(customer_ids)s)
        """,
        {"k": k, "customer_ids": list(by_customer.keys())},
    ).fetchall()
    clusters: dict[int, list[VisitCandidate]] = {}
    for row in rows:
        clusters.setdefault(row["cluster_id"], []).append(by_customer[row["customer_id"]])

    def earliest_deadline(members: list[VisitCandidate]) -> date:
        deadlines = [member.visit_deadline for member in members if member.visit_deadline is not None]
        return min(deadlines) if deadlines else date.max

    for day, members in zip(business_days, sorted(clusters.values(), key=earliest_deadline)):
        assigned[day] = members
    return assigned


def _assign_candidates_to_days(
    conn: Connection,
    *,
    candidates: list[VisitCandidate],
    business_days: list[date],
    max_visits: int,
) -> dict[date, list[VisitCandidate]]:
    """Distributes an already-scored horizon-wide candidate pool across the
    batch's business days: fixed appointments go to the earliest day on or
    before their deadline (_assign_must_visit_days), the rest are clustered
    geographically (_cluster_optional_candidates_by_day). Each day's pool is
    then capped to a multiple of max_visits, keeping the highest value_score
    candidates, so the per-day CP-SAT/RoutingModel step still has room to
    choose the best combination instead of being handed everyone."""
    must_visit = [candidate for candidate in candidates if candidate.must_visit]
    optional = [candidate for candidate in candidates if not candidate.must_visit]
    day_pools = _assign_must_visit_days(must_visit, business_days)
    for day, members in _cluster_optional_candidates_by_day(
        conn, candidates=optional, business_days=business_days
    ).items():
        day_pools[day].extend(members)

    capacity = _day_pool_capacity(max_visits)
    for day, members in day_pools.items():
        mandatory = [candidate for candidate in members if candidate.must_visit]
        rest = sorted(
            (candidate for candidate in members if not candidate.must_visit),
            key=lambda candidate: candidate.value_score,
            reverse=True,
        )
        day_pools[day] = mandatory + rest[: max(0, capacity - len(mandatory))]
    return day_pools


def _round_trip_matrix(
    candidates: list[VisitCandidate], *, speed_kmh: int
) -> list[list[MatrixCell]]:
    """A branch-hub distance estimate used only to keep generate_portfolios'
    time-budget constraint meaningful for a batch's coarse (far-future) days,
    without an external Routes API call. Never used for RoutingModel
    sequencing -- coarse days skip that step -- so inter-candidate cells are
    rough placeholders, not real routes."""
    speed_m_per_sec = speed_kmh * 1000 / 3600
    branch_distances = [0] + [candidate.distance_from_branch_m for candidate in candidates]
    size = len(branch_distances)

    def cell(i: int, j: int) -> MatrixCell:
        if i == j:
            return MatrixCell(0, 0)
        distance = (
            branch_distances[i] + branch_distances[j]
            if i and j
            else max(branch_distances[i], branch_distances[j])
        )
        return MatrixCell(max(60, round(distance / speed_m_per_sec)), distance)

    return [[cell(i, j) for j in range(size)] for i in range(size)]


def _solve_coarse_day(
    *,
    candidates: list[VisitCandidate],
    target_date: date,
    weights: dict[str, int],
    target_gap_ratio: Decimal,
    max_visits: int,
    work_start: time,
    work_end: time,
    turnaround_buffer_min: int,
    break_enabled: bool,
    break_start: time,
    break_end: time,
    min_expected_sales: Decimal | None = None,
    min_expected_gross_profit: Decimal | None = None,
) -> RoutedOption | None:
    """A far-future day inside a batch: CP-SAT still picks a time-budget-
    respecting candidate set, but against the cheap branch-hub matrix instead
    of a real Routes API call, and skips RoutingModel sequencing entirely --
    stops are just packed back-to-back in nearest-branch order. Meant to be
    superseded by a detailed day (_solve_and_persist_day) once this date is
    close enough to be worth the external API cost."""
    if not candidates:
        return None
    score_candidates(
        candidates, target_date=target_date, weights=weights,
        target_gap_ratio=target_gap_ratio,
    )
    matrix = _round_trip_matrix(candidates, speed_kmh=settings.route_batch_assumed_speed_kmh)
    work_min = (
        work_end.hour * 60 + work_end.minute
        - work_start.hour * 60 - work_start.minute
    )
    portfolios = generate_portfolios(
        candidates, matrix, max_visits=max_visits, available_min=work_min,
        min_expected_sales=min_expected_sales,
        min_expected_gross_profit=min_expected_gross_profit,
        limit=1,
        time_limit_sec=2, travel_penalty_weight=0, end_node_index=0,
        turnaround_buffer_min=turnaround_buffer_min,
    )
    if not portfolios:
        return None
    portfolio = portfolios[0]
    chosen = sorted(
        (candidates[index] for index in portfolio.candidate_indexes),
        key=lambda candidate: candidate.distance_from_branch_m,
    )
    speed_m_per_min = settings.route_batch_assumed_speed_kmh * 1000 / 60
    break_start_dt = datetime.combine(target_date, break_start, TOKYO)
    break_end_dt = datetime.combine(target_date, break_end, TOKYO)
    cursor = datetime.combine(target_date, work_start, TOKYO)
    stops: list[dict] = []
    total_distance_m = 0
    total_travel_min = 0
    for order, candidate in enumerate(chosen, start=1):
        if break_enabled and break_start_dt <= cursor < break_end_dt:
            cursor = break_end_dt
        leg_distance_m = candidate.distance_from_branch_m
        leg_travel_min = max(1, round(leg_distance_m / speed_m_per_min))
        arrival_at = cursor
        departure_at = arrival_at + timedelta(minutes=candidate.visit_duration_min)
        stops.append(
            {
                "visit_order": order,
                "customer_id": candidate.customer_id,
                "customer_name": candidate.customer_name,
                "deal_ids": candidate.deal_ids,
                "phase_names": candidate.phase_names,
                "arrival_at": arrival_at,
                "departure_at": departure_at,
                "visit_duration_min": candidate.visit_duration_min,
                "turnaround_buffer_min": turnaround_buffer_min,
                "leg_travel_min": leg_travel_min,
                "leg_distance_m": leg_distance_m,
                "economics": candidate_economics_dict(candidate),
                "selection_reason": (
                    selection_reason(candidate) + " ※概算プランのため訪問順・時刻は未確定です。"
                ),
                "latitude": candidate.latitude,
                "longitude": candidate.longitude,
                "estimated": True,
            }
        )
        total_distance_m += 2 * leg_distance_m
        total_travel_min += leg_travel_min
        cursor = departure_at + timedelta(minutes=turnaround_buffer_min)
    totals = sum_totals(candidates, portfolio.candidate_indexes)
    totals.update(
        total_travel_min=total_travel_min,
        total_distance_m=total_distance_m,
        total_wait_min=0,
        total_turnaround_min=turnaround_buffer_min * len(stops),
        visit_count=len(stops),
        route_end_at=cursor.isoformat(),
    )
    return RoutedOption(
        portfolio=portfolio,
        routing_status="not_routed",
        stops=stops,
        total_travel_min=total_travel_min,
        total_distance_m=total_distance_m,
        total_wait_min=0,
        target_met=True,
        totals=totals,
    )


def _empty_day_result(
    target_date: date, detail_level: str, *, error: RoutePlanningError | None = None
) -> dict:
    return {
        "plan_id": None,
        "target_date": target_date,
        "detail_level": detail_level,
        "status": "failed" if error else "proposed",
        "totals": {
            "planned_sales": 0, "planned_gross_profit": 0,
            "expected_sales": 0, "expected_gross_profit": 0,
            "total_travel_min": 0, "total_distance_m": 0, "visit_count": 0,
        },
        "stops": [],
        "warnings": [f"{error.code}: {error}"] if error else ["この日の訪問候補がありません。"],
        "solver": {},
    }


def _accumulate_totals(batch_totals: dict[str, Any], day_totals: dict[str, Any]) -> None:
    for key in ("total_travel_min", "total_distance_m", "visit_count"):
        batch_totals[key] += int(day_totals.get(key) or 0)
    for key in ("planned_sales", "expected_sales"):
        batch_totals[key] += Decimal(str(day_totals.get(key) or 0))
    for key in ("planned_gross_profit", "expected_gross_profit"):
        if batch_totals[key] is None:
            continue
        value = day_totals.get(key)
        batch_totals[key] = None if value is None else batch_totals[key] + Decimal(str(value))


def _persist_coarse_day(
    conn: Connection,
    *,
    rep_id: int,
    branch: dict,
    start_location: dict[str, Any],
    end_location: dict[str, Any],
    search_area: dict[str, Any],
    candidates: list[VisitCandidate],
    weights: dict[str, int],
    request: RoutePlanPreviewRequest,
    target_gap_ratio: Decimal,
    batch_id: int,
) -> dict:
    option = _solve_coarse_day(
        candidates=candidates,
        target_date=request.target_date,
        weights=weights,
        target_gap_ratio=target_gap_ratio,
        max_visits=request.max_visits,
        work_start=request.work_start,
        work_end=request.work_end,
        turnaround_buffer_min=request.turnaround_buffer_min,
        break_enabled=request.break_enabled,
        break_start=request.break_start,
        break_end=request.break_end,
        min_expected_sales=request.min_expected_sales,
        min_expected_gross_profit=request.min_expected_gross_profit,
    )
    if option is None:
        return _empty_day_result(request.target_date, "coarse")
    note = "概算プランです。移動時間を最適化した詳細ルートは、実行日が近づいたら計画を作り直して確定してください。"
    plan_id, _ = _persist_preview(
        conn,
        rep_id=rep_id,
        branch=branch,
        start_location=start_location,
        end_location=end_location,
        search_area=search_area,
        request=request,
        weights=weights,
        options=[option],
        selected=option,
        warnings=[note],
        batch_id=batch_id,
        detail_level="coarse",
    )
    return {
        "plan_id": plan_id,
        "target_date": request.target_date,
        "detail_level": "coarse",
        "status": "proposed",
        "totals": _jsonable(option.totals),
        "stops": [
            {
                **_jsonable(stop),
                "arrival_at": stop["arrival_at"].isoformat(),
                "departure_at": stop["departure_at"].isoformat(),
            }
            for stop in option.stops
        ],
        "warnings": [note],
        "solver": {"cp_sat": option.portfolio.cp_sat_status, "routing": "not_routed"},
    }


def create_batch_preview(
    conn: Connection,
    *,
    rep_id: int,
    request: RoutePlanBatchPreviewRequest,
    matrix_provider: MatrixProvider | None = None,
) -> dict:
    """Create one target-driven month -> week -> day sales schedule.

    The remaining monthly goal first limits the customer portfolio. That
    amount is then allocated exactly across calendar weeks and business days,
    and each detailed day reuses the same CP-SAT + RoutingModel path as the
    existing single-day route preview. Plans remain previews until their day
    is approved, preserving the current activity_plan workflow.
    """
    branch = _rep_branch(conn, rep_id)
    start_location = _resolve_endpoint(branch, request.start_location, label="出発地点")
    end_location = _resolve_endpoint(branch, request.end_location, label="帰着地点")
    search_area = _resolve_search_area(
        branch, request.search_area, start_location=start_location, conn=conn,
    )

    business_days = _business_days(request.start_date, request.horizon)
    if not business_days:
        raise RoutePlanningError("invalid_horizon", "対象期間内に営業日がありません。")
    target_context = _monthly_target_context(
        conn, rep_id=rep_id, target_date=business_days[0]
    )
    planning_target = _horizon_target_amount(
        target_context["remaining_target_amount"],
        business_days=business_days,
        horizon=request.horizon,
    )
    # Gross-profit target is optional (sales_target.target_gross_profit may be
    # unset) -- cascades through the exact same allocate/proration helpers as
    # revenue, staying None end-to-end when no profit target exists rather
    # than being coerced to 0 (see _monthly_target_context's own comment).
    planning_target_gross_profit = _horizon_target_amount(
        target_context["remaining_target_gross_profit"],
        business_days=business_days,
        horizon=request.horizon,
    )
    business_weeks = _business_weeks(business_days)
    week_target_values = _allocate_target_amounts(
        planning_target, [len(week) for week in business_weeks]
    )
    week_targets = {
        week[0] - timedelta(days=week[0].weekday()): target
        for week, target in zip(business_weeks, week_target_values)
    }
    day_targets: dict[date, Decimal] = {}
    for week, week_target in zip(business_weeks, week_target_values):
        allocations = _allocate_target_amounts(week_target, [1] * len(week))
        day_targets.update(zip(week, allocations))

    week_gross_profit_targets: dict[date, Decimal] = {}
    day_gross_profit_targets: dict[date, Decimal] = {}
    if planning_target_gross_profit is not None:
        week_gross_profit_values = _allocate_target_amounts(
            planning_target_gross_profit, [len(week) for week in business_weeks]
        )
        week_gross_profit_targets = {
            week[0] - timedelta(days=week[0].weekday()): target
            for week, target in zip(business_weeks, week_gross_profit_values)
        }
        for week, week_gross_profit_target in zip(business_weeks, week_gross_profit_values):
            allocations = _allocate_target_amounts(week_gross_profit_target, [1] * len(week))
            day_gross_profit_targets.update(zip(week, allocations))
    detailed_days = min(
        request.detailed_days or settings.route_batch_detailed_days,
        len(business_days),
    )
    day_pool_capacity = _day_pool_capacity(request.max_visits)

    candidates, warnings, _stats = load_candidates(
        conn,
        rep_id=rep_id,
        branch_id=branch["branch_id"],
        target_date=business_days[0],
        origin=search_area,
        fixed_radius_km=(
            request.search_area.radius_km if request.search_area.kind == "custom" else None
        ),
        include_mandatory_anchors=request.search_area.kind == "auto",
        enforce_branch_territory=request.search_area.kind == "auto",
        until_date=business_days[-1],
        limit_override=settings.route_batch_candidate_limit,
        enough_threshold=min(
            settings.route_batch_candidate_limit,
            day_pool_capacity * len(business_days),
        ),
    )
    if not candidates:
        raise RoutePlanningError(
            "no_candidates",
            "対象期間内に、座標確定済みで担当エリア内の新規・商談中候補がありません。",
        )

    weights = policy_weights(
        request.policy,
        sales_weight_percent=request.sales_weight_percent,
        gross_profit_weight_percent=request.gross_profit_weight_percent,
    )
    target_gap_ratio = _target_gap_ratio(conn, rep_id=rep_id, target_date=business_days[0])
    score_candidates(
        candidates, target_date=business_days[0], weights=weights,
        target_gap_ratio=target_gap_ratio,
    )
    selected_candidates = _select_target_customers(
        candidates,
        planning_target=planning_target,
        capacity=request.max_visits * len(business_days),
        max_visits_per_customer=len(business_days),
    )
    visit_occurrences = _expand_visit_occurrences(selected_candidates)
    day_pools = _assign_target_customers_to_days(
        visit_occurrences,
        business_days=business_days,
        day_targets=day_targets,
        max_visits=request.max_visits,
    )

    batch_row = conn.execute(
        """
        insert into route_plan_batch (
          rep_id, branch_id, horizon, start_date, end_date, detailed_days,
          policy, weights, totals, warnings
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning batch_id
        """,
        (
            rep_id, branch["branch_id"], request.horizon, business_days[0],
            business_days[-1], detailed_days, request.policy, Jsonb(weights),
            Jsonb({}), Jsonb(warnings),
        ),
    ).fetchone()
    batch_id = batch_row["batch_id"]

    shared_fields = request.model_dump(
        exclude={"start_date", "horizon", "detailed_days", "min_expected_sales"}
    )
    days_out: list[dict] = []
    batch_totals: dict[str, Any] = {
        "planned_sales": Decimal("0"), "planned_gross_profit": Decimal("0"),
        "expected_sales": Decimal("0"), "expected_gross_profit": Decimal("0"),
        "total_travel_min": 0, "total_distance_m": 0, "visit_count": 0,
    }

    for index, day in enumerate(business_days):
        day_candidates = day_pools.get(day, [])
        is_detailed = index < detailed_days
        derived_day_target = day_targets.get(day, Decimal("0"))
        # The daily amount is a reporting allocation, not a hard routing
        # constraint. Intermediate meetings legitimately recognize zero
        # revenue, so forcing every day to hit this amount would systematically
        # drop the pipeline-building meetings needed to close later in the
        # month. Only an explicitly requested API minimum remains hard.
        requested_day_target = request.min_expected_sales or Decimal("0")
        day_minimum = requested_day_target
        day_request = RoutePlanPreviewRequest(
            target_date=day,
            min_expected_sales=day_minimum if day_minimum > 0 else None,
            **shared_fields,
        )
        try:
            if not day_candidates:
                day_result = _empty_day_result(day, "detailed" if is_detailed else "coarse")
            elif is_detailed:
                day_result = _solve_and_persist_day(
                    conn,
                    rep_id=rep_id,
                    branch=branch,
                    start_location=start_location,
                    end_location=end_location,
                    search_area=search_area,
                    candidates=day_candidates,
                    weights=weights,
                    request=day_request,
                    matrix_provider=matrix_provider,
                    warnings=[],
                    batch_id=batch_id,
                    detail_level="detailed",
                )
            else:
                day_result = _persist_coarse_day(
                    conn,
                    rep_id=rep_id,
                    branch=branch,
                    start_location=start_location,
                    end_location=end_location,
                    search_area=search_area,
                    candidates=day_candidates,
                    weights=weights,
                    request=day_request,
                    target_gap_ratio=target_gap_ratio,
                    batch_id=batch_id,
                )
        except RoutePlanningError as error:
            day_result = _empty_day_result(
                day, "detailed" if is_detailed else "coarse", error=error,
            )
        expected_sales = Decimal(
            str((day_result.get("totals") or {}).get("expected_sales") or 0)
        )
        day_result["target_amount"] = derived_day_target
        day_result["shortfall_amount"] = max(
            Decimal("0"), derived_day_target - expected_sales
        )
        day_result["attainment_rate"] = (
            float(expected_sales / derived_day_target)
            if derived_day_target > 0
            else 0
        )
        day_result["target_gross_profit"] = day_gross_profit_targets.get(day, Decimal("0"))
        days_out.append(day_result)
        _accumulate_totals(batch_totals, day_result.get("totals") or {})

    assigned_dates_by_customer: dict[int, list[date]] = {}
    for day, day_candidates in day_pools.items():
        for candidate in day_candidates:
            assigned_dates_by_customer.setdefault(candidate.customer_id, []).append(day)
    for assigned_dates in assigned_dates_by_customer.values():
        assigned_dates.sort()
    selected_customers_out = [
        {
            "customer_id": candidate.customer_id,
            "customer_name": candidate.customer_name,
            "customer_type": candidate.customer_type,
            "planned_sales": candidate.planned_sales,
            "expected_sales": candidate.expected_sales,
            "expected_gross_profit": candidate.expected_gross_profit,
            "salesperson_fit_score": candidate.salesperson_fit_score,
            "required_visit_count": candidate.required_visit_count,
            "completed_visit_count": candidate.completed_visit_count,
            "scheduled_visit_count": candidate.scheduled_visit_count,
            "remaining_visit_count": candidate.remaining_visit_count,
            "planned_visit_count": len(
                assigned_dates_by_customer.get(candidate.customer_id, [])
            ),
            "visit_count_source": candidate.visit_count_source,
            "assigned_date": assigned_dates_by_customer[candidate.customer_id][0],
            "assigned_dates": assigned_dates_by_customer[candidate.customer_id],
            "selection_reason": selection_reason(candidate),
        }
        for candidate in selected_candidates
        if assigned_dates_by_customer.get(candidate.customer_id)
    ]
    day_result_by_date = {day_result["target_date"]: day_result for day_result in days_out}
    weeks_out: list[dict[str, Any]] = []
    for week_number, week_days in enumerate(business_weeks, start=1):
        monday = week_days[0] - timedelta(days=week_days[0].weekday())
        week_target = week_targets[monday]
        week_gross_profit_target = week_gross_profit_targets.get(monday, Decimal("0"))
        week_day_results = [day_result_by_date[day] for day in week_days]
        week_expected = sum(
            (
                Decimal(str(day_result["totals"].get("expected_sales") or 0))
                for day_result in week_day_results
            ),
            Decimal("0"),
        )
        week_expected_gross_profit = sum(
            (
                Decimal(str(day_result["totals"].get("expected_gross_profit") or 0))
                for day_result in week_day_results
            ),
            Decimal("0"),
        )
        week_candidates = [
            candidate for day in week_days for candidate in day_pools.get(day, [])
        ]
        focus_names = list(dict.fromkeys(
            candidate.customer_name
            for candidate in sorted(
                week_candidates,
                key=lambda candidate: candidate.expected_sales,
                reverse=True,
            )
        ))[:3]
        if focus_names:
            focus = (
                f"{', '.join(focus_names)}を中心に、日別目標へ合わせて訪問順を最適化します。"
            )
        else:
            focus = "この週に割り当てられる営業先候補がないため、候補追加または目標配分の見直しが必要です。"
        weeks_out.append(
            {
                "week_number": week_number,
                "start_date": week_days[0],
                "end_date": week_days[-1],
                "target_amount": week_target,
                "expected_sales": week_expected,
                "shortfall_amount": max(Decimal("0"), week_target - week_expected),
                "attainment_rate": (
                    float(week_expected / week_target) if week_target > 0 else 0
                ),
                "target_gross_profit": week_gross_profit_target,
                "expected_gross_profit": week_expected_gross_profit,
                "visit_count": sum(
                    int(day_result["totals"].get("visit_count") or 0)
                    for day_result in week_day_results
                ),
                "customer_names": list(dict.fromkeys(
                    candidate.customer_name for candidate in week_candidates
                )),
                "focus": focus,
                "days": week_day_results,
            }
        )

    portfolio_expected_sales = sum(
        (candidate.expected_sales for candidate in selected_candidates), Decimal("0")
    )
    conn.execute(
        "update route_plan_batch set totals = %s where batch_id = %s",
        (Jsonb(_jsonable(batch_totals)), batch_id),
    )
    conn.commit()

    remaining = len(business_days) - detailed_days
    coverage_note = (
        f"それ以降の{remaining}営業日は候補選定のみの概算プランです。"
        if remaining > 0 else "対象期間はすべて詳細プランです。"
    )
    target_warnings: list[str] = []
    selected_new_count = sum(
        candidate.customer_type == "new" for candidate in selected_candidates
    )
    selected_ongoing_count = len(selected_candidates) - selected_new_count
    selected_visit_count = sum(
        candidate.planned_visit_count for candidate in selected_candidates
    )
    target_warnings.append(
        f"月の候補は新規{selected_new_count}社・商談中{selected_ongoing_count}社、"
        f"必要商談回数を踏まえて計{selected_visit_count}回を営業日に配分しました。"
    )
    deferred_required_visits = sum(
        max(0, candidate.remaining_visit_count - candidate.planned_visit_count)
        for candidate in selected_candidates
    )
    if deferred_required_visits:
        target_warnings.append(
            f"対象期間の日数上限により、残り商談のうち{deferred_required_visits}回は"
            "翌期間での計画が必要です。"
        )
    monthly_target = target_context["target_amount"]
    achieved_amount = target_context["achieved_amount"] or Decimal("0")
    remaining_target = target_context["remaining_target_amount"]
    monthly_target_gross_profit = target_context["target_gross_profit"]
    achieved_gross_profit = target_context["achieved_gross_profit"] or Decimal("0")
    achievement_probabilities = (
        target_simulation.simulate_achievement(
            _ongoing_deal_economics(conn, rep_id=rep_id),
            already_won_amount=achieved_amount,
            already_won_profit=achieved_gross_profit,
            target_amount=monthly_target,
            target_gross_profit=monthly_target_gross_profit,
        )
        if monthly_target is not None and monthly_target > 0
        else None
    )
    if monthly_target is None:
        target_warnings.append(
            "対象月の目標金額が未登録のため、評価上位の顧客から営業予定を作成しました。"
        )
    elif remaining_target == 0:
        target_warnings.append(
            "対象月の目標金額は成約実績で達成済みです。必須訪問だけを予定候補に残しました。"
        )
    else:
        target_warnings.append(
            f"月の残目標{remaining_target:,.0f}円を週・営業日へ配分し、"
            f"期待売上{portfolio_expected_sales:,.0f}円分の顧客候補を選びました。"
        )
        if planning_target is not None and portfolio_expected_sales < planning_target:
            target_warnings.append(
                f"現在の訪問候補では期間目標に{planning_target - portfolio_expected_sales:,.0f}円不足します。"
            )
    return {
        "batch_id": batch_id,
        "rep_id": rep_id,
        "rep_name": branch["rep_name"],
        "horizon": request.horizon,
        "start_date": business_days[0],
        "end_date": business_days[-1],
        "detailed_days": detailed_days,
        "branch": {
            "branch_id": branch["branch_id"],
            "branch_name": branch["branch_name"],
            "location": branch["location"],
            "latitude": float(branch["latitude"]),
            "longitude": float(branch["longitude"]),
        },
        "policy": request.policy,
        "weights": weights,
        "days": days_out,
        "weeks": weeks_out,
        "selected_customers": selected_customers_out,
        "totals": _jsonable(batch_totals),
        "monthly_target_amount": monthly_target,
        "achieved_amount": achieved_amount,
        "remaining_target_amount": remaining_target,
        "planning_target_amount": planning_target,
        "portfolio_expected_sales": portfolio_expected_sales,
        "portfolio_coverage_rate": (
            float(portfolio_expected_sales / planning_target)
            if planning_target is not None and planning_target > 0
            else 0
        ),
        "monthly_target_gross_profit": monthly_target_gross_profit,
        "achieved_gross_profit": achieved_gross_profit,
        "sales_achievement_probability": (
            achievement_probabilities.sales_probability
            if achievement_probabilities is not None else 0
        ),
        "profit_achievement_probability": (
            achievement_probabilities.profit_probability
            if achievement_probabilities is not None else None
        ),
        "joint_achievement_probability": (
            achievement_probabilities.joint_probability
            if achievement_probabilities is not None else 0
        ),
        "warnings": warnings + target_warnings + [
            f"直近{detailed_days}営業日は移動時間まで最適化した詳細プラン、{coverage_note}",
        ] + (
            ["概算プランの日は、実行日が近づいたらこの計画を作り直して詳細ルートを確定してください。"]
            if remaining > 0
            else []
        ),
    }


def approve_plan(conn: Connection, *, plan_id: int, rep_id: int) -> dict:
    try:
        plan = conn.execute(
            """
            select route_plan_id, rep_id, target_date, status, detail_level
            from route_plan
            where route_plan_id = %s
            for update
            """,
            (plan_id,),
        ).fetchone()
        if not plan or plan["rep_id"] != rep_id:
            raise RoutePlanningError("plan_not_found", "本人の計画案が見つかりません。")
        if plan["detail_level"] == "coarse":
            raise RoutePlanningError(
                "coarse_plan_not_approvable",
                "概算プランは承認できません。実行日が近づいたら計画を作り直して詳細ルートを確定してください。",
            )
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

        stops = conn.execute(
            """
            select rps.stop_id, rps.customer_id, rps.deal_ids,
                   rps.arrival_at, rps.departure_at, rps.economics,
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
                    min(stop["visit_order"], 5),
                    planned_sales,
                    max(0, min(100, probability)),
                    stop["selection_reason"],
                ),
            ).fetchone()
            activity_ids.append(activity["plan_id"])
            conn.execute(
                """
                insert into route_plan_activity(route_plan_id, stop_id, activity_plan_id)
                values (%s, %s, %s)
                """,
                (plan_id, stop["stop_id"], activity["plan_id"]),
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
