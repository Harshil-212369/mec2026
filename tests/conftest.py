"""Shared fixtures. Test names cite the statement's requirement bullets:
R1 crisis submission/validation, R2 priority scoring, R3 heap priority queue, R4 route planning,
R5 greedy resource matching, R6 state machine, R7 event bus, R8 same code on any dataset/source.

networkx is used ONLY in tests, as an independent reference to check routes against
(the engine itself must not use a library shortest path).

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import networkx as nx
import pytest

from core.tables import from_json, from_pg_dump, select_dataset

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))  # from j/routing: top-level modules (routing.py, ...) importable
DATA = REPO / "data"
AADIL_DUMP = REPO / "tests" / "fixtures" / "aadil_dump_2026-11-07.sql"


def make_route_fn(roads: list[dict], closed: set[int] = frozenset()):
    g = nx.Graph()
    for r in roads:
        if r["is_closed"] or r["road_id"] in closed:
            continue
        g.add_edge(r["node_a"], r["node_b"], weight=r["weight"], km=r["distance_km"], road_id=r["road_id"])

    def route_fn(a: int, b: int):
        if a not in g or b not in g:
            return None
        try:
            path = nx.shortest_path(g, a, b, weight="weight")
        except nx.NetworkXNoPath:
            return None
        legs = [g[u][v] for u, v in zip(path, path[1:])]
        return {"path": path, "edges": [e["road_id"] for e in legs],
                "minutes": sum(e["weight"] for e in legs), "km": sum(e["km"] for e in legs)}
    return route_fn


@pytest.fixture
def toronto():
    """(tables, bundle) for Toronto + scenario-toronto, fresh copy per test."""
    bundle = from_json(DATA / "toronto-downtown.json", DATA / "scenario-toronto.json")
    return select_dataset(bundle)[1], bundle


@pytest.fixture
def town():
    bundle = from_json(DATA / "synthetic-town-on.json", DATA / "scenario-town.json")
    return select_dataset(bundle)[1], bundle


@pytest.fixture
def aadil():
    bundle = from_pg_dump(AADIL_DUMP)
    return select_dataset(bundle)[1], bundle


@pytest.fixture
def deep():
    return copy.deepcopy
