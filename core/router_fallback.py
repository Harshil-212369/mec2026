"""Fallback router: plain Dijkstra on our own MinHeap. Used ONLY while Jagan's core/graph.py
(Dijkstra + A*) is not merged; core/routing.py picks his automatically once it exists.

Reference: E. W. Dijkstra (1959); CLRS ch. 24.3 (lazy-deletion variant: a node may be pushed
more than once, stale pops are skipped). Cost = road weight `w` (travel minutes); closed roads
(is_closed = true) are skipped.

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
"""
from __future__ import annotations

import math

from core.heap import MinHeap


def router_factory(nodes: list[dict], roads: list[dict]):
    adj: dict[int, list[tuple[int, float, float, int]]] = {}
    for r in roads:
        if r["is_closed"]:
            continue
        adj.setdefault(r["node_a"], []).append((r["node_b"], r["weight"], r["distance_km"], r["road_id"]))
        adj.setdefault(r["node_b"], []).append((r["node_a"], r["weight"], r["distance_km"], r["road_id"]))

    def route_fn(src: int, dst: int):
        if src == dst:
            return {"path": [src], "edges": [], "minutes": 0.0, "km": 0.0}
        dist = {src: 0.0}
        prev: dict[int, tuple[int, int, float]] = {}
        done: set[int] = set()
        heap = MinHeap()
        heap.push((0.0, src))
        while len(heap):
            d, u = heap.pop()
            if u in done:
                continue
            done.add(u)
            if u == dst:
                break
            for v, w, km, road_id in adj.get(u, ()):
                nd = d + w
                if nd < dist.get(v, math.inf):
                    dist[v] = nd
                    prev[v] = (u, road_id, km)
                    heap.push((nd, v))
        if dst not in done:
            return None
        path, edges, km, node = [dst], [], 0.0, dst
        while node != src:
            u, road_id, leg_km = prev[node]
            path.append(u)
            edges.append(road_id)
            km += leg_km
            node = u
        return {"path": path[::-1], "edges": edges[::-1], "minutes": dist[dst], "km": km}
    return route_fn
