"""ジョブのチェックポイント（docs/08-agent-loop.md §9）。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from packages.core.interfaces.storage import JobRunRepo
from services.agent.progress import publish_job_progress


def latest_interrupted_checkpoint(
    state: JobRunRepo, *, job_name: str, market: str | None
) -> dict[str, Any] | None:
    """同じ job_name+market の最新 interrupted ランからチェックポイントを拾う。"""
    finder = getattr(state, "find_job_runs", None)
    if not callable(finder):
        return None
    rows = finder(status="interrupted")
    candidates = []
    for run in rows:
        if getattr(run, "job_name", None) != job_name:
            continue
        if market is not None and getattr(run, "market", None) not in {None, market}:
            continue
        candidates.append(run)
    if not candidates:
        return None
    candidates.sort(key=lambda r: int(getattr(r, "id", 0) or 0))
    prev = candidates[-1]
    loaded = state.load_checkpoint(int(prev.id))
    if loaded:
        return dict(loaded)
    raw = getattr(prev, "checkpoint", None)
    return dict(raw) if isinstance(raw, dict) else None


def load_or_init(
    state: JobRunRepo,
    run_id: int,
    *,
    job_name: str,
    phase: str,
    market: str | None = None,
) -> dict[str, Any]:
    existing = state.load_checkpoint(run_id)
    if existing:
        return existing
    if market is None:
        run = state.get_job_run(run_id)
        market = getattr(run, "market", None) if run is not None else None
    inherited = latest_interrupted_checkpoint(state, job_name=job_name, market=market)
    if inherited:
        cp = {
            "job_name": job_name,
            "phase": inherited.get("phase") or phase,
            "completed_units": [str(u) for u in (inherited.get("completed_units") or [])],
            "next_unit": inherited.get("next_unit"),
            "metrics": dict(inherited.get("metrics") or {}),
            "inherited_from": int(inherited.get("inherited_from") or 0) or None,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        state.save_checkpoint(run_id, cp)
        return cp
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
