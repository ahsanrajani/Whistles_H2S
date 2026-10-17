"""In-process realtime hub for the care / queue / presence WebSocket
(frontend F0.4).

Each WS connection registers an ``asyncio.Queue`` and a set of topic strings;
``publish(topic, payload)`` fans a frame to every connection subscribed to that
exact topic. ``publish`` is safe to call from a sync request handler (which
FastAPI runs in a threadpool) — delivery is bounced onto the event loop with
``call_soon_threadsafe``. Single-process today (one uvicorn); multi-process
fan-out is a Redis-pubsub bridge and a deployment step (``_bridge_publish`` is
the seam).

Topics: ``case:{id}``, ``queue:{workspace_id}``, ``presence:{workspace_id}``.
The SSE job console (``/jobs/{id}/stream``) is separate and untouched.
"""
from __future__ import annotations

import asyncio
import time

_MAXQ = 512


class Hub:
    def __init__(self) -> None:
        self._subs: dict[int, tuple[asyncio.Queue, set[str]]] = {}
        self._seq = 0
        self._loop: asyncio.AbstractEventLoop | None = None

    def register(self, topics=()) -> tuple[int, asyncio.Queue]:
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        self._seq += 1
        cid = self._seq
        queue: asyncio.Queue = asyncio.Queue(maxsize=_MAXQ)
        self._subs[cid] = (queue, set(topics))
        return cid, queue

    def set_topics(self, cid: int, topics) -> None:
        entry = self._subs.get(cid)
        if entry is not None:
            self._subs[cid] = (entry[0], set(topics))

    def unregister(self, cid: int) -> None:
        self._subs.pop(cid, None)

    def topics_for(self, cid: int) -> set[str]:
        entry = self._subs.get(cid)
        return set(entry[1]) if entry else set()

    def connection_count(self) -> int:
        return len(self._subs)

    def publish(self, topic: str, payload: dict) -> int:
        """Enqueue ``{topic, ts, data}`` for every subscriber of ``topic``.
        Returns the number of connections it targeted."""
        frame = {"topic": topic, "ts": time.time(), "data": payload}
        targets = [q for q, topics in list(self._subs.values()) if topic in topics]
        for queue in targets:
            self._deliver(queue, frame)
        _bridge_publish(frame)
        return len(targets)

    def _deliver(self, queue: asyncio.Queue, frame: dict) -> None:
        try:
            here = asyncio.get_running_loop()
        except RuntimeError:
            here = None
        if here is not None and here is self._loop:
            _put(queue, frame)
        elif self._loop is not None:
            self._loop.call_soon_threadsafe(_put, queue, frame)
        # no loop at all (pure unit context) -> drop


def _put(queue: asyncio.Queue, frame: dict) -> None:
    try:
        queue.put_nowait(frame)
    except asyncio.QueueFull:
        pass


hub = Hub()


def publish(topic: str, payload: dict) -> int:
    """Module-level entry point the domain code calls."""
    return hub.publish(topic, payload)


def _bridge_publish(frame: dict) -> None:
    """Cross-process hook — no-op until a Redis-pubsub bridge is wired at
    deploy (kept as a seam so call sites don't change)."""
    return None
