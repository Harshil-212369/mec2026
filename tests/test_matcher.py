"""R5 greedy resource matching (with a networkx stand-in for routing; R4 closures).
AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil."""
from core.matcher import assign
from tests.conftest import make_route_fn


def _node(t, req_id):
    return {r["req_id"]: r for r in t["requesters"]}[req_id]["location_node"]


def _run(t, ticket, closed=frozenset()):
    return assign(ticket, _node(t, ticket["req_id"]), ticket["servings_requested"],
                  t["suppliers"], t["vehicles"], make_route_fn(t["roads"], set(closed)))


def _vehicle(t, vid):
    return next(v for v in t["vehicles"] if v["vehicle_id"] == vid)


def test_r5_cold_70_at_p3_is_split_across_two_reefers(toronto):
    t, _ = toronto
    res = _run(t, t["tickets"][1])                      # P3, 70 cold, reefers carry 40
    assert res.remaining == 0 and res.reason is None
    assert [a.servings_assigned for a in res.assignments] == [40, 30]
    assert all(_vehicle(t, a.vehicle_id)["refrigerated"] for a in res.assignments)
    assert res.assignments[0].vehicle_id == "V1"        # V1 waits at P0, one road from P3
    assert sum(s["reserved_cold"] for s in t["suppliers"]) == 70


def test_r5_normal_food_leaves_reefers_free(toronto):
    t, _ = toronto
    res = _run(t, t["tickets"][0])                      # P4, 150 normal
    assert res.remaining == 0
    assert not any(_vehicle(t, a.vehicle_id)["refrigerated"] for a in res.assignments)


def test_r5_no_vehicle_or_servings_assigned_twice(toronto):
    t, _ = toronto
    first = _run(t, t["tickets"][0])
    second = _run(t, t["tickets"][2])
    used = [a.vehicle_id for a in first.assignments + second.assignments]
    assert len(used) == len(set(used))
    assert all(_vehicle(t, v)["status"] == "Reserved" for v in used)
    for s in t["suppliers"]:
        assert 0 <= s["reserved_normal"] <= s["normal_stock"]


def test_r5_cold_stock_runs_out_gives_partial_and_depleted(toronto):
    t, _ = toronto
    for s in t["suppliers"]:
        s["cold_stock"] = 20                            # 60 cold servings in the whole city
    res = _run(t, t["tickets"][1])                      # needs 70
    assert sum(a.servings_assigned for a in res.assignments) == 60
    assert res.remaining == 10 and res.depleted and "no cold stock" in res.reason


def test_r5_low_fuel_truck_is_skipped(toronto):
    t, _ = toronto
    _vehicle(t, "V1")["fuel"] = 15.5                    # any trip would end below the 15 % reserve
    res = _run(t, t["tickets"][1])
    assert "V1" not in [a.vehicle_id for a in res.assignments]
    assert res.remaining == 0


def test_r4_r5_closed_bridge_means_no_route_and_nothing_reserved(town):
    t, _ = town
    res = _run(t, t["tickets"][0], closed={24})         # P3 is reachable only over bridge 24
    assert res.assignments == [] and res.remaining == 60
    assert "no route" in res.reason
    assert all(v["status"] == "Available" for v in t["vehicles"])
    assert all(s["reserved_normal"] == 0 for s in t["suppliers"])


def test_r8_same_matcher_runs_on_the_town_dataset(town):
    t, _ = town
    res = _run(t, t["tickets"][1])                      # P2, 35 cold; one reefer (cap 30) in town
    assert [a.servings_assigned for a in res.assignments] == [30]
    assert res.remaining == 5 and res.reason == "no available refrigerated vehicle"
