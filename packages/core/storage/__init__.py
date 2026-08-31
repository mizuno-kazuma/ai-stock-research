"""ストレージ層の公開 API（docs/03-data-model.md）。

他パッケージ（connectors / factors / models / backtest / llm / services）は
**ここに列挙されたものだけ**を使うこと。サブモジュールを直接 import すると
実装を差し替えたときに壊れる。

使い方:

    from packages.core.storage import DuckDBRepo, SQLiteRepo, ParquetLake

    with DuckDBRepo.open() as duck, SQLiteRepo.open() as state:
        duck.init_db()
        state.init_db()

PIT（Point-in-Time）に関わる読み出しは専用メソッドを使うこと:

- `DuckDBRepo.get_financials_as_of(ticker, market, as_of)`
- `DuckDBRepo.get_macro_as_of(series_id, as_of=...)`
- `DuckDBRepo.get_latest_close(ticker, market, as_of=...)`

`financials_pit` ビューや `macro_series_latest` ビューを直接読むと
`as_of` より後の訂正・改訂を拾ってリークする。
"""

from .duckdb_repo import (
    DuckDBRepo,
    InvariantViolation,
    Market,
    StorageError,
)
from .parquet_lake import Compression, ParquetLake
from .paths import (
    assert_windows_safe,
    doc_blob_name,
    is_valid_path_component,
    parquet_partition_path,
    raw_path,
    safe_component,
    timestamp_component,
)
from .seed_flags import (
    LIVE_DATA_KEY,
    SEED_DATA_KEY,
    is_serving_seed,
    mark_live_ingest,
    should_load_seed_payload,
)
from .sqlite_repo import (
    DEFAULT_SETTINGS,
    SETTING_TYPES,
    AgentMemory,
    Alert,
    BackfillProgress,
    Base,
    CostBudget,
    FactorWeight,
    JobRun,
    LlmCall,
    Position,
    RateLimitState,
    Setting,
    SQLiteRepo,
    Trade,
    WatchlistItem,
    to_dict,
    utc_now_iso,
)
from .tickers import canonical_jp_ticker, issuer_key, jp_ticker_aliases, unique_by_issuer
from .vector_store import (
    DocChunk,
    InMemoryVectorStore,
    LanceDBVectorStore,
    SearchHit,
    VectorStore,
    chunk_id_for,
    get_vector_store,
)

__all__ = [
    "DEFAULT_SETTINGS",
    "LIVE_DATA_KEY",
    "SEED_DATA_KEY",
    "SETTING_TYPES",
    "AgentMemory",
    "Alert",
    "BackfillProgress",
    "Base",
    "Compression",
    "CostBudget",
    "DocChunk",
    "DuckDBRepo",
    "FactorWeight",
    "InMemoryVectorStore",
    "InvariantViolation",
    "JobRun",
    "LanceDBVectorStore",
    "LlmCall",
    "Market",
    "ParquetLake",
    "Position",
    "RateLimitState",
    "SQLiteRepo",
    "SearchHit",
    "Setting",
    "StorageError",
    "Trade",
    "VectorStore",
    "WatchlistItem",
    "assert_windows_safe",
    "canonical_jp_ticker",
    "chunk_id_for",
    "doc_blob_name",
    "get_vector_store",
    "init_all",
    "is_serving_seed",
    "is_valid_path_component",
    "issuer_key",
    "jp_ticker_aliases",
    "mark_live_ingest",
    "parquet_partition_path",
    "raw_path",
    "safe_component",
    "should_load_seed_payload",
    "timestamp_component",
    "to_dict",
    "unique_by_issuer",
    "utc_now_iso",
]


def init_all(settings: object | None = None) -> dict[str, object]:
    """DuckDB / SQLite / ディレクトリを一括で初期化する。冪等。

    `uv run python -m packages.core.storage.init_db` の実体。
    """
    from packages.core.config import get_settings

    s = settings or get_settings()  # type: ignore[assignment]
    s.ensure_directories()  # type: ignore[attr-defined]

    with DuckDBRepo.open(s) as duck:  # type: ignore[arg-type]
        applied = duck.init_db()
        counts = duck.row_counts()
    with SQLiteRepo.open(s) as state:  # type: ignore[arg-type]
        state.init_db()
        settings_added = state.ensure_default_settings()

    return {
        "duckdb_path": str(s.duckdb_path),  # type: ignore[attr-defined]
        "sqlite_path": str(s.sqlite_path),  # type: ignore[attr-defined]
        "migrations_applied": applied,
        "tables": sorted(counts),
        "default_settings_added": settings_added,
    }
