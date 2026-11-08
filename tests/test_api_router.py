"""R4 fallback Dijkstra vs networkx on every node pair; R1/R4/R7 API + WebSocket.
AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil."""
import math

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from core.router_fallback import router_factory
from core.tables import from_json, select_dataset
from tests.conftest import DATA


@pytest.mark.parametrize("ds", ["toronto-downtown.json", "synthetic-town-on.json", "synthetic-town-intl.json"])
def test_r4_fallback_dijkstra_matches_networkx_on_every_pair(ds):
    _, t = select_dataset(from_json(DATA / ds))
    g = nx.Graph()
    for r in t["roads"]:
        g.add_edge(r["node_a"], r["node_b"], weight=r["weight"])
    truth = dict(nx.all_pairs_dijkstra_path_length(g, weight="weight"))
    route = router_factory(t["nodes"], t["roads"])
    roads = {r["road_id"]: r for r in t["roads"]}
    for a in g.nodes:
        for b in g.nodes:
            r = route(a, b)
            assert math.isclose(r["minutes"], truth[a][b], abs_tol=1e-9), (a, b)
            assert math.isclose(sum(roads[e]["weight"] for e in r["edges"]), r["minutes"], abs_tol=1e-9)
            assert r["path"][0] == a and r["path"][-1] == b and len(r["edges"]) == len(r["path"]) - 1


@pytest.mark.parametrize("ds", ["toronto-downtown.json", "synthetic-town-on.json", "synthetic-town-intl.json"])
@pytest.mark.parametrize("closed", [set(), {24, 26}, {6, 9, 12}])
def test_r4_production_router_jagan_astar_matches_networkx(ds, closed):
    from core.routing import get_router_factory
    factory, name = get_router_factory()
    assert "Jagan" in name                                     # the merged routing.py is in use
    _, t = select_dataset(from_json(DATA / ds))
    for r in t["roads"]:
        r["is_closed"] = r["road_id"] in closed
    g = nx.Graph()
    g.add_nodes_from(n["node_id"] for n in t["nodes"])
    for r in t["roads"]:
        if not r["is_closed"]:
            g.add_edge(r["node_a"], r["node_b"], weight=r["weight"])
    truth = dict(nx.all_pairs_dijkstra_path_length(g, weight="weight"))
    route = factory(t["nodes"], t["roads"])
    roads = {r["road_id"]: r for r in t["roads"]}
    for a in g.nodes:
        for b in g.nodes:
            r = route(a, b)
            if b not in truth[a]:
                assert r is None, (a, b)
                continue
            assert math.isclose(r["minutes"], truth[a][b], abs_tol=1e-9), (ds, closed, a, b)
            assert not set(r["edges"]) & closed
            assert math.isclose(sum(roads[e]["distance_km"] for e in r["edges"]), r["km"], abs_tol=1e-9)


def test_r4_fallback_respects_closed_bridge():
    _, t = select_dataset(from_json(DATA / "synthetic-town-on.json"))
    for r in t["roads"]:
        if r["road_id"] == 24:
            r["is_closed"] = True
    assert router_factory(t["nodes"], t["roads"])(5, 18) is None


@pytest.fixture
def client():
    from api.main import STATE, app, load
    with TestClient(app) as c:
        load({"source": "json", "path": "data/toronto-downtown.json", "scenario": "data/scenario-toronto.json"})
        yield c
        STATE.running = False


def test_r7_state_lists_map_queue_and_fleet(client):
    s = client.get("/state").json()
    assert len(s["vehicles"]) == 12 and len(s["map"]["roads"]) == 82
    assert s["ranking"] == [] or isinstance(s["ranking"][0], int)
    assert {t["ticket_id"] for t in s["tickets"]} == {1, 2}           # t=0 scenario tickets submitted


def test_r1_api_rejects_invalid_ticket_with_field_errors(client):
    r = client.post("/tickets", json={"req_id": "P4", "crisis_type": "food_shortage", "servings_requested": 10,
                                      "people_affected": 5, "severity": 9, "refrigerated": "maybe", "deadline_min": 30})
    assert r.status_code == 422
    assert {e["field"] for e in r.json()["errors"]} == {"severity", "refrigerated"}


def test_r1_api_accepts_valid_ticket_and_dispatches_it(client):
    r = client.post("/tickets", json={"req_id": "P6", "crisis_type": "food_shortage", "servings_requested": 20,
                                      "people_affected": 15, "severity": 3, "refrigerated": False, "deadline_min": 60})
    assert r.status_code == 201
    tid = r.json()["ticket_id"]
    hist = client.get(f"/tickets/{tid}/history").json()
    assert [h["new_status"] for h in hist][:4] == ["Open", "Prioritized", "Resource Assigned", "In Progress"]


def test_r7_websocket_pushes_road_closed_and_reroute(client):
    with client.websocket_connect("/ws") as ws:
        client.post("/sim/step", json={"minutes": 3})
        client.post("/roads/9/close")
        seen = []
        while "road-closed" not in seen:
            seen.append(ws.receive_json()["type"])
    assert "road-closed" in seen
    assert 9 in client.get("/state").json()["closed_roads"]


def test_r8_unknown_road_and_vehicle_are_404(client):
    assert client.post("/roads/999/close").status_code == 404
    assert client.post("/vehicles/V99/breakdown").status_code == 404


def test_r8_switch_dataset_without_restart(client):
    r = client.post("/datasets/load", json={"source": "json", "path": "data/synthetic-town-on.json",
                                            "scenario": "data/scenario-town.json"})
    assert r.status_code == 200 and r.json()["dataset_id"] == "synthetic-town-on"
    assert len(client.get("/state").json()["vehicles"]) == 4
