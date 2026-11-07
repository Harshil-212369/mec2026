# dispatcher.py - connects the front end (tickets in the database) to routing
# Author: Jagan (team H/A/J). AI assistance: Claude (Anthropic) generated this
# module; reviewed and explained by the author.
#
# What it does each run:
#   1. read open tickets, available vehicles and supplier stock
#   2. heap-based priority queue: highest priority_score first,
#      ties -> older ticket first (created_at), then lower ticket_id
#   3. GREEDY matching: for each ticket, try every (available vehicle, supplier
#      with stock) pair and keep the earliest feasible arrival (trip_planner).
#      A ticket bigger than one truck is SPLIT across several trucks.
#   4. state machine: Open -> Prioritized -> Resource Assigned / Delayed / Failed,
#      every change recorded with a timestamp and a reason
#   5. publish events on an in-process pub/sub bus (stored in system_events)
#
# Two modes:
#   offline (no network, for the Wi-Fi-off demo):
#     .venv\Scripts\python dispatcher.py --offline data\demo_tickets.json
#   database (reads/writes Neon; needs DATABASE_URL and psycopg):
#     .venv\Scripts\python dispatcher.py --once
#
# The decision logic (dispatch) is pure: it only takes lists of dicts and
# returns what should change, so it is tested without a database.

import argparse
import heapq
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import constants as C
import routing as R
import trip_planner as TP

REPO = Path(__file__).resolve().parent

# ----------------------------------------------------------------------------
# State machine: which status changes are allowed
# ----------------------------------------------------------------------------
VALID_TRANSITIONS = {
    "Open": {"Prioritized", "Failed"},
    "Prioritized": {"Resource Assigned", "Delayed", "Failed"},
    "Delayed": {"Prioritized", "Resource Assigned", "Failed"},
    "Resource Assigned": {"In Progress", "Delayed", "Failed"},
    "In Progress": {"Re-Routing", "Delivered", "Delayed", "Failed"},
    "Re-Routing": {"In Progress", "Delayed", "Failed"},
    "Delivered": {"Resolved"},
    "Resolved": set(),
    "Failed": set(),
}


def check_transition(old, new):
    if new not in VALID_TRANSITIONS.get(old, set()):
        raise ValueError(f"invalid status change {old} -> {new}")


# ----------------------------------------------------------------------------
# Publish / subscribe event bus
# ----------------------------------------------------------------------------
class EventBus:
    """Tiny pub/sub: handlers subscribe to an event type (or "*" for all)."""

    def __init__(self):
        self.handlers = {}

    def subscribe(self, event_type, handler):
        self.handlers.setdefault(event_type, []).append(handler)

    def publish(self, event_type, details):
        for h in self.handlers.get(event_type, []) + self.handlers.get("*", []):
            h(event_type, details)


# ----------------------------------------------------------------------------
# Pure decision logic
# ----------------------------------------------------------------------------
def dispatch(graph, tickets, vehicles, suppliers):
    """Decide assignments for one run.

    tickets:   [{"ticket_id", "node", "servings", "refrigerated", "deadline_min",
                 "priority_score", "created_at", "status", "already_assigned"}]
    vehicles:  [{"vehicle_id", "node", "capacity", "refrigerated"}]  (available only)
    suppliers: [{"supp_id", "node", "normal", "cold"}]  (servings still free)

    Returns {"assignments": [...], "changes": [(ticket_id, old, new, reason)],
             "events": [(event_type, details)]}
    """
    free_vehicles = {v["vehicle_id"]: v for v in vehicles}
    stock = {s["supp_id"]: dict(s) for s in suppliers}
    out = {"assignments": [], "changes": [], "events": []}

    # heap-based priority queue; heapq pops the SMALLEST, so negate the score
    heap = []
    for t in tickets:
        created = t.get("created_at") or ""
        heapq.heappush(heap, (-float(t.get("priority_score") or 0), str(created), t["ticket_id"], t))

    while heap:
        _, _, tid, t = heapq.heappop(heap)
        status = t["status"]
        if status == "Open":
            out["changes"].append((tid, "Open", "Prioritized",
                                   f"priority score {float(t.get('priority_score') or 0):.2f}"))
            status = "Prioritized"

        # deadline already gone: nothing can help
        if t["deadline_min"] <= 0:
            reason = f"{C.DEADLINE_UNREACHABLE}: deadline passed {abs(t['deadline_min']):.0f} min ago"
            out["changes"].append((tid, status, "Failed", reason))
            continue

        remaining = t["servings"] - t.get("already_assigned", 0)
        kind = "cold" if t["refrigerated"] else "normal"
        assigned_now = 0
        last_failure = None

        # greedy: keep assigning the best truck until the ticket is covered
        while remaining > 0:
            best = None
            closest = None
            for v in free_vehicles.values():
                if t["refrigerated"] and not v["refrigerated"]:
                    continue
                for s in stock.values():
                    share = min(remaining, v["capacity"], s[kind])
                    if share <= 0:
                        continue
                    stop = {"id": str(tid), "node": t["node"], "servings": share,
                            "refrigerated": t["refrigerated"], "deadline_min": t["deadline_min"]}
                    plan = TP.plan_trip(graph, v["node"], s["node"], [stop], v)
                    if isinstance(plan, TP.Trip):
                        eta = plan.etas[str(tid)]
                        if best is None or eta < best[0]:
                            best = (eta, v, s, share, plan)
                    elif closest is None or plan.details.get("minutes_late", 1e9) < closest.details.get("minutes_late", 1e9):
                        closest = plan

            if best is None:
                last_failure = closest
                break

            eta, v, s, share, plan = best
            route_nodes = list(plan.legs[0].nodes)
            for leg in plan.legs[1:]:
                route_nodes += leg.nodes[1:]
            out["assignments"].append({
                "ticket_id": tid, "vehicle_id": v["vehicle_id"], "supp_id": s["supp_id"],
                "servings": share, "kind": kind, "route": route_nodes,
                "minutes": plan.total_minutes, "km": plan.total_km, "eta": eta})
            out["events"].append(("route-updated", {"ticket_id": tid, "vehicle_id": v["vehicle_id"],
                                                    "eta_min": round(eta, 1), "route": route_nodes}))
            s[kind] -= share
            del free_vehicles[v["vehicle_id"]]
            remaining -= share
            assigned_now += share
            if s[kind] == 0:
                out["events"].append(("resource-depleted", {"supp_id": s["supp_id"], "kind": kind}))

        # status for this ticket
        if assigned_now > 0:
            reason = f"{assigned_now} servings assigned"
            if remaining > 0:
                reason += f"; {remaining} still waiting (not enough trucks/stock)"
            out["changes"].append((tid, status, "Resource Assigned", reason))
        else:
            reason, final = explain_no_assignment(t, kind, free_vehicles, stock, last_failure)
            out["changes"].append((tid, status, final, reason))
            if final == "Delayed":
                out["events"].append(("resource-depleted", {"ticket_id": tid, "reason": reason}))
    return out


def explain_no_assignment(t, kind, free_vehicles, stock, failure):
    """Why nothing was assigned, and whether waiting could help (Delayed) or not (Failed)."""
    if not any(v["refrigerated"] or not t["refrigerated"] for v in free_vehicles.values()):
        need = "refrigerated " if t["refrigerated"] else ""
        return f"{C.NO_SUITABLE_VEHICLE}: no {need}vehicle available right now", "Delayed"
    if not any(s[kind] > 0 for s in stock.values()):
        return f"{C.INSUFFICIENT_STOCK}: no {kind} stock left at any supplier", "Delayed"
    if failure is not None and failure.code == C.DEADLINE_UNREACHABLE:
        return f"{failure.code}: fastest option arrives {failure.details['minutes_late']} min late", "Failed"
    if failure is not None:
        return f"{failure.code}: {failure.message}", "Delayed"
    return "no feasible vehicle/supplier combination", "Delayed"


# ----------------------------------------------------------------------------
# Offline mode: everything from JSON files, results printed
# ----------------------------------------------------------------------------
def load_offline(dataset_path, tickets_path):
    raw = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    pois = {p["id"]: p for p in raw["pois"]}
    suppliers = [{"supp_id": h["poiId"], "node": pois[h["poiId"]]["node"],
                  "normal": h["normal"], "cold": h["cold"]} for h in raw["hubs"]]
    vehicles = [{"vehicle_id": v["id"], "node": v["home"], "capacity": v["capacity"],
                 "refrigerated": v["refrigerated"], "id": v["id"]} for v in raw["trucks"]]
    tickets = json.loads(Path(tickets_path).read_text(encoding="utf-8"))
    for t in tickets:
        t.setdefault("status", "Open")
    return suppliers, vehicles, tickets


def print_result(result):
    for a in result["assignments"]:
        print(f"[ASSIGN] ticket {a['ticket_id']}: {a['vehicle_id']} from {a['supp_id']}, "
              f"{a['servings']} {a['kind']} servings, ETA {a['eta']:.1f} min, route {a['route']}")
    for tid, old, new, reason in result["changes"]:
        print(f"[STATUS] ticket {tid}: {old} -> {new}  ({reason})")
    for etype, details in result["events"]:
        print(f"[EVENT]  {etype}: {details}")


# ----------------------------------------------------------------------------
# Database mode (Neon). psycopg is imported only here, so offline mode needs no extra install.
# ----------------------------------------------------------------------------
def run_db_once(dataset_id):
    import os
    import psycopg
    from psycopg.types.json import Json

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("[FAIL] set DATABASE_URL in this PowerShell window first")
    graph = R.load_graph(REPO / "data" / f"{dataset_id}.json")
    now = datetime.now(timezone.utc)

    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT t.ticket_id, r.location_node, t.servings_requested, t.refrigerated,
                   t.deadline, t.priority_score, t.created_at, t.status,
                   COALESCE((SELECT sum(d.servings_assigned) FROM deliveries d
                             WHERE d.ticket_id = t.ticket_id
                               AND d.status NOT IN ('Failed', 'Cancelled')), 0)
            FROM tickets t JOIN requesters r USING (dataset_id, req_id)
            WHERE t.dataset_id = %s AND t.status IN ('Open', 'Prioritized', 'Delayed')""",
                    (dataset_id,))
        tickets = [{"ticket_id": row[0], "node": row[1], "servings": row[2], "refrigerated": row[3],
                    "deadline_min": (row[4] - now).total_seconds() / 60, "priority_score": row[5],
                    "created_at": row[6], "status": row[7], "already_assigned": int(row[8])}
                   for row in cur.fetchall()]

        cur.execute("""SELECT vehicle_id, current_node, capacity, refrigerated FROM vehicles
                       WHERE dataset_id = %s AND status = 'Available'""", (dataset_id,))
        vehicles = [{"vehicle_id": r_[0], "id": r_[0], "node": r_[1], "capacity": r_[2],
                     "refrigerated": r_[3]} for r_ in cur.fetchall()]

        cur.execute("""SELECT supp_id, location_node, normal_stock - reserved_normal,
                              cold_stock - reserved_cold FROM suppliers WHERE dataset_id = %s""",
                    (dataset_id,))
        suppliers = [{"supp_id": r_[0], "node": r_[1], "normal": r_[2], "cold": r_[3]}
                     for r_ in cur.fetchall()]

        result = dispatch(graph, tickets, vehicles, suppliers)

        bus = EventBus()
        bus.subscribe("*", lambda etype, details: cur.execute(
            "INSERT INTO system_events (dataset_id, event_type, details) VALUES (%s, %s, %s)",
            (dataset_id, etype, Json(details))))

        for a in result["assignments"]:
            cur.execute("""INSERT INTO deliveries (dataset_id, ticket_id, supp_id, vehicle_id,
                               servings_assigned, route, route_weight, route_distance_km, status)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Assigned')""",
                        (dataset_id, a["ticket_id"], a["supp_id"], a["vehicle_id"], a["servings"],
                         Json(a["route"]), a["minutes"], a["km"]))
            col = "reserved_cold" if a["kind"] == "cold" else "reserved_normal"
            cur.execute(f"UPDATE suppliers SET {col} = {col} + %s WHERE dataset_id = %s AND supp_id = %s",
                        (a["servings"], dataset_id, a["supp_id"]))
            cur.execute("UPDATE vehicles SET status = 'Reserved' WHERE dataset_id = %s AND vehicle_id = %s",
                        (dataset_id, a["vehicle_id"]))

        for tid, old, new, reason in result["changes"]:
            check_transition(old, new)
            cur.execute("UPDATE tickets SET status = %s WHERE ticket_id = %s", (new, tid))
            cur.execute("""INSERT INTO ticket_history (dataset_id, ticket_id, old_status, new_status, reason)
                           VALUES (%s, %s, %s, %s, %s)""", (dataset_id, tid, old, new, reason))
            if new == "Prioritized":
                bus.publish("priority-changed", {"ticket_id": tid, "reason": reason})

        for etype, details in result["events"]:
            bus.publish(etype, details)
        conn.commit()

    print_result(result)


def main():
    ap = argparse.ArgumentParser(description="Assign trucks and routes to open tickets")
    ap.add_argument("--dataset", default="toronto-downtown", help="dataset id = data/<id>.json")
    ap.add_argument("--offline", metavar="TICKETS_JSON", help="run without the database")
    ap.add_argument("--once", action="store_true", help="one run against the database")
    args = ap.parse_args()

    if args.offline:
        graph = R.load_graph(REPO / "data" / f"{args.dataset}.json")
        suppliers, vehicles, tickets = load_offline(REPO / "data" / f"{args.dataset}.json", args.offline)
        result = dispatch(graph, tickets, vehicles, suppliers)
        for tid, old, new, _ in result["changes"]:
            check_transition(old, new)
        print_result(result)
    elif args.once:
        run_db_once(args.dataset)
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
