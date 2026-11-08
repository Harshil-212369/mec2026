"""FastAPI layer: thin. Parse -> engine command -> return state. Every engine event is pushed
to WebSocket clients as {"type", "dataset_id", "ts", "data"} (statement 3.1 "System events").

One engine, one asyncio lock: commands and sim ticks never interleave (no double booking).
Runs fully offline; the Postgres source is optional (MEC_DATABASE_URL, read-only).

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
Framework: FastAPI WebSocket pattern from https://fastapi.tiangolo.com/advanced/websockets/
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from core.constants import POLICIES
from core.engine import Engine
from core.random_dataset import generate
from core.routing import get_router_factory
from core.tables import REPO, InputError, from_data, from_json, from_pg_dump, from_postgres

DATA = REPO / "data"
WEB = REPO / "web"
TICK_SECONDS = 1.0   # real seconds per sim tick; each tick advances `speed` sim-minutes


class AppState:
    def __init__(self) -> None:
        self.engine: Engine | None = None
        self.spec: dict = {}
        self.router_factory, self.router_name = get_router_factory()
        self.running = False
        self.started = False
        self.speed = 1.0
        self.lock = asyncio.Lock()
        self.clients: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []


STATE = AppState()


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _send_all(message: dict) -> None:
    text = json.dumps(message, default=str)
    for loop, queue in list(STATE.clients):
        loop.call_soon_threadsafe(queue.put_nowait, text)


def _on_event(row: dict) -> None:
    _send_all({"type": row["event_type"], "dataset_id": row["dataset_id"],
               "ts": _iso(row["created_at"]), "data": row["details"]})


def _in_repo(path: str) -> Path:
    p = (REPO / path).resolve()
    if REPO not in p.parents and p != REPO:
        raise HTTPException(400, f"path must be inside the project folder: {path}")
    return p


def load(spec: dict) -> Engine:
    """spec: {"source": "json"|"dump"|"postgres", "path", "scenario", "dataset_id", "policy"}"""
    source = spec.get("source", "json")
    try:
        if source == "json":
            bundle = from_json(_in_repo(spec["path"]), _in_repo(spec["scenario"]) if spec.get("scenario") else None)
        elif source == "dump":
            bundle = from_pg_dump(_in_repo(spec["path"]))
        elif source == "postgres":
            bundle = from_postgres()
        elif source == "random":   # no input file at all: generated city + tickets + disruptions
            seed = spec.get("seed")
            if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool) or seed < 0):
                raise HTTPException(400, "seed must be a whole number >= 0")
            ds, sc = generate(seed)
            spec = {**spec, "seed": int(ds["id"].split("-", 1)[1])}
            bundle = from_data(ds, sc, f"random:{ds['id']}")
        else:
            raise HTTPException(400, f"unknown source {source!r}")
        engine = Engine.from_bundle(bundle, STATE.router_factory, spec.get("dataset_id"),
                                    spec.get("policy", "balanced"))
    except KeyError as exc:
        raise HTTPException(400, f"missing field {exc}") from exc
    except (InputError, ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc
    engine.notes[:0] = bundle.report
    engine.bus.subscribe("*", _on_event)
    STATE.engine, STATE.spec, STATE.running, STATE.started = engine, dict(spec), False, False
    _send_all({"type": "dataset-loaded", "dataset_id": engine.dataset_id, "ts": _iso(engine.now), "data": spec})
    return engine


def _eng() -> Engine:
    if STATE.engine is None:
        raise HTTPException(409, "no dataset loaded: POST /datasets/load first")
    if not STATE.started:
        STATE.engine.advance(0)   # submit tickets due at the start and dispatch them
        STATE.started = True
    return STATE.engine


def state_view() -> dict:
    eng = _eng()
    snap = eng.snapshot()
    ds = eng.t["datasets"][0]
    snap["map"] = {
        "center": [ds["center_lat"], ds["center_lng"]], "zoom": ds["zoom"],
        "nodes": [{k: n[k] for k in ("node_id", "name", "lat", "lng")} for n in eng.t["nodes"]],
        "roads": [{k: r[k] for k in ("road_id", "node_a", "node_b", "street", "is_closed", "is_highway", "terrain")}
                  for r in eng.t["roads"]],
        "requesters": [{k: r[k] for k in ("req_id", "name", "category", "location_node")} for r in eng.t["requesters"]],
    }
    snap["sim"] = {"running": STATE.running, "speed": STATE.speed, "router": STATE.router_name,
                   "source": STATE.spec, "elapsed_min": (eng.now - eng.start).total_seconds() / 60}
    snap["notes"] = list(eng.notes)
    return snap


async def _sim_loop() -> None:
    while True:
        await asyncio.sleep(TICK_SECONDS)
        async with STATE.lock:
            if STATE.running and STATE.engine is not None:
                _eng().advance(STATE.speed)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if STATE.engine is None:
        load({"source": "json", "path": "data/toronto-downtown.json", "scenario": "data/scenario-toronto.json"})
    task = asyncio.create_task(_sim_loop())
    yield
    task.cancel()


app = FastAPI(title="MEC 2026 Urban Food Crisis Response", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/")
def index():
    page = WEB / "index.html"
    if page.exists():
        return FileResponse(page)
    return {"ok": True, "see": "/docs"}


@app.get("/health")
def health():
    return {"ok": True, "router": STATE.router_name, "dataset": STATE.engine.dataset_id if STATE.engine else None}


@app.get("/datasets")
def datasets():
    out = []
    for f in sorted(DATA.glob("*.json")):
        kind = "scenario" if f.name.startswith("scenario") else "dataset"
        out.append({"path": f"data/{f.name}", "kind": kind})
    for f in sorted((REPO / "tests" / "fixtures").glob("*.sql")):
        out.append({"path": f"tests/fixtures/{f.name}", "kind": "dump"})
    return {"available": out, "loaded": STATE.spec}


@app.post("/datasets/load")
async def datasets_load(spec: dict = Body(...)):
    async with STATE.lock:
        eng = load(spec)
        return {"dataset_id": eng.dataset_id, "notes": eng.notes, "router": STATE.router_name}


@app.post("/datasets/random")
async def datasets_random(body: dict = Body(default={})):
    """Generate a random city in the dataset structure (optional {"seed": n}) and load it."""
    async with STATE.lock:
        eng = load({"source": "random", "seed": body.get("seed")})
        return {"dataset_id": eng.dataset_id, "seed": STATE.spec["seed"], "notes": eng.notes}


@app.get("/state")
async def get_state():
    async with STATE.lock:
        return state_view()


def _parse_time(v, now: datetime):
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v)
        except ValueError:
            return v   # validator reports it
        return dt if dt.tzinfo else dt.astimezone()   # no zone given: read as this computer's local time
    return v


@app.post("/tickets", status_code=201)
async def create_ticket(body: dict = Body(...)):
    async with STATE.lock:
        eng = _eng()
        row = {k: v for k, v in body.items() if k not in ("deadline_min", "created_at", "ticket_id", "status")}
        row["created_at"] = eng.now           # submission time = the system clock at submission
        if "deadline_min" in body and isinstance(body["deadline_min"], (int, float)) \
                and not isinstance(body["deadline_min"], bool):
            row["deadline"] = eng.now + timedelta(minutes=body["deadline_min"])
        elif "deadline" in body:
            row["deadline"] = _parse_time(body["deadline"], eng.now)
        row["dataset_id"], row["status"] = eng.dataset_id, "Open"
        errors = eng.submit(row, eng.now)
        if errors:
            return JSONResponse(status_code=422, content={"errors": [{"field": f, "message": m} for f, m in errors]})
        eng.advance(0)
        sc = eng.meta[row["ticket_id"]]["score"]
        return {"ticket_id": row["ticket_id"], "status": row["status"], "priority_score": row["priority_score"],
                "breakdown": {k: round(x, 2) for k, x in sc.breakdown.items()}, "flags": list(sc.flags)}


def _command(fn, *args):
    eng = _eng()
    try:
        fn(*args, eng.now)
    except ValueError as exc:
        status = 404 if "unknown" in str(exc) else 409
        raise HTTPException(status, str(exc)) from exc
    eng.advance(0)   # let requeued tickets dispatch right away
    return state_view()


@app.post("/roads/{road_id}/close")
async def close_road(road_id: int):
    async with STATE.lock:
        return _command(_eng().close_road, road_id)


@app.post("/roads/{road_id}/reopen")
async def reopen_road(road_id: int):
    async with STATE.lock:
        return _command(_eng().reopen_road, road_id)


@app.post("/vehicles/{vehicle_id}/breakdown")
async def breakdown(vehicle_id: str):
    async with STATE.lock:
        return _command(_eng().breakdown, vehicle_id)


@app.post("/vehicles/{vehicle_id}/repair")
async def repair(vehicle_id: str):
    async with STATE.lock:
        return _command(_eng().repair, vehicle_id)


@app.post("/stock/{supp_id}")
async def stock(supp_id: str, body: dict = Body(...)):
    async with STATE.lock:
        eng = _eng()
        try:
            eng._supplier(supp_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return _command(eng.stock_change, supp_id, int(body.get("normal_delta", 0)), int(body.get("cold_delta", 0)))


@app.post("/policy")
async def policy(body: dict = Body(...)):
    async with STATE.lock:
        preset = body.get("preset")
        if preset not in POLICIES:
            raise HTTPException(400, f"preset must be one of {sorted(POLICIES)}")
        eng = _eng()
        eng.set_policy(preset, eng.now)
        return state_view()


@app.post("/sim/start")
async def sim_start(body: dict = Body(default={})):
    async with STATE.lock:
        _eng()
        speed = body.get("speed", STATE.speed)
        if not isinstance(speed, (int, float)) or isinstance(speed, bool) or not 0 < speed <= 60:
            raise HTTPException(400, "speed = sim minutes per real second, 0 < speed <= 60")
        STATE.speed, STATE.running = float(speed), True
        return {"running": True, "speed": STATE.speed}


@app.post("/sim/pause")
async def sim_pause():
    async with STATE.lock:
        STATE.running = False
        return {"running": False}


@app.post("/sim/step")
async def sim_step(body: dict = Body(default={})):
    async with STATE.lock:
        eng = _eng()
        minutes = body.get("minutes", 1)
        if not isinstance(minutes, (int, float)) or isinstance(minutes, bool) or not 0 < minutes <= 600:
            raise HTTPException(400, "minutes must be between 0 and 600")
        eng.run_for(minutes)
        return state_view()


@app.get("/tickets/{ticket_id}/history")
async def history(ticket_id: int):
    async with STATE.lock:
        eng = _eng()
        if ticket_id not in eng.tickets:
            raise HTTPException(404, f"unknown ticket {ticket_id}")
        return [{k: _iso(v) for k, v in h.items()} for h in eng.sm.history if h["ticket_id"] == ticket_id]


@app.get("/events")
async def events(since: int = 0, include_moves: bool = False):
    async with STATE.lock:
        eng = _eng()
        rows = [(i, e) for i, e in enumerate(eng.bus.log) if i >= since
                and (include_moves or e["event_type"] != "vehicle-moved")]
        return [{"id": i, "type": e["event_type"], "ts": _iso(e["created_at"]), "data": e["details"]} for i, e in rows]


@app.websocket("/ws")
async def ws(socket: WebSocket):
    await socket.accept()
    queue: asyncio.Queue = asyncio.Queue()
    entry = (asyncio.get_running_loop(), queue)
    STATE.clients.append(entry)
    try:
        while True:
            await socket.send_text(await queue.get())
    except WebSocketDisconnect:
        pass
    finally:
        STATE.clients.remove(entry)
