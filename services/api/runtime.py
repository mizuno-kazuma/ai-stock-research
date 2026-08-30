"""API から既存の agent / backtest / LLM へつなぐ薄い接続層。"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from packages.core.backtest.engine import BacktestError, run_backtest
from packages.core.factors.screening import UniverseFilter
from packages.core.llm.cache import input_hash, prompt_hash
from packages.core.llm.prompts import render_prompt
from packages.core.llm.router import LLMRouter
from packages.core.llm.schemas import DocSummaryOutput
from packages.core.storage import DuckDBRepo, StorageError, get_vector_store
from packages.schemas.documents import DocumentChunk, DocumentChunkList, DocumentSummary
from packages.schemas.model_lab import BacktestRequest, BacktestTrade, EquityCurvePoint
from services.agent.wiring import build_llm_router, try_load_ranker
from services.api.deps import AppState
from services.api.mapping import document_summary_from_row
from services.api.util import utc_now

logger = logging.getLogger(__name__)

JOB_FN_NAMES = {
    "collector": "collector",
    "collector_jp": "collector",
    "collector_us": "collector",
    "analyst": "analyst",
    "researcher": "researcher",
    "strategist": "strategist",
    "critic": "critic",
    "evaluator": "evaluator",
    "weekly_review": "weekly_review",
    "model_retrain": "model_retrain",
    "garch_refit": "garch_refit",
    "backup": "backup",
}


def _adapt(state: AppState, warehouse: Any | None = None) -> tuple[Any, Any]:
    from services.agent.main import _adapt_state, _adapt_warehouse

    return _adapt_state(state.sqlite), _adapt_warehouse(warehouse or state.duck)


def _write_warehouse(state: AppState):
    """API が read_only のときだけ、短い書き込み接続を開く。"""
    if not getattr(state.duck, "read_only", False):
        return None
    return DuckDBRepo.open(state.settings, read_only=False)


def _maybe_router(state: AppState, adapted_state: Any, adapted_wh: Any) -> LLMRouter | None:
    return build_llm_router(adapted_state, adapted_wh, state.settings)


def _job_market(job_name: str, market: str | None) -> str:
    if job_name.endswith("_jp"):
        return "JP"
    if job_name.endswith("_us"):
        return "US"
    return market or "JP"


def kick_agent_job(
    state: AppState,
    *,
    job_name: str,
    run_id: int,
    market: str | None,
    as_of: dt.date | None = None,
) -> None:
    """プロセス内で既存ジョブ実装をキックする。失敗しても例外は外に出さない。"""
    from services.agent.jobs.analyst import analyst
    from services.agent.jobs.collector import collector
    from services.agent.jobs.critic import critic
    from services.agent.jobs.evaluator import evaluator
    from services.agent.jobs.backup import daily_backup
    from services.agent.jobs.maintenance import garch_refit, model_retrain, weekly_review
    from services.agent.jobs.researcher import researcher
    from services.agent.jobs.strategist import strategist
    from services.agent.main import session_as_of

    mkt = _job_market(job_name, market)
    day = as_of or session_as_of(mkt)
    write_duck = None
    try:
        write_duck = _write_warehouse(state)
        st, wh = _adapt(state, write_duck)
        fns = {
            "collector": collector,
            "analyst": analyst,
            "researcher": researcher,
            "strategist": strategist,
            "critic": critic,
            "evaluator": evaluator,
            "weekly_review": weekly_review,
            "model_retrain": model_retrain,
            "garch_refit": garch_refit,
            "backup": daily_backup,
        }
        inner_name = JOB_FN_NAMES.get(job_name)
        if job_name == "backtest":
            state.sqlite.update_job_run(
                run_id,
                status="failed",
                finished=True,
                error_type="usage",
                error_message="バックテストは POST /api/v1/backtests を使ってください。",
            )
            _publish_finished(state, run_id, "failed")
            return
        fn = fns.get(inner_name or "")
        if fn is None:
            raise ValueError(f"未知のジョブです: {job_name}")
        kwargs: dict[str, Any] = {
            "state": st,
            "warehouse": wh,
            "trigger": "manual",
            "parent_run_id": run_id,
        }
        if inner_name in {"researcher", "strategist", "critic", "evaluator", "weekly_review"}:
            kwargs["router"] = _maybe_router(state, st, wh)
        if inner_name in {"researcher", "strategist"}:
            try:
                kwargs["vector_store"] = get_vector_store(state.settings)
            except Exception:
                logger.info("ベクトルストアを初期化できないためキーワード検索のみ使います")
            router = kwargs.get("router")
            if router is not None:
                kwargs["embed"] = getattr(router, "embed", None)
        if inner_name == "analyst":
            kwargs["ranker"] = try_load_ranker(state.settings, market=mkt)
        if inner_name in {"strategist", "evaluator", "weekly_review"}:
            kwargs["memory"] = st
        if inner_name == "critic":
            kwargs["jquants_plan"] = str(
                getattr(state.settings, "jquants_plan", "free") or "free"
            )
        if inner_name == "model_retrain":
            kwargs["data_dir"] = getattr(state.settings, "data_dir", None)
        if inner_name == "backup":
            kwargs["settings"] = state.settings
            kwargs["backup_dir"] = getattr(state.settings, "backup_dir", None)
        result = fn(mkt, day, **kwargs)
        status, metrics, error_type, error_message, failed_steps = _payload_from_result(result)
        state.sqlite.update_job_run(
            run_id,
            status=status,
            finished=True,
            metrics=metrics,
            error_type=error_type,
            error_message=error_message,
        )
        _publish_finished(state, run_id, status, failed_steps=failed_steps)
    except Exception as exc:
        logger.exception("ジョブ %s の実行に失敗しました", job_name)
        state.sqlite.update_job_run(
            run_id,
            status="failed",
            finished=True,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        _publish_finished(state, run_id, "failed", failed_steps=[job_name])
    finally:
        if write_duck is not None:
            write_duck.close()


def _payload_from_result(result: Any) -> tuple[str, dict[str, Any], str | None, str | None, list[str]]:
    """ジョブ結果から親 job_run へ書く payload を組み立てる。"""
    status = getattr(result, "status", "success") or "success"
    metrics = dict(getattr(result, "metrics", None) or {})
    steps = getattr(result, "steps", None) or {}
    failed_steps = [
        name
        for name, step in steps.items()
        if getattr(step, "status", None) == "failed"
    ]
    if not failed_steps:
        failed_steps = list(metrics.get("failed_steps") or [])
    if failed_steps:
        metrics["failed_steps"] = failed_steps
        step_errors = {
            name: getattr(step, "error", None)
            for name, step in steps.items()
            if getattr(step, "error", None)
        }
        if step_errors:
            metrics["step_errors"] = step_errors
    error_message = getattr(result, "error", None)
    if not error_message and failed_steps:
        parts = []
        for name in failed_steps:
            step = steps.get(name) if isinstance(steps, dict) else None
            err = getattr(step, "error", None) if step is not None else None
            if err is None and isinstance(metrics.get("step_errors"), dict):
                err = metrics["step_errors"].get(name)
            parts.append(f"{name}: {err}" if err else name)
        error_message = " / ".join(parts)
    if not error_message and status == "failed":
        reason = metrics.get("reason")
        error_message = str(reason) if reason else "ジョブが失敗しました"
    error_type = None
    if error_message:
        error_type = "JobFailed" if status == "failed" else "JobPartial"
    inner_id = getattr(result, "run_id", None)
    if inner_id is not None:
        metrics["inner_run_id"] = inner_id
    metrics["as_of"] = getattr(result, "as_of", None)
    if hasattr(metrics["as_of"], "isoformat"):
        metrics["as_of"] = metrics["as_of"].isoformat()
    return status, metrics, error_type, error_message, failed_steps


def _publish_finished(
    state: AppState,
    run_id: int,
    status: str,
    *,
    failed_steps: list[str] | None = None,
) -> None:
    row = state.sqlite.get_job_run(run_id)
    duration = getattr(row, "duration_sec", None) if row is not None else None
    steps = list(failed_steps or [])
    if not steps and row is not None:
        from packages.core.storage import to_dict

        data = to_dict(row, json_fields=("metrics", "checkpoint"))
        metrics = data.get("metrics") or {}
        if isinstance(metrics, dict):
            steps = list(metrics.get("failed_steps") or [])
    state.bus.publish_nowait(
        "job_finished",
        {
            "job_run_id": run_id,
            "status": status,
            "duration_sec": duration,
            "failed_steps": steps,
        },
    )


def resolve_n_trials(state: AppState, body: BacktestRequest) -> int:
    if body.n_trials is not None:
        return int(body.n_trials)
    counter = getattr(state.duck, "count_backtest_runs", None)
    n = int(counter(strategy_name=body.strategy_name) or 0) if callable(counter) else 0
    return max(n, 0) + 1


def _signals_from_warehouse(state: AppState, body: BacktestRequest) -> pd.DataFrame:
    scores = state.duck.read_scores_daily(market=body.market)
    if scores is None or getattr(scores, "empty", True):
        return pd.DataFrame(columns=["as_of", "ticker", "score"])
    work = scores.copy()
    if "score" not in work.columns:
        for candidate in ("total_score", "ml_pred_h20", "quant_score"):
            if candidate in work.columns:
                work = work.rename(columns={candidate: "score"})
                break
    keep = [c for c in ("as_of", "ticker", "score") if c in work.columns]
    return work.loc[:, keep] if keep else pd.DataFrame(columns=["as_of", "ticker", "score"])


def _universe_filter(body: BacktestRequest) -> UniverseFilter:
    spec = body.universe_filter
    if spec is None:
        return UniverseFilter(market=body.market, require_features_complete=False)
    return UniverseFilter(
        market=body.market,
        min_adv_20d=spec.min_adv_20d,
        min_market_cap=spec.min_market_cap,
        exclude_sectors=tuple(spec.exclude_sectors or ()),
        exclude_recently_listed_days=int(spec.exclude_recently_listed_days or 0),
        require_features_complete=False,
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float) and (value != value):  # NaN
        return None
    return value


def _equity_points(result: Any) -> list[dict[str, Any]]:
    equity = getattr(result, "equity", None)
    if equity is None or len(equity) == 0:
        return []
    peak = equity.cummax()
    drawdown = equity / peak.replace(0, pd.NA) - 1.0
    points = []
    for idx, value in equity.items():
        day = idx.date() if hasattr(idx, "date") else idx
        dd = drawdown.loc[idx] if idx in getattr(drawdown, "index", []) else None
        points.append(
            {
                "date": day.isoformat() if hasattr(day, "isoformat") else str(day),
                "equity": float(value),
                "drawdown": None if dd is None or pd.isna(dd) else float(dd),
            }
        )
    return points


def _trade_rows(result: Any) -> list[dict[str, Any]]:
    trades = getattr(result, "trades", None)
    if trades is None or getattr(trades, "empty", True):
        return []
    rows = []
    for rec in trades.to_dict(orient="records"):
        rows.append(
            {
                "ticker": str(rec.get("ticker") or ""),
                "market": rec.get("market"),
                "entry_date": _json_safe(rec.get("entry_date")),
                "exit_date": _json_safe(rec.get("exit_date")),
                "entry_price": rec.get("entry_price"),
                "exit_price": rec.get("exit_price"),
                "quantity": rec.get("quantity") or rec.get("weight"),
                "pnl": rec.get("pnl"),
                "return_pct": rec.get("raw_return") or rec.get("return_pct"),
                "cost_bps": rec.get("cost_bps"),
            }
        )
    return rows


def execute_backtest(state: AppState, *, body: BacktestRequest, run_id: int, backtest_id: str) -> None:
    n_trials = resolve_n_trials(state, body)
    try:
        prices = state.duck.read_prices_daily(
            market=body.market, start=body.period_start, end=body.period_end
        )
        signals = _signals_from_warehouse(state, body)
        result = run_backtest(
            signals=signals,
            prices=prices if isinstance(prices, pd.DataFrame) else pd.DataFrame(prices),
            market=body.market,
            period=(body.period_start, body.period_end),
            rebalance_freq=body.rebalance_freq,  # type: ignore[arg-type]
            n_positions=body.n_positions,
            fee_bps=body.fee_bps,
            slippage_bps=body.slippage_bps,
            max_turnover_pct=body.max_turnover_pct,
            n_trials=n_trials,
            universe_filter=_universe_filter(body),
            benchmark="TOPIX" if body.market == "JP" else "SPX",
        )
        equity = _equity_points(result)
        trades = _trade_rows(result)
        record = {
            "backtest_id": backtest_id,
            "strategy_name": body.strategy_name,
            "market": body.market,
            "period_start": body.period_start,
            "period_end": body.period_end,
            "rebalance_freq": body.rebalance_freq,
            "n_positions": body.n_positions,
            "fee_bps": body.fee_bps,
            "slippage_bps": body.slippage_bps,
            "max_turnover_pct": body.max_turnover_pct,
            "n_trials": n_trials,
            "status": "finished",
            "run_at": utc_now().replace(tzinfo=None),
            **result.to_record(),
            "annualized_return": result.cagr,
            "config": _json_safe({"equity": equity, "trades": trades}),
        }
        try:
            state.duck.upsert_backtest_runs([record])
        except StorageError:
            logger.info("DuckDB が読み取り専用のため backtest_runs は SQLite にだけ残します")
        state.sqlite.update_job_run(
            run_id,
            status="success",
            finished=True,
            metrics={
                "backtest_id": backtest_id,
                "n_trials": n_trials,
                "strategy_name": body.strategy_name,
                "market": body.market,
                "period_start": body.period_start.isoformat(),
                "period_end": body.period_end.isoformat(),
                "rebalance_freq": body.rebalance_freq,
                "n_positions": body.n_positions,
                "fee_bps": body.fee_bps,
                "slippage_bps": body.slippage_bps,
                "max_turnover_pct": body.max_turnover_pct,
                "equity": equity,
                "trades": trades,
                "sharpe": result.sharpe,
                "deflated_sharpe": result.deflated_sharpe,
            },
        )
        _publish_finished(state, run_id, "success")
    except BacktestError as exc:
        logger.info("バックテスト %s を完了できませんでした: %s", backtest_id, exc)
        _fail_backtest(state, body=body, run_id=run_id, backtest_id=backtest_id, n_trials=n_trials, exc=exc)
    except Exception as exc:
        logger.exception("バックテスト %s が失敗しました", backtest_id)
        _fail_backtest(state, body=body, run_id=run_id, backtest_id=backtest_id, n_trials=n_trials, exc=exc)


def _fail_backtest(
    state: AppState,
    *,
    body: BacktestRequest,
    run_id: int,
    backtest_id: str,
    n_trials: int,
    exc: BaseException,
) -> None:
    error_ja = str(exc)
    try:
        state.duck.upsert_backtest_runs(
            [
                {
                    "backtest_id": backtest_id,
                    "strategy_name": body.strategy_name,
                    "market": body.market,
                    "period_start": body.period_start,
                    "period_end": body.period_end,
                    "rebalance_freq": body.rebalance_freq,
                    "n_positions": body.n_positions,
                    "fee_bps": body.fee_bps,
                    "slippage_bps": body.slippage_bps,
                    "max_turnover_pct": body.max_turnover_pct,
                    "n_trials": n_trials,
                    "status": "failed",
                    "error_ja": error_ja,
                    "run_at": utc_now().replace(tzinfo=None),
                }
            ]
        )
    except StorageError:
        pass
    except Exception:
        logger.exception("失敗したバックテスト行の保存にも失敗しました")
    state.sqlite.update_job_run(
        run_id,
        status="failed",
        finished=True,
        error_type=type(exc).__name__,
        error_message=error_ja,
        metrics={
            "backtest_id": backtest_id,
            "n_trials": n_trials,
            "strategy_name": body.strategy_name,
            "market": body.market,
            "period_start": body.period_start.isoformat(),
            "period_end": body.period_end.isoformat(),
            "rebalance_freq": body.rebalance_freq,
            "n_positions": body.n_positions,
            "fee_bps": body.fee_bps,
            "slippage_bps": body.slippage_bps,
            "max_turnover_pct": body.max_turnover_pct,
            "error_ja": error_ja,
        },
    )
    _publish_finished(state, run_id, "failed")


def queue_backtest_row(state: AppState, *, body: BacktestRequest, backtest_id: str, n_trials: int) -> None:
    try:
        state.duck.upsert_backtest_runs(
            [
                {
                    "backtest_id": backtest_id,
                    "strategy_name": body.strategy_name,
                    "market": body.market,
                    "period_start": body.period_start,
                    "period_end": body.period_end,
                    "rebalance_freq": body.rebalance_freq,
                    "n_positions": body.n_positions,
                    "fee_bps": body.fee_bps,
                    "slippage_bps": body.slippage_bps,
                    "max_turnover_pct": body.max_turnover_pct,
                    "n_trials": n_trials,
                    "status": "queued",
                    "run_at": utc_now().replace(tzinfo=None),
                }
            ]
        )
    except StorageError:
        logger.info("DuckDB 読み取り専用のため queued 行は書き込みません")


def _parse_config(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    raw = row.get("config")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _metrics_for_backtest(state: AppState, backtest_id: str) -> dict[str, Any]:
    for row in state.sqlite.get_job_runs(job_name="backtest", limit=200):
        from packages.core.storage import to_dict

        data = to_dict(row, json_fields=("metrics", "checkpoint"))
        metrics = data.get("metrics") or {}
        if isinstance(metrics, str):
            try:
                metrics = json.loads(metrics)
            except json.JSONDecodeError:
                metrics = {}
        if isinstance(metrics, dict) and metrics.get("backtest_id") == backtest_id:
            return metrics
    return {}


def load_backtest_from_jobs(state: AppState, backtest_id: str) -> dict[str, Any] | None:
    metrics = _metrics_for_backtest(state, backtest_id)
    if not metrics:
        return None
    status = "finished"
    for row in state.sqlite.get_job_runs(job_name="backtest", limit=200):
        from packages.core.storage import to_dict

        data = to_dict(row, json_fields=("metrics", "checkpoint"))
        raw = data.get("metrics") or {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}
        if isinstance(raw, dict) and raw.get("backtest_id") == backtest_id:
            status = data.get("status") or status
            break
    return {
        "backtest_id": backtest_id,
        "strategy_name": metrics.get("strategy_name") or "",
        "market": metrics.get("market") or "JP",
        "status": "failed" if status == "failed" else status,
        "period_start": metrics.get("period_start"),
        "period_end": metrics.get("period_end"),
        "rebalance_freq": metrics.get("rebalance_freq") or "monthly",
        "n_positions": metrics.get("n_positions") or 1,
        "fee_bps": metrics.get("fee_bps") or 0.0,
        "slippage_bps": metrics.get("slippage_bps") or 0.0,
        "max_turnover_pct": metrics.get("max_turnover_pct") or 30.0,
        "n_trials": metrics.get("n_trials"),
        "error_ja": metrics.get("error_ja"),
        "sharpe": metrics.get("sharpe"),
        "deflated_sharpe": metrics.get("deflated_sharpe"),
    }


def load_equity_points(state: AppState, backtest_id: str) -> list[EquityCurvePoint]:
    row = state.duck.get_backtest_run(backtest_id) or {}
    config = _parse_config(row)
    raw = config.get("equity") or _metrics_for_backtest(state, backtest_id).get("equity") or []
    points: list[EquityCurvePoint] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        day = item.get("date")
        if day is None:
            continue
        if isinstance(day, str):
            day = dt.date.fromisoformat(day[:10])
        points.append(
            EquityCurvePoint(
                date=day,
                equity=float(item.get("equity") or 0.0),
                benchmark=item.get("benchmark"),
                drawdown=item.get("drawdown"),
            )
        )
    return points


def load_backtest_trades(state: AppState, backtest_id: str, *, limit: int) -> list[BacktestTrade]:
    row = state.duck.get_backtest_run(backtest_id) or {}
    config = _parse_config(row)
    raw = config.get("trades") or _metrics_for_backtest(state, backtest_id).get("trades") or []
    items: list[BacktestTrade] = []
    for item in raw[:limit]:
        if not isinstance(item, dict) or not item.get("ticker"):
            continue
        entry = item.get("entry_date")
        if isinstance(entry, str):
            entry = dt.date.fromisoformat(entry[:10])
        exit_d = item.get("exit_date")
        if isinstance(exit_d, str):
            exit_d = dt.date.fromisoformat(exit_d[:10])
        items.append(
            BacktestTrade(
                ticker=str(item["ticker"]),
                market=item.get("market"),
                entry_date=entry or dt.date.today(),
                exit_date=exit_d,
                entry_price=item.get("entry_price"),
                exit_price=item.get("exit_price"),
                quantity=item.get("quantity"),
                pnl=item.get("pnl"),
                return_pct=item.get("return_pct"),
                cost_bps=item.get("cost_bps"),
            )
        )
    return items


def load_document_chunks(state: AppState, doc_id: str, *, section: str | None) -> DocumentChunkList:
    try:
        store = get_vector_store(state.settings, allow_fallback=True)
        lister = getattr(store, "list_by_doc", None)
        raw = list(lister(doc_id) or []) if callable(lister) else []
    except Exception:
        logger.info("ベクトルストアから chunks を読めませんでした", exc_info=True)
        raw = []
    items: list[DocumentChunk] = []
    for chunk in raw:
        sec = getattr(chunk, "section", None)
        if section and sec != section:
            continue
        items.append(
            DocumentChunk(
                chunk_id=str(getattr(chunk, "chunk_id", "")),
                doc_id=doc_id,
                section=sec,
                page_from=getattr(chunk, "page_from", None),
                page_to=getattr(chunk, "page_to", None),
                text=str(getattr(chunk, "text", "") or ""),
                token_count=getattr(chunk, "token_count", None),
            )
        )
    return DocumentChunkList(doc_id=doc_id, items=items, total=len(items))


def generate_document_summary(state: AppState, *, doc_id: str, doc: Any) -> DocumentSummary:
    st, wh = _adapt(state)
    router = _maybe_router(state, st, wh)
    if router is None:
        raise RuntimeError("LLM_UNAVAILABLE")
    rendered = render_prompt(
        "doc_summary.jinja",
        company_name=getattr(doc, "title", None) or getattr(doc, "ticker", None) or doc_id,
        ticker=getattr(doc, "ticker", None) or "",
        filed_at=getattr(doc, "filed_at", None),
        doc_type_ja=getattr(doc, "doc_type", None) or "",
        prev_doc_available=False,
        schema_json=DocSummaryOutput.model_json_schema(),
    )
    files: list[Path] = []
    row = state.duck.get_document(doc_id) or {}
    blob = row.get("blob_path")
    if blob and Path(blob).is_file():
        files = [Path(blob)]
    resp = router.complete(
        tier="bulk",
        purpose="doc_summary",
        messages=[{"role": "user", "content": rendered}],
        files=files or None,
        response_schema=DocSummaryOutput,
        entity=doc_id,
        prompt_name="doc_summary.jinja",
        prompt_body=rendered,
    )
    parsed = resp.parsed
    if parsed is None or not isinstance(parsed, DocSummaryOutput):
        raise RuntimeError("LLM_UNAVAILABLE")
    existing = state.duck.get_document_summary(doc_id)
    version = int((existing or {}).get("summary_version") or 0) + 1
    payload = {
        "doc_id": doc_id,
        "summary_version": version,
        "model_id": resp.model_id,
        "prompt_hash": prompt_hash("doc_summary.jinja", rendered),
        "input_hash": input_hash({"doc_id": doc_id, "messages": rendered}),
        "headline_ja": parsed.summary_ja[:80],
        "summary_ja": parsed.summary_ja,
        "key_points": parsed.key_points,
        "risk_factors": parsed.risk_factors,
        "guidance_tone": parsed.guidance_tone,
        "guidance_evidence": parsed.guidance_evidence,
        "qualitative_score": parsed.qualitative_score,
        "citations": [{"page": c.page, "quote": c.quote} for c in parsed.citations],
        "input_tokens": resp.input_tokens,
        "output_tokens": resp.output_tokens,
        "cost_usd": resp.cost_usd,
        "cache_hit": resp.was_cache_hit,
        "computed_at": utc_now(),
    }
    try:
        state.duck.upsert_document_summaries([payload])
    except StorageError:
        logger.info("DuckDB 読み取り専用のため要約はレスポンスのみ返します")
    except Exception:
        logger.exception("要約の保存に失敗しました")
    return document_summary_from_row(payload)
