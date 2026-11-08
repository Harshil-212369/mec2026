"""R8 bonus: the system runs with no input file, on randomly generated cities of the same structure.
AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil."""
import pytest

from core.engine import Engine
from core.random_dataset import generate
from core.routing import get_router_factory
from core.state import TRANSITIONS
from core.tables import from_data, select_dataset
from core.validate import validate_ticket
from tests.test_engine import _invariants

router, _ = get_router_factory()
SEEDS = range(1, 26)


def test_r8_same_seed_gives_the_same_city():
    assert generate(42) == generate(42)
    assert generate(42) != generate(43)


@pytest.mark.parametrize("seed", SEEDS)
def test_r8_random_city_is_valid_and_fully_reachable(seed):
    ds, sc = generate(seed)
    dsid, t = select_dataset(from_data(ds, sc, f"random:{ds['id']}"))
    requesters = {r["req_id"]: r for r in t["requesters"]}
    assert t["tickets"] and all(validate_ticket(row, requesters) == [] for row in t["tickets"])
    route = router(t["nodes"], t["roads"])
    for s in t["suppliers"]:
        for r in t["requesters"]:
            assert route(s["location_node"], r["location_node"]) is not None, (seed, s["supp_id"], r["req_id"])
    assert len({s["location_node"] for s in t["suppliers"]} | {r["location_node"] for r in t["requesters"]}) \
        == len(t["suppliers"]) + len(t["requesters"])                    # no two places share a node


@pytest.mark.parametrize("seed", SEEDS)
def test_r8_engine_runs_random_city_with_disruptions(seed):
    ds, sc = generate(seed)
    eng = Engine.from_bundle(from_data(ds, sc, f"random:{ds['id']}"), router)
    eng.advance(0)
    for _ in range(240):
        eng.advance(1)
        _invariants(eng)
    for h in eng.sm.history:
        assert h["old_status"] is None or h["new_status"] in TRANSITIONS[h["old_status"]]
    assert len(eng.tickets) == len(sc["tickets"]) and not eng.rejected
    types = {e["event_type"] for e in eng.bus.log}
    assert {"crisis-created", "road-closed", "vehicle-breakdown"} <= types


def test_r8_api_random_city_button():
    from fastapi.testclient import TestClient
    from api.main import app
    with TestClient(app) as c:
        r = c.post("/datasets/random", json={"seed": 7})
        assert r.status_code == 200 and r.json()["dataset_id"] == "random-7"
        s = c.get("/state").json()
        assert s["dataset_id"] == "random-7" and s["map"]["nodes"] and s["tickets"]
        assert c.post("/datasets/random", json={"seed": "x"}).status_code == 400
        assert c.post("/datasets/random", json={}).status_code == 200      # no seed: picks one
