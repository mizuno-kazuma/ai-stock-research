"""テスト用の in-memory fake。storage 実装は編集しない。"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from packages.core.interfaces.storage import (
    JobRun,
    LlmCall,
    MemoryRecord,
    SearchHit,
)
from packages.core.llm.errors import InvariantViolationError


class FakeStateRepo:
    def __init__(self) -> None:
        self._runs: dict[int, JobRun] = {}
        self._seq = 0
        self._checkpoints: dict[int, dict[str, Any]] = {}
        self._calls: list[LlmCall] = []
        self._spend: dict[tuple[str, str], float] = {}
        self._kill: dict[tuple[str, str], bool] = {}
        self.alerts: list[dict[str, Any]] = []
        self._memory: dict[str, MemoryRecord] = {}
        self._settings: dict[str, Any] = {}
        self._weights: list[dict[str, Any]] = []
        self._backfill: dict[str, dict[str, Any]] = {}

    def create_job_run(
        self,
        *,
        job_name: str,
        market: str | None = None,
        trigger: str = "schedule",
        parent_run_id: int | None = None,
    ) -> int:
        self._seq += 1
        run_id = self._seq
        self._runs[run_id] = JobRun(
            id=run_id,
            job_name=job_name,
            status="running",
            started_at=datetime.now(UTC),
            market=market,
            trigger=trigger,
            parent_run_id=parent_run_id,
            pid=os.getpid(),
        )
        return run_id

    def record_job_run(
        self,
        run_id: int,
        *,
        status: str,
        metrics: dict[str, Any] | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        error_traceback: str | None = None,
    ) -> None:
        run = self._runs[run_id]
        run.status = status
        run.finished_at = datetime.now(UTC)
        if metrics:
            run.metrics = metrics
        run.error_type = error_type
        run.error_message = error_message

    def get_job_run(self, run_id: int) -> JobRun | None:
        return self._runs.get(run_id)

    def latest_job_run(
        self, *, job_name: str, market: str | None = None, on_date: date | None = None
    ) -> JobRun | None:
        matches = [
            r
            for r in self._runs.values()
            if r.job_name == job_name and (market is None or r.market == market)
        ]
        # job_runs は as_of を持たない。同一プロセスのパイプラインでは
        # started_at（実行日）と分析対象日がずれるため日付では絞らない。
        matches.sort(key=lambda r: r.id)
        return matches[-1] if matches else None

    def find_job_runs(
        self, *, status: str | None = None, started_before: datetime | None = None
    ) -> list[JobRun]:
        rows = list(self._runs.values())
        if status:
            rows = [r for r in rows if r.status == status]
        if started_before:
            rows = [r for r in rows if r.started_at < started_before]
        return rows

    def save_checkpoint(self, run_id: int, checkpoint: dict[str, Any]) -> None:
        self._checkpoints[run_id] = dict(checkpoint)
        run = self._runs.get(run_id)
        if run is not None:
            run.checkpoint = dict(checkpoint)

    def load_checkpoint(self, run_id: int) -> dict[str, Any] | None:
        return self._checkpoints.get(run_id)

    def insert_llm_call(self, call: LlmCall) -> None:
        self._calls.append(call)

    def sum_llm_cost(self, *, period: str, period_key: str) -> float:
        total = 0.0
        for c in self._calls:
            key = c.called_at.date().isoformat() if period == "day" else c.called_at.strftime("%Y-%m")
            if key == period_key:
                total += c.cost_usd
        return total

    def get_budget(self, *, period: str, period_key: str) -> dict[str, Any] | None:
        return {
            "spent_usd": self._spend.get((period, period_key), 0.0),
            "kill_switch_on": self._kill.get((period, period_key), False),
        }

    def add_spend(self, *, period: str, period_key: str, amount_usd: float) -> float:
        key = (period, period_key)
        self._spend[key] = self._spend.get(key, 0.0) + amount_usd
        return self._spend[key]

    def set_kill_switch(self, *, period: str, period_key: str, on: bool) -> None:
        self._kill[(period, period_key)] = on

    def create_alert(self, **kwargs: Any) -> None:
        self.alerts.append(kwargs)

    def select_memory(self, **kwargs: Any) -> list[MemoryRecord]:
        rows = [m for m in self._memory.values() if m.is_active]
        return rows[: kwargs.get("limit", 15)]

    def list_memory(self, *, include_inactive: bool = False) -> list[MemoryRecord]:
        rows = list(self._memory.values())
        if not include_inactive:
            rows = [m for m in rows if m.is_active]
        return rows

    def insert_memory(self, record: MemoryRecord) -> str:
        self._memory[record.memory_id] = record
        return record.memory_id

    def update_memory(self, memory_id: str, fields: dict[str, Any]) -> None:
        rec = self._memory[memory_id]
        for k, v in fields.items():
            setattr(rec, k, v)

    def touch_memory(self, memory_ids: list[str]) -> None:
        for mid in memory_ids:
            if mid in self._memory:
                self._memory[mid].use_count += 1

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        self._settings[key] = value

    def read_open_positions(self) -> pd.DataFrame:
        return pd.DataFrame()

    def read_watchlist(self) -> pd.DataFrame:
        return pd.DataFrame()

    def get_active_factor_weights(self, *, market: str, horizon: str) -> dict[str, Any] | None:
        return None

    def insert_factor_weights(self, row: dict[str, Any]) -> str:
        self._weights.append(row)
        return str(len(self._weights))

    def get_backfill_progress(self, step_name: str) -> dict[str, Any] | None:
        return self._backfill.get(step_name)

    def set_backfill_progress(self, step_name: str, fields: dict[str, Any]) -> None:
        current = dict(self._backfill.get(step_name) or {})
        current.update(fields)
        self._backfill[step_name] = current

    def save_backfill_progress(
        self,
        step_name: str,
        *,
        status: str,
        cursor_value: str | None = None,
        total_units: int | None = None,
        done_units: int | None = None,
    ) -> None:
        self.set_backfill_progress(
            step_name,
            {
                "status": status,
                "cursor_value": cursor_value,
                "total_units": total_units,
                "done_units": done_units,
            },
        )

    def load_rate_limit_state(self, source: str) -> Any:
        return None

    def save_rate_limit_state(self, state: Any) -> None:
        return None


class FakeWarehouse:
    def __init__(self) -> None:
        self.prices = pd.DataFrame()
        self.securities = pd.DataFrame()
        self.features = pd.DataFrame()
        self.scores = pd.DataFrame()
        self.documents: dict[str, dict[str, Any]] = {}
        self.doc_text: dict[str, str] = {}
        self.recs: list[dict[str, Any]] = []
        self.outcomes: list[dict[str, Any]] = []
        self.fx_rows: list[dict[str, Any]] = []
        self.model_runs: list[dict[str, Any]] = []
        self.backtests: list[dict[str, Any]] = []
        self.gaps: list[dict[str, Any]] = []
        self.flags: list[dict[str, Any]] = []
        self.freshness = pd.DataFrame(columns=["source", "latest_as_of"])
        self.summaries: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.coverage: dict[str, date | None] = {}
        self.macro_rows: list[dict[str, Any]] = []

    def upsert_securities(self, df: pd.DataFrame) -> int:
        self.securities = df
        return len(df)

    def read_securities(self, *, market: str | None = None, as_of: date | None = None) -> pd.DataFrame:
        return self.securities.copy()

    def get_securities(self, *, market: str | None = None, **kwargs: Any) -> list[dict[str, Any]]:
        frame = self.securities.copy()
        if market and not frame.empty and "market" in frame.columns:
            frame = frame.loc[frame["market"].astype(str) == market]
        if frame.empty:
            return []
        return frame.to_dict("records")

    def upsert_prices_daily(self, df: pd.DataFrame) -> int:
        self.prices = df
        return len(df)

    def read_prices_daily(self, **kwargs: Any) -> pd.DataFrame:
        df = self.prices.copy()
        tickers = kwargs.get("tickers")
        if tickers and not df.empty and "ticker" in df.columns:
            df = df.loc[df["ticker"].astype(str).isin([str(t) for t in tickers])]
        start = kwargs.get("start")
        end = kwargs.get("end")
        if (start or end) and not df.empty and "trade_date" in df.columns:
            dates = pd.to_datetime(df["trade_date"]).dt.date
            if start:
                df = df.loc[dates >= start]
                dates = pd.to_datetime(df["trade_date"]).dt.date
            if end:
                df = df.loc[dates <= end]
        return df

    def latest_coverage_date(
        self, table: str, *, market: str | None = None, date_col: str | None = None
    ) -> date | None:
        if table in self.coverage:
            return self.coverage[table]
        if table != "prices_daily" or self.prices.empty or "trade_date" not in self.prices.columns:
            return None
        work = self.prices
        if market and "market" in work.columns:
            work = work.loc[work["market"].astype(str) == market]
        if work.empty:
            return None
        dates = pd.to_datetime(work["trade_date"], errors="coerce")
        latest = dates.max()
        if pd.isna(latest):
            return None
        return latest.date()

    def upsert_prices_live(self, df: pd.DataFrame) -> int:
        raise AssertionError("prices_live をモデル経路から呼んではいけない")

    def upsert_financials(self, df: pd.DataFrame) -> int:
        return len(df)

    def get_financials_as_of(self, **kwargs: Any) -> pd.DataFrame:
        return pd.DataFrame()

    def upsert_documents(self, df: pd.DataFrame) -> int:
        for _, row in df.iterrows():
            self.documents[str(row["doc_id"])] = row.to_dict()
        return len(df)

    def read_documents(self, **kwargs: Any) -> pd.DataFrame:
        rows = list(self.documents.values())
        tickers = kwargs.get("tickers")
        if tickers:
            rows = [r for r in rows if str(r.get("ticker")) in {str(t) for t in tickers}]
        return pd.DataFrame(rows)

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        return self.documents.get(doc_id)

    def get_document_text(self, doc_id: str, *, page: int | None = None) -> str | None:
        return self.doc_text.get(doc_id)

    def search_text(
        self,
        query: str,
        *,
        k: int,
        ticker: str | None = None,
        market: str | None = None,
        as_of: date | None = None,
        doc_types: list[str] | None = None,
    ) -> list[SearchHit]:
        q = (query or "").lower()
        hits: list[SearchHit] = []
        for doc_id, row in self.documents.items():
            if ticker and str(row.get("ticker")) != str(ticker):
                continue
            if market and str(row.get("market")) != str(market):
                continue
            hay = f"{row.get('title') or ''} {self.doc_text.get(doc_id) or ''}"
            if q and q.split() and not any(part in hay.lower() for part in q.split() if len(part) >= 2):
                continue
            snippet = hay.strip()[:1200]
            if len(snippet) < 20:
                continue
            hits.append(
                SearchHit(
                    chunk_id=f"{doc_id}:kw",
                    doc_id=str(doc_id),
                    text=snippet,
                    ticker=row.get("ticker"),
                    market=row.get("market"),
                    title=row.get("title"),
                    filed_at=row.get("filed_at") if hasattr(row.get("filed_at"), "date") else None,
                )
            )
            if len(hits) >= k:
                break
        return hits

    def upsert_document_summaries(self, rows: Any) -> int:
        records = rows.to_dict(orient="records") if isinstance(rows, pd.DataFrame) else list(rows)
        for item in records:
            key = (
                str(item.get("doc_id")),
                str(item.get("prompt_hash") or ""),
                str(item.get("input_hash") or ""),
            )
            self.summaries[key] = item
        return len(records)

    def find_summary(
        self, *, doc_id: str, prompt_hash: str | None = None, input_hash: str | None = None
    ) -> dict[str, Any] | None:
        if prompt_hash is not None and input_hash is not None:
            return self.summaries.get((doc_id, prompt_hash, input_hash))
        for (did, _p, _i), row in self.summaries.items():
            if did == doc_id:
                return row
        return None

    def upsert_macro_series(self, df: pd.DataFrame) -> int:
        return len(df)

    def read_macro_as_of(self, **kwargs: Any) -> pd.DataFrame:
        series_ids = kwargs.get("series_ids") or []
        if not self.macro_rows:
            return pd.DataFrame()
        rows = [r for r in self.macro_rows if not series_ids or r.get("series_id") in series_ids]
        return pd.DataFrame(rows)

    def get_macro_as_of(
        self, series_id: str, *, as_of: date, limit: int = 60
    ) -> list[dict[str, Any]]:
        rows = [r for r in self.macro_rows if r.get("series_id") == series_id]
        return rows[: int(limit)]

    def upsert_features_daily(self, df: Any) -> int:
        incoming = df if isinstance(df, pd.DataFrame) else pd.DataFrame(list(df))
        if getattr(self.features, "empty", True):
            self.features = incoming
        else:
            self.features = pd.concat([self.features, incoming], ignore_index=True)
        return len(incoming)

    def read_features_daily(self, **kwargs: Any) -> pd.DataFrame:
        return self.features.copy()

    def upsert_scores_daily(self, df: pd.DataFrame) -> int:
        self.scores = df
        return len(df)

    def read_scores_daily(self, **kwargs: Any) -> pd.DataFrame:
        return self.scores.copy()

    def insert_recommendation(self, rec: dict[str, Any]) -> str:
        bear = (rec.get("bear_case_ja") or "").strip()
        if len(bear) < 20:
            raise InvariantViolationError("bear_case")
        if rec.get("expected_ret_lo") is None or rec.get("expected_ret_hi") is None:
            raise InvariantViolationError("confidence_interval")
        if rec.get("conviction_score") is None:
            raise InvariantViolationError("conviction_score")
        if not rec.get("citations"):
            raise InvariantViolationError("citations")
        n_prior = rec.get("n_prior_samples") or 0
        if n_prior < 20:
            rec["conviction"] = "low"
        self.recs.append(rec)
        return str(rec["rec_id"])

    def update_recommendation(self, rec_id: str, fields: dict[str, Any]) -> int:
        for r in self.recs:
            if r.get("rec_id") == rec_id:
                r.update(fields)
                return 1
        return 0

    def get_recommendations(self, **kwargs: Any) -> list[dict[str, Any]]:
        rows = list(self.recs)
        if kwargs.get("as_of") is not None:
            rows = [r for r in rows if r.get("as_of") == kwargs["as_of"]]
        if kwargs.get("market") is not None:
            rows = [r for r in rows if r.get("market") == kwargs["market"]]
        if kwargs.get("horizon") is not None:
            rows = [r for r in rows if r.get("horizon") == kwargs["horizon"]]
        if "critic_verdict" in kwargs:
            want = kwargs["critic_verdict"]
            rows = [r for r in rows if r.get("critic_verdict") == want]
        return rows

    def upsert_recommendation_outcomes(self, rows: list[dict[str, Any]]) -> int:
        self.outcomes.extend(rows)
        return len(rows)

    def read_recommendation_outcomes(self, **kwargs: Any) -> pd.DataFrame:
        rows = list(self.outcomes)
        if kwargs.get("market") is not None:
            rows = [r for r in rows if r.get("market") == kwargs["market"]]
        if kwargs.get("horizon") is not None:
            rows = [r for r in rows if r.get("horizon") == kwargs["horizon"]]
        return pd.DataFrame(rows)

    def upsert_fx_forecasts(self, df: pd.DataFrame) -> int:
        self.fx_rows.extend(df.to_dict(orient="records"))
        return len(df)

    def insert_model_run(self, row: dict[str, Any]) -> str:
        self.model_runs.append(row)
        return str(len(self.model_runs))

    def update_model_run(self, run_id: str, fields: dict[str, Any]) -> int:
        return 0

    def count_model_runs(self, *, model_kind: str | None = None) -> int:
        return len(self.model_runs)

    def insert_backtest_run(self, row: dict[str, Any]) -> str:
        self.backtests.append(row)
        return str(len(self.backtests))

    def count_backtest_runs(self, *, strategy_name: str | None = None) -> int:
        return len(self.backtests)

    def record_data_gap(self, **kwargs: Any) -> None:
        self.gaps.append(kwargs)

    def record_data_quality_flag(self, **kwargs: Any) -> None:
        self.flags.append(kwargs)

    def record_data_conflict(self, **kwargs: Any) -> None:
        return None

    def read_data_freshness(self) -> pd.DataFrame:
        return self.freshness.copy()

    def upsert_earnings_dates(self, df: pd.DataFrame) -> int:
        return len(df)

    def read_earnings_dates(self, **kwargs: Any) -> pd.DataFrame:
        return pd.DataFrame()


class FakeVectorStore:
    def __init__(self) -> None:
        self.chunks: list[Any] = []

    def upsert(self, chunks: list[Any]) -> int:
        self.chunks.extend(chunks)
        return len(chunks)

    def search(self, query_vec: list[float], *, k: int, filters: dict[str, Any] | None = None) -> list[SearchHit]:
        hits = []
        for ch in self.chunks[:k]:
            filed = getattr(ch, "filed_at", None)
            if filters and "$lte" in (filters.get("filed_at") or {}):
                as_of = filters["filed_at"]["$lte"]
                if filed is not None and filed.date() > as_of:
                    continue
            hits.append(
                SearchHit(
                    chunk_id=ch.chunk_id,
                    doc_id=ch.doc_id,
                    text=ch.text,
                    filed_at=filed,
                    ticker=getattr(ch, "ticker", None),
                    market=getattr(ch, "market", None),
                )
            )
        return hits

    def delete_by_doc(self, doc_id: str) -> int:
        n = len(self.chunks)
        self.chunks = [c for c in self.chunks if c.doc_id != doc_id]
        return n - len(self.chunks)
