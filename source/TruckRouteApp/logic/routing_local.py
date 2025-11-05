"""
Local routing engine built around OR-Tools for TSP optimisation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from ortools.constraint_solver import pywrapcp, routing_enums_pb2


@dataclass
class Stop:
    """
    Simple representation of a stop on the route.

    The first stop is expected to be the warehouse (depot).
    """

    name: str
    lat: float
    lng: float

    def as_tuple(self) -> tuple[float, float]:
        return (self.lat, self.lng)


@dataclass
class RouteResult:
    route_nodes: List[int]
    total_distance_m: int

    def ordered_stops(self, stops: Sequence[Stop]) -> List[Stop]:
        return [stops[i] for i in self.route_nodes]


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """
    Compute Haversine distance between two coordinates in meters.
    """
    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return int(round(2 * radius * math.asin(math.sqrt(a))))


def build_distance_matrix(stops: Sequence[Stop]) -> List[List[int]]:
    """
    Generate an all-pairs distance matrix for the provided stops.
    """
    n = len(stops)
    matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            matrix[i][j] = haversine_meters(
                stops[i].lat,
                stops[i].lng,
                stops[j].lat,
                stops[j].lng,
            )
    return matrix


def _validate_coordinates(stops: Iterable[Stop]) -> None:
    for index, stop in enumerate(stops):
        if not (-90 <= stop.lat <= 90) or not (-180 <= stop.lng <= 180):
            raise ValueError(
                f"Stop #{index} has invalid coordinates: lat={stop.lat}, lng={stop.lng}"
            )


def solve_tsp(distance_matrix: Sequence[Sequence[int]], depot_index: int, return_to_depot: bool) -> RouteResult:
    """
    Solve a TSP with a single vehicle using OR-Tools.
    """
    n = len(distance_matrix)
    manager = pywrapcp.RoutingIndexManager(n, 1, depot_index)
    routing = pywrapcp.RoutingModel(manager)

    def dist_callback(from_index: int, to_index: int) -> int:
        i = manager.IndexToNode(from_index)
        j = manager.IndexToNode(to_index)
        return int(distance_matrix[i][j])

    transit_idx = routing.RegisterTransitCallback(dist_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_params.time_limit.FromSeconds(5)

    solution = routing.SolveWithParameters(search_params)
    if not solution:
        raise RuntimeError("Unable to compute route with OR-Tools.")

    index = routing.Start(0)
    route_nodes = []
    total_distance = 0

    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        route_nodes.append(node)
        next_index = solution.Value(routing.NextVar(index))
        total_distance += routing.GetArcCostForVehicle(index, next_index, 0)
        index = next_index

    end_node = manager.IndexToNode(index)
    route_nodes.append(end_node)

    if not return_to_depot and route_nodes[-1] == depot_index:
        route_nodes = route_nodes[:-1]
        total_distance = sum(
            distance_matrix[route_nodes[i]][route_nodes[i + 1]] for i in range(len(route_nodes) - 1)
        )

    return RouteResult(route_nodes=route_nodes, total_distance_m=total_distance)


def optimise_route(stops: Sequence[Stop], return_to_depot: bool = True) -> RouteResult:
    """
    Public helper that validates input, builds the distance matrix, and solves the TSP.
    """
    stops = list(stops)
    if len(stops) < 2:
        raise ValueError("At least a depot and one customer are required to optimise a route.")

    _validate_coordinates(stops)

    distance_matrix = build_distance_matrix(stops)
    return solve_tsp(distance_matrix, depot_index=0, return_to_depot=return_to_depot)


def pretty_km(distance_m: int) -> str:
    return f"{distance_m / 1000:.2f} km"


__all__ = [
    "Stop",
    "RouteResult",
    "optimise_route",
    "build_distance_matrix",
    "haversine_meters",
    "pretty_km",
]

