"""The engine: one object that owns all live state and runs the loop (ARCHITECTURE.md 2-3).

Each advance(dt) does, in this order:
  1. apply events that are due (road closed/reopened, breakdown, repair, stock change)
  2. move every truck dt minutes along its plan: drive edges -> load at supplier -> drive -> unload
  3. submit tickets whose submission time has come: validate -> Open -> Prioritized
  4. fail tickets that have had no route for FAIL_GRACE_MIN past their deadline
  5. re-score every waiting ticket (aging, travel time); publish priority-changed if the order moved
  6. dispatch: pop the most urgent ticket, greedy-match trucks + stock, start deliveries

Routing is plugged in: router_factory(nodes, roads) -> route_fn(src, dst) returning
{"path", "edges", "minutes", "km"} or None. The engine rebuilds it whenever a road closes or
reopens, so the router only ever has to skip roads whose is_closed is true.

One engine object = one writer, so no two emergencies can grab the same truck or servings.

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from core.constants import (DEFAULT_POLICY, FAIL_GRACE_MIN, FUEL_PCT_PER_KM, LOAD_MIN, POLICIES,
                            UNLOAD_MIN)
from core.crisis_queue import CrisisQueue
from core.events import EventBus
from core.matcher import RouteFn, assign, free_stock
from core.scoring import Score, score_ticket
from core.state import StateMachine
from core.tables import SIM_START, InputBundle, select_dataset
from core.validate import validate_ticket

RouterFactory = Callable[[list[dict], list[dict]], RouteFn]
EVENT_TYPES = ("road_closed", "road_reopened", "vehicle_breakdown", "vehicle_repaired", "stock_change")
ACTIVE = ("In Progress", "Delayed")   # delivery statuses that still hold a truck


@dataclass
class Segment:
    kind: str            # "drive", "load" or "unload"
    minutes: float
    node_from: int
    node_to: int
    edge_id: int | None = None
    km: float = 0.0


@dataclass
class Delivery:
    delivery_id: int
    ticket_id: int
    vehicle_id: str
    supp_id: str
    servings: int
    cold: bool
    supplier_node: int
    requester_node: int
    segments: list[Segment]
    route_nodes: list[int]
    assigned_at: datetime
    seg_idx: int = 0
    into: float = 0.0             # minutes already spent in the current segment
    picked_up: bool = False
    status: str = "In Progress"   # In Progress | Delayed (stuck with cargo) | Delivered | Cancelled
    completed_at: datetime | None = None

    def remaining_edges(self) -> list[int]:
        return [s.edge_id for s in self.segments[self.seg_idx:] if s.kind == "drive"]

    def eta_min(self) -> float:
        return sum(s.minutes for s in self.segments[self.seg_idx:]) - self.into


class Engine:
    def __init__(self, dataset_id: str, tables: dict[str, list[dict]], router_factory: RouterFactory, *,
                 start: datetime, policy: str = DEFAULT_POLICY, scenario_events: list[dict] = (),
                 scenario_start: datetime | None = None) -> None:
        if policy not in POLICIES:
            raise ValueError(f"unknown policy {policy!r}; choose from {sorted(POLICIES)}")
        if start.tzinfo is None:
            raise ValueError("start time needs a time zone")
        self.dataset_id, self.t, self.now, self.policy = dataset_id, tables, start, policy
        self.start = start
        self.bus = EventBus(dataset_id)
        self.sm = StateMachine(self.bus)
        self.queue = CrisisQueue()
        self.suppliers, self.vehicles = tables["suppliers"], tables["vehicles"]
        self._req = {r["req_id"]: r for r in tables["requesters"]}
        self._road = {r["road_id"]: r for r in tables["roads"]}
        self._veh = {v["vehicle_id"]: v for v in tables["vehicles"]}
        self._router_factory = router_factory
        self.tickets: dict[int, dict] = {}
        self.meta: dict[int, dict] = {}            # per ticket: delivered, score, blocked
        self.deliveries: list[Delivery] = []
        self.rejected: list[tuple[dict, list[tuple[str, str]]]] = []
        self.notes: list[str] = []
        self._ranking: list[int] = []
        self._next_delivery = 1
        self._next_ticket = 1 + max((r["ticket_id"] for r in tables["tickets"]
                                     if isinstance(r.get("ticket_id"), int)), default=0)
        self._pending = []
        for r in tables["tickets"]:
            if r.get("status") in (None, "Open"):
                self._pending.append(r)
            else:
                self.notes.append(f"[WARN] ticket {r.get('ticket_id')} is already {r['status']} in the input: "
                                  "not resumed")
        self._pending.sort(key=lambda r: r["created_at"] if isinstance(r.get("created_at"), datetime) else start)
        self._events = self._check_events(list(scenario_events), scenario_start or start)
        self._build_router()

    @classmethod
    def from_bundle(cls, bundle: InputBundle, router_factory: RouterFactory, dataset_id: str | None = None,
                    policy: str = DEFAULT_POLICY) -> "Engine":
        """Engine over a deep copy of one dataset's rows (the input itself is never modified).
        Scenario/JSON runs start at SIM_START; database runs at the earliest open ticket."""
        dsid, tables = select_dataset(bundle, dataset_id)
        tables = copy.deepcopy(tables)
        created = [r["created_at"] for r in tables["tickets"] if isinstance(r.get("created_at"), datetime)]
        start = SIM_START if bundle.source.startswith(("json", "random")) or not created else min(created)
        return cls(dsid, tables, router_factory, start=start, policy=policy,
                   scenario_events=bundle.scenario_events, scenario_start=SIM_START)

    # ------------------------------------------------------------------ loop ----
    def advance(self, dt_min: float) -> None:
        if dt_min < 0:
            raise ValueError("time only moves forward")
        self.now = now = self.now + timedelta(minutes=dt_min)
        while self._events and self._events[0][0] <= now:
            self.apply_event(self._events.pop(0)[2], now)
        if dt_min > 0:
            for d in [d for d in self.deliveries if d.status == "In Progress"]:
                self._move(d, dt_min, now)
        while self._pending and (not isinstance(self._pending[0].get("created_at"), datetime)
                                 or self._pending[0]["created_at"] <= now):
            self.submit(self._pending.pop(0), now)
        self._fail_overdue(now)
        self._rescore(now)
        self._dispatch(now)

    def run_for(self, minutes: float, step_min: float = 1.0) -> None:
        end = self.now + timedelta(minutes=minutes)
        self.advance(0)
        while self.now < end:
            self.advance(min(step_min, (end - self.now).total_seconds() / 60.0))

    # ------------------------------------------------------------- tickets ----
    def submit(self, row: dict, now: datetime) -> list[tuple[str, str]]:
        """Validate a tickets-table row; if valid: Open (crisis-created) -> Prioritized."""
        errors = validate_ticket(row, self._req)
        if errors:
            self.rejected.append((row, errors))
            return errors
        if not isinstance(row.get("ticket_id"), int):
            row["ticket_id"] = self._next_ticket
            self._next_ticket += 1
        tid = row["ticket_id"]
        if tid in self.tickets:
            raise ValueError(f"duplicate ticket id {tid}")
        self.tickets[tid] = row
        if not any(r is row for r in self.t["tickets"]):
            self.t["tickets"].append(row)
        self.meta[tid] = {"delivered": 0, "score": None, "blocked": None}
        self.sm.open(row, now)
        score = self._score(row, now)
        self.sm.transition(row, "Prioritized", f"validated; priority score {score.value:.1f}", now)
        self._push(row, score)
        return []

    def set_policy(self, policy: str, now: datetime) -> None:
        if policy not in POLICIES:
            raise ValueError(f"unknown policy {policy!r}")
        self.policy = policy
        self._rescore(now)

    def remaining(self, tid: int) -> int:
        t = self.tickets[tid]
        in_flight = sum(d.servings for d in self.deliveries if d.ticket_id == tid and d.status in ACTIVE)
        return t["servings_requested"] - self.meta[tid]["delivered"] - in_flight

    def _score(self, t: dict, now: datetime) -> Score:
        sc = score_ticket(t, self._req[t["req_id"]]["category"], now, self._eta_estimate(t),
                          self.remaining(t["ticket_id"]), POLICIES[self.policy])
        self.meta[t["ticket_id"]]["score"] = sc
        t["priority_score"] = round(sc.value, 3)
        return sc

    def _push(self, t: dict, sc: Score) -> None:
        t["priority_version"] = self.queue.push(t["ticket_id"], sc.value, t["deadline"], t["created_at"])

    def _eta_estimate(self, t: dict) -> float:
        """Fastest supplier -> requester drive + load + unload; math.inf if no supplier can reach it."""
        node = self._req[t["req_id"]]["location_node"]
        stocked = [s for s in self.suppliers if free_stock(s, t["refrigerated"]) > 0] or self.suppliers
        best = math.inf
        for s in stocked:
            r = self._route(s["location_node"], node)
            if r is not None:
                best = min(best, r["minutes"])
        return best + LOAD_MIN + UNLOAD_MIN if best < math.inf else math.inf

    def _rescore(self, now: datetime) -> None:
        # Waiting = queued, delayed, or in progress with servings no truck has taken yet
        # (those compete for the next free truck by priority, like everyone else).
        waiting = [t for t in self.tickets.values()
                   if t["status"] in ("Prioritized", "Delayed")
                   or (t["status"] == "In Progress" and self.remaining(t["ticket_id"]) > 0)]
        for t in waiting:
            sc = self._score(t, now)
            if t["status"] in ("Prioritized", "In Progress"):
                self._push(t, sc)
        waiting.sort(key=lambda t: (-self.meta[t["ticket_id"]]["score"].value, t["deadline"],
                                    t["created_at"], t["ticket_id"]))
        ranking = [t["ticket_id"] for t in waiting]
        if ranking != self._ranking:
            self._ranking = ranking
            self.bus.publish("priority-changed", {"ranking": [
                [tid, round(self.meta[tid]["score"].value, 1)] for tid in ranking]}, now)

    def _dispatch(self, now: datetime) -> None:
        while (item := self.queue.pop_valid()) is not None:
            tid = item[0]
            t = self.tickets[tid]
            need = self.remaining(tid)
            if need <= 0:
                raise RuntimeError(f"ticket {tid} was queued with nothing left to deliver")
            node = self._req[t["req_id"]]["location_node"]
            fleet = self.vehicles
            if not t["refrigerated"] and self._cold_demand_waiting():
                fleet = [v for v in self.vehicles if not v["refrigerated"]]   # keep reefers for cold food
            res = assign(t, node, need, self.suppliers, fleet, self._route)
            if t["status"] == "In Progress":
                # Top-up of a partly covered ticket: more trucks join, the status does not change
                # (route-updated is published per truck). Depletion was already reported.
                for a in res.assignments:
                    self._start_delivery(a, t, node, now)
                continue
            if res.depleted:
                self.bus.publish("resource-depleted", {
                    "ticket_id": tid, "food": "cold" if t["refrigerated"] else "normal",
                    "servings_short": res.remaining, "reason": res.reason}, now)
            if not res.assignments:
                self.meta[tid]["blocked"] = "no_route" if res.reason.startswith("no route") else "resources"
                self.sm.transition(t, "Delayed", res.reason, now)
                continue
            self.meta[tid]["blocked"] = None
            plan = ", ".join(f"{a.vehicle_id} takes {a.servings_assigned} from {a.supp_id}" for a in res.assignments)
            if res.remaining:
                plan += f"; {res.remaining} servings wait ({res.reason})"
            self.sm.transition(t, "Resource Assigned", plan, now)
            etas = [self._start_delivery(a, t, node, now) for a in res.assignments]
            self.sm.transition(t, "In Progress", f"{len(etas)} vehicle(s) departed; first arrival in "
                                                 f"{min(etas):.1f} min", now)

    def _fail_overdue(self, now: datetime) -> None:
        grace = timedelta(minutes=FAIL_GRACE_MIN)
        for t in list(self.tickets.values()):
            tid = t["ticket_id"]
            if (t["status"] == "Delayed" and self.meta[tid]["blocked"] == "no_route"
                    and now > t["deadline"] + grace and not self._active(tid)):
                self.sm.transition(t, "Failed", f"still no route {FAIL_GRACE_MIN:g} min after the deadline "
                                                f"({t['deadline'].isoformat()})", now)

    def _requeue_delayed(self, reason: str, now: datetime, kinds: set[str], vehicle: dict | None = None) -> None:
        """Delayed -> Prioritized for tickets the change may help (statement: resources freed,
        road reopened, stock added)."""
        for t in list(self.tickets.values()):
            tid = t["ticket_id"]
            if t["status"] != "Delayed" or self.meta[tid]["blocked"] not in kinds or self._active(tid):
                continue
            if vehicle is not None and t["refrigerated"] and not vehicle["refrigerated"]:
                continue   # a freed ordinary truck cannot help a cold ticket
            self.sm.transition(t, "Prioritized", reason, now)
            self._push(t, self._score(t, now))

    def _cold_demand_waiting(self) -> bool:
        return any(t["refrigerated"] and t["status"] in ("Prioritized", "Delayed", "In Progress")
                   and self.remaining(t["ticket_id"]) > 0 for t in self.tickets.values())

    def _active(self, tid: int) -> bool:
        return any(d.ticket_id == tid and d.status in ACTIVE for d in self.deliveries)

    # ----------------------------------------------------------- deliveries ----
    def _build_router(self) -> None:
        fn = self._router_factory(self.t["nodes"], self.t["roads"])
        cache: dict[tuple[int, int], dict | None] = {}

        def route(a: int, b: int):
            if a == b:
                return {"path": [a], "edges": [], "minutes": 0.0, "km": 0.0}
            if (a, b) not in cache:
                cache[(a, b)] = fn(a, b)
            return cache[(a, b)]
        self._route = route

    def _supplier(self, supp_id: str) -> dict:
        for s in self.suppliers:
            if s["supp_id"] == supp_id:
                return s
        raise KeyError(f"unknown supplier {supp_id!r}")

    def _plan(self, start: int, stops: list[tuple[str, int]]) -> tuple[list[Segment], list[int]] | None:
        segs, nodes, cur = [], [start], start
        for kind, node in stops:
            r = self._route(cur, node)
            if r is None:
                return None
            for edge_id, a, b in zip(r["edges"], r["path"], r["path"][1:]):
                road = self._road[edge_id]
                segs.append(Segment("drive", road["weight"], a, b, edge_id, road["distance_km"]))
            nodes += r["path"][1:]
            segs.append(Segment(kind, LOAD_MIN if kind == "load" else UNLOAD_MIN, node, node))
            cur = node
        return segs, nodes

    def _start_delivery(self, a, t: dict, req_node: int, now: datetime) -> float:
        v, s = self._veh[a.vehicle_id], self._supplier(a.supp_id)
        plan = self._plan(v["current_node"], [("load", s["location_node"]), ("unload", req_node)])
        if plan is None:
            raise RuntimeError(f"matcher chose {a.vehicle_id}/{a.supp_id} but no route can be rebuilt")
        d = Delivery(self._next_delivery, t["ticket_id"], v["vehicle_id"], s["supp_id"], a.servings_assigned,
                     bool(t["refrigerated"]), s["location_node"], req_node, plan[0], plan[1], assigned_at=now)
        self._next_delivery += 1
        self.deliveries.append(d)
        v["status"] = "Delivering"
        self.bus.publish("route-updated", {"ticket_id": t["ticket_id"], "vehicle_id": d.vehicle_id,
                                           "delivery_id": d.delivery_id, "route_nodes": d.route_nodes,
                                           "eta_min": round(d.eta_min(), 1), "why": "assigned"}, now)
        return d.eta_min()

    def _move(self, d: Delivery, dt: float, now: datetime) -> None:
        while dt > 1e-9 and d.status == "In Progress" and d.seg_idx < len(d.segments):
            seg = d.segments[d.seg_idx]
            left = seg.minutes - d.into
            if dt < left - 1e-9:
                d.into += dt
                return
            dt -= left
            d.into, d.seg_idx = 0.0, d.seg_idx + 1
            self._finish(d, seg, now)

    def _finish(self, d: Delivery, seg: Segment, now: datetime) -> None:
        v = self._veh[d.vehicle_id]
        if seg.kind == "drive":
            v["current_node"] = seg.node_to
            v["fuel"] = max(0.0, v["fuel"] - seg.km * FUEL_PCT_PER_KM[bool(v["refrigerated"])])
            self.bus.publish("vehicle-moved", {"vehicle_id": v["vehicle_id"], "node": seg.node_to,
                                               "fuel": round(v["fuel"], 2), "ticket_id": d.ticket_id}, now)
        elif seg.kind == "load":
            s = self._supplier(d.supp_id)
            stock, reserved = ("cold_stock", "reserved_cold") if d.cold else ("normal_stock", "reserved_normal")
            s[stock] -= d.servings
            s[reserved] -= d.servings
            d.picked_up = True
            if s.get("temporary"):
                if not any(s[k] for k in ("normal_stock", "cold_stock", "reserved_normal", "reserved_cold")):
                    self.suppliers.remove(s)
            else:
                v["fuel"] = 100.0   # refuel at any hub while loading (assumption, ARCHITECTURE.md 5)
        else:  # unload = arrival
            d.status, d.completed_at = "Delivered", now
            v["status"] = "Available"   # EMS rule: free again where it is, not at home
            self.meta[d.ticket_id]["delivered"] += d.servings
            self._after_delivery(self.tickets[d.ticket_id], now)
            self._requeue_delayed(f"vehicle {v['vehicle_id']} is free at node {v['current_node']}", now,
                                  {"resources"}, vehicle=v)

    def _after_delivery(self, t: dict, now: datetime) -> None:
        tid = t["ticket_id"]
        if self._active(tid) or t["status"] != "In Progress":
            return   # other trucks still on the way (or the ticket is waiting on a stuck one)
        left = self.remaining(tid)
        self.sm.transition(t, "Delivered", f"{self.meta[tid]['delivered']} of {t['servings_requested']} "
                                           "servings delivered", now)
        if left == 0:
            self.sm.transition(t, "Resolved", "all servings delivered", now)
        else:
            self.sm.transition(t, "Prioritized", f"partial delivery: {left} servings still needed, re-queued", now)
            self._push(t, self._score(t, now))

    # ---------------------------------------------------------- disruptions ----
    def apply_event(self, ev: dict, now: datetime) -> None:
        typ = ev["type"]
        if typ == "road_closed":
            self.close_road(ev["edge_id"], now)
        elif typ == "road_reopened":
            self.reopen_road(ev["edge_id"], now)
        elif typ == "vehicle_breakdown":
            self.breakdown(ev["vehicle_id"], now)
        elif typ == "vehicle_repaired":
            self.repair(ev["vehicle_id"], now)
        elif typ == "stock_change":
            self.stock_change(ev["supp_id"], ev.get("normal_delta", 0), ev.get("cold_delta", 0), now)
        else:
            raise ValueError(f"unknown event type {typ!r}")

    def _check_events(self, events: list[dict], base: datetime) -> list[tuple[datetime, int, dict]]:
        supp_ids = {s["supp_id"] for s in self.suppliers}
        out = []
        for i, ev in enumerate(events):
            typ = ev.get("type")
            if typ not in EVENT_TYPES:
                raise ValueError(f"scenario event {i}: unknown type {typ!r}; known: {EVENT_TYPES}")
            if typ.startswith("road") and ev.get("edge_id") not in self._road:
                raise ValueError(f"scenario event {i}: unknown road {ev.get('edge_id')!r}")
            if typ.startswith("vehicle") and ev.get("vehicle_id") not in self._veh:
                raise ValueError(f"scenario event {i}: unknown vehicle {ev.get('vehicle_id')!r}")
            if typ == "stock_change" and ev.get("supp_id") not in supp_ids:
                raise ValueError(f"scenario event {i}: unknown supplier {ev.get('supp_id')!r}")
            out.append((base + timedelta(minutes=ev["t_min"]), i, ev))
        return sorted(out, key=lambda x: (x[0], x[1]))

    def close_road(self, road_id: int, now: datetime) -> None:
        road = self._road.get(road_id)
        if road is None:
            raise ValueError(f"unknown road {road_id!r}")
        if road["is_closed"]:
            return
        road["is_closed"] = True
        self._build_router()
        self.bus.publish("road-closed", {"road_id": road_id, "street": road["street"],
                                         "node_a": road["node_a"], "node_b": road["node_b"]}, now)
        why = f"road {road_id} ({road['street']}) closed on the route"
        for d in [d for d in self.deliveries if d.status == "In Progress" and road_id in d.remaining_edges()]:
            self._reroute(d, now, why)   # only deliveries whose REMAINING path uses the road

    def _reroute(self, d: Delivery, now: datetime, why: str) -> None:
        t, v = self.tickets[d.ticket_id], self._veh[d.vehicle_id]
        if t["status"] == "In Progress":
            self.sm.transition(t, "Re-Routing", f"{v['vehicle_id']}: {why}", now)
        closed = sorted(r["road_id"] for r in self.t["roads"] if r["is_closed"])
        cur, keep = d.segments[d.seg_idx], []
        if cur.kind == "drive":
            if d.into > 0 and cur.edge_id not in closed:   # finish this open road first
                frac = (1 - d.into / cur.minutes) if cur.minutes else 0.0
                keep = [Segment("drive", cur.minutes - d.into, cur.node_from, cur.node_to, cur.edge_id, cur.km * frac)]
                anchor = cur.node_to
            else:                                          # turn back to the last junction
                anchor = cur.node_from
        else:                                              # still loading at the supplier
            keep = [Segment(cur.kind, cur.minutes - d.into, cur.node_from, cur.node_to)]
            anchor = cur.node_from
        stops = [] if (d.picked_up or cur.kind == "load") else [("load", d.supplier_node)]
        stops.append(("unload", d.requester_node))
        old_eta = d.eta_min()
        plan = self._plan(anchor, stops)
        if plan is not None:
            d.segments, d.seg_idx, d.into = keep + plan[0], 0, 0.0
            d.route_nodes = plan[1]
            if t["status"] == "Re-Routing":
                self.sm.transition(t, "In Progress", f"alternative route found for {v['vehicle_id']}: "
                                                     f"ETA {d.eta_min():.1f} min (was {old_eta:.1f})", now)
            self.bus.publish("route-updated", {"ticket_id": t["ticket_id"], "vehicle_id": v["vehicle_id"],
                                               "delivery_id": d.delivery_id, "route_nodes": d.route_nodes,
                                               "eta_min": round(d.eta_min(), 1), "why": why}, now)
            return

        v["current_node"] = anchor
        d.segments, d.seg_idx, d.into = [], 0, 0.0
        if d.picked_up:
            d.status = "Delayed"
            note = f"{v['vehicle_id']} waits at node {anchor} with the cargo"
        else:
            d.status, d.completed_at = "Cancelled", now
            s = self._supplier(d.supp_id)
            s["reserved_cold" if d.cold else "reserved_normal"] -= d.servings
            v["status"] = "Available"
            note = f"{v['vehicle_id']} released, {d.servings} servings back at {d.supp_id}"
        reason = (f"no route to {t['req_id']} (node {d.requester_node}) while roads "
                  f"{', '.join(map(str, closed))} are closed; {note}")
        if t["status"] == "Re-Routing":
            self.meta[t["ticket_id"]]["blocked"] = "no_route"
            self.sm.transition(t, "Delayed", reason, now)
        self.bus.publish("route-updated", {"ticket_id": t["ticket_id"], "vehicle_id": v["vehicle_id"],
                                           "delivery_id": d.delivery_id, "route_nodes": [],
                                           "unavailable": True, "why": reason}, now)
        if d.status == "Cancelled":
            self._requeue_delayed(f"vehicle {v['vehicle_id']} is free at node {anchor}", now, {"resources"}, v)

    def reopen_road(self, road_id: int, now: datetime) -> None:
        road = self._road.get(road_id)
        if road is None:
            raise ValueError(f"unknown road {road_id!r}")
        if not road["is_closed"]:
            return
        road["is_closed"] = False
        self._build_router()
        self.bus.publish("road-reopened", {"road_id": road_id, "street": road["street"]}, now)
        for d in [d for d in self.deliveries if d.status == "Delayed"]:
            v, t = self._veh[d.vehicle_id], self.tickets[d.ticket_id]
            plan = self._plan(v["current_node"], [("unload", d.requester_node)])
            if plan is None:
                continue
            d.segments, d.seg_idx, d.into, d.route_nodes, d.status = plan[0], 0, 0.0, plan[1], "In Progress"
            if t["status"] == "Delayed":
                self.sm.transition(t, "In Progress", f"road {road_id} reopened: {v['vehicle_id']} continues, "
                                                     f"ETA {d.eta_min():.1f} min", now)
            self.bus.publish("route-updated", {"ticket_id": t["ticket_id"], "vehicle_id": v["vehicle_id"],
                                               "delivery_id": d.delivery_id, "route_nodes": d.route_nodes,
                                               "eta_min": round(d.eta_min(), 1), "why": "road reopened"}, now)
        self._requeue_delayed(f"road {road_id} ({road['street']}) reopened", now, {"no_route", "resources"})

    def breakdown(self, vehicle_id: str, now: datetime) -> None:
        v = self._veh.get(vehicle_id)
        if v is None:
            raise ValueError(f"unknown vehicle {vehicle_id!r}")
        if v["status"] == "Broken":
            return
        d = next((d for d in self.deliveries if d.vehicle_id == vehicle_id and d.status in ACTIVE), None)
        v["status"] = "Broken"
        node = v["current_node"]
        if d is None:
            self.bus.publish("vehicle-breakdown", {"vehicle_id": vehicle_id, "node": node, "ticket_id": None}, now)
            return
        d.status, d.completed_at = "Cancelled", now
        if d.picked_up:   # the cargo waits at the breakdown node as a temporary pickup point
            self.suppliers.append({
                "dataset_id": self.dataset_id, "supp_id": f"{vehicle_id}-cargo-{d.delivery_id}",
                "name": f"cargo on broken {vehicle_id}", "location_node": node, "address": None,
                "normal_stock": 0 if d.cold else d.servings, "cold_stock": d.servings if d.cold else 0,
                "reserved_normal": 0, "reserved_cold": 0, "temporary": True})
            note = f"{d.servings} servings wait on {vehicle_id} at node {node} for a rescue truck"
        else:
            self._supplier(d.supp_id)["reserved_cold" if d.cold else "reserved_normal"] -= d.servings
            note = f"{d.servings} reserved servings released at {d.supp_id}"
        t = self.tickets[d.ticket_id]
        self.bus.publish("vehicle-breakdown", {"vehicle_id": vehicle_id, "node": node,
                                               "ticket_id": t["ticket_id"], "note": note}, now)
        if t["status"] == "In Progress" and not self._active(t["ticket_id"]):
            self.meta[t["ticket_id"]]["blocked"] = "resources"
            self.sm.transition(t, "Delayed", f"vehicle {vehicle_id} broke down at node {node}; {note}", now)
            self._requeue_delayed(f"rescue: {note}", now, {"resources"})

    def repair(self, vehicle_id: str, now: datetime) -> None:
        v = self._veh.get(vehicle_id)
        if v is None or v["status"] != "Broken":
            raise ValueError(f"vehicle {vehicle_id!r} is not broken")
        v["status"] = "Available"
        self.bus.publish("vehicle-repaired", {"vehicle_id": vehicle_id, "node": v["current_node"]}, now)
        self._requeue_delayed(f"vehicle {vehicle_id} repaired", now, {"resources"}, vehicle=v)

    def stock_change(self, supp_id: str, normal_delta: int, cold_delta: int, now: datetime) -> None:
        s = self._supplier(supp_id)
        for col, reserved, delta in (("normal_stock", "reserved_normal", normal_delta),
                                     ("cold_stock", "reserved_cold", cold_delta)):
            new = s[col] + delta
            if new < s[reserved]:   # cannot go below zero or below servings already promised to trucks
                self.notes.append(f"[WARN] {supp_id} {col}: {s[col]} {delta:+d} = {new} is below the "
                                  f"{s[reserved]} servings reserved for trucks; set to {s[reserved]}")
                new = s[reserved]
            s[col] = new
        self.bus.publish("stock-changed", {"supp_id": supp_id, "normal_stock": s["normal_stock"],
                                           "cold_stock": s["cold_stock"]}, now)
        if normal_delta > 0 or cold_delta > 0:
            self._requeue_delayed(f"stock added at {supp_id}", now, {"resources"})

    # ------------------------------------------------------------- snapshot ----
    def snapshot(self) -> dict:
        """JSON-friendly view of the whole state, for the API / dashboard."""
        def tk(t):
            m = self.meta[t["ticket_id"]]
            sc = m["score"]
            return {"ticket_id": t["ticket_id"], "req_id": t["req_id"], "status": t["status"],
                    "severity": t["severity"], "refrigerated": t["refrigerated"],
                    "servings_requested": t["servings_requested"], "delivered": m["delivered"],
                    "remaining": self.remaining(t["ticket_id"]), "deadline": t["deadline"].isoformat(),
                    "priority_score": t["priority_score"],
                    "breakdown": {k: round(x, 2) for k, x in sc.breakdown.items()} if sc else None,
                    "flags": list(sc.flags) if sc else []}
        return {
            "dataset_id": self.dataset_id, "now": self.now.isoformat(), "policy": self.policy,
            "ranking": list(self._ranking),
            "tickets": [tk(t) for t in self.tickets.values()],
            "vehicles": [{k: v[k] for k in ("vehicle_id", "name", "status", "current_node", "fuel",
                                            "capacity", "refrigerated")} for v in self.vehicles],
            "suppliers": [{**{k: s[k] for k in ("supp_id", "name", "location_node", "normal_stock", "cold_stock",
                                                "reserved_normal", "reserved_cold")},
                           "temporary": bool(s.get("temporary"))} for s in self.suppliers],
            "closed_roads": [r["road_id"] for r in self.t["roads"] if r["is_closed"]],
            "deliveries": [{"delivery_id": d.delivery_id, "ticket_id": d.ticket_id, "vehicle_id": d.vehicle_id,
                            "supp_id": d.supp_id, "servings": d.servings, "status": d.status,
                            "picked_up": d.picked_up, "route_nodes": d.route_nodes,
                            "remaining_edges": d.remaining_edges(), "eta_min": round(d.eta_min(), 1)}
                           for d in self.deliveries],
            "rejected": [{"ticket": {k: str(v) for k, v in r.items()}, "errors": [list(e) for e in errs]}
                         for r, errs in self.rejected],
        }
