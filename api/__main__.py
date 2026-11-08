"""Start the server (offline by default: Toronto + scenario).

  .venv\\Scripts\\python -m api
  .venv\\Scripts\\python -m api --dataset data/synthetic-town-on.json --scenario data/scenario-town.json
  .venv\\Scripts\\python -m api --dump tests/fixtures/aadil_dump_2026-11-07.sql
  .venv\\Scripts\\python -m api --postgres            (MEC_DATABASE_URL, read-only)
  .venv\\Scripts\\python -m api --postgres --write-back   (also writes decisions to his tables)
  .venv\\Scripts\\python -m api --random [SEED]       (generated city: no input file at all)

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
ap.add_argument("--write-back", action="store_true",
                help="with --postgres: write decisions back to the database tables every 3 s")
ap.add_argument("--random", nargs="?", const=-1, type=int, metavar="SEED",
                help="generated city, no input file (optional seed)")
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, default=8000)
args = ap.parse_args()

if args.random is not None:
    load({"source": "random", "seed": None if args.random < 0 else args.random})
elif args.postgres:
    load({"source": "postgres", "write_back": args.write_back})
elif args.write_back:
    ap.error("--write-back needs --postgres")
elif args.dump:
    load({"source": "dump", "path": args.dump})
else:
    scenario = args.scenario
    if scenario is None and args.dataset == "data/toronto-downtown.json":
        scenario = "data/scenario-toronto.json"
    load({"source": "json", "path": args.dataset, "scenario": scenario})
uvicorn.run(app, host=args.host, port=args.port)
