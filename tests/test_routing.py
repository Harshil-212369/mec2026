# test_routing.py - spec for routing.py, step by step
# Author: Jagan (team H/A/J). AI assistance: Claude (Anthropic) generated these
# tests; reference values were computed from data/toronto-downtown.json.
#
# Run one step at a time:   .venv\Scripts\python -m pytest tests -k step1 -q
# Costs are compared, not exact paths: the grid has equal-cost ties.

import copy
import itertools
import json
from pathlib import Path

import pytest

import constants as C
import routing as R

DATA = Path(__file__).resolve().parents[1] / "data" / "toronto-downtown.json"


@pytest.fixture
def g():
    return R.load_graph(DATA)


def path_cost(g, edge_path):
    return sum(g["edges"][e]["w"] for e in edge_path)


# ---------------- step 1: loading ----------------
def test_step1_counts(g):
    assert len(g["nodes"]) == 48
    assert len(g["edges"]) == 82


def test_step1_two_way(g):
    assert {(v, e) for v, e, _ in g["adj"][0]} == {(1, 0), (8, 1)}
    assert any(v == 0 and e == 0 for v, e, _ in g["adj"][1])  # reverse direction


def test_step1_min_w_per_km(g):
    assert g["min_w_per_km"] == pytest.approx(2.4, abs=0.01)
    assert g["closed"] == set()


# ---------------- step 2: Dijkstra ----------------
def test_step2_known_costs(g):
    cost, nodes, edges, _ = R.dijkstra(g, 0, 47)
    assert cost == pytest.approx(17.4794, abs=1e-3)
    assert nodes[0] == 0 and nodes[-1] == 47
    assert len(edges) == len(nodes) - 1
    assert path_cost(g, edges) == pytest.approx(cost)
    assert R.dijkstra(g, 33, 22)[0] == pytest.approx(8.3242, abs=1e-3)


def test_step2_same_node(g):
    cost, nodes, edges, _ = R.dijkstra(g, 5, 5)
    assert cost == 0 and nodes == [5] and edges == []


def test_step2_closed_edge_avoided(g):
    g["closed"].add(1)
    cost, _, edges, _ = R.dijkstra(g, 0, 47)
    assert 1 not in edges
    assert cost == pytest.approx(17.4804, abs=1e-3)


def test_step2_unreachable_returns_none(g):
    g["closed"].update({74, 81})  # the only two roads into node 47
    assert R.dijkstra(g, 0, 47) is None


# ---------------- step 3: A* ----------------
def test_step3_haversine():
    # 1 degree of latitude is ~111.19 km
    assert R.haversine_km(43.0, -79.0, 44.0, -79.0) == pytest.approx(111.19, abs=0.1)


def test_step3_heuristic_admissible(g):
    # h must never exceed the true shortest cost (otherwise A* can be wrong)
    for dst in (0, 22, 47):
        for n in g["nodes"]:
            true = R.dijkstra(g, n, dst)[0]
            assert R.heuristic(g, n, dst) <= true + 1e-9


def test_step3_astar_equals_dijkstra_all_pairs(g):
    for s, t in itertools.product(g["nodes"], repeat=2):
        d = R.dijkstra(g, s, t)
        a = R.astar(g, s, t)
        assert a[0] == pytest.approx(d[0], abs=1e-9), (s, t)


def test_step3_astar_expands_fewer_overall(g):
    tot_d = tot_a = 0
    for s, t in itertools.product(g["nodes"], repeat=2):
        tot_d += R.dijkstra(g, s, t)[3]
        tot_a += R.astar(g, s, t)[3]
    assert tot_a < tot_d


def test_step3_astar_respects_closures(g):
    g["closed"].update({74, 81})
    assert R.astar(g, 0, 47) is None


# ---------------- step 4: API, ETA, closures ----------------
def test_step4_route_object(g):
    r = R.shortest_path(g, 0, 47)
    assert isinstance(r, R.Route)
    assert r.minutes == pytest.approx(17.4794, abs=1e-3)
    assert r.km == pytest.approx(sum(g["edges"][e]["km"] for e in r.edges))


def test_step4_unavailable_explains(g):
    R.close_road(g, 74)
    R.close_road(g, 81)
    r = R.shortest_path(g, 0, 47)
    assert isinstance(r, R.Unavailable)
    assert r.code == C.NO_ROUTE
    assert r.details["closed_edges"] == [74, 81]
    assert "Parliament St & Bloor St" in r.message


def test_step4_unknown_node_is_unavailable(g):
    assert isinstance(R.shortest_path(g, 0, 9999), R.Unavailable)


def test_step4_reopen(g):
    R.close_road(g, 1)
    R.reopen_road(g, 1)
    R.reopen_road(g, 1)  # second reopen must not crash
    assert R.shortest_path(g, 0, 47).minutes == pytest.approx(17.4794, abs=1e-3)


def test_step4_eta_buffer():
    # travel + stops * service time + max(minimum buffer, 20% of travel)
    # 20 min trip: 20 + 5 + max(10, 4) = 35  (minimum buffer applies)
    assert R.planned_eta_minutes(20) == pytest.approx(
        20 + C.SERVICE_TIME_MIN + max(C.MIN_BUFFER_MIN, C.BUFFER_PCT * 20))
    # 100 min trip: 20% of travel is bigger than the minimum
    assert R.planned_eta_minutes(100) == pytest.approx(
        100 + C.SERVICE_TIME_MIN + C.BUFFER_PCT * 100)
    # two stops add two unloading times
    assert R.planned_eta_minutes(20, stops=2) - R.planned_eta_minutes(20) == pytest.approx(
        C.SERVICE_TIME_MIN)


def test_step4_works_on_modified_dataset(tmp_path):
    # Stand-in for Dataset 2: different speeds, a highway, a removed hub.
    d = json.loads(DATA.read_text(encoding="utf-8"))
    d = copy.deepcopy(d)
    for e in d["edges"][:10]:
        e["hwy"] = True
        e["terrain"] = "rural"
        e["w"] = e["km"] * 0.8
    d["hubs"] = d["hubs"][:2]
    p = tmp_path / "other.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    g2 = R.load_graph(p)
    assert g2["min_w_per_km"] == pytest.approx(0.8, abs=0.01)
    for s, t in [(0, 47), (7, 40), (33, 22)]:
        assert R.astar(g2, s, t)[0] == pytest.approx(R.dijkstra(g2, s, t)[0], abs=1e-9)
