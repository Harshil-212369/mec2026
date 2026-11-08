---
title: MEC 2026 Programming: approach, dataset, architecture (Day 1 build)
This chat's date: 2026-11-07
Today's date: 2026-11-07
source: https://claude.ai/code/session_01FBV2tfETRm66BaXk8jx6TH
tags: [mec-2026, competition, routing, dijkstra, a-star, heap, greedy, state-machine, pubsub, fastapi, leaflet, system-design, food-security]
Subject:
- 12:47 Shared the Toronto dataset JSON, the friend's Postgres dump, the rules docx, the abstract, the rulebook and an organizer map screenshot. Asked: brainstorm the approach, which courier algorithm is closest (UPS vs U-Haul), how to split work (J = routing, me = choosing A/B, Aadil = UI), what to reuse legitimately, how to build a small-town test dataset.
- 14:16 Asked about fuel, whether to train an ML model, data cleaning, weighted sum vs Bayesian, weights from rubric points, what pois/hubs are, refuelling, converting w, terrain, two models (urban vs suburb), the EMS next-job rule, aging, truck UI requirements, a laptop "road blocked" button, OSM, a Gemini prompt for Aadil, how many dashboards.
- 15:04 Asked whether the JSON is ML training data, what cold/normal mean, hub = source or destination, Google Maps/Gemini for live data. Relayed the judge's Calgary flood + traffic tip. Asked for a system-design architecture and fuel assumptions.
- 15:34 Asked for this KB entry.
---

## What I was trying to do overall
Build the MEC 2026 "Urban Food Crisis Response & Routing System" in an 8-hour sprint (submit by 6:45 PM Sat Nov 7; demo Sun Nov 8, 10 min + 5 min Q&A). Team: me (Harshil), J (Jagan), A (Aadil). The same code must run the Day-2 dataset (a "more open, less-serviced town") with zero code changes.

## What I learned
**Rules / scoring (the revised docx is the authority)**
- Required algorithms: heap-based priority queue with aging and tie-breaks; Dijkstra or A* with closures and rerouting; greedy resource matching with no double-booking; a 9-state machine (Open, Prioritized, Resource Assigned, In Progress, Re-Routing, Delivered, Resolved, Delayed, Failed) with timestamp + reason on every change; pub/sub events (crisis-created, priority-changed, route-updated, resource-depleted, road-closed, vehicle-breakdown, crisis-resolved), WebSocket optional.
- Scorecard /100: Routing 15, Priority queue 10, Resource matching 15, Input validation + scoring 15, State machine 10, Real-time comms 10, Dashboard 5 (optional), Hidden tests/edge cases 10, Outputs + justifying decisions 10.
- Penalties: insufficient citation −50, late −50, absent member −25. Plagiarism = disqualification.
- AI allowed (code gen included) but must be reviewed, explainable and cited in code comments, README and presentation. You can't let a library solve the whole problem (so no OR-Tools VRP, no networkx shortest_path in core). The abstract PDF also bans AI-written presentation scripts, so write the story ourselves.
- Submission: `TeamName_Programming_Code.zip` (README: team, names, title, overview, run steps, dependencies, citations) + `TeamName_Programming_Presentation.pdf`. No edits after the deadline.

**Dataset (toronto-downtown.json)**
- `nodes` = 48 intersections (id, name, lat, lng). `edges` = 82 undirected roads with `km`, `w`, `street`, `hwy`, `terrain`.
- `w` = travel MINUTES: w/km is exactly 2.4 (25 km/h N–S) or 2.727 (22 km/h E–W). Route on `w`; use `km` for fuel.
- `pois` = points of interest: every named place on a node. `hubs` = the POIs that are food SOURCES, with stock `normal` (shelf-stable) and `cold` (refrigerated; only reefer trucks can carry it). Non-hub POIs are DESTINATIONS (P3 hospital, P4 shelter, P5/P6 community).
- Toronto: hubs P0, P1, P2, each 300 normal / 100 cold. 12 trucks = 4 per hub (1 reefer cap 40 + 3 trucks cap 60), fuel 100.
- In Toronto `hwy` is always false and top-level `terrain` is []. Day 2 will likely use them, so the loader must tolerate unknown values and extra fields.
- Tickets and disruptions are NOT in the JSON. They come from the UI form, the API or scenario files.
- The JSON is NOT ML training data: it describes the world, with no past decisions or outcomes, so there is nothing to train on. "Weights" = hand-chosen, justified numbers (weighted multi-criteria score), not ML. Bayesian decision theory doesn't fit (it needs probabilities we don't have).
- The friend's schema already maps to the rubric: `priority_version` (lazy heap invalidation), `reserved_normal/cold` (no double booking), `ticket_history` (state log), `system_events` (event log), `deliveries.route` jsonb.

**Approach / concepts**
- Closest real-world model: EMS / 911 computer-aided dispatch (triage score → heap → nearest suitable unit → route → unit status), not UPS ORION (fixed daily manifests, left-turn avoidance). The U-Haul idea = EMS "system status management" (prepositioning). It only helps if trucks are loaded, so the cheap version: after delivering, a truck becomes Available at its current node and goes to the nearest stocked hub, not home.
- "Live matching to nearest courier" = Uber Eats/DoorDash style: assign each new order to the closest free driver right now instead of pre-planning the day.
- Aging = a request's score rises the longer it waits, so low-priority requests aren't starved.
- Ethics: don't use deadline-only or people-only. Log-damp people (fairness). Include travel time in deadline pressure. A missed deadline is not dropped (D=1 + "at risk" flag). Policy presets (balanced / deadline_first / max_people / equity) re-rank live. Human override with a logged reason.
- One engine, not two models (two would violate "no code changes"). Highways have lower w, so Dijkstra adapts automatically. An urban vs suburban profile can be auto-selected from the data (long edges or highways present → raise travel/deadline weight).
- Don't convert `w`. Use it as cost; on load, print implied speed `60*km/w` as a sanity check. Terrain is already inside `w`; treat it as a label (don't double-count).
- Validation, not "cleaning": reject bad tickets with field-level 422 errors; skip and report bad dataset records.
- OSM = OpenStreetMap (free, community-edited map). Used only as basemap tiles; routing is on the dataset graph. Don't route with Google Maps (replaces our algorithm, needs keys/network) or Gemini (not reliable live data). Instead a `ConditionsProvider` interface fed by UI buttons today, real feeds later.
- Reuse with citation: Python heapq docs "Priority Queue Implementation Notes" (lazy deletion + tie-break pattern), CLRS (heap, Dijkstra), Red Blob Games A* intro, FastAPI WebSocket docs, Leaflet + OSM tiles (attribution required). networkx only in tests to verify our Dijkstra.
- Humanitarian OpenStreetMap Team = argument that OSM works in developing regions ("universal").

**Architecture (ARCHITECTURE.md)**
- One Python process: thin FastAPI layer → a single in-memory Engine (loader, graph, scoring, heap, matcher, state, events, sim) under one asyncio.Lock. Single writer, so no double assignment. EventBus subscribers: WebSocket broadcaster + audit log.
- Postgres optional (`--db` write-behind) because judges must be able to run it with `pip install` + `python run.py --dataset X.json`.
- Dashboard = ONE page, 3 panels: Fleet tracker (one card per truck from JSON count: status, job, load, fuel, ETA; click → route on map) | Map (click road → close; closed = dashed red) | Crisis queue / dispatch board (rank, score, status, deadline, "why this rank" bar) + event log. Palette red/blue only. Mobile driver view dropped; buttons live on the laptop.

**Fuel assumptions (final; the earlier 2%/km was demo-only, replaced)**
| Item | Value |
|---|---|
| Tank | 100 L, so fuel % = litres |
| Truck | 25 L/100 km = 0.25 %/km |
| Reefer | 30 L/100 km = 0.30 %/km |
| Idle | 0 |
| Load / unload | 10 min each, added to ETA |
| Reserve | never plan below 15 % |
| Refuel | any hub, to 100 %, +10 min (data silent) |
| Rush hour | ×1.6 on urban non-highway edges |
Fuel never binds in a town (about 340 usable km). It's a feasibility constraint, not a weight. Demo it with one truck starting at 5 %.

**Synthetic test data I now have**
- `synthetic-town-on.json` (Ontario-like) and `synthetic-town-intl.json` (southern hemisphere / east longitude, catches hard-coded Toronto assumptions). Same schema; 24 nodes, 31 edges; highway (hwy=true), rural/unpaved roads; bridge edge 24 is the only access to P3 (closing it makes P3 unreachable); closing Sideroad 10 (edge 26) reroutes P4 from 10.2 → 32.6 min; P1 hub has 0 cold; 4 trucks.
- `scenario-toronto.json` / `scenario-town.json`: tickets (submit_min/deadline_min relative), timed events (road_closed, road_reopened, vehicle_breakdown, stock_change), plus 7 invalid tickets for validation tests.

## Project decisions I made
- Roles: J = getting from A to B (routing); Harshil = choosing A and B (priority + matching); Aadil = UI/map display.
- Don't spend much time on UI and database.
- Not sure about a mobile part, so the road-blocked button goes on the laptop.
- J is staying (not leaving after lunch); both teammates are present.
- Trucks don't have to return to their home hub or the hub they came from; they can be reallocated by need.
- Follow the revised docx rules; cite Claude and every tool used.
- Demo tells the story of how we built it, not only the technical part.
- Judge's flood-zone and traffic-button tips are extras, only if time allows.
- Judge (available Day 1) is prioritized for business-side advice.

## Open questions / next actions
- Confirm with the team (my recommendation): no ML model (no training data, not scored). Put the effort into routing, tests and validation.
- Does Day-2 dataset ship tickets/events files, or do we enter them? Is `w` still minutes? (Loader must handle both.)
- Freeze the API contract (`/state` shape) with Aadil; Aadil builds from `GEMINI_PROMPT_FOR_AADIL.md` with mock-data fallback.
- Integration milestone at 4:00 PM: create ticket → assigned → route on map.
- Then: events + WebSocket + sim tick; run on synthetic-town-on.json; README + CITATIONS; slides; zip + PDF; submit by 6:30 (deadline 6:45).
- Business questions for the judge: who buys it (city emergency office / food bank networks / NGOs); decide vs recommend + override; default priority policy; SMS intake for low-connectivity areas.
- Demo story: problem → "we dispatch food like 911 dispatches ambulances" → live policy switch re-ranks queue → closure + breakdown live → switch to town dataset, no code change → explain failures/unreachable.

## Tasks I decided that I will do later or may do later
- Flood zone (click + radius closes all edges inside), traffic toggle (Normal / Rush hour ×1.6): about 20 min each, reuse close() + reroute.
- Policy presets UI; aging visual.
- Postgres write-behind (`--db`) into ticket_history / system_events / deliveries.
- Mobile driver view (Delivered / Road blocked / Breakdown).
- i18n (EN/FR + one more) instead of the Google Translate widget.
- Multi-stop deliveries (one truck, several tickets on the way).
- Future-work slide: learn weights from dispatcher overrides (where ML fits), batched assignment (Hungarian / min-cost flow), contraction hierarchies, live closure feeds, SMS intake.
- Cut order if late: policy presets → aging animation → fuel. Never cut validation or citations.

## Snippets worth keeping
**Priority score (0–100, explainable)**
```python
S = severity/5
P = math.log1p(people)/math.log1p(500)            # log-damped: fairness
F = min(1, servings_remaining/200)                 # food shortfall
C = {"hospital":1.0,"shelter":0.9,"community":0.7}.get(cat, 0.5)
D = 1 - clamp((deadline - now - best_eta)/120, 0, 1)   # includes travel time
W = min(1, minutes_waiting/120)                    # aging
score = 100*(.30*S + .20*P + .10*F + .10*C + .20*D + .10*W)
# heap entry: (-score, deadline, created_at, ticket_id, version); tie-break = earlier deadline → FIFO → id
```
Weighted multi-criteria score; return each term × weight as the "why this rank" breakdown. Weights live in config as presets.

**Admissible A\* heuristic (works on any dataset)**
```python
min_rate = min(e["w"]/e["km"] for e in edges if e["km"] > 0)   # minutes per km, fastest road
h = lambda n: haversine_km(pos[n], pos[dst]) * min_rate
```
Straight-line distance × fastest minutes-per-km never overestimates, so A* stays optimal on urban and highway graphs alike.

**Fuel feasibility (constraint, not weight)**
```python
FUEL_PER_KM = {False: 0.25, True: 0.30}   # % per km: truck / reefer
def can_make_trip(v, km_to_hub, km_to_req, km_back_to_nearest_hub):
    need = (km_to_hub + km_to_req + km_back_to_nearest_hub) * FUEL_PER_KM[v.refrigerated]
    return v.fuel - need >= 15.0           # 15 % reserve
```
The truck must be able to reach hub → destination → nearest hub. Refuel to 100 at any hub.

**Road closure → re-route only affected deliveries**
```python
def on_road_closed(edge_id):
    graph.close(edge_id); bus.publish("road.closed", {"edge_id": edge_id})
    for d in deliveries:
        if edge_id not in d.route_edges[d.progress_idx:]:
            continue                                   # spec: don't reroute everything
        sm.transition(t := tickets[d.ticket_id], "Re-Routing", f"edge {edge_id} closed")
        r = plan_from(vehicles[d.vehicle_id].current_node, d.stops)   # chain A* through remaining stops
        if r: d.set_route(r); sm.transition(t, "In Progress", f"alt route ETA {r.minutes:.1f}")
        else: sm.transition(t, "Delayed", f"no route while edge {edge_id} closed")
        bus.publish("route.updated", {"ticket_id": t.id, "route": r.nodes if r else []})
```
The same pattern serves flood zones (close many edges, then this loop) and reopen (re-queue Delayed tickets).

**Dataset sanity check (throwaway Dijkstra, closures)**
```python
def dj(d, s, closed=set()):
    adj = {}
    for e in d["edges"]:
        if e["id"] in closed: continue
        adj.setdefault(e["a"], []).append((e["b"], e["w"])); adj.setdefault(e["b"], []).append((e["a"], e["w"]))
    dist, pq = {s: 0}, [(0, s)]
    while pq:
        c, u = heapq.heappop(pq)
        if c > dist[u]: continue
        for v, w in adj.get(u, []):
            if c + w < dist.get(v, 1e18): dist[v] = c + w; heapq.heappush(pq, (c + w, v))
    return dist   # node -> minutes; missing node = unreachable
```
Quick check that every node is reachable and that closing the bridge cuts P3 off. Testing only; the core needs our own heap.

**Synthetic edge weight (generator)**
```python
km = haversine_km(pos[a], pos[b]) * WINDING[terrain]     # urban 1.0, rural 1.2, unpaved 1.3
w  = km * 60 / SPEED_KMH[terrain]                         # urban 25, rural 50, unpaved 30, highway 80, bridge 40
```
Produces `w` in minutes, matching how Dataset 1 encodes it.

**Files produced in this chat (downloaded):** `mec_starter.zip` (SPEC.md, CITATIONS.md, schema.sql, tools/gen_town_dataset.py, data/toronto-downtown.json, data/synthetic-town-on.json, data/synthetic-town-intl.json, data/scenario-toronto.json, data/scenario-town.json), `ARCHITECTURE.md`, `GEMINI_PROMPT_FOR_AADIL.md`, `core_disruptions_example.py`, `dataset_overview.png`.
