"""Write-back to Aadil's tables: what is written, retry on failure, no duplicates after success.
The SQL itself needs a live database and is not exercised here.
AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil."""
from core.db_sync import DbSync
from core.engine import Engine
from core.routing import get_router_factory
from core.tables import from_pg_dump
from tests.conftest import AADIL_DUMP

router, _ = get_router_factory()
UNREACHABLE = "postgresql://nobody@127.0.0.1:1/none?connect_timeout=2"


def _engine_with_db_ticket(minutes=5):
    bundle = from_pg_dump(AADIL_DUMP)
    bundle.tables["tickets"][0]["severity"] = 4          # what his new column would hold
    eng = Engine.from_bundle(bundle, router)
    eng.run_for(minutes)                                 # truck still on the way
    return eng


def test_db_sync_batch_contains_only_database_rows_and_real_changes():
    eng = _engine_with_db_ticket()
    sync = DbSync(eng, UNREACHABLE)
    eng.submit({"req_id": "P5", "crisis_type": "flood", "servings_requested": 10, "people_affected": 5,
                "severity": 2, "refrigerated": False, "created_at": eng.now,
                "deadline": eng.now.replace(hour=23)}, eng.now)   # made by our API, not in his DB
    b = sync.collect()
    assert [row[-1] for row in b["tickets"]] == [1]                # only his ticket 1
    assert b["history"] and all(row[1] == 1 and row[2] is not None for row in b["history"])
    assert b["events"] and all(row[1] != "vehicle-moved" for row in b["events"])
    assert [d[1][1] for d in b["new_deliveries"]] == [1]           # delivery for ticket 1
    assert {row[-1] for row in b["vehicles"]} == {v["vehicle_id"] for v in eng.vehicles}


def test_db_sync_failed_flush_is_retried_and_success_writes_nothing_twice():
    eng = _engine_with_db_ticket()
    sync = DbSync(eng, UNREACHABLE)
    b = sync.collect()
    sync.flush(b)                                                  # database unreachable
    assert sync.errors and sync.flushes == 0 and sync.hist_i == 0
    again = sync.collect()
    assert len(again["history"]) == len(b["history"]) and len(again["new_deliveries"]) == 1
    sync.mark_written(again, {again["new_deliveries"][0][0]: 501})  # as if the commit succeeded
    after = sync.collect()
    assert after["history"] == [] and after["events"] == [] and after["new_deliveries"] == []
    assert after["tickets"] == [] and after["vehicles"] == []
    eng.advance(30)                                                # truck arrives -> only the changes
    later = sync.collect()
    assert later["deliveries"] and later["deliveries"][0][1][0] == "Delivered"
    assert any(row[3] == "Resolved" for row in later["history"])


def test_db_sync_reads_new_form_tickets_into_the_engine():
    eng = _engine_with_db_ticket()
    sync = DbSync(eng, UNREACHABLE)
    sync.incoming = [{"ticket_id": 2, "dataset_id": eng.dataset_id, "req_id": "P4", "crisis_type": "food_shortage",
                      "servings_requested": 30, "people_affected": 20, "severity": 5, "refrigerated": False,
                      "deadline": eng.now.replace(hour=23), "created_at": eng.now, "priority_score": None,
                      "status": "Open", "priority_version": 0}]
    sync.collect()
    assert eng.tickets[2]["status"] == "Prioritized" and 2 in sync.db_tickets
