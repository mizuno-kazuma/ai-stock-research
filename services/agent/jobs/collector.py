"""Collector: 外部APIから取得し Raw 保存 → 正規化 → upsert（docs/08-agent-loop.md §3）。

`prices` のみ必須。他ソースの失敗は機能縮退（partial）として後続へ渡す。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
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


def _secret(settings: Any, name: str) -> str:
    value = getattr(settings, name, None)
    if value is None:
        return ""
    getter = getattr(value, "get_secret_value", None)
    if callable(getter):
        return str(getter() or "")
    return str(value or "")


def _env_from_settings(settings: Any) -> dict[str, str]:
    """pydantic Settings の値をコネクタが読む env dict にする。

    `.env` は Settings に載るが、プロセスの os.environ には自動では入らない。
    """
    ua = getattr(settings, "edgar_user_agent", None) or ""
    return {
        "JQUANTS_API_KEY": _secret(settings, "jquants_api_key"),
        "JQUANTS_PLAN": str(getattr(settings, "jquants_plan", "free") or "free"),
        "EDINET_SUBSCRIPTION_KEY": _secret(settings, "edinet_subscription_key"),
        "FRED_API_KEY": _secret(settings, "fred_api_key"),
        "EDGAR_USER_AGENT": str(ua),
        "ALPHA_VANTAGE_API_KEY": _secret(settings, "alpha_vantage_api_key"),
        "FINNHUB_API_KEY": _secret(settings, "finnhub_api_key"),
        "GEMINI_API_KEY": _secret(settings, "gemini_api_key"),
        "ANTHROPIC_API_KEY": _secret(settings, "anthropic_api_key"),
        "OPENAI_API_KEY": _secret(settings, "openai_api_key"),
    }


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
        "step_errors": {k: v.error for k, v in results.items() if v.error},
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


def _watchlist_symbols(state: JobRunRepo | None, market: str) -> list[str]:
    """ウォッチリストから yfinance 用シンボルを作る。"""
    if state is None:
        return []
    getter = getattr(state, "get_watchlist", None)
    if not callable(getter):
        return []
    symbols: list[str] = []
    try:
        items = getter() or []
    except TypeError:
        items = getter(None) or []
    for item in items:
        ticker = getattr(item, "ticker", None)
        mkt = getattr(item, "market", None)
        if ticker is None and isinstance(item, dict):
            ticker = item.get("ticker")
            mkt = item.get("market")
        if not ticker:
            continue
        if mkt and str(mkt) != market:
            continue
        text = str(ticker).strip()
        if market == "JP":
            code = text[:-2] if text.endswith(".T") else text
            symbols.append(f"{code}.T")
        else:
            symbols.append(text)
    return list(dict.fromkeys(symbols))


def builtin_connector_steps(
    *, warehouse: WarehouseRepo | None = None, state: JobRunRepo | None = None
) -> dict[str, StepFn]:
    """本番用。コネクタを遅延 import し、鍵が無ければそのステップだけ失敗させる。"""

    def _run(
        source: str,
        market: str,
        as_of: date,
        *,
        fetch_kwargs: dict[str, Any] | None = None,
        lookback_days: int = 0,
        apply_delay: bool = True,
    ) -> dict[str, Any]:
        from packages.core.config import get_settings
        from packages.core.connectors import get_connector
        from packages.core.connectors.base import FetchWindow

        settings = get_settings()
        cls = get_connector(source)
        connector = cls(
            data_dir=settings.raw_dir,
            warehouse=warehouse,
            state=state,
            env=_env_from_settings(settings),
        )
        end = as_of
        delay = int(getattr(connector, "delay_weeks", 0) or 0) if apply_delay else 0
        if delay:
            end = as_of - timedelta(weeks=delay)
        start = end - timedelta(days=lookback_days) if lookback_days else end
        window = FetchWindow(start=start, end=end)
        batches = 0
        rows = 0
        extra = fetch_kwargs or {}
        try:
            for batch in connector.fetch(window, **extra):
                batches += 1
                frame = connector.normalize(batch)
                rows += int(connector.upsert(frame) or 0)
        finally:
            close = getattr(connector, "close", None)
            if callable(close):
                close()
        return {"batches": batches, "rows": rows, "window_start": start.isoformat(), "window_end": end.isoformat()}

    def _fn_for(step: str) -> StepFn:
        def _fn(market: str, as_of: date) -> dict[str, Any]:
            if step == "securities_master":
                if market != "JP":
                    return {"skipped": True}
                return _run(
                    "jquants",
                    market,
                    as_of,
                    fetch_kwargs={"endpoint": "equities_master"},
                )
            if step == "prices":
                if market == "JP":
                    return _run(
                        "jquants",
                        market,
                        as_of,
                        fetch_kwargs={"endpoint": "equities_bars_daily"},
                        lookback_days=90,
                    )
                symbols = _watchlist_symbols(state, "US")
                if not symbols:
                    return {"skipped": True, "reason": "watchlist empty"}
                return _run(
                    "yfinance",
                    market,
                    as_of,
                    fetch_kwargs={"symbols": symbols, "endpoint": "download_daily"},
                    lookback_days=30,
                    apply_delay=False,
                )
            if step == "prices_live":
                symbols = _watchlist_symbols(state, market)
                if not symbols:
                    return {"skipped": True, "reason": "watchlist empty"}
                return _run(
                    "yfinance",
                    market,
                    as_of,
                    fetch_kwargs={"symbols": symbols, "endpoint": "download_live"},
                    lookback_days=7,
                    apply_delay=False,
                )
            if step == "financials":
                if market != "JP":
                    return {"skipped": True}
                return _run(
                    "jquants",
                    market,
                    as_of,
                    fetch_kwargs={"endpoint": "fins_summary"},
                    lookback_days=120,
                )
            if step == "documents":
                if market == "JP":
                    return _run("edinet", market, as_of, lookback_days=4, apply_delay=False)
                return {"skipped": True}
            if step == "macro":
                return _run("fred", market, as_of, lookback_days=400, apply_delay=False)
            return {"skipped": True}

        return _fn

    return {name: _fn_for(name) for name, _ in COLLECTOR_STEPS}
