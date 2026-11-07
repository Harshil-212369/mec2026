# Architecture: Urban Food Crisis Response & Routing System

AI-assisted: drafted with Claude (Anthropic), reviewed/modified by the team.

## 1. Requirements
**Functional:** submit and validate crisis tickets → score → heap queue → greedy match (hub + truck) → Dijkstra/A* route → simulate movement → handle road closure, breakdown, stock depletion → state machine with timestamped history → pub/sub events → live dashboard. The same code must run any dataset JSON.

**Non-functional:**
| Need | Target | Why |
|---|---|---|
| Runs on a judge's laptop | `pip install -r requirements.txt && python run.py --dataset X.json` | Judges must run it; a Postgres install is a risk |
| Deterministic | Same scenario gives the same result | Demo can be repeated, tests are stable |
| Responsive | Re-plan in < 50 ms for about 1,000 nodes | Dijkstra is O(E log V), so this is trivial |
| Explainable | Every decision logged with a reason | Rubric: "justify decisions" |

**Constraints:** 3 people, about 3.5 h, Python. Dijkstra/A*, heap and greedy are written by us.

## 2. High-level design
```
            ┌──────────────────────────── Browser (Leaflet + OSM tiles) ───────────────────────────┐
            │  Fleet tracker  |  Map (click road = close)  |  Crisis queue + event log  |  Controls │
            └──────────▲───────────────────────────┬──────────────────────────────────────────────┘
               WebSocket /ws (push)            REST (commands)
                       │                           │
┌──────────────────────┴───────────────────────────▼───────────────────────────────────────────┐
│ api/main.py (FastAPI) - thin layer: parse → validate → engine.command(...) → return          │
├───────────────────────────────────────────────────────────────────────────────────────────────┤
│ core/engine.py  - ONE Engine object = the single source of truth (in memory)                  │
│   ├─ loader.py      JSON → Dataset (+ validation report; unknown fields ignored)             │
│   ├─ graph.py       adjacency list, closures, traffic multipliers, Dijkstra, A*  [J]         │
│   ├─ scoring.py     weighted score + breakdown; policy presets from config      [H]          │
│   ├─ heap.py        own binary max-heap; lazy invalidation by version           [H]          │
│   ├─ matcher.py     greedy hub+truck assignment, reservations, fuel check       [H]          │
│   ├─ state.py       transition table; illegal → error; writes history           [H]          │
│   ├─ events.py      EventBus: subscribe(topic, fn) / publish(topic, data)                    │
│   └─ sim.py         SimClock tick: move trucks, fire scenario events, rescore, dispatch      │
├───────────────────────────────────────────────────────────────────────────────────────────────┤
│ Subscribers on the EventBus:  ws_broadcaster (→ browser)  |  audit_log (→ JSONL or Postgres)  │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Key decision: in-memory engine, database optional
| Option | Upside | Downside | Verdict |
|---|---|---|---|
| Postgres as source of truth | Durable, the given schema | Judges must install and seed it; slower to build; transactions needed against double-booking | ✗ |
| **In-memory engine + audit log** | Zero setup, deterministic, single writer means no race conditions | Lost on restart | **✓ now** |
| Postgres write-behind (the audit_log subscriber writes `ticket_history`, `system_events`, `deliveries`) | Shows the schema is used | 30 min of work | Only if time; enable with `--db URL` |

**Double assignment** is prevented because every mutation goes through `Engine` under a single `asyncio.Lock`. A truck is `Reserved` and hub stock is `reserved_*` **before** the route is published, so one thing can only be assigned once.

## 3. Data flow (one ticket)
```
POST /tickets → validate (422 on error) → state Open → crisis.created
   → score() → heap.push → state Prioritized
sim tick (every 1 s real = N sim-min):
   rescore all (aging, traffic) → priority.changed if rank moved
   while heap and free trucks: t = heap.pop_valid()
       matcher.assign(t) → for each (truck, hub): eta = A*(truck→hub) + A*(hub→req) + load + unload
                         → pick min feasible (fuel, capacity, reefer, route exists)
       ok   → reserve → state Resource Assigned → In Progress → route.updated
       none → state Delayed (reason) → resource.depleted if stock is the cause
   move trucks along route by elapsed sim-minutes (edge w × traffic factor)
   arrival → Delivered → Resolved (or re-queue the remainder) → crisis.resolved
   truck → Available at CURRENT node (EMS rule) → next job or go to nearest stocked hub
```

## 4. Disruptions (all reuse the same re-route function)
| Input | Engine action | Events |
|---|---|---|
| Close road (click edge) | `graph.close(e)`; re-route only deliveries whose **remaining** path uses e | road.closed, route.updated |
| **Flood zone** (click map + radius) [judge tip, Calgary] | close every edge with an endpoint inside the radius, then as above | road.closed ×n |
| **Traffic** toggle: Normal / Rush hour [judge tip] | `traffic_factor` on urban, non-highway edges (×1.6 rush hour); recompute ETAs, rescore (deadline term changes) | route.updated, priority.changed |
| Truck breakdown | truck → Broken; its ticket → Delayed; dispatch a rescue truck to the breakdown node to take over the cargo | vehicle.breakdown |
| Stock runs out | matcher finds no hub → Delayed | resource.depleted |

Traffic and flood are about 20 min each because they reuse `close()` and re-route. Build them **after** the 4:00 integration milestone.

**Live data:** a `ConditionsProvider` interface (`get_closures()`, `get_traffic_factor(edge)`) is fed by the UI buttons and scenario files today. A real feed (city closure API, Waze for Cities) would plug in here later. We do **not** route with Google Maps: that replaces our algorithm (rule 4.3) and needs keys plus a network connection.

## 5. Assumptions (state them in the README)
| Item | Value | Basis |
|---|---|---|
| `w` | travel minutes | w/km = 2.4 / 2.727 in Dataset 1 |
| Fuel field | % of a 100 L tank (so 1% = 1 L) | dataset gives 100 = full |
| Consumption | truck 25 L/100 km → **0.25 %/km**; reefer 30 L/100 km → **0.30 %/km** (cooling unit) | typical medium box-truck range |
| Idle burn | 0 | stated simplification |
| Reserve | never plan below 15 % | safety margin |
| Refuel | at any hub, to 100 %, adds 10 min | data silent |
| Load at hub | 10 min; unload at site 10 min | reasonable service time |
| Capacity unit | servings; cold food only in reefers; normal food may use reefers only if no truck is free | protects scarce reefers |
| Trucks | may load at any hub, need not return home | EMS "nearest available unit" |
| Rush hour | ×1.6 on urban, non-highway edges | typical peak congestion |

At 0.25 %/km a full tank is about 340 usable km, so fuel will not bind in a town. The check exists for regional scale. In the demo, show it with one truck that starts at 5 % fuel (set in the scenario).

## 6. API (stable contract)
`GET /state`, `GET /datasets`, `POST /datasets/load`, `POST /tickets`, `POST /roads/{id}/close|reopen`, `POST /zones/flood {lat,lng,radius_km}`, `POST /traffic {mode}`, `POST /vehicles/{id}/breakdown|repair`, `POST /policy {preset}`, `POST /sim/start|pause`, `POST /scenario/load`, `GET /tickets/{id}/history`, `WS /ws`.

## 7. Error handling
- Validation errors → 422 with field messages; they never reach the engine.
- No route → ticket Delayed or Failed with a **human-readable reason** (which closures block it).
- An illegal state transition raises, is logged, and the engine state stays unchanged.
- Dataset problems (unknown node in an edge, negative w, duplicate id) → the bad record is skipped and listed in the load report. The system still starts.

## 8. Scale (for the "innovation & scalability" slide)
| Today | At city or country scale |
|---|---|
| 1 process, in memory | Engine per region, Postgres/PostGIS as source of truth, Redis pub/sub instead of the in-process bus |
| Dijkstra/A* per request | Contraction hierarchies, cached hub→node trees (one Dijkstra per hub, reused) |
| Greedy one-ticket-at-a-time | Batched assignment (Hungarian / min-cost flow) every N seconds |
| Hand-set weights + presets | Learn weights from dispatcher overrides (this is where ML fits) |
| Buttons for traffic/flood | Live feeds (city 311 / closure APIs, OSM HOT updates), SMS intake for low-connectivity areas |

## 9. Revisit later
Persistence and restart recovery · multi-stop loads (one truck, several tickets) · real driver mobile app · authentication and roles.
