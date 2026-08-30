"""初回バックフィル（docs/02-data-ingestion.md §10）。

日次バッチとは別ジョブ。`backfill_progress` で中断・再開する。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

from packages.core.interfaces.storage import JobRunRepo, WarehouseRepo
from services.agent.deps import begin_run, finish_run
from services.agent.jobs.collector import builtin_connector_steps
from services.agent.types import JobResult, StepResult

StepFn = Callable[[str, date], Any]

# 仕様の所要見積もりに対応する lookback（暦日）。
LOOKBACKS_JP = {
    "prices": 365 * 2,
    "prices_live": 84,
    "financials": 365 * 2,
    "documents": 365,
    "macro": 365 * 10,
}
LOOKBACKS_US = {
    "prices": 365 * 5,
    "financials": 365 * 5,
    "documents": 365,
    "macro": 365 * 10,
}

BACKFILL_STEPS: tuple[tuple[str, str], ...] = (
    ("JP", "securities_master"),
    ("JP", "macro"),
    ("JP", "prices"),
    ("US", "prices"),
    ("JP", "prices_live"),
    ("US", "financials"),
    ("JP", "documents"),
    ("US", "documents"),
    ("JP", "features"),
)


def _progress_key(market: str, step: str) -> str:
    return f"{market}.{step}"


def _progress_status(state: JobRunRepo, key: str) -> str | None:
    getter = getattr(state, "get_backfill_progress", None)
    if not callable(getter):
        return None
    row = getter(key)
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get("status")
    return getattr(row, "status", None)


def _save_progress(state: JobRunRepo, key: str, status: str, *, cursor: str | None = None) -> None:
    saver = getattr(state, "save_backfill_progress", None) or getattr(
        state, "set_backfill_progress", None
    )
    if not callable(saver):
        return
    try:
        saver(key, status=status, cursor_value=cursor)
    except TypeError:
        saver(key, {"status": status, "cursor_value": cursor})


def _run_features(
    state: JobRunRepo, warehouse: WarehouseRepo | None, market: str, as_of: date
) -> dict[str, Any]:
    if warehouse is None:
        return {"skipped": True, "reason": "no_warehouse"}
    from services.agent.jobs.analyst import analyst

    result = analyst(market, as_of, state=state, warehouse=warehouse, trigger="backfill")
    return {"status": result.status, "metrics": result.metrics}


def backfill(
    market: str,
    as_of: date,
    *,
    state: JobRunRepo,
    warehouse: WarehouseRepo | None = None,
    steps: dict[str, StepFn] | None = None,
    trigger: str = "manual",
    parent_run_id: int | None = None,
) -> JobResult:
    """市場引数は互換のため残す。実体は JP/US の固定順序を回す。"""
    del market
    run_id = begin_run(
        state, job_name="backfill", market="ALL", trigger=trigger, parent_run_id=parent_run_id
    )
    jp_fns = steps or builtin_connector_steps(
        warehouse=warehouse, state=state, lookbacks=LOOKBACKS_JP
    )
    us_fns = steps or builtin_connector_steps(
        warehouse=warehouse, state=state, lookbacks=LOOKBACKS_US
    )
    results: dict[str, StepResult] = {}
    overall = "success"
    for mkt, name in BACKFILL_STEPS:
        key = _progress_key(mkt, name)
        if _progress_status(state, key) == "done":
            results[key] = StepResult(status="skipped", metrics={"reason": "already_done"})
            continue
        _save_progress(state, key, "running", cursor=as_of.isoformat())
        try:
            if name == "features":
                feat_fn = (steps or {}).get("features")
                if feat_fn is not None:
                    metrics = feat_fn(mkt, as_of) or {}
                else:
                    metrics = _run_features(state, warehouse, mkt, as_of)
            else:
                fns = jp_fns if mkt == "JP" else us_fns
                fn = fns.get(name)
                if fn is None:
                    metrics = {"skipped": True, "reason": "step not wired"}
                else:
                    metrics = fn(mkt, as_of) or {}
            status = "success"
            if metrics.get("skipped"):
                status = "skipped"
            results[key] = StepResult(status=status, metrics=dict(metrics))
            _save_progress(state, key, "done" if status != "failed" else "failed", cursor=as_of.isoformat())
        except Exception as exc:
            overall = "failed"
            results[key] = StepResult(status="failed", error=f"{type(exc).__name__}: {exc}")
            _save_progress(state, key, "failed", cursor=as_of.isoformat())
            break
    if overall != "failed" and any(v.status == "failed" for v in results.values()):
        overall = "partial"
    metrics = {
        "steps": {k: v.status for k, v in results.items()},
        "n_done": sum(1 for v in results.values() if v.status in {"success", "skipped"}),
    }
    finish_run(state, run_id, status=overall, metrics=metrics)
    return JobResult(
        job_name="backfill",
        status=overall,
        market="ALL",
        as_of=as_of,
        run_id=run_id,
        steps=results,
        metrics=metrics,
    )
