"""Two-way sync with Aadil's Postgres (Neon) tables, so his dashboard shows the engine's decisions.

  collect(engine)  -> batch     runs under the engine lock: pure Python, only rows that CHANGED
  flush(batch)                  runs in a worker thread: ONE transaction, then reads new Open tickets
                                from his requester form; they are submitted on the next collect()

Writes (only rows that exist in his database; tickets our API created itself are not written):
  tickets (status, priority_score, priority_version), ticket_history, system_events (not the
  noisy vehicle-moved), deliveries (insert, then status / completed_at), vehicles (status,
  current_node, fuel), suppliers (stock + reserved). A failed flush is rolled back and retried
  next time; the engine keeps running.

Opt-in only: python -m api --postgres --write-back   (MEC_DATABASE_URL in the environment)

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
"""
from __future__ import annotations

import os

from core.engine import Engine


class DbSync:
    def __init__(self, engine: Engine, dsn: str | None = None) -> None:
        self.dsn = dsn or os.environ.get("MEC_DATABASE_URL")
        if not self.dsn:
            raise ValueError("write-back needs MEC_DATABASE_URL")
        self.eng = engine
        self.db_tickets = {r["ticket_id"] for r in engine.t["tickets"] if isinstance(r.get("ticket_id"), int)}
        self.db_suppliers = {s["supp_id"] for s in engine.suppliers if not s.get("temporary")}
        self.hist_i = 0
        self.event_i = 0
        self.written: dict[tuple, tuple] = {}      # (table, key) -> last values written
        self.delivery_ids: dict[int, int] = {}     # engine delivery_id -> database delivery_id
        self.incoming: list[dict] = []             # new Open tickets read from the database
        self.errors: list[str] = []
        self.flushes = 0
        self._conn = None

    # ------------------------------------------------------------ main thread ----
    def collect(self) -> dict:
        eng, ds = self.eng, self.eng.dataset_id
        known = set(eng.tickets) | {r.get("ticket_id") for r, _ in eng.rejected} \
            | {r.get("ticket_id") for r in eng._pending}
        for row in self.incoming:                  # Aadil's form -> engine
            if row["ticket_id"] not in known:
                self.db_tickets.add(row["ticket_id"])
                eng.submit(row, eng.now)
        self.incoming = []

        def changed(key, values):
            return self.written.get(key) != values

        b = {"tickets": [], "history": [], "events": [], "vehicles": [], "suppliers": [],
             "new_deliveries": [], "deliveries": [], "marks": {}}
        for t in eng.tickets.values():
            if t["ticket_id"] in self.db_tickets:
                vals = (t["status"], round(t["priority_score"] or 0.0, 1), t.get("priority_version", 0))
                if changed(("t", t["ticket_id"]), vals):
                    b["tickets"].append((*vals, ds, t["ticket_id"]))
                    b["marks"][("t", t["ticket_id"])] = vals
        hist = eng.sm.history
        b["history"] = [(ds, h["ticket_id"], h["old_status"], h["new_status"], h["reason"], h["changed_at"])
                        for h in hist[self.hist_i:]
                        if h["ticket_id"] in self.db_tickets and h["old_status"] is not None]  # his form wrote 'Open'
        b["hist_end"] = len(hist)
        log = eng.bus.log
        b["events"] = [(ds, e["event_type"], e["details"], e["created_at"]) for e in log[self.event_i:]
                       if e["event_type"] != "vehicle-moved"]
        b["event_end"] = len(log)
        for v in eng.vehicles:
            vals = (v["status"], v["current_node"], round(float(v["fuel"]), 2))
            if changed(("v", v["vehicle_id"]), vals):
                b["vehicles"].append((*vals, ds, v["vehicle_id"]))
                b["marks"][("v", v["vehicle_id"])] = vals
        for s in eng.suppliers:
            if s["supp_id"] in self.db_suppliers:
                vals = (s["normal_stock"], s["cold_stock"], s["reserved_normal"], s["reserved_cold"])
                if changed(("s", s["supp_id"]), vals):
                    b["suppliers"].append((*vals, ds, s["supp_id"]))
                    b["marks"][("s", s["supp_id"])] = vals
        for d in eng.deliveries:
            if d.ticket_id not in self.db_tickets or d.supp_id not in self.db_suppliers:
                continue   # cargo picked up from a broken truck has no supplier row in his schema
            if d.delivery_id not in self.delivery_ids:
                drive = [s for s in d.segments if s.kind == "drive"]
                b["new_deliveries"].append((d.delivery_id, (
                    ds, d.ticket_id, d.supp_id, d.vehicle_id, d.servings, d.route_nodes,
                    sum(s.minutes for s in drive), sum(s.km for s in drive), d.status, d.assigned_at, d.completed_at)))
            else:
                vals = (d.status, d.completed_at)
                if changed(("d", d.delivery_id), vals):
                    b["deliveries"].append((d.delivery_id, vals))
        return b

    # ---------------------------------------------------------- worker thread ----
    def flush(self, b: dict) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg.types.json import Json
            if self._conn is None or self._conn.closed:
                self._conn = psycopg.connect(self.dsn, connect_timeout=10)
            conn, ds = self._conn, self.eng.dataset_id
            new_ids: dict[int, int] = {}
            with conn.transaction(), conn.cursor() as cur:
                if b["tickets"]:
                    cur.executemany("UPDATE tickets SET status = %s, priority_score = %s, priority_version = %s "
                                    "WHERE dataset_id = %s AND ticket_id = %s", b["tickets"])
                if b["history"]:
                    cur.executemany("INSERT INTO ticket_history (dataset_id, ticket_id, old_status, new_status, "
                                    "reason, changed_at) VALUES (%s, %s, %s, %s, %s, %s)", b["history"])
                if b["events"]:
                    cur.executemany("INSERT INTO system_events (dataset_id, event_type, details, created_at) "
                                    "VALUES (%s, %s, %s, %s)", [(a, t, Json(d), c) for a, t, d, c in b["events"]])
                if b["vehicles"]:
                    cur.executemany("UPDATE vehicles SET status = %s, current_node = %s, fuel = %s "
                                    "WHERE dataset_id = %s AND vehicle_id = %s", b["vehicles"])
                if b["suppliers"]:
                    cur.executemany("UPDATE suppliers SET normal_stock = %s, cold_stock = %s, reserved_normal = %s, "
                                    "reserved_cold = %s WHERE dataset_id = %s AND supp_id = %s", b["suppliers"])
                for engine_id, row in b["new_deliveries"]:
                    (dsid, tid, supp, veh, servings, route, minutes, km, status, assigned, completed) = row
                    cur.execute("INSERT INTO deliveries (dataset_id, ticket_id, supp_id, vehicle_id, servings_assigned, "
                                "route, route_weight, route_distance_km, status, assigned_at, completed_at) "
                                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING delivery_id",
                                (dsid, tid, supp, veh, servings, Json(route), minutes, km, status, assigned, completed))
                    new_ids[engine_id] = cur.fetchone()[0]
                for engine_id, (status, completed) in b["deliveries"]:
                    cur.execute("UPDATE deliveries SET status = %s, completed_at = %s WHERE delivery_id = %s",
                                (status, completed, self.delivery_ids[engine_id]))
            with conn.cursor(row_factory=dict_row) as cur:    # read Aadil's new form submissions
                self.incoming = [dict(r) for r in cur.execute(
                    "SELECT * FROM tickets WHERE dataset_id = %s AND status = 'Open'", (ds,))]
            conn.commit()
        except Exception as exc:   # network / database trouble must never stop dispatching
            self.errors.append(f"{type(exc).__name__}: {exc}"[:300])
            try:
                if self._conn is not None and not self._conn.closed:
                    self._conn.rollback()
            except Exception:      # broken connection: reconnect on the next flush
                self._conn = None
            return
        self.mark_written(b, new_ids)

    def mark_written(self, b: dict, new_ids: dict[int, int]) -> None:
        """After a committed flush: remember what is now in the database (no duplicates next time)."""
        self.hist_i, self.event_i = b["hist_end"], b["event_end"]
        self.written.update(b["marks"])
        self.delivery_ids.update(new_ids)
        for engine_id, vals in b["deliveries"]:
            self.written[("d", engine_id)] = vals
        for engine_id, row in b["new_deliveries"]:
            self.written[("d", engine_id)] = (row[8], row[10])
        self.flushes += 1
