# test_trip_planner.py - spec for trip_planner.py (step 5)
# Author: Jagan (team H/A/J). AI assistance: Claude (Anthropic) generated these
# tests; reference values were computed from data/toronto-downtown.json.
#
# Run:  .venv\Scripts\python -m pytest tests -k step5 -q

from pathlib import Path

import pytest

import constants as C
import routing as R
import trip_planner as TP

DATA = Path(__file__).resolve().parents[1] / "data" / "toronto-downtown.json"
TRUCK = {"id": "V2", "capacity": 60, "refrigerated": False}
REEFER = {"id": "V1", "capacity": 40, "refrigerated": True}


@pytest.fixture
def g():
    return R.load_graph(DATA)


def stop(tid, node, deadline, servings=10, cold=False):
    return {"id": tid, "node": node, "servings": servings,
            "refrigerated": cold, "deadline_min": deadline}


def test_step5_single_stop(g):
    # hub node 33 -> node 22 is 8.3242 min; + 5 unload + 10 min buffer
    t = TP.plan_trip(g, 33, 33, [stop("T1", 22, 60)], TRUCK)
    assert isinstance(t, TP.Trip)
    assert t.order == ["T1"]
    assert t.total_minutes == pytest.approx(8.3242, abs=1e-3)
    assert t.etas["T1"] == pytest.approx(R.planned_eta_minutes(8.3242), abs=1e-3)


def test_step5_drives_to_supplier_first(g):
    # truck starts at node 8, picks up at 33, then delivers to 22
    t = TP.plan_trip(g, 8, 33, [stop("T1", 22, 60)], TRUCK)
    assert t.legs[0].nodes[0] == 8 and t.legs[0].nodes[-1] == 33
    assert t.total_minutes == pytest.approx(13.9595, abs=1e-3)


def test_step5_picks_fastest_order(g):
    # node 34 is on the way to 22, so A (34) then B (22) is fastest
    t = TP.plan_trip(g, 33, 33, [stop("B", 22, 60), stop("A", 34, 60)], TRUCK)
    assert t.order == ["A", "B"]
    assert t.total_minutes == pytest.approx(8.3242, abs=1e-3)


def test_step5_deadline_changes_order(g):
    # B's deadline is tight: B must go first even though the total is longer
    t = TP.plan_trip(g, 33, 33, [stop("A", 34, 60), stop("B", 22, 24)], TRUCK)
    assert t.order == ["B", "A"]
    assert t.etas["B"] <= 24


def test_step5_capacity(g):
    r = TP.plan_trip(g, 33, 33, [stop("A", 34, 60, servings=40),
                                 stop("B", 22, 60, servings=30)], TRUCK)
    assert isinstance(r, R.Unavailable) and r.code == C.NO_SUITABLE_VEHICLE
    assert r.details == {"capacity": 60, "needed": 70}


def test_step5_capacity_exactly_full_is_ok(g):
    t = TP.plan_trip(g, 33, 33, [stop("A", 34, 60, servings=60)], TRUCK)
    assert isinstance(t, TP.Trip)


def test_step5_refrigeration(g):
    cold = [stop("A", 34, 60, cold=True)]
    assert TP.plan_trip(g, 33, 33, cold, TRUCK).code == C.NO_SUITABLE_VEHICLE
    assert isinstance(TP.plan_trip(g, 33, 33, cold, REEFER), TP.Trip)


def test_step5_missed_deadline_explains_closest(g):
    r = TP.plan_trip(g, 33, 33, [stop("T1", 22, 15)], TRUCK)
    assert isinstance(r, R.Unavailable) and r.code == C.DEADLINE_UNREACHABLE
    assert r.details["best_order"] == ["T1"]
    assert r.details["minutes_late"] == pytest.approx(
        R.planned_eta_minutes(8.3242) - 15, abs=0.1)


def test_step5_closest_miss_is_least_late_order(g):
    # B needs to arrive by 20: impossible either way, but B-first is less late
    r = TP.plan_trip(g, 33, 33, [stop("A", 34, 60), stop("B", 22, 20)], TRUCK)
    assert r.code == C.DEADLINE_UNREACHABLE
    assert r.details["best_order"] == ["B", "A"]


def test_step5_unreachable_stop(g):
    R.close_road(g, 74)
    R.close_road(g, 81)   # node 47 cut off
    r = TP.plan_trip(g, 33, 33, [stop("T1", 47, 60)], TRUCK)
    assert isinstance(r, R.Unavailable) and r.code == C.NO_ROUTE


def test_step5_too_many_stops(g):
    stops = [stop(f"T{i}", 22, 60, servings=1) for i in range(C.MAX_STOPS + 1)]
    with pytest.raises(ValueError):
        TP.plan_trip(g, 33, 33, stops, TRUCK)
