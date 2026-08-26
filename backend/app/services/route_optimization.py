from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol
from zoneinfo import ZoneInfo

import httpx
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from ortools.sat.python import cp_model

TOKYO = ZoneInfo("Asia/Tokyo")
YEN = Decimal("1")


class RoutePlanningError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code



class RouteMatrixPartialError(RoutePlanningError):
    def __init__(self, point_indexes: set[int]):
        super().__init__(
            "routes_partial_failure", "一部候補の移動経路を取得できませんでした。"
        )
        self.point_indexes = point_indexes


@dataclass(frozen=True)
class DealEconomics:
    estimated_amount: Decimal
    cost: Decimal | None
    win_probability: Decimal

    def __post_init__(self) -> None:
        if not Decimal("0") <= self.win_probability <= Decimal("100"):
            raise ValueError("win_probability must be between 0 and 100")

    @property
    def planned_gross_profit(self) -> Decimal | None:
        if self.cost is None:
            return None
        return (self.estimated_amount - self.cost).quantize(YEN, rounding=ROUND_HALF_UP)

    @property
    def gross_profit_margin(self) -> Decimal | None:
        profit = self.planned_gross_profit
        if profit is None or self.estimated_amount <= 0:
            return None
        return (
            profit / self.estimated_amount * Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def expected_sales(self) -> Decimal:
        return (
            self.estimated_amount * self.win_probability / Decimal("100")
        ).quantize(YEN, rounding=ROUND_HALF_UP)

    @property
    def expected_gross_profit(self) -> Decimal | None:
        profit = self.planned_gross_profit
        if profit is None:
            return None
        return (
            profit * self.win_probability / Decimal("100")
        ).quantize(YEN, rounding=ROUND_HALF_UP)


@dataclass
class VisitCandidate:
    customer_id: int
    customer_name: str
    latitude: float
    longitude: float
    deal_ids: list[int]
    phase_names: list[str]
    economics: list[DealEconomics]
    visit_duration_min: int = 60
    window_start: time | None = None
    window_end: time | None = None
    must_visit: bool = False
    visit_deadline: date | None = None
    distance_from_branch_m: int = 0
    value_score: Decimal = Decimal("0")
    score_components: dict[str, Decimal] = field(default_factory=dict)

    @property
    def planned_sales(self) -> Decimal:
        return sum((item.estimated_amount for item in self.economics), Decimal("0")).quantize(YEN)

    @property
    def planned_gross_profit(self) -> Decimal | None:
        values = [item.planned_gross_profit for item in self.economics]
        if any(value is None for value in values):
            return None
        return sum((value for value in values if value is not None), Decimal("0")).quantize(YEN)

    @property
    def expected_sales(self) -> Decimal:
        return sum((item.expected_sales for item in self.economics), Decimal("0")).quantize(YEN)

    @property
    def expected_gross_profit(self) -> Decimal | None:
        values = [item.expected_gross_profit for item in self.economics]
        if any(value is None for value in values):
            return None
        return sum((value for value in values if value is not None), Decimal("0")).quantize(YEN)

    @property
    def gross_profit_margin(self) -> Decimal | None:
        profit = self.planned_gross_profit
        if profit is None or self.planned_sales <= 0:
            return None
        return (profit / self.planned_sales * Decimal("100")).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class MatrixCell:
    duration_sec: int
    distance_m: int


class MatrixProvider(Protocol):
    def get_matrix(
        self,
        points: list[tuple[float, float]],
        departure_at: datetime,
    ) -> list[list[MatrixCell]]: ...


@dataclass(frozen=True)
class Portfolio:
    candidate_indexes: tuple[int, ...]
    business_value: Decimal
    cp_sat_status: str
    target_constraints_relaxed: bool = False


@dataclass
class RoutedOption:
    portfolio: Portfolio
    routing_status: str
    stops: list[dict]
    total_travel_min: int
    total_distance_m: int
    total_wait_min: int
    target_met: bool
    totals: dict[str, Decimal | int | None]
    rejection_reason: str | None = None
    return_leg: dict | None = None


def _normalize(values: list[Decimal]) -> list[Decimal]:
    if not values:
        return []
    low, high = min(values), max(values)
    if low == high:
        return [Decimal("100") if high > 0 else Decimal("0") for _ in values]
    return [
        ((value - low) * Decimal("100") / (high - low)).quantize(Decimal("0.01"))
        for value in values
    ]


def score_candidates(
    candidates: list[VisitCandidate],
    *,
    target_date: date,
    weights: dict[str, int],
    target_gap_ratio: Decimal = Decimal("0"),
) -> None:
    sales_scores = _normalize([candidate.expected_sales for candidate in candidates])
    profit_scores = _normalize([
        candidate.expected_gross_profit or Decimal("0") for candidate in candidates
    ])
    phase_scores = _normalize([
        Decimal(max((_phase_value(name) for name in candidate.phase_names), default=0))
        for candidate in candidates
    ])
    urgencies = [
        Decimal("0")
        if candidate.visit_deadline is None
        else Decimal(max(0, min(100, 100 - max(0, (candidate.visit_deadline - target_date).days) * 4)))
        for candidate in candidates
    ]
    gap = max(Decimal("0"), min(Decimal("100"), target_gap_ratio * Decimal("100")))

    for index, candidate in enumerate(candidates):
        components = {
            "sales": sales_scores[index],
            "gross_profit": profit_scores[index],
            "urgency": urgencies[index],
            "phase": phase_scores[index],
            "target_gap": gap,
        }
        candidate.score_components = components
        candidate.value_score = (
            sum(
                components[name] * Decimal(str(weights[name]))
                for name in components
            )
            / Decimal("100")
        ).quantize(Decimal("0.01"))


def _phase_value(name: str) -> int:
    return {
        "初回接触": 20,
        "ヒアリング": 40,
        "提案": 60,
        "見積": 80,
        "契約交渉": 100,
    }.get(name, 0)


def _money_int(value: Decimal | None) -> int:
    if value is None:
        return 0
    return int(value.quantize(YEN, rounding=ROUND_HALF_UP))


def generate_portfolios(
    candidates: list[VisitCandidate],
    matrix: list[list[MatrixCell]],
    *,
    max_visits: int,
    available_min: int,
    min_expected_sales: Decimal | None,
    min_expected_gross_profit: Decimal | None,
    limit: int = 10,
    time_limit_sec: int = 5,
    travel_penalty_weight: int = 0,
    end_node_index: int = 0,
    turnaround_buffer_min: int = 0,
) -> list[Portfolio]:
    strict = _solve_portfolios(
        candidates,
        matrix,
        max_visits=max_visits,
        available_min=available_min,
        min_expected_sales=min_expected_sales,
        min_expected_gross_profit=min_expected_gross_profit,
        limit=limit,
        time_limit_sec=time_limit_sec,
        travel_penalty_weight=travel_penalty_weight,
        end_node_index=end_node_index,
        turnaround_buffer_min=turnaround_buffer_min,
        relaxed=False,
    )
    if strict or (min_expected_sales is None and min_expected_gross_profit is None):
        return strict
    return _solve_portfolios(
        candidates,
        matrix,
        max_visits=max_visits,
        available_min=available_min,
        min_expected_sales=None,
        min_expected_gross_profit=None,
        limit=limit,
        time_limit_sec=time_limit_sec,
        travel_penalty_weight=travel_penalty_weight,
        end_node_index=end_node_index,
        turnaround_buffer_min=turnaround_buffer_min,
        relaxed=True,
    )


def _solve_portfolios(
    candidates: list[VisitCandidate],
    matrix: list[list[MatrixCell]],
    *,
    max_visits: int,
    available_min: int,
    min_expected_sales: Decimal | None,
    min_expected_gross_profit: Decimal | None,
    limit: int,
    time_limit_sec: int,
    travel_penalty_weight: int,
    end_node_index: int,
    turnaround_buffer_min: int,
    relaxed: bool,
) -> list[Portfolio]:
    if not candidates:
        return []
    model = cp_model.CpModel()
    selected = [model.new_bool_var(f"visit_{index}") for index in range(len(candidates))]
    model.add(sum(selected) <= max_visits)
    model.add(sum(selected) >= 1)

    for index, candidate in enumerate(candidates):
        if candidate.must_visit:
            model.add(selected[index] == 1)

    # CP-SAT only needs a conservative order-free estimate; RoutingModel makes
    # the final feasibility decision using the complete road matrix.
    estimated_minutes = []
    for index, candidate in enumerate(candidates):
        endpoint_travel = (
            matrix[0][index + 1].duration_sec
            + matrix[index + 1][end_node_index].duration_sec
        ) // 60
        estimated_minutes.append(
            candidate.visit_duration_min
            + turnaround_buffer_min
            + endpoint_travel
        )
    model.add(
        sum(selected[index] * estimated_minutes[index] for index in range(len(candidates)))
        <= available_min
    )

    if min_expected_sales is not None:
        model.add(
            sum(
                selected[index] * _money_int(candidate.expected_sales)
                for index, candidate in enumerate(candidates)
            )
            >= _money_int(min_expected_sales)
        )
    if min_expected_gross_profit is not None:
        for index, candidate in enumerate(candidates):
            if candidate.expected_gross_profit is None:
                # An unknown cost cannot prove a mandatory gross-profit floor.
                model.add(selected[index] == 0)
        model.add(
            sum(
                selected[index] * _money_int(candidate.expected_gross_profit)
                for index, candidate in enumerate(candidates)
            )
            >= _money_int(min_expected_gross_profit)
        )

    max_distance = max(
        (candidate.distance_from_branch_m for candidate in candidates), default=1
    )
    scores = [
        max(
            0,
            int(candidate.value_score * Decimal("100"))
            - (
                candidate.distance_from_branch_m
                * travel_penalty_weight
                * 100
                // max(1, max_distance)
            ),
        )
        for candidate in candidates
    ]
    model.maximize(sum(selected[index] * scores[index] for index in range(len(candidates))))

    portfolios: list[Portfolio] = []
    for _ in range(limit):
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit_sec)
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 0
        status = solver.solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break
        chosen = tuple(index for index, variable in enumerate(selected) if solver.value(variable))
        status_name = "optimal" if status == cp_model.OPTIMAL else "feasible"
        portfolios.append(
            Portfolio(
                candidate_indexes=chosen,
                business_value=sum(
                    (candidates[index].value_score for index in chosen), Decimal("0")
                ).quantize(Decimal("0.01")),
                cp_sat_status=status_name,
                target_constraints_relaxed=relaxed,
            )
        )
        model.add(
            sum(
                variable if index in chosen else 1 - variable
                for index, variable in enumerate(selected)
            )
            <= len(candidates) - 1
        )
    return portfolios


def _sum_totals(candidates: list[VisitCandidate], indexes: tuple[int, ...]) -> dict:
    chosen = [candidates[index] for index in indexes]
    known_profit = all(candidate.planned_gross_profit is not None for candidate in chosen)
    known_expected_profit = all(candidate.expected_gross_profit is not None for candidate in chosen)
    return {
        "planned_sales": sum((candidate.planned_sales for candidate in chosen), Decimal("0")),
        "planned_gross_profit": (
            sum((candidate.planned_gross_profit or Decimal("0") for candidate in chosen), Decimal("0"))
            if known_profit else None
        ),
        "expected_sales": sum((candidate.expected_sales for candidate in chosen), Decimal("0")),
        "expected_gross_profit": (
            sum((candidate.expected_gross_profit or Decimal("0") for candidate in chosen), Decimal("0"))
            if known_expected_profit else None
        ),
    }


def route_portfolio(
    candidates: list[VisitCandidate],
    matrix: list[list[MatrixCell]],
    portfolio: Portfolio,
    *,
    target_date: date,
    work_start: time,
    work_end: time,
    blocked_windows: list[tuple[time, time]] | None = None,
    time_limit_sec: int = 5,
    end_node_index: int = 0,
    turnaround_buffer_min: int = 0,
) -> RoutedOption:
    candidate_indexes = portfolio.candidate_indexes
    totals = _sum_totals(candidates, candidate_indexes)
    if not candidate_indexes:
        return RoutedOption(portfolio, "routing_infeasible", [], 0, 0, 0, False, totals)

    candidate_global_nodes = tuple(index + 1 for index in candidate_indexes)
    if end_node_index == 0:
        global_nodes = (0,) + candidate_global_nodes
        manager = pywrapcp.RoutingIndexManager(len(global_nodes), 1, 0)
    else:
        global_nodes = (0,) + candidate_global_nodes + (end_node_index,)
        manager = pywrapcp.RoutingIndexManager(
            len(global_nodes), 1, [0], [len(global_nodes) - 1]
        )
    routing = pywrapcp.RoutingModel(manager)

    def candidate_at_local_node(local_node: int) -> VisitCandidate | None:
        if 1 <= local_node <= len(candidate_indexes):
            return candidates[candidate_indexes[local_node - 1]]
        return None

    def travel_seconds(from_index: int, to_index: int) -> int:
        source = global_nodes[manager.IndexToNode(from_index)]
        destination = global_nodes[manager.IndexToNode(to_index)]
        return matrix[source][destination].duration_sec

    def time_seconds(from_index: int, to_index: int) -> int:
        source_local = manager.IndexToNode(from_index)
        candidate = candidate_at_local_node(source_local)
        service = (
            (candidate.visit_duration_min + turnaround_buffer_min) * 60
            if candidate is not None
            else 0
        )
        return service + travel_seconds(from_index, to_index)

    time_callback = routing.RegisterTransitCallback(time_seconds)
    cost_callback = routing.RegisterTransitCallback(
        lambda from_index, to_index: (
            travel_seconds(from_index, to_index)
            + matrix[
                global_nodes[manager.IndexToNode(from_index)]
            ][global_nodes[manager.IndexToNode(to_index)]].distance_m // 20
        )
    )
    routing.SetArcCostEvaluatorOfAllVehicles(cost_callback)

    work_start_dt = datetime.combine(target_date, work_start, TOKYO)
    work_end_dt = datetime.combine(target_date, work_end, TOKYO)
    horizon_sec = int((work_end_dt - work_start_dt).total_seconds())
    routing.AddDimension(time_callback, horizon_sec, horizon_sec, False, "Time")
    time_dimension = routing.GetDimensionOrDie("Time")
    time_dimension.CumulVar(routing.Start(0)).SetRange(0, 0)
    time_dimension.CumulVar(routing.End(0)).SetRange(0, horizon_sec)

    for local_node, candidate_index in enumerate(candidate_indexes, start=1):
        candidate = candidates[candidate_index]
        earliest = 0
        latest = horizon_sec - candidate.visit_duration_min * 60
        if candidate.window_start is not None:
            earliest = max(
                earliest,
                int(
                    (
                        datetime.combine(target_date, candidate.window_start, TOKYO)
                        - work_start_dt
                    ).total_seconds()
                ),
            )
        if candidate.window_end is not None:
            latest = min(
                latest,
                int(
                    (
                        datetime.combine(target_date, candidate.window_end, TOKYO)
                        - work_start_dt
                    ).total_seconds()
                )
                - candidate.visit_duration_min * 60,
            )
        if earliest > latest:
            return RoutedOption(
                portfolio, "routing_infeasible", [], 0, 0, 0, False, totals,
                "訪問可能時間が勤務時間外です。",
            )
        time_dimension.CumulVar(manager.NodeToIndex(local_node)).SetRange(earliest, latest)


    break_intervals = []
    for break_index, (blocked_start, blocked_end) in enumerate(blocked_windows or []):
        start_sec = max(
            0,
            int(
                (
                    datetime.combine(target_date, blocked_start, TOKYO)
                    - work_start_dt
                ).total_seconds()
            ),
        )
        end_sec = min(
            horizon_sec,
            int(
                (
                    datetime.combine(target_date, blocked_end, TOKYO)
                    - work_start_dt
                ).total_seconds()
            ),
        )
        if end_sec > start_sec:
            break_intervals.append(
                routing.solver().FixedDurationIntervalVar(
                    start_sec,
                    start_sec,
                    end_sec - start_sec,
                    False,
                    f"fixed_schedule_{break_index}",
                )
            )
    if break_intervals:
        node_visit_transits = []
        for route_index in range(routing.Size()):
            local_node = manager.IndexToNode(route_index)
            candidate = candidate_at_local_node(local_node)
            service_sec = (
                (candidate.visit_duration_min + turnaround_buffer_min) * 60
                if candidate is not None
                else 0
            )
            node_visit_transits.append(service_sec)
        time_dimension.SetBreakIntervalsOfVehicle(
            break_intervals, 0, node_visit_transits
        )

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    )
    search.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search.time_limit.seconds = max(1, time_limit_sec)
    solution = routing.SolveWithParameters(search)
    if solution is None:
        return RoutedOption(
            portfolio, "routing_infeasible", [], 0, 0, 0, False, totals,
            "勤務時間または訪問時間枠を満たす経路がありません。",
        )

    stops: list[dict] = []
    total_travel_sec = 0
    total_distance_m = 0
    total_wait_sec = 0
    route_index = routing.Start(0)
    previous_global = 0
    previous_ready_at = work_start_dt
    while not routing.IsEnd(route_index):
        next_route_index = solution.Value(routing.NextVar(route_index))
        next_local = manager.IndexToNode(next_route_index)
        next_global = global_nodes[next_local]
        cell = matrix[previous_global][next_global]
        total_travel_sec += cell.duration_sec
        total_distance_m += cell.distance_m
        if not routing.IsEnd(next_route_index):
            candidate_index = candidate_indexes[next_local - 1]
            candidate = candidates[candidate_index]
            arrival_sec = solution.Value(time_dimension.CumulVar(next_route_index))
            arrival_at = work_start_dt + timedelta(seconds=arrival_sec)
            departure_at = arrival_at + timedelta(minutes=candidate.visit_duration_min)
            theoretical_arrival = previous_ready_at + timedelta(seconds=cell.duration_sec)
            total_wait_sec += max(0, int((arrival_at - theoretical_arrival).total_seconds()))
            stops.append(
                {
                    "visit_order": len(stops) + 1,
                    "candidate_index": candidate_index,
                    "customer_id": candidate.customer_id,
                    "customer_name": candidate.customer_name,
                    "deal_ids": candidate.deal_ids,
                    "phase_names": candidate.phase_names,
                    "arrival_at": arrival_at,
                    "departure_at": departure_at,
                    "visit_duration_min": candidate.visit_duration_min,
                    "turnaround_buffer_min": turnaround_buffer_min,
                    "leg_travel_min": round(cell.duration_sec / 60),
                    "leg_distance_m": cell.distance_m,
                    "economics": candidate_economics_dict(candidate),
                    "selection_reason": selection_reason(candidate),
                    "latitude": candidate.latitude,
                    "longitude": candidate.longitude,
                }
            )
            previous_ready_at = departure_at + timedelta(
                minutes=turnaround_buffer_min
            )
        previous_global = next_global
        route_index = next_route_index

    for blocked_start, blocked_end in blocked_windows or []:
        blocked_start_dt = datetime.combine(target_date, blocked_start, TOKYO)
        blocked_end_dt = datetime.combine(target_date, blocked_end, TOKYO)
        if any(
            stop["arrival_at"] < blocked_end_dt and stop["departure_at"] > blocked_start_dt
            for stop in stops
        ):
            return RoutedOption(
                portfolio, "routing_infeasible", stops,
                round(total_travel_sec / 60), total_distance_m,
                round(total_wait_sec / 60), False, totals,
                "既存の固定予定と訪問時刻が重複します。",
            )

    route_end_sec = solution.Value(time_dimension.CumulVar(routing.End(0)))
    route_end_at = work_start_dt + timedelta(seconds=route_end_sec)
    totals.update(
        total_travel_min=round(total_travel_sec / 60),
        total_distance_m=total_distance_m,
        total_wait_min=round(total_wait_sec / 60),
        total_turnaround_min=turnaround_buffer_min * len(stops),
        visit_count=len(stops),
        route_end_at=route_end_at.isoformat(),
    )
    return RoutedOption(
        portfolio=portfolio,
        routing_status="feasible",
        stops=stops,
        total_travel_min=round(total_travel_sec / 60),
        total_distance_m=total_distance_m,
        total_wait_min=round(total_wait_sec / 60),
        target_met=not portfolio.target_constraints_relaxed,
        totals=totals,
    )


def candidate_economics_dict(candidate: VisitCandidate) -> dict:
    return {
        "planned_sales": candidate.planned_sales,
        "planned_gross_profit": candidate.planned_gross_profit,
        "gross_profit_margin": candidate.gross_profit_margin,
        "expected_sales": candidate.expected_sales,
        "expected_gross_profit": candidate.expected_gross_profit,
        "value_score": candidate.value_score,
        "gross_profit_available": candidate.planned_gross_profit is not None,
    }


def selection_reason(candidate: VisitCandidate) -> str:
    profit = candidate.expected_gross_profit
    profit_text = "粗利評価不可" if profit is None else f"期待粗利{profit:,.0f}円"
    return (
        f"期待売上{candidate.expected_sales:,.0f}円、{profit_text}、"
        f"出発地点から約{candidate.distance_from_branch_m / 1000:.1f}kmを総合評価しました。"
    )


def evaluate_options(options: list[RoutedOption]) -> RoutedOption:
    feasible = [option for option in options if option.routing_status == "feasible"]
    if not feasible:
        raise RoutePlanningError(
            "routing_infeasible",
            "すべての候補セットが勤務時間または固定予定の制約を満たせませんでした。",
        )

    def key(option: RoutedOption) -> tuple:
        expected_profit = option.totals["expected_gross_profit"]
        return (
            1 if option.target_met else 0,
            expected_profit if expected_profit is not None else Decimal("-Infinity"),
            option.totals["expected_sales"],
            -option.total_travel_min,
        )

    return max(feasible, key=key)


class OpenTripPlannerTransitMatrixProvider:
    """Local ODPT/GTFS + OpenStreetMap door-to-door transit matrix."""

    PLAN_QUERY = """
    query Plan($from: InputCoordinates!, $to: InputCoordinates!, $date: String!, $time: String!) {
      plan(
        from: $from
        to: $to
        date: $date
        time: $time
        locale: "ja"
        numItineraries: 10
        maxTransfers: 4
        minTransferTime: 120
      ) {
        itineraries {
          duration
          startTime
          endTime
          walkDistance
          legs {
            mode
            duration
            distance
          }
        }
        messageStrings
      }
    }
    """

    DETAILED_PLAN_QUERY = """
    query Plan($from: InputCoordinates!, $to: InputCoordinates!, $date: String!, $time: String!) {
      plan(
        from: $from
        to: $to
        date: $date
        time: $time
        locale: "ja"
        numItineraries: 10
        maxTransfers: 4
        minTransferTime: 120
      ) {
        itineraries {
          duration
          startTime
          endTime
          walkDistance
          legs {
            mode
            duration
            distance
            realTime
            headsign
            start {
              scheduledTime
              estimated { time delay }
            }
            end {
              scheduledTime
              estimated { time delay }
            }
            from {
              name
              stop { gtfsId name platformCode }
            }
            to {
              name
              stop { gtfsId name platformCode }
            }
            route { gtfsId shortName longName }
            trip { gtfsId tripHeadsign }
          }
        }
        messageStrings
      }
    }
    """

    def __init__(self, *, api_url: str, timeout: float = 30):
        self.api_url = api_url
        self.timeout = timeout

    def get_matrix(
        self,
        points: list[tuple[float, float]],
        departure_at: datetime,
    ) -> list[list[MatrixCell]]:
        size = len(points)
        matrix: list[list[MatrixCell | None]] = [
            [MatrixCell(0, 0) if origin == destination else None for destination in range(size)]
            for origin in range(size)
        ]
        local_departure = departure_at.astimezone(TOKYO)

        try:
            with httpx.Client(timeout=self.timeout) as client:
                for origin, start in enumerate(points):
                    for destination, goal in enumerate(points):
                        if origin == destination:
                            continue
                        response = client.post(
                            self.api_url,
                            json={
                                "query": self.PLAN_QUERY,
                                "variables": {
                                    "from": {"lat": start[0], "lon": start[1]},
                                    "to": {"lat": goal[0], "lon": goal[1]},
                                    "date": local_departure.date().isoformat(),
                                    "time": local_departure.time().replace(microsecond=0).isoformat(),
                                },
                            },
                        )
                        response.raise_for_status()
                        cell = self._parse_response(response.json(), local_departure)
                        if cell is not None:
                            matrix[origin][destination] = cell
        except (httpx.HTTPError, ValueError) as error:
            raise RoutePlanningError(
                "otp_api_unavailable",
                "ODPT経路検索サービスが起動していません。GTFSグラフの初期化状態を確認してください。",
            ) from error

        missing_pairs = [
            (origin, destination)
            for origin, row in enumerate(matrix)
            for destination, cell in enumerate(row)
            if cell is None
        ]
        if missing_pairs:
            affected = self._missing_point_indexes(matrix, missing_pairs)
            if not affected:
                raise RoutePlanningError(
                    "otp_api_unavailable",
                    "ODPTデータ内に利用可能な公共交通経路がありません。",
                )
            raise RouteMatrixPartialError(affected)
        return [[cell for cell in row if cell is not None] for row in matrix]

    @staticmethod
    def _missing_point_indexes(
        matrix: list[list[MatrixCell | None]],
        missing_pairs: list[tuple[int, int]],
    ) -> set[int]:
        """Prefer removing points disconnected from the start, then the worst node."""
        unreachable_from_start = {
            index
            for index in range(1, len(matrix))
            if matrix[0][index] is None or matrix[index][0] is None
        }
        if unreachable_from_start:
            return unreachable_from_start

        missing_counts = {
            index: sum(index in pair for pair in missing_pairs)
            for index in range(1, len(matrix))
        }
        worst_count = max(missing_counts.values(), default=0)
        return {
            index for index, count in missing_counts.items() if count == worst_count and count > 0
        }

    def get_itinerary(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        departure_at: datetime,
    ) -> dict:
        """Return a time-specific, door-to-door itinerary with each transit leg."""
        local_departure = departure_at.astimezone(TOKYO)
        try:
            response = httpx.post(
                self.api_url,
                json={
                    "query": self.DETAILED_PLAN_QUERY,
                    "variables": {
                        "from": {"lat": origin[0], "lon": origin[1]},
                        "to": {"lat": destination[0], "lon": destination[1]},
                        "date": local_departure.date().isoformat(),
                        "time": local_departure.time().replace(microsecond=0).isoformat(),
                    },
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise RoutePlanningError(
                "otp_api_unavailable",
                "ODPT経路検索サービスから時刻別の乗車経路を取得できませんでした。",
            ) from error

        itinerary = self._best_itinerary(body)
        if itinerary is None:
            raise RoutePlanningError(
                "transit_route_unavailable",
                "指定時刻に利用できる公共交通経路がありません。",
            )
        legs = itinerary.get("legs")
        if not isinstance(legs, list) or not legs:
            raise RoutePlanningError(
                "transit_route_unavailable",
                "指定時刻の公共交通経路に乗車区間がありません。",
            )

        parsed_legs = [self._parse_leg(leg) for leg in legs if isinstance(leg, dict)]
        if not parsed_legs:
            raise RoutePlanningError(
                "transit_route_unavailable",
                "指定時刻の公共交通経路を解釈できませんでした。",
            )
        scheduled_duration = itinerary.get("duration")
        if not isinstance(scheduled_duration, (int, float)):
            raise RoutePlanningError(
                "transit_route_unavailable",
                "指定時刻の公共交通経路の所要時間を解釈できませんでした。",
            )
        itinerary_arrival = datetime.fromisoformat(parsed_legs[-1]["arrival_at"])
        elapsed_duration = max(
            1,
            int(round((itinerary_arrival - local_departure).total_seconds())),
        )
        distance = sum(leg["distance_m"] for leg in parsed_legs)
        return {
            "departure_at": parsed_legs[0]["departure_at"],
            "arrival_at": parsed_legs[-1]["arrival_at"],
            "duration_sec": elapsed_duration,
            "scheduled_duration_sec": int(round(float(scheduled_duration))),
            "distance_m": int(round(distance)),
            "walk_distance_m": int(round(float(itinerary.get("walkDistance") or 0))),
            "real_time": any(leg["real_time"] for leg in parsed_legs),
            "data_status": (
                "リアルタイム反映" if any(leg["real_time"] for leg in parsed_legs)
                else "時刻表ベース"
            ),
            "legs": parsed_legs,
        }

    @staticmethod
    def _best_itinerary(body: object) -> dict | None:
        if not isinstance(body, dict) or body.get("errors"):
            return None
        data = body.get("data")
        plan = data.get("plan") if isinstance(data, dict) else None
        itineraries = plan.get("itineraries") if isinstance(plan, dict) else None
        if not isinstance(itineraries, list) or not itineraries:
            return None
        valid = [
            itinerary
            for itinerary in itineraries
            if isinstance(itinerary, dict)
            and isinstance(itinerary.get("duration"), (int, float))
            and itinerary["duration"] > 0
        ]
        if not valid:
            return None

        def uses_transit(itinerary: dict) -> bool:
            legs = itinerary.get("legs")
            return isinstance(legs, list) and any(
                isinstance(leg, dict) and leg.get("mode") != "WALK"
                for leg in legs
            )

        transit_itineraries = [itinerary for itinerary in valid if uses_transit(itinerary)]
        preferred = transit_itineraries or valid

        def preference(itinerary: dict) -> tuple[float, float, float]:
            end_time = itinerary.get("endTime")
            return (
                float(end_time) if isinstance(end_time, (int, float)) else float(itinerary["duration"]),
                float(itinerary["duration"]),
                float(itinerary.get("walkDistance") or 0),
            )

        return min(preferred, key=preference)

    @staticmethod
    def _parse_leg(leg: dict) -> dict:
        start = leg.get("start") if isinstance(leg.get("start"), dict) else {}
        end = leg.get("end") if isinstance(leg.get("end"), dict) else {}
        start_estimated = (
            start.get("estimated") if isinstance(start.get("estimated"), dict) else None
        )
        end_estimated = (
            end.get("estimated") if isinstance(end.get("estimated"), dict) else None
        )
        origin = leg.get("from") if isinstance(leg.get("from"), dict) else {}
        destination = leg.get("to") if isinstance(leg.get("to"), dict) else {}
        origin_stop = origin.get("stop") if isinstance(origin.get("stop"), dict) else {}
        destination_stop = (
            destination.get("stop") if isinstance(destination.get("stop"), dict) else {}
        )
        route = leg.get("route") if isinstance(leg.get("route"), dict) else {}
        trip = leg.get("trip") if isinstance(leg.get("trip"), dict) else {}
        scheduled_departure = start.get("scheduledTime")
        scheduled_arrival = end.get("scheduledTime")
        departure = start_estimated.get("time") if start_estimated else scheduled_departure
        arrival = end_estimated.get("time") if end_estimated else scheduled_arrival
        headsign = leg.get("headsign") or trip.get("tripHeadsign")
        return {
            "mode": str(leg.get("mode") or "WALK"),
            "departure_at": departure,
            "arrival_at": arrival,
            "scheduled_departure_at": scheduled_departure,
            "scheduled_arrival_at": scheduled_arrival,
            "departure_delay_sec": int(start_estimated.get("delay") or 0) if start_estimated else 0,
            "arrival_delay_sec": int(end_estimated.get("delay") or 0) if end_estimated else 0,
            "duration_sec": int(round(float(leg.get("duration") or 0))),
            "distance_m": int(round(float(leg.get("distance") or 0))),
            "from_name": origin_stop.get("name") or origin.get("name") or "出発地点",
            "to_name": destination_stop.get("name") or destination.get("name") or "到着地点",
            "from_stop_id": origin_stop.get("gtfsId"),
            "to_stop_id": destination_stop.get("gtfsId"),
            "from_platform": origin_stop.get("platformCode"),
            "to_platform": destination_stop.get("platformCode"),
            "route_name": route.get("shortName") or route.get("longName"),
            "route_id": route.get("gtfsId"),
            "headsign": headsign,
            "trip_id": trip.get("gtfsId"),
            "real_time": bool(leg.get("realTime")),
        }

    @staticmethod
    def _parse_response(
        body: object,
        requested_departure: datetime | None = None,
    ) -> MatrixCell | None:
        itinerary = OpenTripPlannerTransitMatrixProvider._best_itinerary(body)
        if itinerary is None:
            return None
        duration = itinerary.get("duration")
        end_time = itinerary.get("endTime")
        legs = itinerary.get("legs")
        if not isinstance(duration, (int, float)) or duration <= 0 or not isinstance(legs, list):
            return None
        if requested_departure is not None and isinstance(end_time, (int, float)):
            end_at = datetime.fromtimestamp(float(end_time) / 1000, tz=TOKYO)
            duration = max(1, (end_at - requested_departure).total_seconds())
        distance = sum(
            float(leg["distance"])
            for leg in legs
            if isinstance(leg, dict) and isinstance(leg.get("distance"), (int, float))
        )
        return MatrixCell(int(round(float(duration))), int(round(distance)))


class GoogleRoutesMatrixProvider:
    """Google Routes matrix for every supported travel mode, with batching."""

    TRAVEL_MODES = {
        "driving": "DRIVE",
        "walking": "WALK",
        "cycling": "BICYCLE",
    }

    def __init__(
        self,
        *,
        api_key: str,
        api_url: str,
        travel_mode: str,
        timeout: float = 30,
    ):
        if travel_mode not in self.TRAVEL_MODES:
            raise ValueError(f"Unsupported travel mode: {travel_mode}")
        self.api_key = api_key
        self.api_url = api_url
        self.travel_mode = travel_mode
        self.timeout = timeout

    def get_matrix(
        self,
        points: list[tuple[float, float]],
        departure_at: datetime,
    ) -> list[list[MatrixCell]]:
        if not self.api_key:
            raise RoutePlanningError(
                "google_routes_api_unavailable",
                "移動時間を取得するにはGoogle Routes APIキーの設定が必要です。",
            )

        size = len(points)
        matrix: list[list[MatrixCell | None]] = [
            [MatrixCell(0, 0) if origin == destination else None for destination in range(size)]
            for origin in range(size)
        ]
        google_mode = self.TRAVEL_MODES[self.travel_mode]
        # The total number of coordinate origins and destinations must stay <= 50.
        origin_chunk_size = max(
            1,
            min(625 // max(1, size), max(1, 50 - size)),
        )
        destinations = [self._waypoint(point) for point in points]

        for origin_start in range(0, size, origin_chunk_size):
            origin_points = points[origin_start:origin_start + origin_chunk_size]
            payload = {
                "origins": [self._waypoint(point) for point in origin_points],
                "destinations": destinations,
                "travelMode": google_mode,
            }
            try:
                response = httpx.post(
                    self.api_url,
                    headers={
                        "Content-Type": "application/json",
                        "X-Goog-Api-Key": self.api_key,
                        "X-Goog-FieldMask": (
                            "originIndex,destinationIndex,duration,distanceMeters,"
                            "condition,status"
                        ),
                    },
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                body = response.json()
            except (httpx.HTTPError, ValueError) as error:
                raise RoutePlanningError(
                    "google_routes_api_unavailable",
                    "Google Routes APIから移動時間を取得できませんでした。",
                ) from error
            if not isinstance(body, list):
                raise RoutePlanningError(
                    "routes_api_invalid",
                    "Google Routes APIの移動行列の形式が不正です。",
                )

            for element in body:
                if not isinstance(element, dict):
                    continue
                try:
                    origin = origin_start + int(element["originIndex"])
                    destination = int(element["destinationIndex"])
                except (KeyError, TypeError, ValueError):
                    continue
                if origin == destination:
                    matrix[origin][destination] = MatrixCell(0, 0)
                    continue
                status = element.get("status")
                if isinstance(status, dict) and status.get("code") not in (None, 0):
                    continue
                if element.get("condition") not in (None, "ROUTE_EXISTS"):
                    continue
                duration = self._duration_seconds(element.get("duration"))
                distance = element.get("distanceMeters")
                if duration > 0 and isinstance(distance, (int, float)) and distance >= 0:
                    matrix[origin][destination] = MatrixCell(
                        duration, int(round(distance))
                    )

        missing_pairs = [
            (origin, destination)
            for origin, row in enumerate(matrix)
            for destination, cell in enumerate(row)
            if cell is None
        ]
        if missing_pairs:
            valid_non_diagonal = any(
                cell is not None and origin != destination
                for origin, row in enumerate(matrix)
                for destination, cell in enumerate(row)
            )
            if not valid_non_diagonal:
                raise RoutePlanningError(
                    "google_routes_api_unavailable",
                    "Google Routes APIから選択した移動手段の経路を取得できませんでした。",
                )
            affected = {
                point_index
                for pair in missing_pairs
                for point_index in pair
                if point_index != 0
            }
            if not affected:
                raise RoutePlanningError(
                    "google_routes_api_unavailable",
                    "選択した移動手段で利用できる経路がありません。",
                )
            raise RouteMatrixPartialError(affected)
        return [[cell for cell in row if cell is not None] for row in matrix]

    @staticmethod
    def _waypoint(point: tuple[float, float]) -> dict:
        latitude, longitude = point
        return {
            "waypoint": {
                "location": {
                    "latLng": {
                        "latitude": latitude,
                        "longitude": longitude,
                    }
                }
            }
        }

    @staticmethod
    def _duration_seconds(value: object) -> int:
        if not isinstance(value, str) or not value.endswith("s"):
            return 0
        try:
            return int(round(float(value[:-1])))
        except ValueError:
            return 0
