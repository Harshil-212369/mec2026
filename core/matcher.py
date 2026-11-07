"""Greedy resource matching (statement 3.1 "Resource matching").

For one ticket, repeat until it is covered or nothing fits:
  1. suppliers with free stock of the right kind (cold if refrigerated):  stock - reserved >= 1
  2. vehicles that are Available, refrigerated if the food is cold, and have the fuel to go
     vehicle -> supplier -> requester -> nearest supplier and still keep the reserve
  3. among all (vehicle, supplier) pairs pick the best key:
       (reefer used for normal food?, eta, -load, vehicle id, supplier id)
     so normal food uses ordinary trucks first and reefers stay free for cold requests;
     eta = drive to supplier + load + drive to requester + unload
  4. load = min(servings still needed, truck capacity, supplier free stock); reserve the stock
     and mark the truck Reserved BEFORE looking for the next one, so the same truck or the
     same servings can never be given to two emergencies.

Routing is Jagan's: route_fn(src_node, dst_node) -> {"path", "edges", "minutes", "km"} or None.

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from core.constants import FUEL_PCT_PER_KM, FUEL_RESERVE_PCT, LOAD_MIN, UNLOAD_MIN

RouteFn = Callable[[int, int], "dict | None"]


@dataclass
class Assignment:
    ticket_id: int
    supp_id: str
    vehicle_id: str
    servings_assigned: int
    route: list[int]            # nodes: vehicle -> supplier -> requester
    route_edges: list[int]
    route_weight: float         # driving minutes only (the dataset's w)
    route_distance_km: float
    eta_min: float              # driving + loading + unloading

    def as_row(self, dataset_id: str) -> dict:
        """Shaped like Aadil's deliveries table (minus the generated id and timestamps)."""
        return {"dataset_id": dataset_id, "ticket_id": self.ticket_id, "supp_id": self.supp_id,
                "vehicle_id": self.vehicle_id, "servings_assigned": self.servings_assigned,
                "route": self.route, "route_weight": self.route_weight,
                "route_distance_km": self.route_distance_km, "status": "Assigned"}


@dataclass
class MatchResult:
    assignments: list[Assignment] = field(default_factory=list)
    remaining: int = 0          # servings still not covered
    reason: str | None = None   # why matching stopped early (None = fully covered)
    depleted: bool = False      # stopped because stock ran out -> publish resource-depleted


def _free(supplier: dict, cold: bool) -> int:
    if cold:
        return supplier["cold_stock"] - supplier["reserved_cold"]
    return supplier["normal_stock"] - supplier["reserved_normal"]


def _natural(ident: str) -> tuple:
    """'V2' sorts before 'V10'."""
    m = re.search(r"\d+", ident)
    return (ident[:m.start()] if m else ident, int(m.group()) if m else -1, ident)


def assign(ticket: dict, req_node: int, servings_remaining: int, suppliers: list[dict],
           vehicles: list[dict], route_fn: RouteFn) -> MatchResult:
    """Mutates suppliers (reserved_*) and vehicles (status -> Reserved) for what it assigns."""
    if servings_remaining <= 0:
        raise ValueError(f"nothing to match: servings_remaining={servings_remaining}")
    cold = ticket["refrigerated"]
    kind = "cold" if cold else "normal"
    cache: dict[tuple[int, int], dict | None] = {}

    def route(a: int, b: int):
        if a == b:
            return {"path": [a], "edges": [], "minutes": 0.0, "km": 0.0}
        if (a, b) not in cache:
            cache[(a, b)] = route_fn(a, b)
        return cache[(a, b)]

    back = [r["km"] for r in (route(req_node, s["location_node"]) for s in suppliers) if r is not None]
    back_km = min(back) if back else None   # to refuel at the nearest supplier afterwards

    result = MatchResult(remaining=servings_remaining)
    while result.remaining > 0:
        stocked = [s for s in suppliers if _free(s, cold) > 0]
        fleet = [v for v in vehicles if v["status"] == "Available" and (v["refrigerated"] or not cold)]
        if not stocked:
            result.reason, result.depleted = f"no {kind} stock left at any supplier", True
            return result
        if not fleet:
            result.reason = f"no available {'refrigerated ' if cold else ''}vehicle"
            return result

        best, saw_route, saw_low_fuel = None, False, False
        for v in fleet:
            for s in stocked:
                r1 = route(v["current_node"], s["location_node"])
                r2 = route(s["location_node"], req_node)
                if r1 is None or r2 is None or back_km is None:
                    continue
                saw_route = True
                need = (r1["km"] + r2["km"] + back_km) * FUEL_PCT_PER_KM[bool(v["refrigerated"])]
                if v["fuel"] - need < FUEL_RESERVE_PCT:
                    saw_low_fuel = True
                    continue
                load = min(result.remaining, v["capacity"], _free(s, cold))
                eta = r1["minutes"] + LOAD_MIN + r2["minutes"] + UNLOAD_MIN
                key = (bool(v["refrigerated"]) and not cold, eta, -load,
                       _natural(v["vehicle_id"]), _natural(s["supp_id"]))
                if best is None or key < best[0]:
                    best = (key, v, s, r1, r2, load, eta)

        if best is None:
            if not saw_route:
                result.reason = f"no route to requester node {req_node} from any stocked supplier/vehicle"
            else:
                result.reason = f"no vehicle has enough fuel for the trip (reserve {FUEL_RESERVE_PCT:g} %)"
                if not saw_low_fuel:
                    result.reason = "no feasible vehicle"
            return result

        _, v, s, r1, r2, load, eta = best
        v["status"] = "Reserved"
        s["reserved_cold" if cold else "reserved_normal"] += load
        result.assignments.append(Assignment(
            ticket_id=ticket["ticket_id"], supp_id=s["supp_id"], vehicle_id=v["vehicle_id"],
            servings_assigned=load, route=r1["path"] + r2["path"][1:], route_edges=r1["edges"] + r2["edges"],
            route_weight=r1["minutes"] + r2["minutes"], route_distance_km=r1["km"] + r2["km"], eta_min=eta))
        result.remaining -= load
    return result
