"""ジョブ間依存。前段の成否は `job_runs` を見て判断する（docs/01-architecture.md §4.1）。"""

from __future__ import annotations

from datetime import date

from packages.core.interfaces.storage import JobRun, JobRunRepo


class UpstreamFailed(RuntimeError):
    """必須の前段ジョブが失敗している。"""


def latest(
    state: JobRunRepo, *, job_name: str, market: str | None, on_date: date | None
) -> JobRun | None:
    return state.latest_job_run(job_name=job_name, market=market, on_date=on_date)


def require_not_failed(
    state: JobRunRepo,
    *,
    job_name: str,
    market: str,
    on_date: date,
    required: bool = True,
) -> JobRun | None:
    run = latest(state, job_name=job_name, market=market, on_date=on_date)
    if run is None:
        if required:
            raise UpstreamFailed(f"{job_name} がまだ実行されていません")
        return None
    if run.status == "failed" and required:
        raise UpstreamFailed(f"{job_name} が failed のため後続を止めます")
    return run


def begin_run(
    state: JobRunRepo,
    *,
    job_name: str,
    market: str,
    trigger: str = "schedule",
    parent_run_id: int | None = None,
) -> int:
    return state.create_job_run(
        job_name=job_name, market=market, trigger=trigger, parent_run_id=parent_run_id
    )


def attach_step_failures(metrics: dict | None, steps: dict) -> dict:
    """失敗したステップ名とメッセージを metrics に載せる（UI が表示する）。"""
    out = dict(metrics or {})
    failed = [name for name, step in steps.items() if getattr(step, "status", None) == "failed"]
    errors = {
        name: step.error
        for name, step in steps.items()
        if getattr(step, "error", None)
    }
    if failed:
        out["failed_steps"] = failed
    if errors:
        out["step_errors"] = errors
    return out


def first_step_error(steps: dict) -> str | None:
    parts = []
    for name, step in steps.items():
        if getattr(step, "status", None) != "failed":
            continue
        err = getattr(step, "error", None)
        parts.append(f"{name}: {err}" if err else name)
    return " / ".join(parts) if parts else None


def finish_run(
    state: JobRunRepo,
    run_id: int,
    *,
    status: str,
    metrics: dict | None = None,
    error: BaseException | None = None,
) -> None:
    state.record_job_run(
        run_id,
        status=status,
        metrics=metrics,
        error_type=None if error is None else type(error).__name__,
        error_message=None if error is None else str(error),
    )
