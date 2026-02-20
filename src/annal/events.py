"""Simple in-process event bus for dashboard live updates."""

from __future__ import annotations

import logging
import queue
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """A dashboard event."""
    type: str      # "memory_stored", "memory_deleted", "index_started", "index_complete"
    project: str
    detail: str = ""


class EventBus:
    """Fan-out event bus: push to all connected SSE clients.

    Uses threading queues (not asyncio queues) so push() is safe to call
    from any thread — including MCP tool handlers that run synchronously.
    """

    def __init__(self) -> None:
        self._queues: list[queue.Queue[Event]] = []

    def subscribe(self) -> queue.Queue[Event]:
        """Create a new subscription queue for an SSE client."""
        q: queue.Queue[Event] = queue.Queue(maxsize=256)
        self._queues.append(q)
        return q

    def unsubscribe(self, q: queue.Queue[Event]) -> None:
        """Remove a subscription queue."""
        try:
            self._queues.remove(q)
        except ValueError:
            pass

    def push(self, event: Event) -> None:
        """Push an event to all subscribers. Safe to call from any thread."""
        for q in list(self._queues):
            try:
                q.put_nowait(event)
            except queue.Full:
                logger.warning("SSE client queue full, dropping event")


# Singleton instance shared between server.py and dashboard routes
event_bus = EventBus()
