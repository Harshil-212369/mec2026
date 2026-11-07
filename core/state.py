"""Crisis state machine (statement 3.1 "Crisis state machine").

Every change is checked against TRANSITIONS, recorded as a ticket_history-shaped row
(old_status, new_status, reason, changed_at) and published on the event bus. An illegal
change raises IllegalTransition and leaves the ticket and the history untouched.

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
"""
from __future__ import annotations

from datetime import datetime

from core.constants import STATES
from core.events import EventBus

TRANSITIONS: dict[str, frozenset[str]] = {
    "Open": frozenset({"Prioritized",          # validated, scored, queued
                       "Failed"}),             # cancelled before it was queued
    "Prioritized": frozenset({"Resource Assigned",  # matcher found stock + truck + route
                              "Delayed",            # no stock / truck / route right now
                              "Failed"}),           # unreachable past deadline + grace, or cancelled
    "Resource Assigned": frozenset({"In Progress",  # truck departs
                                    "Delayed"}),    # truck broke down before leaving
    "In Progress": frozenset({"Re-Routing",    # a closed road is on the REMAINING path (only then)
                              "Delayed",       # truck breakdown: cargo waits for a rescue truck
                              "Delivered"}),   # arrival
    "Re-Routing": frozenset({"In Progress",    # alternative route found
                             "Delayed"}),      # no alternative route
    "Delayed": frozenset({"Prioritized",       # resources freed / road reopened / stock added
                          "In Progress",       # same loaded truck can continue after a reopen
                          "Failed"}),          # unreachable past deadline + grace, or cancelled
    "Delivered": frozenset({"Resolved",        # all servings delivered
                            "Prioritized"}),   # partial delivery: remainder re-queued
    "Resolved": frozenset(),
    "Failed": frozenset(),
}


class IllegalTransition(Exception):
    pass


class StateMachine:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self.history: list[dict] = []   # ticket_history-shaped rows

    def open(self, ticket: dict, now: datetime, reason: str = "Emergency ticket submitted") -> dict:
        """First state of a new ticket (old_status NULL -> Open), plus crisis-created."""
        if ticket.get("status") not in (None, "Open"):
            raise IllegalTransition(f"ticket {ticket['ticket_id']} is already {ticket['status']}")
        ticket["status"] = "Open"
        row = self._record(ticket, None, "Open", reason, now)
        self.bus.publish("crisis-created", {"ticket_id": ticket["ticket_id"], "req_id": ticket["req_id"]}, now)
        return row

    def transition(self, ticket: dict, new_status: str, reason: str, now: datetime) -> dict:
        old = ticket["status"]
        if new_status not in STATES:
            raise IllegalTransition(f"{new_status!r} is not a state; states are {STATES}")
        if new_status not in TRANSITIONS[old]:
            raise IllegalTransition(f"ticket {ticket['ticket_id']}: {old} -> {new_status} is not allowed "
                                    f"(allowed from {old}: {sorted(TRANSITIONS[old])}); reason given: {reason!r}")
        if not reason or not reason.strip():
            raise ValueError("every status change needs an explanation")
        ticket["status"] = new_status
        row = self._record(ticket, old, new_status, reason, now)
        self.bus.publish("ticket-status", {"ticket_id": ticket["ticket_id"], "old_status": old,
                                           "new_status": new_status, "reason": reason}, now)
        if new_status == "Resolved":
            self.bus.publish("crisis-resolved", {"ticket_id": ticket["ticket_id"], "reason": reason}, now)
        return row

    def _record(self, ticket: dict, old: str | None, new: str, reason: str, now: datetime) -> dict:
        if now.tzinfo is None:
            raise ValueError("timestamps must carry a time zone")
        row = {"dataset_id": self.bus.dataset_id, "ticket_id": ticket["ticket_id"], "old_status": old,
               "new_status": new, "reason": reason, "changed_at": now}
        self.history.append(row)
        return row
