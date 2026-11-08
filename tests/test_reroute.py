# test_reroute.py - spec for reroute.py (step 6)
# Author: Jagan (team H/A/J). AI assistance: Claude (Anthropic) generated these tests.
#
# Run:  .venv\Scripts\python -m pytest tests -k step6 -q

from pathlib import Path

import pytest

import constants as C
import reroute as RR
import routing as R

DATA = Path(__file__).resolve().parents[1] / "data" / "toronto-downtown.json"


@pytest.fixture
def g():
    return R.load_graph(DATA)


def active(g, tid, current, stops):
    """Build an active trip from today's routes."""
    route = RR.plan_remaining(g, current, stops)
    return {"id": tid, "current_node": current, "stops": stops, "edges": route.edges}, route


def test_step6_plan_remaining_single_stop_matches_shortest_path(g):
    r = RR.plan_remaining(g, 33, [22])
    assert r.minutes == pytest.approx(R.shortest_path(g, 33, 22).minutes)
    assert r.nodes[0] == 33 and r.nodes[-1] == 22


def test_step6_plan_remaining_chains_stops(g):
    r = RR.plan_remaining(g, 33, [34, 22])
    expected = R.shortest_path(g, 33, 34).minutes + R.shortest_path(g, 34, 22).minutes
    assert r.minutes == pytest.approx(expected)
    assert len(r.edges) == len(r.nodes) - 1          # no duplicated nodes at the joins
    assert 34 in r.nodes and r.nodes[-1] == 22


def test_step6_affected_trip_is_rerouted(g):
    trip, old = active(g, "V2", 33, [22])
    closed = old.edges[2]
    out = RR.handle_road_closed(g, [trip], closed)
    new = out["V2"]
    assert isinstance(new, R.Route)
    assert closed not in new.edges
    assert new.nodes[0] == 33 and new.nodes[-1] == 22
    assert new.minutes >= old.minutes - 1e-9          # a detour is never faster


def test_step6_unaffected_trip_left_alone(g):
    trip, old = active(g, "V2", 33, [22])
    unused = next(e for e in g["edges"] if e not in old.edges)
    out = RR.handle_road_closed(g, [trip], unused)
    assert out == {}
    assert unused in g["closed"]                      # the road is still closed


def test_step6_only_affected_trips_returned(g):
    t1, r1 = active(g, "V1", 33, [22])
    t2, r2 = active(g, "V2", 0, [7])
    shared = set(r1.edges) & set(r2.edges)
    closed = next(e for e in r1.edges if e not in shared)
    out = RR.handle_road_closed(g, [t1, t2], closed)
    assert set(out) == {"V1"}


def test_step6_reroute_failed_explains(g):
    trip, _ = active(g, "V2", 33, [47])
    RR.handle_road_closed(g, [trip], 74)
    out = RR.handle_road_closed(g, [trip], 81)        # node 47 now cut off
    r = out["V2"]
    assert isinstance(r, R.Unavailable) and r.code == C.REROUTE_FAILED
    assert r.details["unreachable_stop"] == 47
    assert "Parliament St & Bloor St" in r.message
