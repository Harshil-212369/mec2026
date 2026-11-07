# routing.py - road graph loading and shortest-path routing (Dijkstra / A*)
# Author: Jagan (team H/A/J). AI assistance: Claude (Anthropic) generated this
# skeleton (signatures, docstrings, hints); function bodies written by the author.
# Algorithm references:
#   Dijkstra, E. W. (1959). A note on two problems in connexion with graphs.
#   Hart, Nilsson & Raphael (1968). A formal basis for the heuristic
#   determination of minimum cost paths (A*).
#
# Rules for this module:
#   - Works on ANY dataset with the same JSON format: no hard-coded node ids,
#     speeds, or "urban" assumptions. Derive everything at load time.
#   - Never return None / inf to callers of shortest_path(): return Route or
#     Unavailable (with a reason code and numbers) so the UI can explain it.

import heapq
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import constants as C

REPO_ROOT = Path(__file__).resolve().parent


# ----------------------------------------------------------------------------
# Result types (done for you)
# ----------------------------------------------------------------------------
@dataclass
class Route:
    nodes: list          # node ids from src to dst, inclusive
    edges: list          # edge ids in travel order
    minutes: float       # sum of edge weights "w"
    km: float            # sum of edge "km"


@dataclass
class Unavailable:
    code: str            # one of the reason codes in constants.py
    message: str         # human-readable, with numbers
    details: dict = field(default_factory=dict)


# ----------------------------------------------------------------------------
# STEP 1 - load the graph
# ----------------------------------------------------------------------------
def load_graph(path):
    """Read a dataset JSON file and return a graph dict:

        {
          "nodes": {node_id: {"name": str, "lat": float, "lng": float}},
          "edges": {edge_id: <the edge dict from the JSON>},
          "adj":   {node_id: [(neighbor_id, edge_id, w), ...]},
          "min_w_per_km": float,   # smallest w/km over all edges (for A*)
          "closed": set(),         # edge ids currently closed
        }

    Hints:
      - open(path, encoding="utf-8") and json.load
      - every node gets an "adj" entry, even if it has no edges
      - roads are two-way: add (b, id, w) to adj[a] AND (a, id, w) to adj[b]
      - skip edges with km == 0 when computing min_w_per_km
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    
    nodes = {n["id"]: {"name": n["name"], "lat": n["lat"], "lng": n["lng"]} for n in data["nodes"]}
    adj = {node_id: [] for node_id in nodes}

    # edges
    edges = {}
    for e in data["edges"]:
        edges[e["id"]] = e
        adj[e["a"]].append((e["b"], e["id"], e["w"]))
        adj[e["b"]].append((e["a"], e["id"], e["w"]))     # the reverse direction

    min_w_per_km = min((e["w"] / e["km"] for e in edges.values() if e["km"] > 0), default=1.0)
    return {"nodes": nodes, "edges": edges, "adj": adj,
        "min_w_per_km": min_w_per_km, "closed": set()}


# ----------------------------------------------------------------------------
# STEP 2 - Dijkstra
# ----------------------------------------------------------------------------
def dijkstra(graph, src, dst):
    """Shortest path by edge weight w, skipping edges in graph["closed"].

    Returns (cost, node_path, edge_path, expanded) or None if dst unreachable.
    `expanded` = number of nodes popped from the heap and processed
    (not counting stale entries) - used for the Dijkstra vs A* benchmark.

    Plan:
      1. dist = {src: 0.0}, prev = {}, heap = [(0.0, src)]
      2. pop smallest; if cost > dist[node] it's stale -> skip
      3. if node == dst -> stop
      4. for each (nbr, eid, w) in adj[node]: skip closed eid;
         if cost + w < dist.get(nbr, inf): update dist, prev[nbr] = (node, eid), push
      5. rebuild the path by walking prev back from dst, then reverse
    """
    dist = {src: 0.0}          # "best times so far"
    prev = {}                  # "came from" notes: node -> (previous node, edge id)
    heap = [(0.0, src)]        # to-do list, always gives the closest first
    expanded = 0

    while heap:
        cost, node = heapq.heappop(heap)    # closest unfinished place
        if cost > dist[node]:               # old entry (like "A = 4" after we found 3)
            continue
        expanded += 1
        if node == dst:                     # destination reached: stop
            break
        for nbr, eid, w in graph["adj"][node]:
            if eid in graph["closed"]:                        # closed road? skip it
                continue
            new_cost = cost + w                 # time to reach nbr through this node
            if new_cost < dist.get(nbr, math.inf):   # beats the old time?
                dist[nbr] = new_cost
                prev[nbr] = (node, eid)
                heapq.heappush(heap, (new_cost, nbr))

    if dst not in dist:                     # never reached: no route
        return None

    # follow the "came from" notes backwards from dst to src
    node_path = [dst]
    edge_path = []
    while node_path[-1] != src:
        prev_node, eid = prev[node_path[-1]]
        edge_path.append(eid)
        node_path.append(prev_node)
    node_path.reverse()
    edge_path.reverse()

    return dist[dst], node_path, edge_path, expanded
# ----------------------------------------------------------------------------
# STEP 3 - A*
# ----------------------------------------------------------------------------
def haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance in km. Earth radius R = 6371 km.

    a = sin^2(dlat/2) + cos(lat1) * cos(lat2) * sin^2(dlng/2)
    d = 2 * R * asin(sqrt(a))          (all angles in radians)
    """
    R = 6371.0                                   # Earth radius in km
    lat1, lng1, lat2, lng2 = map(math.radians, (lat1, lng1, lat2, lng2))
    dlat = lat2 - lat1                                  # difference in latitude
    dlng = lng2 - lng1                                  # difference in longitude
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def heuristic(graph, node, dst):
    """Lower bound on minutes from node to dst:
    haversine_km(node, dst) * graph["min_w_per_km"] * C.ASTAR_SAFETY
    """
    a = graph["nodes"][node]
    b = graph["nodes"][dst]
    km = haversine_km(a["lat"], a["lng"], b["lat"], b["lng"])   # straight-line km
    return km * graph["min_w_per_km"] * C.ASTAR_SAFETY        # km x fastest minutes-per-km x 0.99


def astar(graph, src, dst):
    """Same contract as dijkstra() (same return shape).
    Difference: the heap is ordered by g + h, where g = cost so far and
    h = heuristic(graph, node, dst). Keep a separate dict of g values.
    """
    dist = {src: 0.0}
    prev = {}
    heap = [(heuristic(graph, src, dst), 0.0, src)]   # <-- CHANGED: (guess total, time so far, node)
    expanded = 0

    while heap:
        _, cost, node = heapq.heappop(heap)           # <-- CHANGED: ignore the guess, keep real time
        if cost > dist[node]:
            continue
        expanded += 1
        if node == dst:
            break
        for nbr, eid, w in graph["adj"][node]:
            if eid in graph["closed"]:
                continue
            new_cost = cost + w
            if new_cost < dist.get(nbr, math.inf):
                dist[nbr] = new_cost
                prev[nbr] = (node, eid)
                heapq.heappush(heap, (new_cost + heuristic(graph, nbr, dst), new_cost, nbr))   #  time so far + guess for neighbour nbr

    if dst not in dist:
        return None

    node_path = [dst]
    edge_path = []
    while node_path[-1] != src:
        prev_node, eid = prev[node_path[-1]]
        edge_path.append(eid)
        node_path.append(prev_node)
    node_path.reverse()
    edge_path.reverse()

    return dist[dst], node_path, edge_path, expanded


# ----------------------------------------------------------------------------
# STEP 4 - public API with explainable failures
# ----------------------------------------------------------------------------
def shortest_path(graph, src, dst, algorithm="astar"):
    """Return Route or Unavailable(code=C.NO_ROUTE, ...).

    - also return Unavailable if src or dst is not a node in the graph
    - message should name the nodes (use graph["nodes"][id]["name"])
    - details should include "closed_edges": sorted list of graph["closed"]
    - Route.km = sum of graph["edges"][eid]["km"] over the path
    """
    # unknown node -> explain, don't crash
    if src not in graph["nodes"] or dst not in graph["nodes"]:
        return Unavailable(C.NO_ROUTE, f"Unknown node: {src} or {dst}",
                           {"src": src, "dst": dst})

    search = astar if algorithm == "astar" else dijkstra
    result = search(graph, src, dst)

    if result is None:                       # closures cut the destination off
        src_name = graph["nodes"][src]["name"]
        dst_name = graph["nodes"][dst]["name"]                      # same idea for dst
        return Unavailable(
            C.NO_ROUTE,
            f"No open road from {src_name} to {dst_name}",
            {"closed_edges": sorted(graph["closed"])},          # sorted list of the closed edge ids
        )

    minutes, nodes, edges, _ = result
    km = sum(graph["edges"][eid]["km"] for eid in edges)          # add up each edge's "km"
    return Route(nodes, edges, minutes, km)


def planned_eta_minutes(route_minutes, stops=1):
    """Minutes until delivery, INCLUDING the safety buffer.
    Assumption: the buffer covers traffic and a refuelling stop,
    so fuel is not calculated separately (see constants.py)."""
    buffer = max(C.MIN_BUFFER_MIN, C.BUFFER_PCT * route_minutes)
    return route_minutes + stops * C.SERVICE_TIME_MIN + buffer


def close_road(graph, edge_id):
    """Mark edge closed. (Step 5 will also return affected active trips.)"""
    graph["closed"].add(edge_id)


def reopen_road(graph, edge_id):
    """Undo close_road. Must not fail if the edge was not closed."""
    graph["closed"].discard(edge_id)
