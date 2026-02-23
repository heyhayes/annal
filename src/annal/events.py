"""Simple in-process event bus for dashboard live updates."""

from __future__ import annotations

import logging
import queue
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """A dashboard event."""
    type: str      # "memory_stored", "memory_updated", "memory_deleted", "index_started", "index_complete", "index_failed"
    project: str
    detail: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EventBus:
    """Fan-out event bus: push to all connected SSE clients.

    Uses threading queues (not asyncio queues) so push() is safe to call
    from any thread — including MCP tool handlers that run synchronously.
    """

    def __init__(self, history_size: int = 50) -> None:
        self._queues: list[queue.Queue[Event]] = []
        self._lock = threading.Lock()
        self._history: deque[Event] = deque(maxlen=history_size)

    def subscribe(self) -> queue.Queue[Event]:
        """Create a new subscription queue for an SSE client."""
        q: queue.Queue[Event] = queue.Queue(maxsize=256)
        with self._lock:
            self._queues.append(q)
        return q

    def unsubscribe(self, q: queue.Queue[Event]) -> None:
        """Remove a subscription queue."""
        with self._lock:
            try:
                self._queues.remove(q)
            except ValueError:
                pass

    def push(self, event: Event) -> None:
        """Push an event to all subscribers and record in history."""
        with self._lock:
            snapshot = list(self._queues)
            self._history.append(event)
        for q in snapshot:
            try:
                q.put_nowait(event)
            except queue.Full:
                logger.warning("SSE client queue full, dropping event")

    def recent(self, limit: int = 20) -> list[Event]:
        """Return the most recent events, newest first."""
        with self._lock:
            items = list(self._history)
        items.reverse()
        return items[:limit]


# Singleton instance shared between server.py and dashboard routes
event_bus = EventBus()
