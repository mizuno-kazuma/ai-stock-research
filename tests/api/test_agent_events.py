"""GET /api/v1/agent/events は SSE で job_progress を流す。"""

from __future__ import annotations

import asyncio
import json

from services.api.events import EventBus, sse_iterator


def test_sse_iterator_yields_job_progress() -> None:
    async def _run() -> None:
        bus = EventBus()
        agen = sse_iterator(bus, heartbeat_sec=30)
        first = await agen.__anext__()
        assert first["event"] == "heartbeat"
        await bus.publish(
            "job_progress",
            {
                "job_run_id": 1284,
                "job_name": "pipeline",
                "phase": "collector",
                "completed": 1,
                "total": 6,
            },
        )
        second = await agen.__anext__()
        assert second["event"] == "job_progress"
        payload = json.loads(second["data"])
        assert payload["job_run_id"] == 1284
        assert payload["phase"] == "collector"
        await agen.aclose()

    asyncio.run(_run())
