"""Ticket validation (statement 3.1 "Crisis submission": check for missing or invalid
information before processing). Works on a tickets-table row from any source.

Returns a list of (field, message). Empty list = valid. Nothing is defaulted or fixed here.

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
"""
from __future__ import annotations

from datetime import datetime

from core.constants import SEVERITY_MAX, SEVERITY_MIN

# Statement: location, crisis type, people affected, food quantity, refrigeration, severity,
# deadline, submission time. Location category comes from the requester row.
REQUIRED = ("req_id", "crisis_type", "servings_requested", "people_affected", "severity",
            "refrigerated", "deadline", "created_at")


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)  # True is an int in Python: reject it


def _is_aware_time(v) -> bool:
    return isinstance(v, datetime) and v.tzinfo is not None


def validate_ticket(t: dict, requesters: dict[str, dict]) -> list[tuple[str, str]]:
    errors: list[tuple[str, str]] = []
    for f in REQUIRED:
        if f not in t or t[f] is None:
            errors.append((f, "missing"))
    present = {f for f in REQUIRED if t.get(f) is not None}

    if "req_id" in present:
        if not isinstance(t["req_id"], str) or t["req_id"] not in requesters:
            errors.append(("req_id", f"unknown location {t['req_id']!r}: not a requester in this dataset"))
        elif not requesters[t["req_id"]].get("category"):
            errors.append(("req_id", f"requester {t['req_id']} has no location category"))
    if "crisis_type" in present and (not isinstance(t["crisis_type"], str) or not t["crisis_type"].strip()):
        errors.append(("crisis_type", "must be a non-empty text"))
    for f, label in (("servings_requested", "servings"), ("people_affected", "people affected")):
        if f in present and (not _is_int(t[f]) or t[f] <= 0):
            errors.append((f, f"{label} must be a whole number > 0 (got {t[f]!r})"))
    if "severity" in present and (not _is_int(t["severity"]) or not SEVERITY_MIN <= t["severity"] <= SEVERITY_MAX):
        errors.append(("severity", f"must be a whole number {SEVERITY_MIN}..{SEVERITY_MAX} (got {t['severity']!r})"))
    if "refrigerated" in present and not isinstance(t["refrigerated"], bool):
        errors.append(("refrigerated", f"must be true or false (got {t['refrigerated']!r})"))
    for f in ("deadline", "created_at"):
        if f in present and not _is_aware_time(t[f]):
            errors.append((f, f"must be a date-time with time zone (got {t[f]!r})"))
    if (_is_aware_time(t.get("deadline")) and _is_aware_time(t.get("created_at"))
            and t["deadline"] <= t["created_at"]):
        errors.append(("deadline", "deadline must be after the submission time"))
    return errors
