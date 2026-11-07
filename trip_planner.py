# trip_planner.py - plan one truck's trip: start -> supplier -> 1..3 delivery stops
# Author: Jagan (team H/A/J). AI assistance: Claude (Anthropic) generated this
# skeleton (structure, comments); the feasibility checks were written by the author.
#
# Idea: with at most MAX_STOPS stops there are at most 3! = 6 possible orders,
# so we simply TRY EVERY ORDER, cost each one with shortest_path(), and keep
# the fastest order that meets every deadline. If no order works, we explain
# the closest miss ("best order arrives N min late") instead of just saying no.
#
# Input formats (matching / the front end build these):
#   vehicle = {"id": "V2", "capacity": 60, "refrigerated": False}
#   stop    = {"id": "T1", "node": 22, "servings": 10,
#              "refrigerated": False, "deadline_min": 45}   # minutes from now

import itertools
from dataclasses import dataclass

import constants as C
import routing as R


@dataclass
class Trip:
    order: list          # ticket ids in delivery order
    legs: list           # Route objects: start->supplier, supplier->stop1, ...
    etas: dict           # ticket id -> planned arrival, minutes from now (with buffer)
    total_minutes: float # driving minutes for the whole trip (no buffer)
    total_km: float


def plan_trip(graph, start_node, supplier_node, stops, vehicle):
    """Return Trip, or R.Unavailable explaining why the trip can't be done."""
    if not stops:
        raise ValueError("plan_trip needs at least one stop")
    if len(stops) > C.MAX_STOPS:
        raise ValueError(f"at most {C.MAX_STOPS} stops per trip")

    # --- 1. checks that don't depend on the route ---------------------------
    total_servings = sum(s["servings"] for s in stops)
    if total_servings > int(vehicle["capacity"]):                                  #  more food than the truck holds?
        return R.Unavailable(
            C.NO_SUITABLE_VEHICLE,
            f"{vehicle['id']} holds {vehicle['capacity']} servings; "
            f"these stops need {total_servings}",
            {"capacity": vehicle["capacity"], "needed": total_servings},
        )

    needs_cold = any(s["refrigerated"] for s in stops)
    if needs_cold and not bool(vehicle["refrigerated"]) :                                  #  cold food but truck isn't a reefer?
        return R.Unavailable(
            C.NO_SUITABLE_VEHICLE,
            f"{vehicle['id']} is not refrigerated; a stop needs cold food",
            {"vehicle": vehicle["id"]},
        )

    # --- 2. drive to the supplier first (same for every order) --------------
    to_supplier = R.shortest_path(graph, start_node, supplier_node)
    if isinstance(to_supplier, R.Unavailable):
        return to_supplier

    best = None          # fastest order that meets every deadline
    closest_miss = None  # (order ids, minutes late) of the least-late order
    blocked = None       # an Unavailable if some stop can't be reached at all

    # --- 3. try every order of the stops --------------------------------------
    for order in itertools.permutations(stops):
        travel = to_supplier.minutes      # driving minutes so far
        here = supplier_node
        legs = [to_supplier]
        etas = {}
        worst_late = 0.0                  # most minutes late over all stops (<= 0 = on time)
        reachable = True

        for k, stop in enumerate(order, start=1):
            leg = R.shortest_path(graph, here, stop["node"])
            if isinstance(leg, R.Unavailable):
                blocked = leg
                reachable = False
                break
            travel += leg.minutes
            legs.append(leg)
            here = stop["node"]

            eta = R.planned_eta_minutes(travel, stops=k)   # includes unloading + buffer
            etas[stop["id"]] = eta
            late = eta - stop["deadline_min"]                   #  minutes after the deadline (negative = early)
            worst_late = max(worst_late, late)

        if not reachable:
            continue

        ids = [s["id"] for s in order]
        if worst_late <= 0:
            # every stop on time: keep it if it's the fastest so far
            if best is None or travel < best.total_minutes:                      #  no best yet, OR this trip is faster
                best = Trip(ids, legs, etas, travel, sum(l.km for l in legs))
        else:
            # some stop is late: remember the least-late order for the explanation
            if closest_miss is None or worst_late < closest_miss[1]:                      #  no miss yet, OR this one is less late
                closest_miss = (ids, worst_late)

    # --- 4. answer -----------------------------------------------------------
    if best is not None:
        return best
    if closest_miss is not None:
        ids, late = closest_miss
        return R.Unavailable(
            C.DEADLINE_UNREACHABLE,
            f"Best order {ids} still arrives {late:.1f} min late",
            {"best_order": ids, "minutes_late": round(late, 1)},
        )
    return blocked   # every order hit a stop with no open road
