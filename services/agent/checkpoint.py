"""ジョブのチェックポイント（docs/08-agent-loop.md §9）。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from packages.core.interfaces.storage import JobRunRepo
from services.agent.progress import publish_job_progress


def load_or_init(
    state: JobRunRepo, run_id: int, *, job_name: str, phase: str
) -> dict[str, Any]:
    existing = state.load_checkpoint(run_id)
    if existing:
        return existing
    return {
        "job_name": job_name,
        "phase": phase,
        "completed_units": [],
        "next_unit": None,
        "metrics": {},
        "updated_at": datetime.now(UTC).isoformat(),
    }


def with_checkpoint(
    state: JobRunRepo,
    run_id: int,
    *,
    job_name: str,
    phase: str,
    units: Iterable[str],
    fn: Callable[[str], None],
) -> dict[str, Any]:
    """各単位の処理後にチェックポイントを保存する。完了済みはスキップ。"""
    cp = load_or_init(state, run_id, job_name=job_name, phase=phase)
    completed = [str(u) for u in cp.get("completed_units") or []]
    unit_list = [str(u) for u in units]
    for i, unit in enumerate(unit_list):
        if unit in completed:
            continue
        fn(unit)
        completed.append(unit)
        next_unit = unit_list[i + 1] if i + 1 < len(unit_list) else None
        cp = {
            "job_name": job_name,
            "phase": phase,
            "completed_units": completed,
            "next_unit": next_unit,
            "completed": len(completed),
            "total": len(unit_list),
            "metrics": cp.get("metrics") or {},
            "updated_at": datetime.now(UTC).isoformat(),
        }
        state.save_checkpoint(run_id, cp)
        publish_job_progress(
            job_run_id=run_id,
            job_name=job_name,
            phase=phase,
            completed=len(completed),
            total=len(unit_list),
        )
    return cp
