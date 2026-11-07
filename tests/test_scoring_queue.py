"""R2 scoring and R3 heap priority queue (aging, re-scoring, tie-breaks).
AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil."""
import heapq
import math
import random
from datetime import timedelta

import pytest

from core.constants import POLICIES
from core.crisis_queue import CrisisQueue
from core.heap import MinHeap
from core.scoring import check_weights, score_ticket

W = POLICIES["balanced"]


def _score(t, row, now, eta=None):
    cat = {r["req_id"]: r for r in t["requesters"]}[row["req_id"]]["category"]
    return score_ticket(row, cat, now, eta, row["servings_requested"], W)


def test_r2_every_policy_preset_is_valid():
    for w in POLICIES.values():
        check_weights(w)
    with pytest.raises(ValueError):
        check_weights({**W, "S": 0.9})


def test_r2_breakdown_sums_to_score_and_stays_in_0_100(toronto):
    t, _ = toronto
    now = t["tickets"][0]["created_at"]
    for row in t["tickets"]:
        sc = _score(t, row, now)
        assert math.isclose(sum(sc.breakdown.values()), sc.value)
        assert 0.0 <= sc.value <= 100.0


def test_r2_higher_severity_scores_higher(toronto):
    t, _ = toronto
    row = t["tickets"][2]
    now = row["created_at"]
    assert _score(t, dict(row, severity=5), now).value > _score(t, dict(row, severity=2), now).value


def test_r2_no_route_and_late_tickets_get_full_deadline_pressure(toronto):
    t, _ = toronto
    row = t["tickets"][0]                       # deadline 60 min after submission
    now = row["created_at"]
    no_route = _score(t, row, now, eta=math.inf)
    late = _score(t, row, now, eta=90.0)
    assert no_route.terms["D"] == 1.0 and "no_route" in no_route.flags
    assert late.terms["D"] == 1.0 and "at_risk" in late.flags
    assert _score(t, row, now, eta=5.0).terms["D"] < 1.0


def test_r3_waiting_raises_priority_aging(toronto):
    t, _ = toronto
    row = t["tickets"][3]                       # P6: low priority, deadline 240 min
    start = row["created_at"]
    later = _score(t, row, start + timedelta(minutes=90))
    assert later.terms["W"] > 0 and later.value > _score(t, row, start).value


def test_r3_heap_pops_in_sorted_order():
    rng = random.Random(7)
    items = [(rng.randint(0, 50), rng.random()) for _ in range(500)]
    h, ref = MinHeap(), []
    for it in items:
        h.push(it)
        heapq.heappush(ref, it)
    assert [h.pop() for _ in range(len(items))] == [heapq.heappop(ref) for _ in range(len(items))]
    with pytest.raises(IndexError):
        h.pop()


def test_r3_rescore_supersedes_old_entry(toronto):
    t, _ = toronto
    a, b = t["tickets"][0], t["tickets"][1]
    q = CrisisQueue()
    q.push(1, 50.0, a["deadline"], a["created_at"])
    q.push(2, 60.0, b["deadline"], b["created_at"])
    assert q.push(1, 70.0, a["deadline"], a["created_at"]) == 2      # version bumped
    assert q.pop_valid() == (1, 70.0, 2)
    assert q.pop_valid() == (2, 60.0, 1)
    assert q.pop_valid() is None                                     # stale 50.0 entry skipped


def test_r3_equal_scores_break_ties_deadline_then_fifo_then_id(toronto):
    t, _ = toronto
    base = t["tickets"][3]
    q = CrisisQueue()
    q.push(30, 40.0, base["deadline"], base["created_at"])
    q.push(20, 40.0, base["deadline"], base["created_at"])                              # same: lower id wins
    q.push(10, 40.0, base["deadline"], base["created_at"] + timedelta(minutes=1))       # later submission
    q.push(40, 40.0, base["deadline"] - timedelta(minutes=5), base["created_at"])       # earlier deadline
    assert [tid for tid, _ in q.ranking()] == [40, 20, 30, 10]


def test_r3_scenario_identical_tickets_tie_break_by_ticket_id(toronto):
    t, _ = toronto
    r4, r5 = t["tickets"][3], t["tickets"][4]   # "_tests": identical score -> tie-break
    now = r4["created_at"]
    s4, s5 = _score(t, r4, now), _score(t, r5, now)
    assert s4.value == s5.value
    q = CrisisQueue()
    q.push(5, s5.value, r5["deadline"], r5["created_at"])
    q.push(4, s4.value, r4["deadline"], r4["created_at"])
    assert [tid for tid, _ in q.ranking()] == [4, 5]


def test_r3_remove_and_compaction_keep_queue_correct(toronto):
    t, _ = toronto
    row = t["tickets"][0]
    q = CrisisQueue()
    for i in range(200):                       # many re-scores of 3 tickets -> compaction
        for tid in (1, 2, 3):
            q.push(tid, float(i + tid), row["deadline"], row["created_at"])
    q.remove(3)
    assert len(q) == 2 and 3 not in q
    assert [q.pop_valid()[0], q.pop_valid()[0], q.pop_valid()] == [2, 1, None]
