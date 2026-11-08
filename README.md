# Urban Food Crisis Response and Routing System

**MEC 2026 Programming Competition** · Team **Deeper Blue** · Harshil, Aadil Shaikh, Jagan

A dispatcher for food emergencies, modelled on how 911 dispatches ambulances. It receives
emergency food requests, validates them, scores how urgent each one is, keeps them in a
heap-based priority queue, greedily assigns food hubs and trucks, routes the trucks with A*
on the road graph, and tracks every request through a state machine. Road closures, truck
breakdowns and stock running out are handled live, and every change is published as an
event and pushed to the dashboard over a WebSocket.

The same program runs **Dataset 1 (Toronto), Dataset 2 (any city in the same format), a
pg_dump of the team database, the live Postgres database, or a randomly generated city**,
with no code changes.

## Run it (Windows, Python 3.11+; tested on 3.14)
```
scripts\setup.cmd                         # once: creates .venv and installs requirements.txt
.venv\Scripts\python -m api               # Toronto + scenario -> open http://127.0.0.1:8000
```
Other inputs (no code change; Tier 1 options need no network):

| Command | Input |
|---|---|
| `.venv\Scripts\python -m api --dataset data\synthetic-town-on.json --scenario data\scenario-town.json` | any dataset JSON (Dataset 2 goes here) |
| `.venv\Scripts\python -m api --random` or `--random 42` | generated city, **no input file** (seed reproduces it) |
| `.venv\Scripts\python -m api --dump tests\fixtures\aadil_dump_2026-11-07.sql` | team database dump (offline) |
| `.venv\Scripts\python -m api --postgres` | live database, read-only (set `MEC_DATABASE_URL` first) |
| `.venv\Scripts\python -m api --postgres --write-back` | also writes decisions back to the database tables every 3 s |

On the page: pick a dataset or press **Random city**, then **Start** (or **+5 min**). Click a
road on the map to select it, then **Close road**; type a vehicle id and press **Breakdown**;
switch the **policy** to re-rank the queue live. All endpoints: http://127.0.0.1:8000/docs

Command-line checks:
```
.venv\Scripts\python -m pytest -q                                   # 153 tests
.venv\Scripts\python -m tests.run_scenario data\toronto-downtown.json data\scenario-toronto.json
.venv\Scripts\python -m core.check_input json data\toronto-downtown.json data\scenario-toronto.json
```

## How it works
| Requirement | Where | What it does |
|---|---|---|
| Crisis submission | `core/validate.py` | Every field required and type-checked (severity 1-5, people > 0, servings > 0, true/false refrigeration, deadline after submission, known location). Bad input -> 422 with a message per field. |
| Priority scoring | `core/scoring.py`, `core/constants.py` | Score 0-100 = weighted severity, people (log-damped for fairness), food still missing, location type, deadline pressure **including travel time**, and waiting time. Every score shows its breakdown ("why this rank"). Presets: balanced, deadline_first, max_people, equity. A deadline we cannot meet is flagged `at_risk` and still served late, not dropped. |
| Heap priority queue | `core/heap.py`, `core/crisis_queue.py` | Our own array binary heap. Re-scoring pushes a new version; stale entries are skipped (lazy deletion). Waiting time raises the score (no starvation). Ties: earlier deadline, then first submitted, then lower ticket id. |
| Route planning | `routing.py` (Jagan), `core/graph.py` | A* with a haversine heuristic (admissible), Dijkstra as reference. Closed roads are skipped; "no route" names the closed roads. |
| Resource matching | `core/matcher.py` | Greedy: for each (truck, hub) pair pick the earliest arrival; cold food only in reefers; reefers kept for cold food; fuel check with reserve; big orders split across trucks. Stock and truck are reserved before the next choice, so nothing is assigned twice. |
| State machine | `core/state.py` | Open, Prioritized, Resource Assigned, In Progress, Re-Routing, Delivered, Resolved, Delayed, Failed. Only allowed transitions; each one stores old/new status, reason and time. Re-Routing happens only when a closed road is on a truck's remaining path. |
| Events | `core/events.py`, `api/main.py` | Publish/subscribe bus: crisis-created, priority-changed, route-updated, resource-depleted, road-closed, vehicle-breakdown, crisis-resolved (+ road-reopened, vehicle-moved, ticket-status, stock-changed), pushed live over WebSocket `/ws`. |
| Engine | `core/engine.py` | Each tick: apply disruptions, move trucks, submit new tickets, re-score, dispatch. Breakdown: cargo waits at the breakdown point and a rescue truck collects it. |
| Inputs | `core/tables.py`, `core/random_dataset.py`, `core/db_sync.py` | All sources become the same table rows (the team Postgres schema). |

## Assumptions (data does not say otherwise)
| Item | Value |
|---|---|
| Edge `w` | travel minutes (w/km is 2.4 or 2.727 in Dataset 1 = 25 / 22 km/h) |
| Fuel | % of a 100 L tank; truck 0.25 %/km, reefer 0.30 %/km; never plan below 15 %; refuel to 100 % at any hub |
| Service time | 10 min loading, 10 min unloading |
| Trucks | may load at any hub; after a delivery a truck is free where it is (nearest-unit rule) |
| No route | ticket stays Delayed (roads may reopen); Failed 60 min after its deadline |

## Dependencies
Python 3.11+ (developed on 3.14). Pinned in `requirements.txt`: FastAPI, Uvicorn, websockets,
psycopg 3 (only for the Postgres options), pytest, httpx (test client), networkx (**tests
only**, as an independent check of our routes; never used by the program). Browser page:
Leaflet 1.9.4 and OpenStreetMap tiles, loaded from the internet; offline the map is hidden
and the rest of the page works.

## Citations
- **Datasets:** `data/toronto-downtown.json` provided by the MEC 2026 organizers (sources listed in the file: City of Toronto Open Data, Fort York Food Bank). `data/synthetic-*.json`, `data/scenario-*.json` and random cities are generated by our own code.
- **Algorithms:** E. W. Dijkstra (1959), "A note on two problems in connexion with graphs". Hart, Nilsson and Raphael (1968), "A formal basis for the heuristic determination of minimum cost paths" (A*). Cormen, Leiserson, Rivest, Stein, *Introduction to Algorithms* (CLRS), ch. 6 (binary heaps) and ch. 24 (shortest paths). Python documentation, `heapq` "Priority Queue Implementation Notes" (lazy deletion with version numbers): https://docs.python.org/3/library/heapq.html
- **Frameworks and libraries:** FastAPI and its WebSocket guide (https://fastapi.tiangolo.com/advanced/websockets/), Uvicorn, psycopg 3, pytest, networkx (tests only), Leaflet (BSD-2), map data (c) OpenStreetMap contributors (ODbL).
- **Generative AI:** Claude Code (Anthropic, Claude Opus 5.5) was used by Harshil to draft and debug `core/`, `api/`, `web/`, `tests/` and this README. Claude (Anthropic) was used by Jagan to draft the skeleton of `routing.py`, `trip_planner.py` and `reroute.py`; the function bodies were written by Jagan. Every AI-assisted file says so in its header. All AI output was reviewed, modified and tested by the team (153 automated tests), and each author can explain their code.

## Repository map
`core/` engine and algorithms · `api/` web server · `web/` dashboard page · `routing.py`, `trip_planner.py`, `reroute.py` Jagan's routing · `data/` datasets and scenarios · `tests/` automated tests · `scripts/` setup · `docs/` problem statement and rubric (verbatim) · `AGENTS.md` team rules
