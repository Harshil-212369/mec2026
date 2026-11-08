"""In-process publish/subscribe event bus (statement 3.1 "System events").

publish() builds a row shaped like Aadil's system_events table
(dataset_id, event_type, details, created_at), keeps it in `log`, and calls every
subscriber of that topic plus every "*" subscriber. A WebSocket broadcaster and a database
writer are just two more subscribers.

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Callable

from core.constants import EVENTS

Subscriber = Callable[[dict], None]


class EventBus:
    def __init__(self, dataset_id: str) -> None:
        self.dataset_id = dataset_id
        self._subs: dict[str, list[Subscriber]] = defaultdict(list)
        self.log: list[dict] = []                     # system_events-shaped rows
        self.subscriber_errors: list[tuple[str, str]] = []

    def subscribe(self, topic: str, fn: Subscriber) -> None:
        if topic != "*" and topic not in EVENTS:
            raise ValueError(f"unknown event topic {topic!r}; known: {EVENTS}")
        self._subs[topic].append(fn)

    def publish(self, topic: str, details: dict, now: datetime) -> dict:
        if topic not in EVENTS:
            raise ValueError(f"unknown event topic {topic!r}; known: {EVENTS}")
        row = {"dataset_id": self.dataset_id, "event_type": topic, "details": dict(details), "created_at": now}
        self.log.append(row)
        for fn in self._subs[topic] + self._subs["*"]:
            try:
                fn(row)
            except Exception as exc:  # one broken subscriber (e.g. a closed socket) must not stop the engine
                self.subscriber_errors.append((topic, f"{type(exc).__name__}: {exc}"))
        return row
