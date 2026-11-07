# test_dispatcher.py - spec for dispatcher.py (offline, no database)
# Author: Jagan (team H/A/J). AI assistance: Claude (Anthropic) generated these tests.
#
# Run:  .venv\Scripts\python -m pytest tests -k dispatch -q

from pathlib import Path

import pytest

import dispatcher as D
import routing as R

DATA = Path(__file__).resolve().parents[1] / "data" / "toronto-downtown.json"


@pytest.fixture
def world():
    g = R.load_graph(DATA)
    suppliers, vehicles, _ = D.load_offline(DATA, Path(__file__).resolve().parents[1] / "data" / "demo_tickets.json")
    return g, suppliers, vehicles


def ticket(tid, node, servings, deadline, cold=False, score=1.0, created="2026-11-07T15:00"):
    return {"ticket_id": tid, "node": node, "servings": servings, "refrigerated": cold,
            "deadline_min": deadline, "priority_score": score, "created_at": created, "status": "Open"}


def test_dispatch_big_cold_ticket_is_split_across_reefers(world):
    g, s, v = world
    out = D.dispatch(g, [ticket(2, 22, 125, 75, cold=True)], v, s)
    assert [a["servings"] for a in out["assignments"]] == [40, 40, 40]
    assert len({a["vehicle_id"] for a in out["assignments"]}) == 3      # never the same truck twice
    assert out["changes"][-1][2] == "Resource Assigned"
    assert "5 still waiting" in out["changes"][-1][3]


def test_dispatch_past_deadline_fails_with_reason(world):
    g, s, v = world
    out = D.dispatch(g, [ticket(1, 34, 28, -30)], v, s)
    assert out["assignments"] == []
    assert out["changes"][-1][2] == "Failed"
    assert "DEADLINE_UNREACHABLE" in out["changes"][-1][3]


def test_dispatch_no_vehicle_means_delayed(world):
    g, s, _ = world
    out = D.dispatch(g, [ticket(5, 22, 10, 60, cold=True)], [], s)
    assert out["changes"][-1][2] == "Delayed"
    assert "NO_SUITABLE_VEHICLE" in out["changes"][-1][3]


def test_dispatch_higher_priority_served_first(world):
    g, s, v = world
    out = D.dispatch(g, [ticket(7, 22, 10, 60, score=1.0), ticket(8, 44, 10, 60, score=9.0)], v, s)
    assert out["assignments"][0]["ticket_id"] == 8


def test_dispatch_equal_priority_older_first(world):
    g, s, v = world
    out = D.dispatch(g, [ticket(7, 22, 10, 60, created="2026-11-07T15:30"),
                         ticket(8, 44, 10, 60, created="2026-11-07T15:00")], v, s)
    assert out["assignments"][0]["ticket_id"] == 8


def test_invalid_transition_rejected():
    D.check_transition("Open", "Prioritized")
    with pytest.raises(ValueError):
        D.check_transition("Open", "Delivered")
