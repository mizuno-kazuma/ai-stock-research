"""ジョブ進捗の配信（docs/09-api-spec.md §2.8）。

API プロセス内の EventBus を共有する。未設定なら何もしない
（単体テストや agent 単独起動でも落ちない）。
"""

from __future__ import annotations

from typing import Any

_shared_bus: Any = None


def set_shared_bus(bus: Any | None) -> None:
    global _shared_bus
    _shared_bus = bus


def get_shared_bus() -> Any | None:
    return _shared_bus


def publish_job_progress(
    *,
    job_run_id: int,
    job_name: str,
    phase: str,
    completed: int,
    total: int,
    eta_sec: int | None = None,
) -> None:
    bus = _shared_bus
    if bus is None:
        return
    payload: dict[str, Any] = {
        "job_run_id": job_run_id,
        "job_name": job_name,
        "phase": phase,
        "completed": completed,
        "total": total,
        "eta_sec": eta_sec,
    }
    _emit(bus, "job_progress", payload)


def publish_job_finished(
    *,
    job_run_id: int,
    status: str,
    duration_sec: float | None = None,
    failed_steps: list[str] | None = None,
) -> None:
    bus = _shared_bus
    if bus is None:
        return
    _emit(
        bus,
        "job_finished",
        {
            "job_run_id": job_run_id,
            "status": status,
            "duration_sec": duration_sec,
            "failed_steps": list(failed_steps or []),
        },
    )


def _emit(bus: Any, event: str, data: dict[str, Any]) -> None:
    nowait = getattr(bus, "publish_nowait", None)
    if callable(nowait):
        nowait(event, data)
        return
    publish = getattr(bus, "publish", None)
    if callable(publish):
        publish(event, data)
