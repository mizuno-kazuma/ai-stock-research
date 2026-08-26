"""APScheduler エントリ（docs/08-agent-loop.md §2）。

cron や Windows タスクスケジューラは使わない。ジョブ定義は SQLAlchemyJobStore に
永続化し、プロセス再起動後も失われない。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def create_scheduler(*, db_url: str, timezone: str = "Asia/Tokyo") -> Any:
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler(
        timezone=timezone,
        jobstores={"default": SQLAlchemyJobStore(url=db_url)},
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 3600,
        },
    )
    scheduler.add_job(
        run_pipeline_job,
        "cron",
        day_of_week="tue-sat",
        hour=6,
        minute=30,
        args=["US"],
        id="pipeline_us",
        replace_existing=True,
    )
    scheduler.add_job(
        run_pipeline_job,
        "cron",
        day_of_week="mon-fri",
        hour=18,
        minute=30,
        args=["JP"],
        id="pipeline_jp",
        replace_existing=True,
    )
    scheduler.add_job(
        run_weekly_review,
        "cron",
        day_of_week="sat",
        hour=9,
        minute=0,
        id="weekly_review",
        replace_existing=True,
    )
    scheduler.add_job(
        run_model_retrain,
        "cron",
        day="1-7",
        day_of_week="sat",
        hour=10,
        minute=0,
        id="model_retrain",
        replace_existing=True,
    )
    scheduler.add_job(
        refit_garch,
        "cron",
        day_of_week="mon",
        hour=7,
        minute=0,
        id="garch_refit",
        replace_existing=True,
    )
    scheduler.add_job(
        resume_interrupted_jobs,
        "interval",
        minutes=15,
        id="resume_check",
        replace_existing=True,
    )
    return scheduler


def run_pipeline_job(market: str) -> None:
    """スケジュールから呼ばれる。storage は遅延 import。"""
    from datetime import date

    from packages.core.storage import DuckDBRepo, SQLiteRepo

    from services.agent.pipeline import run_pipeline

    as_of = date.today()
    with DuckDBRepo.open() as warehouse, SQLiteRepo.open() as sqlite:
        state = _adapt_state(sqlite)
        run_pipeline(
            market,
            as_of,
            state=state,
            warehouse=_adapt_warehouse(warehouse),
        )


def run_weekly_review() -> None:
    logger.info("weekly_review: deep 層は pipeline 側で別途起動する")


def run_model_retrain() -> None:
    logger.info("model_retrain: LightGBM 再学習は月次。実装は ranker.train_ranker")


def refit_garch() -> None:
    logger.info("garch_refit: 週次パラメータ再推定")


def resume_interrupted_jobs(*, state: Any | None = None, max_chain: int = 5) -> list[int]:
    """15 分ごとに実行。running のまま 2 時間以上経過し、プロセスが死んでいれば再開。"""
    if state is None:
        return []
    stale = state.find_job_runs(
        status="running",
        started_before=datetime.now(UTC) - timedelta(hours=2),
    )
    resumed: list[int] = []
    for run in stale:
        if _is_process_alive(getattr(run, "pid", None)):
            continue
        chain = 0
        parent = getattr(run, "parent_run_id", None)
        while parent is not None and chain <= max_chain:
            chain += 1
            parent_run = state.get_job_run(parent)
            parent = None if parent_run is None else parent_run.parent_run_id
        if chain >= max_chain:
            state.record_job_run(
                run.id, status="failed", error_type="resume_limit", error_message="再開連鎖が上限"
            )
            continue
        state.record_job_run(run.id, status="interrupted")
        new_id = state.create_job_run(
            job_name=run.job_name,
            market=run.market,
            trigger="resume",
            parent_run_id=run.id,
        )
        resumed.append(new_id)
    return resumed


def _is_process_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        import os

        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _adapt_state(sqlite: Any) -> Any:
    """SQLiteRepo のメソッド名を Protocol に寄せる薄いアダプタ。"""

    class Adapter:
        def __init__(self, inner: Any) -> None:
            self._i = inner

        def create_job_run(self, **kwargs: Any) -> int:
            name = kwargs.pop("job_name")
            return self._i.start_job_run(name, **kwargs)

        def record_job_run(self, run_id: int, **kwargs: Any) -> None:
            kwargs.pop("error_traceback", None)
            self._i.update_job_run(run_id, finished=True, **kwargs)

        def get_job_run(self, run_id: int) -> Any:
            return self._i.get_job_run(run_id)

        def latest_job_run(self, **kwargs: Any) -> Any:
            return self._i.latest_job_run(
                kwargs.get("job_name"),
                market=kwargs.get("market"),
                on_date=kwargs.get("on_date"),
            )

        def find_job_runs(self, **kwargs: Any) -> list[Any]:
            finder = getattr(self._i, "find_job_runs", None)
            if callable(finder):
                return finder(
                    status=kwargs.get("status"),
                    started_before=kwargs.get("started_before"),
                )
            return self._i.get_job_runs(status=kwargs.get("status"))

        def save_checkpoint(self, run_id: int, checkpoint: dict) -> None:
            self._i.update_job_run(run_id, checkpoint=checkpoint)

        def load_checkpoint(self, run_id: int) -> dict | None:
            row = self._i.get_job_run(run_id)
            if row is None or not getattr(row, "checkpoint", None):
                return None
            import json

            raw = row.checkpoint
            return json.loads(raw) if isinstance(raw, str) else raw

        def insert_llm_call(self, call: Any) -> None:
            payload = call if isinstance(call, dict) else {
                "call_id": getattr(call, "call_id"),
                "tier": getattr(call, "tier"),
                "model_id": getattr(call, "model_id"),
                "purpose": getattr(call, "purpose"),
                "input_tokens": getattr(call, "input_tokens"),
                "output_tokens": getattr(call, "output_tokens"),
                "cost_usd": getattr(call, "cost_usd"),
                "status": getattr(call, "status"),
                "called_at": getattr(call, "called_at"),
                "job_run_id": getattr(call, "job_run_id", None),
                "entity": getattr(call, "entity", None),
                "cached_tokens": getattr(call, "cached_tokens", 0),
                "latency_ms": getattr(call, "latency_ms", None),
                "was_cache_hit": getattr(call, "was_cache_hit", False),
                "error_message": getattr(call, "error_message", None),
            }
            called = payload.get("called_at")
            if hasattr(called, "isoformat"):
                payload["called_at"] = called.isoformat()
            self._i.record_llm_call(**payload)

        def sum_llm_cost(self, *, period: str, period_key: str) -> float:
            if period == "day":
                summary = self._i.llm_cost_summary(day_key=period_key, month_key=period_key[:7])
                return float(summary.get("spent_today_usd") or 0.0)
            summary = self._i.llm_cost_summary(day_key=f"{period_key}-01", month_key=period_key)
            return float(summary.get("spent_month_usd") or 0.0)

        def get_budget(self, *, period: str, period_key: str) -> dict[str, Any] | None:
            row = self._i.get_cost_budget(period, period_key)
            if row is None:
                return None
            return {
                "spent_usd": getattr(row, "spent_usd", 0.0),
                "kill_switch_on": getattr(row, "kill_switch_on", False),
                "cap_usd": getattr(row, "cap_usd", 0.0),
            }

        def load_rate_limit_state(self, source: str) -> Any:
            row = self._i.get_rate_limit_state(source)
            if row is None:
                return None
            from datetime import UTC, datetime

            from packages.core.interfaces.storage import RateLimitState as RL

            last = getattr(row, "last_refill_at", None)
            if isinstance(last, str):
                last = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if last is not None and getattr(last, "tzinfo", None) is None:
                last = last.replace(tzinfo=UTC)
            return RL(
                source=str(row.source),
                tokens=float(row.tokens),
                last_refill_at=last or datetime.now(UTC),
                calls_today=int(getattr(row, "calls_today", 0) or 0),
                day_key=str(getattr(row, "day_key", "") or ""),
            )

        def save_rate_limit_state(self, state: Any) -> None:
            self._i.save_rate_limit_state(state)

        def __getattr__(self, name: str) -> Any:
            return getattr(self._i, name)

    return Adapter(sqlite)


def _adapt_warehouse(duck: Any) -> Any:
    class Adapter:
        def __init__(self, inner: Any) -> None:
            self._i = inner

        def insert_recommendation(self, rec: dict) -> str:
            self._i.insert_recommendations([rec])
            return str(rec.get("rec_id") or "")

        def read_securities(self, **kwargs: Any) -> Any:
            import pandas as pd

            return pd.DataFrame(self._i.get_securities(**kwargs) or [])

        def read_scores_daily(self, **kwargs: Any) -> Any:
            import pandas as pd

            return pd.DataFrame(self._i.get_scores(**kwargs) or [])

        def read_documents(self, **kwargs: Any) -> Any:
            import pandas as pd

            mapped: dict[str, Any] = {"market": kwargs.get("market")}
            if kwargs.get("filed_from") is not None:
                mapped["since"] = kwargs["filed_from"]
            if kwargs.get("filed_to") is not None:
                mapped["until"] = kwargs["filed_to"]
            tickers = kwargs.get("tickers")
            if tickers:
                mapped["ticker"] = tickers[0]
            doc_types = kwargs.get("doc_types")
            if doc_types:
                mapped["doc_type"] = doc_types[0]
            mapped = {k: v for k, v in mapped.items() if v is not None}
            return pd.DataFrame(self._i.get_documents(**mapped) or [])

        def find_summary(self, **kwargs: Any) -> dict | None:
            doc_id = kwargs.get("doc_id")
            if doc_id is None:
                return None
            return self._i.get_document_summary(doc_id)

        def record_data_gap(self, **kwargs: Any) -> None:
            method = getattr(self._i, "record_data_gap", None)
            if callable(method):
                method(**kwargs)
                return
            self._i.upsert_data_gaps([kwargs])

        def record_data_quality_flag(self, **kwargs: Any) -> None:
            method = getattr(self._i, "record_data_quality_flag", None)
            if callable(method):
                method(**kwargs)
                return
            self._i.upsert_data_quality_flags([kwargs])

        def record_data_conflict(self, **kwargs: Any) -> None:
            method = getattr(self._i, "record_data_conflict", None)
            if callable(method):
                method(**kwargs)
                return
            self._i.upsert_data_conflicts([kwargs])

        def insert_backtest_run(self, row: dict) -> str:
            self._i.upsert_backtest_runs([row])
            return str(row.get("backtest_id") or "")

        def insert_model_run(self, row: dict) -> str:
            self._i.upsert_model_runs([row])
            return str(row.get("run_id") or "")

        def read_prices_daily(self, **kwargs: Any) -> Any:
            reader = getattr(self._i, "read_prices_daily", None)
            if callable(reader):
                return reader(**kwargs)
            import pandas as pd

            ticker = None
            tickers = kwargs.get("tickers")
            if tickers:
                ticker = tickers[0]
            if ticker and kwargs.get("market"):
                return pd.DataFrame(
                    self._i.get_prices_daily(
                        ticker,
                        kwargs["market"],
                        start=kwargs.get("start"),
                        end=kwargs.get("end"),
                    )
                    or []
                )
            return pd.DataFrame()

        def get_document_text(self, doc_id: str, *, page: int | None = None) -> str | None:
            getter = getattr(self._i, "get_document_text", None)
            if callable(getter):
                return getter(doc_id, page=page)
            return None

        def count_model_runs(self, *, model_kind: str | None = None) -> int:
            counter = getattr(self._i, "count_model_runs", None)
            if callable(counter):
                return int(counter(model_kind=model_kind))
            rows = self._i.get_model_runs(model_kind=model_kind, limit=10_000)
            return len(rows or [])

        def upsert_earnings_dates(self, df: Any) -> int:
            method = getattr(self._i, "upsert_earnings_dates", None)
            if callable(method):
                return int(method(df))
            return 0

        def __getattr__(self, name: str) -> Any:
            return getattr(self._i, name)

    return Adapter(duck)


def main() -> None:
    from packages.core.config import get_settings

    settings = get_settings()
    url = settings.database_url or f"sqlite:///{settings.state_db_path}"
    # aiosqlite URL は APScheduler には使えないので同期に戻す。
    url = url.replace("sqlite+aiosqlite://", "sqlite://")
    scheduler = create_scheduler(db_url=url, timezone=settings.tz)
    logger.info("agent scheduler starting (tz=%s)", settings.tz)
    scheduler.start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
