"""Check an input source end to end: read tables, validate every ticket, rank the valid ones.

  .venv\\Scripts\\python -m core.check_input dump tests/fixtures/aadil_dump_2026-11-07.sql
  .venv\\Scripts\\python -m core.check_input json data/toronto-downtown.json data/scenario-toronto.json
  .venv\\Scripts\\python -m core.check_input postgres      (reads MEC_DATABASE_URL, read-only)

Exit code 0 = every ticket valid, 1 = some ticket invalid, 2 = input unreadable.
Travel time is not in the ranking yet (routing is Jagan's module), so every ticket is
flagged eta_unknown.

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
"""
from __future__ import annotations

import argparse
import sys

from core.constants import DEFAULT_POLICY, POLICIES
from core.crisis_queue import CrisisQueue
from core.scoring import score_ticket
from core.tables import KNOWN_TABLES, InputError, from_json, from_pg_dump, from_postgres, select_dataset
from core.validate import REQUIRED, validate_ticket


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m core.check_input", description=__doc__.splitlines()[0])
    ap.add_argument("source", choices=["dump", "json", "postgres"])
    ap.add_argument("path", nargs="?", help="dump file, or dataset JSON")
    ap.add_argument("scenario", nargs="?", help="scenario JSON (json source only)")
    ap.add_argument("--dataset", help="dataset_id (default: app_settings.active_dataset_id)")
    ap.add_argument("--policy", default=DEFAULT_POLICY, choices=sorted(POLICIES))
    args = ap.parse_args(argv)
    if args.source in ("dump", "json") and not args.path:
        ap.error(f"{args.source} needs a file path")

    try:
        if args.source == "dump":
            bundle = from_pg_dump(args.path)
        elif args.source == "json":
            bundle = from_json(args.path, args.scenario)
        else:
            bundle = from_postgres()
        dsid, t = select_dataset(bundle, args.dataset)
    except (InputError, OSError) as exc:
        print(f"[FAIL] {exc}")
        return 2

    print(f"Source: {bundle.source}   dataset: {dsid}")
    for line in bundle.report:
        print("  " + line)
    for name in KNOWN_TABLES:
        print(f"  {name:<15}{len(t[name]):>5} rows")

    if t["tickets"]:
        columns = set().union(*(r.keys() for r in t["tickets"]))
        absent = [f for f in REQUIRED if f not in columns]
        if absent:
            print(f"[WARN] the tickets data has no {', '.join(absent)} field(s): every ticket fails "
                  "validation until they are added")

    requesters = {r["req_id"]: r for r in t["requesters"]}
    valid = []
    print("\nTicket validation:")
    if not t["tickets"]:
        print("  (no tickets)")
    for row in t["tickets"]:
        errs = validate_ticket(row, requesters)
        label = f"ticket {row.get('ticket_id')} {row.get('req_id')}"
        if errs:
            print(f"[FAIL] {label}: " + "; ".join(f"{f}: {m}" for f, m in errs))
        else:
            print(f"[PASS] {label}")
            valid.append(row)

    if bundle.extra_tickets:
        print("\nDeliberately invalid tickets (each must be rejected):")
        for i, row in enumerate(bundle.extra_tickets, 1):
            errs = validate_ticket(row, requesters)
            verdict = "[PASS] rejected" if errs else "[FAIL] ACCEPTED"
            print(f"{verdict} #{i} (expected: {row.get('_expect', '?')}): " + "; ".join(f"{f}: {m}" for f, m in errs))

    if valid:
        now = max(r["created_at"] for r in valid)
        queue, scores = CrisisQueue(), {}
        for row in valid:
            delivered = sum(d["servings_assigned"] for d in t["deliveries"]
                            if d["ticket_id"] == row["ticket_id"] and d["status"] == "Delivered")
            sc = score_ticket(row, requesters[row["req_id"]]["category"], now, None,
                              row["servings_requested"] - delivered, POLICIES[args.policy])
            scores[row["ticket_id"]] = sc
            queue.push(row["ticket_id"], sc.value, row["deadline"], row["created_at"])
        by_id = {r["ticket_id"]: r for r in valid}
        print(f"\nPriority ranking at {now.isoformat()} (policy {args.policy}):")
        print("  rank ticket req  category    score   S    P    F    C    D    W   flags")
        for rank, (tid, value) in enumerate(queue.ranking(), 1):
            sc, row = scores[tid], by_id[tid]
            b = " ".join(f"{sc.breakdown[k]:4.1f}" for k in ("S", "P", "F", "C", "D", "W"))
            print(f"  {rank:>4} {tid:>6} {row['req_id']:<4} {requesters[row['req_id']]['category']:<10} "
                  f"{value:6.1f}  {b}  {','.join(sc.flags)}")
    return 1 if len(valid) < len(t["tickets"]) else 0


if __name__ == "__main__":
    sys.exit(main())
