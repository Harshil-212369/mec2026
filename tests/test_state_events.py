"""R6 state machine and R7 event bus.
AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil."""
from datetime import datetime, timedelta, timezone

import pytest

from core.constants import STATES
from core.events import EventBus
from core.state import TRANSITIONS, IllegalTransition, StateMachine

T0 = datetime(2026, 11, 7, 19, 0, tzinfo=timezone.utc)


def _sm():
    bus = EventBus("toronto-downtown")
    return StateMachine(bus), bus


def test_r6_table_covers_exactly_the_nine_states():
    assert set(TRANSITIONS) == set(STATES)
    assert all(target in STATES for targets in TRANSITIONS.values() for target in targets)


def test_r6_full_lifecycle_records_reason_and_time_and_publishes():
    sm, bus = _sm()
    tk = {"ticket_id": 1, "req_id": "P4"}
    sm.open(tk, T0)
    path = ["Prioritized", "Resource Assigned", "In Progress", "Re-Routing", "In Progress", "Delivered", "Resolved"]
    for i, st in enumerate(path, 1):
        sm.transition(tk, st, f"step {i}", T0 + timedelta(minutes=i))
    assert tk["status"] == "Resolved"
    assert [h["new_status"] for h in sm.history] == ["Open"] + path
    assert all(h["reason"] and h["changed_at"].tzinfo for h in sm.history)
    types = [e["event_type"] for e in bus.log]
    assert types[0] == "crisis-created" and types[-1] == "crisis-resolved"


def test_r6_illegal_transition_raises_and_changes_nothing():
    sm, _ = _sm()
    tk = {"ticket_id": 2, "req_id": "P5"}
    sm.open(tk, T0)
    with pytest.raises(IllegalTransition, match="Open -> Delivered"):
        sm.transition(tk, "Delivered", "skip ahead", T0)
    assert tk["status"] == "Open" and len(sm.history) == 1


def test_r6_reroute_is_not_reachable_without_being_in_progress():
    sm, _ = _sm()
    tk = {"ticket_id": 3, "req_id": "P5"}
    sm.open(tk, T0)
    sm.transition(tk, "Prioritized", "scored", T0)
    with pytest.raises(IllegalTransition):
        sm.transition(tk, "Re-Routing", "road closed", T0)


def test_r6_every_change_needs_a_reason():
    sm, _ = _sm()
    tk = {"ticket_id": 4, "req_id": "P5"}
    sm.open(tk, T0)
    with pytest.raises(ValueError):
        sm.transition(tk, "Prioritized", "  ", T0)


def test_r7_subscribers_wildcard_unknown_topic_and_broken_subscriber():
    bus = EventBus("toronto-downtown")
    got, everything = [], []
    bus.subscribe("road-closed", got.append)
    bus.subscribe("*", everything.append)

    def broken(_row):
        raise RuntimeError("socket closed")
    bus.subscribe("road-closed", broken)
    row = bus.publish("road-closed", {"edge_id": 9}, T0)
    bus.publish("vehicle-breakdown", {"vehicle_id": "V2"}, T0)
    assert got == [row] and len(everything) == 2
    assert row == {"dataset_id": "toronto-downtown", "event_type": "road-closed",
                   "details": {"edge_id": 9}, "created_at": T0}
    assert bus.subscriber_errors == [("road-closed", "RuntimeError: socket closed")]
    with pytest.raises(ValueError):
        bus.publish("road.closed", {}, T0)
