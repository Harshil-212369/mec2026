"""Read the system's input as database-shaped tables.

Every source returns the same thing: {table_name: [row_dict, ...]} using the exact column
names of Aadil's Postgres schema (tickets, requesters, suppliers, vehicles, roads, ...).
The engine only sees these rows, so it does not care where they came from:

  from_pg_dump(path)            a `pg_dump` text file: offline, what the tests use
  from_postgres(dsn)            Aadil's live database, read-only (psycopg + MEC_DATABASE_URL)
  from_json(dataset, scenario)  organizers' dataset JSON + our scenario file (same rows)

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

KNOWN_TABLES = (
    "app_settings", "datasets", "nodes", "roads", "requesters", "suppliers",
    "vehicles", "tickets", "ticket_history", "system_events", "deliveries",
)

# Scenario files give times as minutes from the start; we anchor them to a fixed instant so
# every run is identical (14:00 EST on build day).
SIM_START = datetime(2026, 11, 7, 19, 0, tzinfo=timezone.utc)


class InputError(ValueError):
    """The input cannot be read. The message names the file/table/row and the reason."""


@dataclass
class InputBundle:
    source: str
    tables: dict[str, list[dict]]
    scenario_events: list[dict] = field(default_factory=list)
    extra_tickets: list[dict] = field(default_factory=list)  # scenario "invalid_tickets"
    report: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ pg_dump ----
_CREATE_RE = re.compile(r"^CREATE TABLE (?:public\.)?(\w+) \((.*?)^\);", re.S | re.M)
_COL_RE = re.compile(r"^(\w+) (.+?)(?: DEFAULT .*| NOT NULL.*)?,?$")
_COPY_RE = re.compile(r"^COPY (?:public\.)?(\w+) \(([^)]*)\) FROM stdin;\n(.*?)^\\\.$", re.S | re.M)
_ESCAPES = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\"}


def _kind(pg_type: str) -> str:
    t = pg_type.lower()
    if t in ("integer", "bigint", "smallint"):
        return "int"
    if t in ("double precision", "real") or t.startswith("numeric"):
        return "float"
    if t == "boolean":
        return "bool"
    if t == "timestamp with time zone":
        return "ts"
    if t in ("jsonb", "json"):
        return "json"
    return "str"  # text, varchar, and anything we do not know: kept as text


def _unescape(field_text: str) -> str:
    """Undo COPY text-format backslash escapes (\\t, \\n, \\\\ ...)."""
    if "\\" not in field_text:
        return field_text
    out, i = [], 0
    while i < len(field_text):
        ch = field_text[i]
        if ch == "\\" and i + 1 < len(field_text):
            nxt = field_text[i + 1]
            out.append(_ESCAPES.get(nxt, nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _convert(raw: str, kind: str, where: str):
    if raw == "\\N":
        return None
    s = _unescape(raw)
    try:
        if kind == "int":
            return int(s)
        if kind == "float":
            return float(s)
        if kind == "bool":
            if s in ("t", "true"):
                return True
            if s in ("f", "false"):
                return False
            raise ValueError(f"not a boolean: {s!r}")
        if kind == "ts":
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                raise ValueError(f"timestamp without time zone: {s!r}")
            return dt
        if kind == "json":
            return json.loads(s)
    except ValueError as exc:  # json.JSONDecodeError is a ValueError too
        raise InputError(f"{where}: {exc}") from exc
    return s


def from_pg_dump(path: str | Path) -> InputBundle:
    """Parse a plain-text pg_dump: column types from CREATE TABLE, rows from COPY blocks."""
    path = Path(path)
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    types: dict[str, dict[str, str]] = {}
    for m in _CREATE_RE.finditer(text):
        cols = {}
        for line in m.group(2).splitlines():
            line = line.strip()
            if not line or line.startswith("CONSTRAINT"):
                continue
            cm = _COL_RE.match(line)
            if cm:
                cols[cm.group(1)] = _kind(cm.group(2))
        types[m.group(1)] = cols

    tables: dict[str, list[dict]] = {}
    report: list[str] = []
    for m in _COPY_RE.finditer(text):
        name = m.group(1)
        cols = [c.strip() for c in m.group(2).split(",")]
        if name not in KNOWN_TABLES:
            report.append(f"[WARN] table {name} is not used by the engine (ignored)")
            continue
        col_types = types.get(name)
        if col_types is None:
            report.append(f"[WARN] no CREATE TABLE for {name}: its values are kept as text")
            col_types = {}
        rows = []
        for i, line in enumerate(m.group(3).splitlines(), 1):
            fields = line.split("\t")
            if len(fields) != len(cols):
                raise InputError(
                    f"{path.name}: table {name} row {i} has {len(fields)} fields, expected {len(cols)} "
                    f"({', '.join(cols)}). If the dump was copy-pasted, its tabs may have become "
                    "spaces: re-export it with `pg_dump ... -f file.sql`.")
            rows.append({c: _convert(v, col_types.get(c, "str"), f"{path.name}: {name} row {i} column {c}")
                         for c, v in zip(cols, fields)})
        tables[name] = rows
    if not tables:
        raise InputError(f"{path}: no COPY data blocks found (is this a plain-text pg_dump?)")
    for name in KNOWN_TABLES:
        if name not in tables:
            tables[name] = []
            report.append(f"[WARN] table {name} not in the dump (treated as empty)")
    return InputBundle(f"pg_dump:{path.name}", tables, report=report)


# ----------------------------------------------------------------- Postgres ----
def from_postgres(dsn: str | None = None) -> InputBundle:
    """Read every known table from a live Postgres database in a READ ONLY session.

    The URL comes from the argument or the MEC_DATABASE_URL environment variable. It is never
    printed or logged.
    """
    if dsn is None:
        dsn = os.environ.get("MEC_DATABASE_URL")
    if not dsn:
        raise InputError("no database URL: set the MEC_DATABASE_URL environment variable "
                         "(keep it in .env; never commit it or paste it in chat)")
    try:
        import psycopg
        from psycopg import sql
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise InputError("psycopg is not installed: run scripts/setup.cmd") from exc

    tables: dict[str, list[dict]] = {}
    report: list[str] = []
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=10) as conn:
        conn.read_only = True
        present = {r["table_name"] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
        for name in KNOWN_TABLES:
            if name not in present:
                tables[name] = []
                report.append(f"[WARN] table {name} does not exist in the database (treated as empty)")
                continue
            query = sql.SQL("SELECT * FROM public.{}").format(sql.Identifier(name))
            tables[name] = [dict(r) for r in conn.execute(query)]
        unused = sorted(present - set(KNOWN_TABLES))
        if unused:
            report.append(f"[WARN] tables not used by the engine: {', '.join(unused)}")
    return InputBundle("postgres", tables, report=report)


# --------------------------------------------------------------------- JSON ----
def _scenario_ticket(t: dict, ticket_id: int | None, dataset_id: str, start: datetime) -> dict:
    """Scenario ticket -> tickets-table row. Values are copied as-is (bad ones included):
    validation is validate.py's job, not the reader's."""
    row = {k: v for k, v in t.items()
           if k not in ("submit_min", "deadline_min") and (not k.startswith("_") or k == "_expect")}
    row.update(dataset_id=dataset_id, status="Open", priority_score=None, priority_version=0)
    if ticket_id is not None:
        row["ticket_id"] = ticket_id
    for src, dst in (("submit_min", "created_at"), ("deadline_min", "deadline")):
        if src in t:
            v = t[src]
            is_number = isinstance(v, (int, float)) and not isinstance(v, bool)
            row[dst] = start + timedelta(minutes=v) if is_number else v
    return row


def from_json(dataset_path: str | Path, scenario_path: str | Path | None = None,
              sim_start: datetime = SIM_START) -> InputBundle:
    """Organizers' dataset JSON (nodes/edges/pois/hubs/trucks) -> the same rows Aadil's
    database holds. Optional scenario file adds tickets, timed events and invalid tickets."""
    dataset_path = Path(dataset_path)
    ds = json.loads(dataset_path.read_text(encoding="utf-8"))
    sc, source = None, f"json:{dataset_path.name}"
    if scenario_path is not None:
        scenario_path = Path(scenario_path)
        sc = json.loads(scenario_path.read_text(encoding="utf-8"))
        source += f"+{scenario_path.name}"
    return from_data(ds, sc, source, sim_start)


def from_data(ds: dict, sc: dict | None = None, source: str = "data",
              sim_start: datetime = SIM_START) -> InputBundle:
    """Dataset dict in the organizers' JSON structure (+ optional scenario dict) -> table rows.
    Used for files (from_json) and for generated cities (core/random_dataset.py)."""
    report: list[str] = []
    dsid = ds["id"]
    pois = {p["id"]: p for p in ds["pois"]}
    hub_ids = [h["poiId"] for h in ds["hubs"]]
    missing = [h for h in hub_ids if h not in pois]
    if missing:
        raise InputError(f"dataset {dsid}: hubs {missing} have no matching entry in pois")
    node_to_hub: dict[int, str] = {}
    for h in hub_ids:
        node_to_hub.setdefault(pois[h]["node"], h)

    t: dict[str, list[dict]] = {name: [] for name in KNOWN_TABLES}
    t["app_settings"] = [{"setting_id": 1, "active_dataset_id": dsid}]
    center = ds.get("center")
    t["datasets"] = [{"dataset_id": dsid, "name": ds["name"],
                      "center_lat": center[0] if center else None,
                      "center_lng": center[1] if center else None,
                      "zoom": ds.get("zoom")}]
    t["nodes"] = [{"dataset_id": dsid, "node_id": n["id"], "name": n["name"], "lat": n["lat"], "lng": n["lng"]}
                  for n in ds["nodes"]]
    t["roads"] = [{"dataset_id": dsid, "road_id": e["id"], "node_a": e["a"], "node_b": e["b"],
                   "street": e.get("street"), "distance_km": e["km"], "weight": e["w"],
                   "is_highway": e.get("hwy", False),  # DB column default false
                   "terrain": e.get("terrain"), "is_closed": False}
                  for e in ds["edges"]]
    t["requesters"] = [{"dataset_id": dsid, "req_id": p["id"], "name": p["name"], "category": p["kind"],
                        "location_node": p["node"], "address": p.get("address")}
                       for p in ds["pois"] if p["id"] not in hub_ids]
    t["suppliers"] = [{"dataset_id": dsid, "supp_id": h["poiId"], "name": pois[h["poiId"]]["name"],
                       "location_node": pois[h["poiId"]]["node"], "address": pois[h["poiId"]].get("address"),
                       "normal_stock": h["normal"], "cold_stock": h["cold"],
                       "reserved_normal": 0, "reserved_cold": 0}
                      for h in ds["hubs"]]
    for tr in ds["trucks"]:
        supp = node_to_hub.get(tr["home"])
        if supp is None:
            report.append(f"[WARN] truck {tr['id']} home node {tr['home']} is not a hub: supp_id left empty")
        if "fuel" not in tr:
            report.append(f"[WARN] truck {tr['id']} has no fuel value: using 100 (DB column default)")
        t["vehicles"].append({"dataset_id": dsid, "vehicle_id": tr["id"], "supp_id": supp, "name": tr["name"],
                              "start_node": tr["home"], "current_node": tr["home"],
                              "capacity": tr["capacity"], "refrigerated": tr["refrigerated"],
                              "fuel": tr["fuel"] if "fuel" in tr else 100, "status": "Available"})

    bundle = InputBundle(source, t, report=report)
    if sc is not None:
        if sc.get("dataset_id") not in (None, dsid):
            report.append(f"[WARN] scenario was written for {sc['dataset_id']!r}, "
                          f"dataset is {dsid!r}: ids used as-is")
        t["tickets"] = [_scenario_ticket(tk, i, dsid, sim_start) for i, tk in enumerate(sc.get("tickets", []), 1)]
        bundle.extra_tickets = [_scenario_ticket(tk, None, dsid, sim_start) for tk in sc.get("invalid_tickets", [])]
        bundle.scenario_events = [dict(ev) for ev in sc.get("events", [])]
    return bundle


# ---------------------------------------------------------------- selection ----
def select_dataset(bundle: InputBundle, dataset_id: str | None = None) -> tuple[str, dict[str, list[dict]]]:
    """Keep only one dataset's rows. Default: app_settings.active_dataset_id, else the only one."""
    t = bundle.tables
    ids = [d["dataset_id"] for d in t["datasets"]]
    if dataset_id is None:
        active = [r["active_dataset_id"] for r in t["app_settings"]]
        if len(active) == 1:
            dataset_id = active[0]
        elif len(ids) == 1:
            dataset_id = ids[0]
        else:
            raise InputError(f"several datasets and no active one; choose one of {ids}")
    if dataset_id not in ids:
        raise InputError(f"dataset {dataset_id!r} not found; available: {ids}")
    return dataset_id, {name: [r for r in rows if r.get("dataset_id", dataset_id) == dataset_id]
                        for name, rows in t.items()}
