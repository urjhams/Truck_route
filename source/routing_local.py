"""
Backward compatibility wrapper for the legacy routing module location.

The actual implementation now lives in ``TruckRouteApp.logic.routing_local``.
"""

from TruckRouteApp.logic.routing_local import (
    RouteResult,
    Stop,
    build_distance_matrix,
    haversine_meters,
    optimise_route,
    pretty_km,
    solve_tsp,
)

__all__ = [
    "RouteResult",
    "Stop",
    "build_distance_matrix",
    "haversine_meters",
    "optimise_route",
    "pretty_km",
    "solve_tsp",
]

