# route_demo.py - try the routing on real tickets from the command line (offline)
# Author: Jagan (team H/A/J). AI assistance: Claude (Anthropic) generated this
# demo script; reviewed by the author.
#
# Examples (from C:\dev\mec2026):
#   .venv\Scripts\python scripts\route_demo.py --stop T1:22:10:45
#   .venv\Scripts\python scripts\route_demo.py --truck V1 --stop T1:22:10:45:cold --stop T2:44:15:60
#   .venv\Scripts\python scripts\route_demo.py --stop T1:47:10:60 --close 74 --close 81
#
# --stop  ID:NODE:SERVINGS:DEADLINE_MIN[:cold]   (deadline = minutes from now)
# The truck picks up at its home hub (from the dataset), then delivers.

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import routing as R          # noqa: E402
import trip_planner as TP    # noqa: E402


def parse_stop(text):
    parts = text.split(":")
    if len(parts) not in (4, 5):
        raise SystemExit(f"[FAIL] bad --stop '{text}': use ID:NODE:SERVINGS:DEADLINE_MIN[:cold]")
    return {"id": parts[0], "node": int(parts[1]), "servings": int(parts[2]),
            "deadline_min": float(parts[3]),
            "refrigerated": len(parts) == 5 and parts[4].lower() == "cold"}


def main():
    ap = argparse.ArgumentParser(description="Plan a delivery trip for one truck")
    ap.add_argument("--dataset", default=str(REPO / "data" / "toronto-downtown.json"))
    ap.add_argument("--truck", default="V2", help="vehicle id from the dataset")
    ap.add_argument("--stop", action="append", required=True, type=parse_stop)
    ap.add_argument("--close", action="append", type=int, default=[], help="edge id to close")
    args = ap.parse_args()

    g = R.load_graph(args.dataset)
    raw = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    trucks = {t["id"]: t for t in raw["trucks"]}
    if args.truck not in trucks:
        raise SystemExit(f"[FAIL] unknown truck {args.truck}; options: {', '.join(trucks)}")
    t = trucks[args.truck]
    vehicle = {"id": t["id"], "capacity": t["capacity"], "refrigerated": t["refrigerated"]}
    home = t["home"]

    for eid in args.close:
        R.close_road(g, eid)
        print(f"[INFO] closed edge {eid} ({g['edges'][eid]['street']})")

    name = lambda n: g["nodes"][n]["name"]
    print(f"[INFO] {t['name']} ({t['id']}): capacity {t['capacity']}, "
          f"{'refrigerated' if t['refrigerated'] else 'not refrigerated'}, "
          f"picks up at {name(home)} (node {home})")

    result = TP.plan_trip(g, home, home, args.stop, vehicle)
    if isinstance(result, R.Unavailable):
        print(f"[FAIL] {result.code}: {result.message}")
        print(f"       details: {result.details}")
        return

    print(f"[PASS] order: {' -> '.join(result.order)}   "
          f"driving {result.total_minutes:.1f} min, {result.total_km:.2f} km")
    stops = {s["id"]: s for s in args.stop}
    for leg, tid in zip(result.legs[1:], result.order):
        s = stops[tid]
        print(f"  {tid}: {name(s['node'])}  ETA {result.etas[tid]:.1f} min "
              f"(deadline {s['deadline_min']:.0f})  via {' > '.join(str(n) for n in leg.nodes)}")


if __name__ == "__main__":
    main()
