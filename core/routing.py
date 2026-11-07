"""Pick the router: Jagan's core/graph.py if present, else our fallback Dijkstra.

Contract for core/graph.py: router_factory(nodes, roads) -> route_fn(src, dst) returning
{"path": [node ids], "edges": [road ids], "minutes": float, "km": float} or None (no path),
skipping roads whose is_closed is true.

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
"""
from __future__ import annotations

import importlib


def get_router_factory():
    try:
        graph = importlib.import_module("core.graph")
    except ModuleNotFoundError as exc:
        if exc.name != "core.graph":
            raise   # core.graph exists but one of ITS imports is missing: fail loudly
        from core.router_fallback import router_factory
        return router_factory, "core.router_fallback (Dijkstra on our MinHeap)"
    if not hasattr(graph, "router_factory"):
        raise ImportError("core/graph.py must define router_factory(nodes, roads) -> route_fn")
    return graph.router_factory, "core.graph"
