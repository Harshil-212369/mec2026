"""Run a scenario through the engine and print the timeline (uses the production router:
Jagan's A* via core/graph.py).

  .venv\\Scripts\\python -m tests.run_scenario data/toronto-downtown.json data/scenario-toronto.json
  .venv\\Scripts\\python -m tests.run_scenario data/synthetic-town-on.json data/scenario-town.json
  .venv\\Scripts\\python -m tests.run_scenario --dump tests/fixtures/aadil_dump_2026-11-07.sql

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
"""
from __future__ import annotations

import argparse

from core.engine import Engine
from core.tables import from_json, from_pg_dump
from core.routing import get_router_factory

QUIET = {"vehicle-moved", "priority-changed", "ticket-status"}


router, ROUTER_NAME = get_router_factory()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", nargs="?")
    ap.add_argument("scenario", nargs="?")
    ap.add_argument("--dump")
    ap.add_argument("--minutes", type=float, default=240)
    ap.add_argument("--step", type=float, default=1.0)
    ap.add_argument("--policy", default="balanced")
    args = ap.parse_args(argv)
    bundle = from_pg_dump(args.dump) if args.dump else from_json(args.dataset, args.scenario)
    eng = Engine.from_bundle(bundle, router, policy=args.policy)

    def clock(ts):
        return f"t+{(ts - eng.start).total_seconds() / 60:6.1f}"

    def show(row):
        if row["event_type"] in QUIET:
            return
        print(f"{clock(row['created_at'])}  EVENT {row['event_type']:<17} {row['details']}")
    eng.bus.subscribe("*", show)
    n_hist = 0
    end_min = args.minutes
    eng.advance(0)
    while True:
        for h in eng.sm.history[n_hist:]:
            old = h["old_status"] or "-"
            print(f"{clock(h['changed_at'])}  ticket {h['ticket_id']:<3} {old:>17} -> {h['new_status']:<17} {h['reason']}")
        n_hist = len(eng.sm.history)
        if (eng.now - eng.start).total_seconds() / 60 >= end_min:
            break
        eng.advance(args.step)

    print("\nRejected tickets:", len(eng.rejected))
    for row, errs in eng.rejected:
        print("  ", row.get("req_id"), "; ".join(f"{f}: {m}" for f, m in errs))
    print("\nFinal:")
    for t in eng.snapshot()["tickets"]:
        print(f"  ticket {t['ticket_id']:<3} {t['req_id']:<4} {t['status']:<12} delivered "
              f"{t['delivered']:>3}/{t['servings_requested']:<3} flags={t['flags']}")
    for n in eng.notes:
        print(" ", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
