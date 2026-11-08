"""Random city generator: same structure as toronto-downtown.json (nodes / edges / pois / hubs /
trucks) plus a scenario (tickets + timed disruptions), so the system runs with NO input file.

Every city is reproducible from its seed. Guarantees, checked by tests: the road network is
connected, every ticket is valid, every event refers to a real road/vehicle/supplier.

Weight model = the one inferred from Dataset 1: w = km * 60 / speed_kmh (travel minutes).
Inspired by tools/gen_town_dataset.py (ours).

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
"""
from __future__ import annotations

import math
import random

SPEED = {"urban_ns": 25.0, "urban_ew": 22.0, "highway": 70.0}   # km/h (Toronto: 25 N-S, 22 E-W)
KINDS = ("hospital", "shelter", "community")


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def _connected(n: int, edges: list[dict]) -> bool:
    adj = {i: [] for i in range(n)}
    for e in edges:
        adj[e["a"]].append(e["b"])
        adj[e["b"]].append(e["a"])
    seen, stack = {0}, [0]
    while stack:
        for v in adj[stack.pop()]:
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return len(seen) == n


def generate(seed: int | None = None) -> tuple[dict, dict]:
    """Return (dataset, scenario) dicts. seed=None picks one (reported in the dataset name)."""
    if seed is None:
        seed = random.SystemRandom().randrange(1, 1_000_000)
    rng = random.Random(seed)
    rows, cols = rng.randint(5, 7), rng.randint(6, 8)
    center = (rng.uniform(-45.0, 60.0), rng.uniform(-125.0, 150.0))     # anywhere on Earth
    ns_km, ew_km = rng.uniform(0.35, 0.6), rng.uniform(0.3, 0.9)
    lat_per_km = 1 / 110.574
    lng_per_km = 1 / (111.320 * math.cos(math.radians(center[0])))
    streets = [f"{i + 1}{'st' if i == 0 else 'nd' if i == 1 else 'rd' if i == 2 else 'th'} St" for i in range(rows)]
    avenues = [f"{n} Ave" for n in ("Maple", "Cedar", "Birch", "Elm", "Oak", "Pine", "Willow", "Ash")[:cols]]

    nodes, grid = [], {}
    for i in range(rows):
        for j in range(cols):
            north = (i - rows / 2) * ns_km + rng.uniform(-0.12, 0.12) * ns_km
            east = (j - cols / 2) * ew_km + rng.uniform(-0.12, 0.12) * ew_km
            nid = len(nodes)
            grid[(i, j)] = nid
            nodes.append({"id": nid, "name": f"{avenues[j]} & {streets[i]}",
                          "lat": round(center[0] + north * lat_per_km, 6),
                          "lng": round(center[1] + east * lng_per_km, 6)})
    pos = {n["id"]: (n["lat"], n["lng"]) for n in nodes}
    highway_col = rng.randrange(cols)

    def edge(a: int, b: int, street: str, kind: str) -> dict:
        km = _haversine_km(pos[a], pos[b])
        return {"a": a, "b": b, "km": round(km, 4), "w": round(km * 60 / SPEED[kind], 4), "street": street,
                "hwy": kind == "highway", "terrain": "highway" if kind == "highway" else "urban"}

    edges = []
    for i in range(rows):
        for j in range(cols):
            if j + 1 < cols:
                edges.append(edge(grid[(i, j)], grid[(i, j + 1)], streets[i], "urban_ew"))
            if i + 1 < rows:
                kind = "highway" if j == highway_col else "urban_ns"
                edges.append(edge(grid[(i, j)], grid[(i + 1, j)], f"Hwy {j + 1}" if kind == "highway" else avenues[j], kind))
    for e in rng.sample(edges, k=len(edges) // 8):        # remove some blocks, never disconnect the city
        rest = [x for x in edges if x is not e]
        if _connected(len(nodes), rest):
            edges = rest
    for k, e in enumerate(edges):
        e["id"] = k
        edges[k] = {"id": k, **{key: e[key] for key in ("a", "b", "km", "w", "street", "hwy", "terrain")}}

    picks = rng.sample(range(len(nodes)), k=rng.randint(2, 4) + rng.randint(4, 7))
    n_hubs = rng.randint(2, 4)
    hub_nodes, req_nodes = picks[:n_hubs], picks[n_hubs:]
    pois, hubs, trucks = [], [], []
    for k, node in enumerate(hub_nodes):
        pid = f"P{k}"
        pois.append({"id": pid, "name": f"Food hub {k + 1} (random)", "kind": "hub", "node": node,
                     "lat": pos[node][0], "lng": pos[node][1], "address": nodes[node]["name"]})
        hubs.append({"poiId": pid, "normal": rng.randrange(150, 351, 10), "cold": rng.randrange(40, 121, 10)})
        for t in range(rng.randint(2, 4)):
            vid = f"V{len(trucks) + 1}"
            reefer = t == 0
            trucks.append({"id": vid, "name": f"{'Reefer' if reefer else 'Truck'} {len(trucks) + 1}", "home": node,
                           "refrigerated": reefer, "capacity": rng.choice((30, 40)) if reefer else rng.choice((40, 50, 60)),
                           "fuel": 100})
    for k, node in enumerate(req_nodes, start=n_hubs):
        kind = rng.choice(KINDS)
        pois.append({"id": f"P{k}", "name": f"{kind.title()} {k} (random)", "kind": kind, "node": node,
                     "lat": pos[node][0], "lng": pos[node][1], "address": nodes[node]["name"]})

    req_ids = [p["id"] for p in pois if p["kind"] != "hub"]
    tickets, submit = [], 0
    for k in range(rng.randint(6, 10)):
        cold = rng.random() < 0.25
        tickets.append({"req_id": rng.choice(req_ids), "crisis_type": rng.choice(("food_shortage", "flood", "fire", "power_outage")),
                        "servings_requested": rng.randrange(20, 81, 5) if cold else rng.randrange(20, 151, 5),
                        "people_affected": rng.randrange(10, 251, 5), "severity": rng.randint(1, 5),
                        "refrigerated": cold, "submit_min": submit, "deadline_min": submit + rng.randrange(30, 181, 5)})
        submit += rng.randint(0, 6)

    closed = rng.sample([e["id"] for e in edges], k=rng.randint(1, 3))
    events = [{"t_min": rng.randint(3, 15), "type": "road_closed", "edge_id": e} for e in closed]
    events.append({"t_min": rng.randint(20, 40), "type": "road_reopened", "edge_id": closed[0]})
    events.append({"t_min": rng.randint(5, 20), "type": "vehicle_breakdown", "vehicle_id": rng.choice(trucks)["id"]})
    events.sort(key=lambda ev: ev["t_min"])

    lats, lngs = [n["lat"] for n in nodes], [n["lng"] for n in nodes]
    dsid = f"random-{seed}"
    dataset = {"id": dsid, "name": f"Random city (seed {seed})",
               "center": [round(sum(lats) / len(lats), 5), round(sum(lngs) / len(lngs), 5)], "zoom": 14,
               "nodes": nodes, "edges": edges, "pois": pois, "hubs": hubs, "trucks": trucks, "terrain": [],
               "sources": [f"Generated by core/random_dataset.py, seed {seed}"],
               "disclosure": "Randomly generated test city: not a real place."}
    scenario = {"dataset_id": dsid, "tickets": tickets, "events": events}
    return dataset, scenario
