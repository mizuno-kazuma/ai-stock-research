"""ジョブ進捗 SSE の配信（docs/09-api-spec.md §2.8）。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any


class EventBus:
    """プロセス内の pub/sub。Phase A は単一 API プロセス前提。"""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[tuple[str, dict[str, Any]]]] = []

    def subscribe(self) -> asyncio.Queue[tuple[str, dict[str, Any]]]:
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[tuple[str, dict[str, Any]]]) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    async def publish(self, event: str, data: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            await queue.put((event, data))

    def publish_nowait(self, event: str, data: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait((event, data))
            except asyncio.QueueFull:
                continue


async def sse_iterator(
    bus: EventBus, *, heartbeat_sec: float = 15.0
) -> AsyncIterator[dict[str, str]]:
    queue = bus.subscribe()
    try:
        yield {
            "event": "heartbeat",
            "data": "{}",
        }
        while True:
            try:
                event, data = await asyncio.wait_for(queue.get(), timeout=heartbeat_sec)
                import json

                yield {"event": event, "data": json.dumps(data, ensure_ascii=False)}
            except TimeoutError:
                from services.api.util import utc_now

                import json

                yield {
                    "event": "heartbeat",
                    "data": json.dumps({"at": utc_now().isoformat().replace("+00:00", "Z")}),
                }
    finally:
        bus.unsubscribe(queue)
