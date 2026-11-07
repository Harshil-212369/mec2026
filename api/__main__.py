"""Start the server (offline by default: Toronto + scenario).

  .venv\\Scripts\\python -m api
  .venv\\Scripts\\python -m api --dataset data/synthetic-town-on.json --scenario data/scenario-town.json
  .venv\\Scripts\\python -m api --dump tests/fixtures/aadil_dump_2026-11-07.sql
  .venv\\Scripts\\python -m api --postgres            (MEC_DATABASE_URL, read-only)

Then open http://127.0.0.1:8000 (live page) or http://127.0.0.1:8000/docs (all endpoints).

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
"""
import argparse

import uvicorn

from api.main import app, load

ap = argparse.ArgumentParser(prog="python -m api")
ap.add_argument("--dataset", default="data/toronto-downtown.json")
ap.add_argument("--scenario", default=None, help="default: data/scenario-toronto.json when --dataset is not given")
ap.add_argument("--dump")
ap.add_argument("--postgres", action="store_true")
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, default=8000)
args = ap.parse_args()

if args.postgres:
    load({"source": "postgres"})
elif args.dump:
    load({"source": "dump", "path": args.dump})
else:
    scenario = args.scenario
    if scenario is None and args.dataset == "data/toronto-downtown.json":
        scenario = "data/scenario-toronto.json"
    load({"source": "json", "path": args.dataset, "scenario": scenario})
uvicorn.run(app, host=args.host, port=args.port)
