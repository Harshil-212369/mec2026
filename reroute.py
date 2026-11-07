# reroute.py - handle a road closure for trucks that are already driving
# Author: Jagan (team H/A/J). AI assistance: Claude (Anthropic) generated this
# skeleton (structure, comments); the re-routing logic was completed by the author.
#
# Idea: when a road closes, only trucks whose REMAINING route uses that road
# are affected. For each one, plan again from where the truck is now, through
# its remaining stops in the same order. If a stop can no longer be reached,
# explain why (REROUTE_FAILED) so the ticket can go to Delayed / Failed.
#
# Active trip format (kept by matching / the simulation):
#   {"id": "V2",              # trip or vehicle id
#    "current_node": 14,      # node the truck is at / heading to next
#    "stops": [22, 47],       # remaining delivery nodes, in order
#    "edges": [28, 43, ...]}  # edge ids still to drive
#
# State machine (done by the caller): affected ticket -> "Re-Routing", then
#   Route       -> back to "In Progress" (publish route-updated)
#   Unavailable -> "Delayed" or "Failed" with result.message as the reason

import constants as C
import routing as R


def plan_remaining(graph, current_node, stops):
    """Chain shortest paths: current_node -> stops[0] -> stops[1] -> ...
    Returns one combined R.Route, or R.Unavailable(C.REROUTE_FAILED, ...)."""
    nodes = [current_node]
    edges = []
    minutes = 0.0
    km = 0.0
    here = current_node

    for stop_node in stops:
        leg = R.shortest_path(graph, here, stop_node)
        if isinstance(leg, R.Unavailable):
            stop_name = graph["nodes"][stop_node]["name"] if stop_node in graph["nodes"] else stop_node
            return R.Unavailable(
                C.REROUTE_FAILED,
                f"No open road from the truck's position to {stop_name}",
                {"stuck_at": current_node, "unreachable_stop": stop_node,
                 "closed_edges": sorted(graph["closed"])},
            )
        nodes += leg.nodes[1:]        # skip the first node: it's already the last one we added
        edges += leg.edges
        minutes += leg.minutes               # add this leg's driving time
        km += leg.km
        here = stop_node                   # the next leg starts where this one ended

    return R.Route(nodes, edges, minutes, km)


def handle_road_closed(graph, active_trips, edge_id):
    """Close the road, then re-plan every affected trip.
    Returns {trip_id: Route or Unavailable} for AFFECTED trips only."""
    R.close_road(graph, edge_id)
    results = {}
    for trip in active_trips:
        if edge_id not in trip["edges"]:                      # this trip's remaining edges don't use the closed road. if closed road is not on this list then continue, else reroute
            continue                  # not affected: leave it alone
        results[trip["id"]] = plan_remaining(graph, trip["current_node"], trip["stops"])
    return results
