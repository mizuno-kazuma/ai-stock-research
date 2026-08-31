"""Collector: 外部APIから取得し Raw 保存 → 正規化 → upsert（docs/08-agent-loop.md §3）。

`prices` のみ必須。他ソースの失敗は機能縮退（partial）として後続へ渡す。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from packages.core.interfaces.storage import JobRunRepo, WarehouseRepo
from services.agent.checkpoint import load_or_init
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

# 既存カバレッジがある日は、訂正取り込み用にこの日数だけ重ねて再取得する。
INCREMENTAL_OVERLAP_DAYS = 5


def coverage_lookback_days(
    configured: int,
    *,
    latest: date | None,
    end: date,
    overlap_days: int = INCREMENTAL_OVERLAP_DAYS,
) -> int:
    """倉庫に既にある期間は再取得しない。lookback をギャップ + overlap に縮める。"""
    if configured <= 0 or latest is None:
        return configured
    gap = (end - latest).days + overlap_days
    return max(0, min(configured, gap))


def _latest_coverage(warehouse: Any, table: str, market: str | None) -> date | None:
    getter = getattr(warehouse, "latest_coverage_date", None)
    if not callable(getter):
        return None
    try:
        value = getter(table, market=market)
    except Exception:
        return None
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value)
    return date.fromisoformat(text[:10])


def _format_step_error(exc: BaseException) -> str:
    """OSError は filename が str(exc) に出ないことがあるので明示する。"""
    detail = str(exc).strip() or repr(exc)
    filename = getattr(exc, "filename", None)
    if filename and str(filename) not in detail:
        detail = f"{detail}: {filename}"
    return f"{type(exc).__name__}: {detail}"


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
            if (
                name == "documents"
                and not metrics.get("skipped")
                and int(metrics.get("rows") or 0) == 0
                and warehouse is not None
                and _latest_coverage(warehouse, "documents", market) is None
            ):
                results[name] = StepResult(
                    status="failed",
                    error="開示資料が0件で、倉庫にも既存がありません",
                    metrics=dict(metrics),
                    required=required,
                )
                if overall != "failed":
                    overall = "partial"
                return
            results[name] = StepResult(status="success", metrics=dict(metrics), required=required)
        except Exception as exc:
            results[name] = StepResult(
                status="failed", error=_format_step_error(exc), required=required
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

    done: list[str] = []
    cp = load_or_init(
        state, run_id, job_name="collector", phase="collector", market=market
    )
    already = {str(u) for u in (cp.get("completed_units") or [])}

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
        if name in already:
            results[name] = StepResult(
                status="success", metrics={"resumed": True}, required=required
            )
            done.append(name)
            state.save_checkpoint(
                run_id,
                {
                    "job_name": "collector",
                    "phase": f"collector.{name}",
                    "completed_units": list(done),
                    "next_unit": None,
                    "metrics": {"overall": overall, "resumed": True},
                },
            )
            continue
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
    prices_step = results.get("prices")
    if prices_step is not None and prices_step.status == "success":
        price_metrics = prices_step.metrics or {}
        n_rows = int(price_metrics.get("rows") or 0)
        if n_rows > 0 and not price_metrics.get("skipped"):
            from packages.core.storage import mark_live_ingest

            if mark_live_ingest(state, rows=n_rows):
                metrics["cleared_seed_data"] = True
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


def _edgar_user_agent(settings: Any) -> str:
    ua = getattr(settings, "edgar_user_agent", None) or ""
    return str(ua).strip()


def _edgar_skip_reason(settings: Any) -> str | None:
    """UA が無い／不正なら理由を返す。パイプライン全体は落とさない。"""
    ua = _edgar_user_agent(settings)
    if not ua:
        return "edgar_user_agent_missing"
    try:
        from packages.core.connectors.edgar import validate_user_agent

        validate_user_agent(ua)
    except Exception as exc:
        return f"edgar_user_agent_invalid: {exc}"
    return None


def _us_ciks(warehouse: Any, state: JobRunRepo | None) -> list[str]:
    """倉庫の証券マスタから US の CIK を集める。"""
    ciks: list[str] = []
    rows: list[Any] = []
    getter = getattr(warehouse, "get_securities", None) if warehouse is not None else None
    if callable(getter):
        try:
            rows = list(getter(market="US") or [])
        except TypeError:
            rows = list(getter() or [])
    elif warehouse is not None:
        reader = getattr(warehouse, "read_securities", None)
        if callable(reader):
            frame = reader(market="US")
            if frame is not None and getattr(frame, "empty", True) is False:
                rows = frame.to_dict("records")
    wanted: set[str] | None = None
    if state is not None:
        symbols = _watchlist_symbols(state, "US")
        if symbols:
            wanted = {s.replace(".US", "").upper() for s in symbols}
    for row in rows:
        if isinstance(row, dict):
            ticker = str(row.get("ticker") or "").upper()
            cik = row.get("cik")
            market = row.get("market")
        else:
            ticker = str(getattr(row, "ticker", "") or "").upper()
            cik = getattr(row, "cik", None)
            market = getattr(row, "market", None)
        if market and str(market) != "US":
            continue
        if wanted is not None and ticker and ticker not in wanted:
            continue
        text = str(cik or "").strip()
        if text:
            ciks.append(text)
    return list(dict.fromkeys(ciks))


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
    *,
    warehouse: WarehouseRepo | None = None,
    state: JobRunRepo | None = None,
    lookbacks: dict[str, int] | None = None,
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
        coverage_table: str | None = None,
        skip_if_fresh_days: int = 0,
    ) -> dict[str, Any]:
        from packages.core.config import get_settings
        from packages.core.connectors import get_connector
        from packages.core.connectors.base import FetchWindow

        settings = get_settings()
        settings.ensure_directories()
        cls = get_connector(source)
        connector = cls(
            data_dir=settings.data_dir,
            warehouse=warehouse,
            state=state,
            env=_env_from_settings(settings),
        )
        end = as_of
        delay = int(getattr(connector, "delay_weeks", 0) or 0) if apply_delay else 0
        if delay:
            end = as_of - timedelta(weeks=delay)
        if skip_if_fresh_days and coverage_table:
            latest = _latest_coverage(
                warehouse, coverage_table, None if coverage_table == "macro_series" else market
            )
            if latest is not None and (as_of - latest).days < skip_if_fresh_days:
                return {
                    "skipped": True,
                    "reason": "fresh",
                    "latest": latest.isoformat(),
                    "window_end": end.isoformat(),
                }
        lookback = lookback_days
        if lookback and coverage_table:
            latest = _latest_coverage(
                warehouse, coverage_table, None if coverage_table == "macro_series" else market
            )
            lookback = coverage_lookback_days(lookback, latest=latest, end=end)
        start = end - timedelta(days=lookback) if lookback else end
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

    def _run_edgar(
        market: str,
        as_of: date,
        *,
        endpoint: str,
        lookback_days: int,
        coverage_table: str,
    ) -> dict[str, Any]:
        from packages.core.config import get_settings

        settings = get_settings()
        skip = _edgar_skip_reason(settings)
        if skip:
            return {"skipped": True, "reason": skip}
        ciks = _us_ciks(warehouse, state)
        if not ciks:
            return {"skipped": True, "reason": "cik_missing"}
        return _run(
            "edgar",
            market,
            as_of,
            fetch_kwargs={"endpoint": endpoint, "ciks": ciks},
            lookback_days=lookback_days,
            apply_delay=False,
            coverage_table=coverage_table,
        )

    def _lookback(step: str, default: int) -> int:
        if lookbacks and step in lookbacks:
            return int(lookbacks[step])
        return default

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
                    coverage_table="securities",
                    skip_if_fresh_days=7,
                )
            if step == "prices":
                if market == "JP":
                    return _run(
                        "jquants",
                        market,
                        as_of,
                        fetch_kwargs={"endpoint": "equities_bars_daily"},
                        lookback_days=_lookback("prices", 90),
                        coverage_table="prices_daily",
                    )
                symbols = _watchlist_symbols(state, "US")
                if not symbols:
                    return {"skipped": True, "reason": "watchlist empty"}
                return _run(
                    "yfinance",
                    market,
                    as_of,
                    fetch_kwargs={"symbols": symbols, "endpoint": "download_daily"},
                    lookback_days=_lookback("prices", 30),
                    apply_delay=False,
                    coverage_table="prices_daily",
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
                    lookback_days=_lookback("prices_live", 7),
                    apply_delay=False,
                )
            if step == "financials":
                if market == "JP":
                    return _run(
                        "jquants",
                        market,
                        as_of,
                        fetch_kwargs={"endpoint": "fins_summary"},
                        lookback_days=_lookback("financials", 120),
                        coverage_table="financials",
                    )
                return _run_edgar(
                    market,
                    as_of,
                    endpoint="companyfacts",
                    lookback_days=_lookback("financials", 120),
                    coverage_table="financials",
                )
            if step == "documents":
                if market == "JP":
                    # 土日を含む短い窓だと平日が2-3日しかなく、空レスポンスを成功扱いにしていた。
                    return _run(
                        "edinet",
                        market,
                        as_of,
                        lookback_days=_lookback("documents", 14),
                        apply_delay=False,
                        coverage_table="documents",
                    )
                return _run_edgar(
                    market,
                    as_of,
                    endpoint="submissions",
                    lookback_days=_lookback("documents", 14),
                    coverage_table="documents",
                )
            if step == "macro":
                return _run(
                    "fred",
                    market,
                    as_of,
                    lookback_days=_lookback("macro", 400),
                    apply_delay=False,
                    coverage_table="macro_series",
                )
            return {"skipped": True}

        return _fn

    return {name: _fn_for(name) for name, _ in COLLECTOR_STEPS}
