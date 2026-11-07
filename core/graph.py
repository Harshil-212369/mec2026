"""Adapter: Jagan's routing.py (Dijkstra + A*, j/routing branch) behind the engine's router contract.

His load_graph() reads a dataset JSON file. Our input is table rows (JSON, pg_dump or live
Postgres), so we build the SAME graph dict from the rows and call his shortest_path():
    nodes {id: {name, lat, lng}}, edges {id: edge}, adj {id: [(nbr, edge_id, w)]},
    min_w_per_km (A* heuristic), closed {edge ids}
His Route -> {"path", "edges", "minutes", "km"}; his Unavailable -> None (the engine and the
matcher turn that into a "no route ..." reason naming the closed roads).

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
Routing algorithms: Jagan (routing.py).
"""
from __future__ import annotations

import routing as jagan


def build_graph(nodes: list[dict], roads: list[dict]) -> dict:
    g_nodes = {n["node_id"]: {"name": n["name"], "lat": n["lat"], "lng": n["lng"]} for n in nodes}
    adj: dict[int, list] = {nid: [] for nid in g_nodes}
    edges: dict[int, dict] = {}
    for r in roads:
        if r["node_a"] not in g_nodes or r["node_b"] not in g_nodes:
            raise ValueError(f"road {r['road_id']} joins unknown node(s) {r['node_a']}, {r['node_b']}")
        e = {"id": r["road_id"], "a": r["node_a"], "b": r["node_b"], "km": r["distance_km"], "w": r["weight"],
             "street": r["street"], "hwy": r["is_highway"], "terrain": r["terrain"]}
        edges[e["id"]] = e
        adj[e["a"]].append((e["b"], e["id"], e["w"]))
        adj[e["b"]].append((e["a"], e["id"], e["w"]))
    min_w_per_km = min((e["w"] / e["km"] for e in edges.values() if e["km"] > 0), default=1.0)
    closed = {r["road_id"] for r in roads if r["is_closed"]}
    return {"nodes": g_nodes, "edges": edges, "adj": adj, "min_w_per_km": min_w_per_km, "closed": closed}


def router_factory(nodes: list[dict], roads: list[dict], algorithm: str = "astar"):
    graph = build_graph(nodes, roads)

    def route_fn(src: int, dst: int):
        res = jagan.shortest_path(graph, src, dst, algorithm)
        if isinstance(res, jagan.Unavailable):
            return None
        return {"path": res.nodes, "edges": res.edges, "minutes": res.minutes, "km": res.km}
    return route_fn
