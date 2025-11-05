#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import csv
import math
import argparse
from pathlib import Path
from typing import List, Dict
from ortools.constraint_solver import pywrapcp, routing_enums_pb2


def haversine_meters(lat1, lon1, lat2, lon2) -> int:
    """Khoảng cách Haversine ~ mét (làm tròn int)."""
    R = 6371000.0  # bán kính Trái Đất (m)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return int(round(2 * R * math.asin(math.sqrt(a))))


def build_distance_matrix(stops: List[Dict]) -> List[List[int]]:
    """Tạo ma trận khoảng cách (m) theo Haversine."""
    n = len(stops)
    dist = [[0]*n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                dist[i][j] = 0
            else:
                dist[i][j] = haversine_meters(
                    stops[i]["lat"], stops[i]["lng"],
                    stops[j]["lat"], stops[j]["lng"]
                )
    return dist


def solve_tsp(distance_matrix: List[List[int]], depot_index: int = 0, return_to_depot: bool = True):
    """Giải TSP: xuất phát tại depot. Nếu return_to_depot=True thì quay về depot."""
    n = len(distance_matrix)
    # Nếu không quay về depot, trick: thêm 'end' ảo = depot để model route mở.
    # Ở đây dùng OR-Tools chuẩn: vẫn đặt start=end tại depot, rồi tùy xử lý output.
    manager = pywrapcp.RoutingIndexManager(n, 1, depot_index)
    routing = pywrapcp.RoutingModel(manager)

    # Callback distance
    def dist_cb(from_index, to_index):
        i = manager.IndexToNode(from_index)
        j = manager.IndexToNode(to_index)
        return distance_matrix[i][j]

    transit_idx = routing.RegisterTransitCallback(dist_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    # Nếu KHÔNG quay về depot: đặt depot là start, end là node khác (giải pháp: set disjunction để tránh quay về)
    if not return_to_depot:
        end_index = manager.NodeToIndex(depot_index)
        routing.SetFixedCostOfAllVehicles(0)
        # Cho phép không bắt buộc quay lại: một cách đơn giản là đặt chi phí quay về rất lớn
        # bằng cách override cost evaluator? Ở đây dùng thêm penalty cho depot để không chọn quay về.
        # Tuy nhiên cách an toàn: sau khi giải, nếu route kết thúc tại depot, ta cắt bỏ bước cuối.
        pass

    # Tham số tìm kiếm
    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search.time_limit.FromSeconds(5)

    solution = routing.SolveWithParameters(search)
    if not solution:
        return None

    # Trích xuất route
    index = routing.Start(0)
    route_nodes = []
    route_distance = 0
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        route_nodes.append(node)
        next_index = solution.Value(routing.NextVar(index))
        route_distance += routing.GetArcCostForVehicle(index, next_index, 0)
        index = next_index
    # node cuối (End)
    end_node = manager.IndexToNode(index)
    route_nodes.append(end_node)

    if not return_to_depot and route_nodes[-1] == depot_index:
        # Nếu không muốn quay về depot, nhưng model vẫn trả về depot, cắt node cuối
        route_nodes = route_nodes[:-1]

    return {
        "route_nodes": route_nodes,          # danh sách index theo thứ tự đi (0 = depot)
        "total_distance_m": route_distance if return_to_depot else sum(
            distance_matrix[route_nodes[i]][route_nodes[i+1]]
            for i in range(len(route_nodes)-1)
        )
    }


def pretty_km(meters: int) -> str:
    return f"{meters/1000:.2f} km"


def main():
    parser = argparse.ArgumentParser(
        description="Tối ưu route local (TSP, Haversine). JSON đầu vào: phần tử đầu tiên là kho."
    )
    parser.add_argument("json_path", type=Path, help="Đường dẫn file JSON stops.")
    parser.add_argument("--no-return", action="store_true",
                        help="Mặc định quay về kho. Thêm cờ này để KHÔNG quay về kho.")
    parser.add_argument("--csv-out", type=Path, default=None,
                        help="Nếu chỉ định, ghi CSV kết quả (stt,name,lat,lng,distance_to_next_m).")
    args = parser.parse_args()

    # Đọc JSON
    stops = json.loads(args.json_path.read_text(encoding="utf-8"))
    if not isinstance(stops, list) or len(stops) < 2:
        raise SystemExit("JSON phải là list >= 2 điểm (depot + ít nhất 1 khách).")

    required = {"name", "lat", "lng"}
    for i, s in enumerate(stops):
        if not required.issubset(s):
            raise SystemExit(f"Stop #{i} thiếu trường {required}.")

    # Ma trận khoảng cách
    dist = build_distance_matrix(stops)

    # Giải TSP
    result = solve_tsp(dist, depot_index=0, return_to_depot=not args.no_return)
    if not result:
        raise SystemExit("Không tìm được lời giải.")

    route = result["route_nodes"]
    total_m = result["total_distance_m"]

    # In kết quả
    print("\n=== ROUTE TỐI ƯU ===")
    for idx, node in enumerate(route):
        tag = " (DEPOT)" if node == 0 else ""
        print(f"{idx:02d}. {stops[node]['name']}{tag}  [{stops[node]['lat']}, {stops[node]['lng']}]")
    print(f"\nTổng quãng đường: {pretty_km(total_m)} (Haversine xấp xỉ)")

    # CSV (tùy chọn)
    if args.csv_out:
        with args.csv_out.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["order", "name", "lat", "lng", "distance_to_next_m"])
            for i, node in enumerate(route):
                if i < len(route) - 1:
                    nxt = route[i+1]
                    d = dist[node][nxt]
                else:
                    d = 0
                writer.writerow([i, stops[node]["name"], stops[node]["lat"], stops[node]["lng"], d])
        print(f"Đã ghi CSV: {args.csv_out}")


if __name__ == "__main__":
    main()