"""Fan out job events from the worker thread to SSE subscribers on the asyncio loop."""

import asyncio
from collections.abc import AsyncIterator


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, event: dict) -> None:
        """Safe to call from any thread."""
        if self._loop is None or self._loop.is_closed():
            return
        self._loop.call_soon_threadsafe(self._fan_out, event)

    def _fan_out(self, event: dict) -> None:
        for queue in list(self._subscribers):
            if queue.qsize() < 500:  # drop events for a stalled client instead of growing forever
                queue.put_nowait(event)

    async def subscribe(self, heartbeat_sec: float = 15) -> AsyncIterator[dict | None]:
        """Yield events; yields None as a heartbeat when idle."""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=heartbeat_sec)
                except TimeoutError:
                    yield None
        finally:
            self._subscribers.discard(queue)
