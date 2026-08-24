"""ストレージ層（`packages/core/storage/`）に対する契約。

docs/03-data-model.md のテーブル定義から素直に導けるシグネチャのみを置く。
DuckDB 側（分析）を `WarehouseRepo`、SQLite 側（状態）を `StateRepo` として分け、
docs/03-data-model.md §1 の「ライタは agent のみ / API は read_only」という
方針をそのまま型に反映する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable

import pandas as pd

# ---------------------------------------------------------------------------
# 値オブジェクト
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class RateLimitState:
    """SQLite `rate_limit_state` テーブルの1行に対応する。"""

    source: str
    tokens: float
    last_refill_at: datetime
    calls_today: int = 0
    day_key: str = ""


@dataclass(slots=True)
class SearchHit:
    """LanceDB / FTS からの検索結果1件。docs/03-data-model.md §4。"""

    chunk_id: str
    doc_id: str
    text: str
    score: float = 0.0
    ticker: str | None = None
    market: str | None = None
    doc_type: str | None = None
    filed_at: datetime | None = None
    section: str | None = None
    page_from: int | None = None
    page_to: int | None = None
    title: str | None = None


@dataclass(slots=True)
class DocChunk:
    chunk_id: str
    doc_id: str
    text: str
    embedding: list[float]
    ticker: str | None = None
    market: str | None = None
    doc_type: str | None = None
    filed_at: datetime | None = None
    fiscal_period: str | None = None
    section: str | None = None
    page_from: int | None = None
    page_to: int | None = None
    token_count: int | None = None
    embedding_model: str | None = None
    embedding_version: str | None = None


@dataclass(slots=True)
class JobRun:
    """SQLite `job_runs` テーブルの1行。"""

    id: int
    job_name: str
    status: str
    started_at: datetime
    market: str | None = None
    trigger: str = "schedule"
    finished_at: datetime | None = None
    duration_sec: float | None = None
    checkpoint: dict[str, Any] | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    parent_run_id: int | None = None
    pid: int | None = None


@dataclass(slots=True)
class LlmCall:
    """SQLite `llm_calls` テーブルの1行。"""

    call_id: str
    tier: str
    model_id: str
    purpose: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    status: str
    called_at: datetime
    job_run_id: int | None = None
    entity: str | None = None
    cached_tokens: int = 0
    latency_ms: int | None = None
    was_cache_hit: bool = False
    error_message: str | None = None


@dataclass(slots=True)
class MemoryRecord:
    """SQLite `agent_memory` テーブルの1行。"""

    memory_id: str
    scope: str
    category: str
    lesson_ja: str
    evidence_ja: str
    n_observations: int
    confidence: float
    scope_value: str | None = None
    derived_from: list[str] = field(default_factory=list)
    hit_rate_before: float | None = None
    hit_rate_after: float | None = None
    is_active: bool = True
    superseded_by: str | None = None
    use_count: int = 0


# ---------------------------------------------------------------------------
# DuckDB 側（分析）
# ---------------------------------------------------------------------------


@runtime_checkable
class WarehouseRepo(Protocol):
    """DuckDB（`data/warehouse/analytics.duckdb`）へのアクセス。

    「読み取りは as_of を必ず引数に取る」「生SQLを呼び出し側に書かせない」
    という docs/03-data-model.md §2.4 の方針を型で強制する。
    """

    # --- 銘柄マスタ ---
    def upsert_securities(self, df: pd.DataFrame) -> int: ...

    def read_securities(
        self, *, market: str | None = None, as_of: date | None = None
    ) -> pd.DataFrame:
        """`as_of` 時点で有効だった行のみを返す（valid_from/valid_to で絞る）。

        `as_of=None` は現行行（valid_to IS NULL）。上場廃止銘柄も
        生存者バイアスを避けるため削除せず残す。
        """
        ...

    # --- 価格 ---
    def upsert_prices_daily(self, df: pd.DataFrame) -> int: ...

    def read_prices_daily(
        self,
        *,
        market: str | None = None,
        tickers: list[str] | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> pd.DataFrame: ...

    def upsert_prices_live(self, df: pd.DataFrame) -> int: ...

    # --- 財務（PIT） ---
    def upsert_financials(self, df: pd.DataFrame) -> int: ...

    def get_financials_as_of(
        self,
        *,
        as_of: date,
        market: str | None = None,
        tickers: list[str] | None = None,
    ) -> pd.DataFrame:
        """`filed_at <= as_of` かつ会計期間ごとに最新提出のものだけを返す。

        docs/03-data-model.md §2.4。呼び出し側に `financials` 生テーブルを
        触らせないための唯一の入口。
        """
        ...

    # --- 開示資料 ---
    def upsert_documents(self, df: pd.DataFrame) -> int: ...

    def read_documents(
        self,
        *,
        market: str | None = None,
        tickers: list[str] | None = None,
        filed_from: date | None = None,
        filed_to: date | None = None,
        doc_types: list[str] | None = None,
    ) -> pd.DataFrame: ...

    def get_document(self, doc_id: str) -> dict[str, Any] | None: ...

    def get_document_text(self, doc_id: str, *, page: int | None = None) -> str | None: ...

    def upsert_document_summaries(self, df: pd.DataFrame) -> int: ...

    def find_summary(
        self, *, doc_id: str, prompt_hash: str, input_hash: str
    ) -> dict[str, Any] | None: ...

    # --- マクロ ---
    def upsert_macro_series(self, df: pd.DataFrame) -> int: ...

    def read_macro_as_of(
        self, *, series_ids: list[str], as_of: date, start: date | None = None
    ) -> pd.DataFrame:
        """`vintage_date <= as_of` の中で最新 vintage の値を返す。"""
        ...

    # --- 特徴量・スコア ---
    def upsert_features_daily(self, df: pd.DataFrame) -> int: ...

    def read_features_daily(
        self,
        *,
        as_of: date | None = None,
        start: date | None = None,
        end: date | None = None,
        market: str | None = None,
        feature_version: str | None = None,
        tickers: list[str] | None = None,
    ) -> pd.DataFrame: ...

    def upsert_scores_daily(self, df: pd.DataFrame) -> int: ...

    def read_scores_daily(
        self,
        *,
        as_of: date,
        market: str | None = None,
        weight_set_id: str | None = None,
    ) -> pd.DataFrame: ...

    # --- 推奨 ---
    def insert_recommendation(self, rec: dict[str, Any]) -> str:
        """不変条件（docs/03-data-model.md §2.9）を満たさない場合は
        `InvariantViolationError` を投げる。"""
        ...

    def update_recommendation(self, rec_id: str, fields: dict[str, Any]) -> int: ...

    def get_recommendations(
        self,
        *,
        as_of: date | None = None,
        market: str | None = None,
        horizon: str | None = None,
        critic_verdict: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def upsert_recommendation_outcomes(self, rows: list[dict[str, Any]]) -> int: ...

    def read_recommendation_outcomes(
        self, *, market: str | None = None, horizon: str | None = None, since: date | None = None
    ) -> pd.DataFrame: ...

    # --- 予測・モデル ---
    def upsert_fx_forecasts(self, df: pd.DataFrame) -> int: ...

    def insert_model_run(self, row: dict[str, Any]) -> str: ...

    def update_model_run(self, run_id: str, fields: dict[str, Any]) -> int: ...

    def count_model_runs(self, *, model_kind: str | None = None) -> int:
        """DSR の `n_trials` 自動集計に使う（docs/04-analysis-engine.md §4.4）。"""
        ...

    def insert_backtest_run(self, row: dict[str, Any]) -> str: ...

    def count_backtest_runs(self, *, strategy_name: str | None = None) -> int: ...

    # --- 補助 ---
    def record_data_gap(
        self,
        *,
        source: str,
        entity: str,
        gap_start: date,
        gap_end: date,
        reason: str,
    ) -> None: ...

    def record_data_quality_flag(
        self,
        *,
        table_name: str,
        entity: str,
        as_of: date,
        flag_code: str,
        detail: str | None = None,
    ) -> None: ...

    def record_data_conflict(
        self,
        *,
        entity: str,
        field: str,
        as_of: date,
        source_a: str,
        value_a: float | None,
        source_b: str,
        value_b: float | None,
    ) -> None: ...

    def read_data_freshness(self) -> pd.DataFrame:
        """`data_freshness` ビュー（source, latest_as_of）。"""
        ...

    def upsert_earnings_dates(self, df: pd.DataFrame) -> int: ...

    def read_earnings_dates(
        self, *, market: str | None = None, tickers: list[str] | None = None
    ) -> pd.DataFrame: ...


# ---------------------------------------------------------------------------
# SQLite 側（状態）
# ---------------------------------------------------------------------------


@runtime_checkable
class JobRunRepo(Protocol):
    def create_job_run(
        self,
        *,
        job_name: str,
        market: str | None = None,
        trigger: str = "schedule",
        parent_run_id: int | None = None,
    ) -> int: ...

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
        """終了状態の記録。`status` は running/success/partial/failed/skipped。"""
        ...

    def get_job_run(self, run_id: int) -> JobRun | None: ...

    def latest_job_run(
        self, *, job_name: str, market: str | None = None, on_date: date | None = None
    ) -> JobRun | None:
        """ジョブ間の依存判定に使う（docs/01-architecture.md §4.1）。"""
        ...

    def find_job_runs(
        self, *, status: str | None = None, started_before: datetime | None = None
    ) -> list[JobRun]: ...

    def save_checkpoint(self, run_id: int, checkpoint: dict[str, Any]) -> None: ...

    def load_checkpoint(self, run_id: int) -> dict[str, Any] | None: ...


@runtime_checkable
class RateLimitStateStore(Protocol):
    """`rate_limit_state` テーブル。プロセス再起動後も制限を守るため永続化する。"""

    def load_rate_limit_state(self, source: str) -> RateLimitState | None: ...

    def save_rate_limit_state(self, state: RateLimitState) -> None: ...


@runtime_checkable
class LlmCallLog(Protocol):
    def insert_llm_call(self, call: LlmCall) -> None: ...

    def sum_llm_cost(self, *, period: str, period_key: str) -> float: ...


@runtime_checkable
class CostBudgetRepo(Protocol):
    def get_budget(self, *, period: str, period_key: str) -> dict[str, Any] | None: ...

    def add_spend(self, *, period: str, period_key: str, amount_usd: float) -> float: ...

    def set_kill_switch(self, *, period: str, period_key: str, on: bool) -> None: ...


@runtime_checkable
class AlertSink(Protocol):
    def create_alert(
        self,
        *,
        severity: str,
        category: str,
        title_ja: str,
        body_ja: str | None = None,
        entity: str | None = None,
    ) -> None: ...


@runtime_checkable
class MemoryRepo(Protocol):
    def select_memory(
        self,
        *,
        market: str | None = None,
        sector: str | None = None,
        ticker: str | None = None,
        limit: int = 15,
    ) -> list[MemoryRecord]:
        """docs/08-agent-loop.md §6.2 の SQL に対応。
        is_active=1 / confidence>=0.6 / n_observations>=10 で絞る。"""
        ...

    def list_memory(self, *, include_inactive: bool = False) -> list[MemoryRecord]: ...

    def insert_memory(self, record: MemoryRecord) -> str: ...

    def update_memory(self, memory_id: str, fields: dict[str, Any]) -> None: ...

    def touch_memory(self, memory_ids: list[str]) -> None:
        """use_count と last_used_at の更新。"""
        ...


@runtime_checkable
class StateRepo(
    JobRunRepo, RateLimitStateStore, LlmCallLog, CostBudgetRepo, AlertSink, MemoryRepo, Protocol
):
    """SQLite 側のすべてを束ねたリポジトリ。"""

    def get_setting(self, key: str, default: Any = None) -> Any: ...

    def set_setting(self, key: str, value: Any) -> None: ...

    def read_open_positions(self) -> pd.DataFrame: ...

    def read_watchlist(self) -> pd.DataFrame: ...

    def get_active_factor_weights(self, *, market: str, horizon: str) -> dict[str, Any] | None: ...

    def insert_factor_weights(self, row: dict[str, Any]) -> str: ...

    def get_backfill_progress(self, step_name: str) -> dict[str, Any] | None: ...

    def set_backfill_progress(self, step_name: str, fields: dict[str, Any]) -> None: ...


# ---------------------------------------------------------------------------
# ベクトルストア
# ---------------------------------------------------------------------------


@runtime_checkable
class VectorStore(Protocol):
    def upsert(self, chunks: list[DocChunk]) -> int: ...

    def search(
        self, query_vec: list[float], *, k: int, filters: dict[str, Any] | None = None
    ) -> list[SearchHit]: ...

    def delete_by_doc(self, doc_id: str) -> int: ...


@runtime_checkable
class KeywordSearch(Protocol):
    """DuckDB FTS によるキーワード検索（ハイブリッド検索の片側）。"""

    def search_text(
        self,
        query: str,
        *,
        k: int,
        ticker: str | None = None,
        market: str | None = None,
        as_of: date | None = None,
        doc_types: list[str] | None = None,
    ) -> list[SearchHit]: ...
