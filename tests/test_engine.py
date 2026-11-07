"""Engine loop: R4 closures/rerouting, R5 no double booking, R6 state machine under
disruptions, R7 events, R8 same engine on Toronto, the town and Aadil's database.
Router = networkx stand-in until Jagan's Dijkstra lands.

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil."""
from datetime import timedelta

from core.engine import Engine
from core.state import TRANSITIONS
from core.tables import from_json, from_pg_dump
from tests.conftest import AADIL_DUMP, DATA, make_route_fn


def router(nodes, roads):
    return make_route_fn(roads)


def _engine(dataset, scenario=None):
    return Engine.from_bundle(from_json(DATA / dataset, DATA / scenario if scenario else None), router)


def _invariants(eng):
    active = [d for d in eng.deliveries if d.status in ("In Progress", "Delayed")]
    trucks = [d.vehicle_id for d in active]
    assert len(trucks) == len(set(trucks)), "a truck is on two jobs"
    assert all(eng._veh[v]["status"] == "Delivering" for v in trucks)
    for s in eng.suppliers:
        assert 0 <= s["reserved_normal"] <= s["normal_stock"], s
        assert 0 <= s["reserved_cold"] <= s["cold_stock"], s
    assert all(eng.remaining(tid) >= 0 for tid in eng.tickets)
    assert all(v["fuel"] >= 0 for v in eng.vehicles)


def _run_checked(eng, minutes):
    eng.advance(0)
    _invariants(eng)
    for _ in range(int(minutes)):
        eng.advance(1)
        _invariants(eng)


def _history(eng, tid):
    return [h for h in eng.sm.history if h["ticket_id"] == tid]


def _ticket_row(eng, req_id, servings, cold=False, severity=4, deadline_min=90):
    return {"req_id": req_id, "crisis_type": "food_shortage", "servings_requested": servings,
            "people_affected": 50, "severity": severity, "refrigerated": cold,
            "created_at": eng.now, "deadline": eng.now + timedelta(minutes=deadline_min)}


def test_r6_toronto_scenario_matches_acceptance_demo():
    eng = _engine("toronto-downtown.json", "scenario-toronto.json")
    _run_checked(eng, 240)
    assigned = [h for h in eng.sm.history if h["new_status"] == "Resource Assigned"]
    assert assigned[0]["ticket_id"] == 1                                   # P4 is served first
    cold = [d for d in eng.deliveries if d.ticket_id == 2]
    assert [d.servings for d in cold] == [40, 30]
    assert all(eng._veh[d.vehicle_id]["refrigerated"] for d in cold)      # split across two reefers
    reroutes = [h for h in eng.sm.history if h["new_status"] == "Re-Routing"]
    assert reroutes and all("road 9 " in h["reason"] or "road 6 " in h["reason"] for h in reroutes)
    assert any("V2 broke down" in h["reason"] for h in _history(eng, 4))
    types = [e["event_type"] for e in eng.bus.log]
    assert {"crisis-created", "priority-changed", "route-updated", "resource-depleted",
            "road-closed", "vehicle-breakdown", "crisis-resolved"} <= set(types)   # all 7 required events
    status = {tid: t["status"] for tid, t in eng.tickets.items()}
    assert status == {1: "Resolved", 2: "Resolved", 3: "Resolved", 4: "Resolved", 5: "Resolved", 6: "Delayed"}
    assert eng.meta[6]["delivered"] == 230 and eng.meta[2]["delivered"] + 230 == 300   # every cold serving used


def test_r6_every_recorded_transition_is_legal():
    for ds, sc in (("toronto-downtown.json", "scenario-toronto.json"), ("synthetic-town-on.json", "scenario-town.json")):
        eng = _engine(ds, sc)
        eng.run_for(240)
        for h in eng.sm.history:
            if h["old_status"] is None:
                assert h["new_status"] == "Open"
            else:
                assert h["new_status"] in TRANSITIONS[h["old_status"]], h
            assert h["reason"].strip() and h["changed_at"].tzinfo is not None


def test_r4_only_deliveries_using_the_closed_road_are_rerouted():
    eng = _engine("toronto-downtown.json")
    eng.submit(_ticket_row(eng, "P5", 50), eng.now)
    eng.advance(0)
    d = eng.deliveries[0]
    off_route = next(r["road_id"] for r in eng.t["roads"] if r["road_id"] not in d.remaining_edges())
    eng.close_road(off_route, eng.now)
    assert not any(h["new_status"] == "Re-Routing" for h in eng.sm.history)
    eng.advance(12)
    on_route = d.remaining_edges()[-1]
    eng.close_road(on_route, eng.now)
    statuses = [h["new_status"] for h in _history(eng, d.ticket_id)]
    assert statuses[-2:] == ["Re-Routing", "In Progress"]
    assert on_route not in d.remaining_edges()
    eng.run_for(60)
    assert eng.tickets[d.ticket_id]["status"] == "Resolved"


def test_r4_bridge_closure_gives_no_route_reason_then_reopen_resolves():
    eng = _engine("synthetic-town-on.json", "scenario-town.json")
    _run_checked(eng, 240)
    hist = _history(eng, 1)                                                # P3 behind bridge 24
    delayed = [h for h in hist if h["new_status"] == "Delayed"]
    assert "no route to P3" in delayed[0]["reason"] and "24" in delayed[0]["reason"]
    assert any("reopened" in h["reason"] for h in hist)
    assert eng.tickets[1]["status"] == "Resolved"


def test_r4_unreachable_ticket_fails_after_deadline_plus_grace():
    eng = _engine("synthetic-town-on.json")
    eng.close_road(24, eng.now)
    eng.submit(_ticket_row(eng, "P3", 20, deadline_min=40), eng.now)
    eng.run_for(120)
    t = next(iter(eng.tickets.values()))
    assert t["status"] == "Failed"
    assert any("no route" in h["reason"] for h in _history(eng, t["ticket_id"]))


def test_r6_breakdown_after_pickup_sends_rescue_to_breakdown_node():
    eng = _engine("toronto-downtown.json")
    eng.submit(_ticket_row(eng, "P6", 40), eng.now)
    eng.advance(0)
    d = eng.deliveries[0]
    eng.advance(14)                                                         # loaded, one road past the hub
    assert d.picked_up and eng._veh[d.vehicle_id]["current_node"] != d.supplier_node
    eng.breakdown(d.vehicle_id, eng.now)
    assert any(s.get("temporary") for s in eng.suppliers)
    eng.advance(1)
    rescue = eng.deliveries[-1]
    assert rescue.vehicle_id != d.vehicle_id and rescue.supp_id.startswith(f"{d.vehicle_id}-cargo")
    eng.run_for(90)
    t = eng.tickets[d.ticket_id]
    assert t["status"] == "Resolved" and eng.meta[t["ticket_id"]]["delivered"] == 40
    assert not any(s.get("temporary") for s in eng.suppliers)               # pickup point used up


def test_bug1_partly_served_ticket_gets_the_next_free_truck():
    eng = _engine("toronto-downtown.json")
    eng.breakdown("V5", eng.now)
    eng.breakdown("V9", eng.now)                                            # only reefer V1 left
    eng.submit(_ticket_row(eng, "P3", 80, cold=True, severity=5), eng.now)
    eng.advance(0)
    tid = eng.deliveries[0].ticket_id
    assert len(eng.deliveries) == 1 and eng.remaining(tid) == 40
    eng.repair("V5", eng.now)
    eng.advance(1)
    assert [d.vehicle_id for d in eng.deliveries if d.ticket_id == tid] == ["V1", "V5"]
    assert eng.tickets[tid]["status"] == "In Progress"
    assert sum(h["new_status"] == "Resource Assigned" for h in _history(eng, tid)) == 1


def test_bug2_reefer_is_not_spent_on_normal_food_while_cold_food_waits():
    eng = _engine("synthetic-town-on.json", "scenario-town.json")
    eng.run_for(60)
    second = [h for h in _history(eng, 2) if h["new_status"] == "Resource Assigned"][1]
    assert (second["changed_at"] - eng.start) == timedelta(minutes=22)       # V1 goes straight back to cold P2


def test_r8_aadil_database_ticket_rejected_until_severity_exists_then_resolved():
    eng = Engine.from_bundle(from_pg_dump(AADIL_DUMP), router)
    eng.run_for(1)
    assert [f for f, _ in eng.rejected[0][1]] == ["severity"] and eng.sm.history == []

    bundle = from_pg_dump(AADIL_DUMP)
    bundle.tables["tickets"][0]["severity"] = 4                              # what Aadil's column would hold
    eng = Engine.from_bundle(bundle, router)
    _run_checked(eng, 120)
    assert eng.tickets[1]["status"] == "Resolved" and eng.meta[1]["delivered"] == 28


def test_r8_engine_never_modifies_the_input_bundle():
    bundle = from_json(DATA / "toronto-downtown.json", DATA / "scenario-toronto.json")
    before = repr(bundle.tables)
    Engine.from_bundle(bundle, router).run_for(60)
    assert repr(bundle.tables) == before


def test_r7_snapshot_is_json_serialisable():
    import json
    eng = _engine("toronto-downtown.json", "scenario-toronto.json")
    eng.run_for(30)
    snap = json.loads(json.dumps(eng.snapshot()))
    assert snap["ranking"] == [t for t in snap["ranking"]] and len(snap["vehicles"]) == 12
    assert {t["status"] for t in snap["tickets"]} <= set(TRANSITIONS)
