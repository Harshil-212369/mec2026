"""Dynamic priority queue of tickets on top of our MinHeap (statement 3.1 "Dynamic priority queue").

Re-scoring does not search the heap. It pushes a NEW entry with version+1; the old entry
stays in the heap but is "stale" and skipped by pop_valid(). This lazy-deletion pattern is
the one described in Python's heapq docs, "Priority Queue Implementation Notes"
(https://docs.python.org/3/library/heapq.html); the version number matches Aadil's
tickets.priority_version column.

Equal priority (tie-break), in order: earlier deadline -> earlier submission (FIFO) ->
lower ticket id. That is simply the tuple order (-score, deadline, created_at, ticket_id).

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
"""
from __future__ import annotations

from datetime import datetime

from core.heap import MinHeap


class CrisisQueue:
    def __init__(self) -> None:
        self._heap = MinHeap()
        self._version: dict[int, int] = {}    # ticket_id -> latest version ever issued
        self._live: dict[int, tuple] = {}     # ticket_id -> its current (valid) heap entry

    def __len__(self) -> int:
        return len(self._live)

    def __contains__(self, ticket_id: int) -> bool:
        return ticket_id in self._live

    def push(self, ticket_id: int, score: float, deadline: datetime, created_at: datetime) -> int:
        """Add or re-score a ticket. Returns the new priority_version."""
        version = self._version.get(ticket_id, 0) + 1
        self._version[ticket_id] = version
        entry = (-score, deadline.timestamp(), created_at.timestamp(), ticket_id, version)
        self._live[ticket_id] = entry
        self._heap.push(entry)
        self._compact_if_needed()
        return version

    def remove(self, ticket_id: int) -> None:
        """Take a ticket out (assigned, failed, resolved). Its heap entries become stale."""
        if ticket_id not in self._live:
            raise KeyError(f"ticket {ticket_id} is not queued")
        del self._live[ticket_id]
        self._version[ticket_id] += 1

    def pop_valid(self) -> tuple[int, float, int] | None:
        """Most urgent ticket as (ticket_id, score, version), or None when empty."""
        while len(self._heap):
            entry = self._heap.pop()
            ticket_id = entry[3]
            if self._live.get(ticket_id) == entry:
                del self._live[ticket_id]
                return ticket_id, -entry[0], entry[4]
            # stale: an older version of a re-scored ticket, or a removed one -> skip
        return None

    def ranking(self) -> list[tuple[int, float]]:
        """All queued tickets, most urgent first, as (ticket_id, score). Does not modify the queue."""
        return [(e[3], -e[0]) for e in sorted(self._live.values())]

    def _compact_if_needed(self) -> None:
        # Re-scoring every tick leaves stale entries behind; rebuild when they dominate.
        if len(self._heap) > 4 * len(self._live) + 16:
            fresh = MinHeap()
            for entry in self._live.values():
                fresh.push(entry)
            self._heap = fresh
