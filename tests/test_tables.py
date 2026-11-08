"""R8: the engine reads the same table rows from Aadil's database dump and from the JSON.
AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil."""
from datetime import datetime, timezone

import pytest

from core.tables import InputError, from_json, from_pg_dump, select_dataset
from tests.conftest import AADIL_DUMP, DATA

WORLD = ("datasets", "nodes", "roads", "requesters", "suppliers", "vehicles")


def test_r8_dump_reads_aadil_tables_with_types(aadil):
    t, _ = aadil
    counts = {k: len(t[k]) for k in ("nodes", "roads", "requesters", "suppliers", "vehicles", "tickets")}
    assert counts == {"nodes": 48, "roads": 82, "requesters": 4, "suppliers": 3, "vehicles": 12, "tickets": 1}
    assert t["app_settings"] == [{"setting_id": 1, "active_dataset_id": "toronto-downtown"}]
    assert t["roads"][0]["is_closed"] is False and isinstance(t["roads"][0]["weight"], float)
    tk = t["tickets"][0]
    assert tk["req_id"] == "P3" and tk["servings_requested"] == 28 and tk["refrigerated"] is False
    assert tk["deadline"] == datetime(2026, 11, 7, 21, 16, tzinfo=timezone.utc)
    assert t["system_events"][0]["details"] == {"req_id": "P3", "ticket_id": 1}
    assert t["ticket_history"][0]["old_status"] is None


def test_r8_aadil_tickets_table_has_no_severity_column(aadil):
    # Documents the gap to fix with Aadil: the statement requires a severity level.
    t, _ = aadil
    assert "severity" not in t["tickets"][0]


def test_r8_json_rows_equal_aadil_dump_rows_for_world_tables(aadil):
    t_db, _ = aadil
    _, t_json = select_dataset(from_json(DATA / "toronto-downtown.json"))
    for name in WORLD:
        assert t_json[name] == t_db[name], name


def test_r8_dump_with_spaces_instead_of_tabs_fails_loudly(tmp_path):
    bad = tmp_path / "pasted.sql"
    bad.write_text("COPY public.nodes (dataset_id, node_id, name, lat, lng) FROM stdin;\n"
                   "toronto-downtown        0       Bathurst St & Front St  43.6432 -79.4096\n\\.\n",
                   encoding="utf-8")
    with pytest.raises(InputError, match="tabs"):
        from_pg_dump(bad)


def test_r8_unknown_dataset_is_rejected():
    with pytest.raises(InputError, match="not found"):
        select_dataset(from_pg_dump(AADIL_DUMP), "nowhere")


def test_r8_scenario_tickets_become_ticket_rows(toronto):
    t, bundle = toronto
    assert [r["ticket_id"] for r in t["tickets"]] == [1, 2, 3, 4, 5, 6]
    assert t["tickets"][0]["created_at"].tzinfo is not None
    assert len(bundle.extra_tickets) == 7 and len(bundle.scenario_events) == 5
