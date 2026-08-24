"""Collector: 外部APIから取得し Raw 保存 → 正規化 → upsert（docs/08-agent-loop.md §3）。

`prices` のみ必須。他ソースの失敗は機能縮退（partial）として後続へ渡す。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from packages.core.interfaces.storage import JobRunRepo, WarehouseRepo
from services.agent.deps import begin_run, finish_run
from services.agent.types import JobResult, StepResult

StepFn = Callable[[str, date], Any]

COLLECTOR_STEPS: tuple[tuple[str, bool], ...] = (
    ("securities_master", False),
    ("prices", True),
    ("prices_live", False),
    ("financials", False),
    ("documents", False),
    ("macro", False),
    ("earnings_calendar", False),
)


def collector(
    market: str,
    as_of: date,
    *,
    state: JobRunRepo,
    warehouse: WarehouseRepo | None = None,
    steps: dict[str, StepFn] | None = None,
    trigger: str = "schedule",
    parent_run_id: int | None = None,
) -> JobResult:
    run_id = begin_run(
        state, job_name="collector", market=market, trigger=trigger, parent_run_id=parent_run_id
    )
    fns = steps if steps is not None else builtin_connector_steps(
        warehouse=warehouse, state=state
    )
    results: dict[str, StepResult] = {}
    overall = "success"

    def run_step(name: str) -> None:
        nonlocal overall
        required = dict(COLLECTOR_STEPS)[name]
        fn = fns.get(name)
        if fn is None:
            results[name] = StepResult(
                status="skipped", error="step not wired", required=required
            )
            if required:
                overall = "failed"
            elif overall == "success":
                overall = "partial"
            return
        try:
            metrics = fn(market, as_of) or {}
            results[name] = StepResult(status="success", metrics=dict(metrics), required=required)
        except Exception as exc:
            results[name] = StepResult(
                status="failed", error=f"{type(exc).__name__}: {exc}", required=required
            )
            if warehouse is not None:
                try:
                    warehouse.record_data_gap(
                        source=name,
                        entity=market,
                        gap_start=as_of,
                        gap_end=as_of,
                        reason=str(exc),
                    )
                except Exception:
                    pass
            if required:
                overall = "failed"
            elif overall != "failed":
                overall = "partial"

    names = [n for n, _ in COLLECTOR_STEPS]
    done: list[str] = []

    def _one(name: str) -> None:
        run_step(name)
        done.append(name)
        state.save_checkpoint(
            run_id,
            {
                "job_name": "collector",
                "phase": f"collector.{name}",
                "completed_units": list(done),
                "next_unit": None,
                "metrics": {"overall": overall},
            },
        )

    for name, required in COLLECTOR_STEPS:
        _one(name)
        if required and results[name].status == "failed":
            overall = "failed"
            break

    metrics = {
        "steps": {k: v.status for k, v in results.items()},
        "n_success": sum(1 for v in results.values() if v.status == "success"),
        "n_failed": sum(1 for v in results.values() if v.status == "failed"),
    }
    finish_run(state, run_id, status=overall, metrics=metrics)
    return JobResult(
        job_name="collector",
        status=overall,
        market=market,
        as_of=as_of,
        run_id=run_id,
        steps=results,
        metrics=metrics,
    )


def builtin_connector_steps(
    *, warehouse: WarehouseRepo | None = None, state: JobRunRepo | None = None
) -> dict[str, StepFn]:
    """本番用。コネクタを遅延 import し、鍵が無ければそのステップだけ失敗させる。"""

    def _run(source: str, market: str, as_of: date) -> dict[str, Any]:
        from packages.core.config import get_settings
        from packages.core.connectors import get_connector
        from packages.core.connectors.base import FetchWindow

        settings = get_settings()
        cls = get_connector(source)
        connector = cls(
            data_dir=settings.raw_dir,
            warehouse=warehouse,
            state=state,
        )
        window = FetchWindow(start=as_of, end=as_of)
        batches = 0
        rows = 0
        try:
            for batch in connector.fetch(window):
                batches += 1
                frame = connector.normalize(batch)
                rows += int(connector.upsert(frame) or 0)
        finally:
            close = getattr(connector, "close", None)
            if callable(close):
                close()
        return {"batches": batches, "rows": rows}

    mapping = {
        "JP": {
            "prices": "jquants",
            "financials": "jquants",
            "documents": "edinet",
            "macro": "fred",
            "prices_live": "yfinance",
        },
        "US": {
            "prices": "yfinance",
            "financials": "edgar",
            "documents": "edgar",
            "macro": "fred",
            "prices_live": "yfinance",
        },
    }

    def make(step: str) -> StepFn:
        def _fn(market: str, as_of: date) -> dict[str, Any]:
            source = mapping.get(market, {}).get(step)
            if source is None:
                return {"skipped": True}
            return _run(source, market, as_of)

        return _fn

    return {name: make(name) for name, _ in COLLECTOR_STEPS if name != "securities_master"}
