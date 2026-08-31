"""DuckDB リポジトリ（docs/03-data-model.md §2）。

生 SQL を各所に散らかさないための唯一の入口。特に PIT（Point-in-Time）を
壊しやすい参照は専用メソッドを用意してある。

    from packages.core.storage import DuckDBRepo

    with DuckDBRepo.open() as repo:
        repo.init_db()
        repo.upsert_prices_daily(rows)
        df = repo.get_financials_as_of("7203", "JP", date(2026, 6, 30))

読み取り専用で開くと同じファイルを複数プロセスから開ける。書き込みは
単一プロセスのみ（DuckDB の制約。docs/01-architecture.md §2）。
"""

from __future__ import annotations

import datetime as dt
import logging
import math
import threading
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import fields as dc_fields
from dataclasses import is_dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, Self

import duckdb

from packages.core.config import Settings, get_settings
from packages.core.interfaces.storage import SearchHit
from packages.core.storage.tickers import jp_ticker_aliases, unique_by_issuer

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations" / "duckdb"

_COVERAGE_TABLES: dict[str, tuple[str, bool]] = {
    "prices_daily": ("trade_date", True),
    "financials": ("filed_at", True),
    "documents": ("filed_at", True),
    "macro_series": ("observation_date", False),
    "securities": ("valid_from", True),
}

# 推奨の不変条件（docs/03-data-model.md §2.9）
MIN_BEAR_CASE_CHARS = 20
MIN_PRIOR_SAMPLES_FOR_HIGH_CONVICTION = 20
_UNSET = object()


class StorageError(RuntimeError):
    """ストレージ層の一般エラー。"""


class InvariantViolation(StorageError):
    """リポジトリ層で強制する不変条件の違反。

    docs/03-data-model.md §2.9 の「本ツールの誠実性の担保」に対応する。
    """


def _as_mapping(row: Any) -> dict[str, Any]:
    """dict / Pydantic モデル / dataclass（frozen + slots 含む）を受け付ける。"""
    if isinstance(row, Mapping):
        return dict(row)
    dump = getattr(row, "model_dump", None)
    if callable(dump):
        return dict(dump(mode="python"))
    if is_dataclass(row) and not isinstance(row, type):
        return {f.name: getattr(row, f.name) for f in dc_fields(row)}
    to_dict = getattr(row, "to_dict", None)
    if callable(to_dict) and not hasattr(row, "columns"):
        try:
            return dict(to_dict())
        except TypeError:
            pass
    if hasattr(row, "__dict__"):
        return {k: v for k, v in vars(row).items() if not k.startswith("_")}
    raise TypeError(f"行に変換できません: {type(row)!r}")


def _materialize_rows(rows: Iterable[Any]) -> list[dict[str, Any]]:
    """list[dict] / DataFrame / 単一 Mapping を行のリストにする。"""
    to_dict = getattr(rows, "to_dict", None)
    if callable(to_dict) and getattr(rows, "columns", None) is not None:
        records = to_dict(orient="records")
        return [_as_mapping(r) for r in records]
    if isinstance(rows, Mapping):
        return [_as_mapping(rows)]
    return [_as_mapping(r) for r in rows]


class DuckDBRepo:
    """DuckDB への読み書き。スレッド安全（内部で 1 本の接続を直列化する）。"""

    def __init__(
        self,
        path: str | Path,
        *,
        read_only: bool = False,
        memory_limit: str | None = None,
        threads: int | None = None,
        temp_directory: str | Path | None = None,
    ) -> None:
        self.path = Path(path) if path != ":memory:" else Path(":memory:")
        self.read_only = read_only
        if path != ":memory:" and not read_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        elif path != ":memory:" and read_only and not self.path.exists():
            raise StorageError(
                f"読み取り専用で開こうとしましたが DB がありません: {self.path}。"
                "先に `uv run python -m packages.core.storage.init_db` を実行してください。"
            )

        config: dict[str, str] = {}
        if memory_limit:
            config["memory_limit"] = memory_limit
        if threads:
            config["threads"] = str(threads)
        if temp_directory:
            Path(temp_directory).mkdir(parents=True, exist_ok=True)
            config["temp_directory"] = str(temp_directory)

        connect_kwargs: dict[str, Any] = {"read_only": read_only}
        if config:
            connect_kwargs["config"] = config
        database: str | Path = ":memory:" if str(self.path) in {":memory:", "memory"} else str(self.path)
        if isinstance(path, str) and path == ":memory:":
            database = ":memory:"
        self._con = duckdb.connect(database, **connect_kwargs)
        self._lock = threading.RLock()
        self._columns_cache: dict[str, list[str]] = {}
        self._required_cache: dict[str, list[str]] = {}

    # -- ライフサイクル ------------------------------------------------------

    @classmethod
    def open(
        cls, settings: Settings | None = None, *, read_only: bool = False
    ) -> Self:
        """`.env` の設定から開く。"""
        s = settings or get_settings()
        return cls(
            s.duckdb_path,
            read_only=read_only,
            memory_limit=s.duckdb_memory_limit,
            threads=s.duckdb_threads,
            temp_directory=s.duckdb_temp_dir,
        )

    @classmethod
    def in_memory(cls) -> Self:
        """テスト用のインメモリ DB。`init_db()` 済みで返す。"""
        repo = cls(":memory:", read_only=False)
        repo.init_db()
        return repo

    def close(self) -> None:
        with self._lock:
            self._con.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        """低レベル接続。原則としてリポジトリのメソッドを使うこと。"""
        return self._con

    # -- スキーマ ------------------------------------------------------------

    def init_db(self) -> list[str]:
        """未適用のマイグレーションを順に適用する。冪等。

        Returns:
            このコールで適用したマイグレーションのファイル名。
        """
        if self.read_only:
            raise StorageError("読み取り専用の接続では init_db() できません。")
        with self._lock:
            self._con.execute(
                "CREATE TABLE IF NOT EXISTS schema_version ("
                "  version VARCHAR NOT NULL PRIMARY KEY,"
                "  applied_at TIMESTAMP NOT NULL,"
                "  checksum VARCHAR"
                ")"
            )
            applied = {
                r[0] for r in self._con.execute("SELECT version FROM schema_version").fetchall()
            }
            newly: list[str] = []
            for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if sql_file.name in applied:
                    continue
                script = sql_file.read_text(encoding="utf-8")
                logger.info("DuckDB マイグレーション適用: %s", sql_file.name)
                self._con.execute("BEGIN TRANSACTION")
                try:
                    self._con.execute(script)
                    self._con.execute(
                        "INSERT INTO schema_version VALUES (?, ?, ?)",
                        [sql_file.name, dt.datetime.now(dt.UTC).replace(tzinfo=None), None],
                    )
                    self._con.execute("COMMIT")
                except Exception:
                    self._con.execute("ROLLBACK")
                    raise
                newly.append(sql_file.name)
            self._columns_cache.clear()
            self._required_cache.clear()
            return newly

    def schema_version(self) -> list[str]:
        """適用済みマイグレーションの一覧。"""
        try:
            rows = self._con.execute(
                "SELECT version FROM schema_version ORDER BY version"
            ).fetchall()
        except duckdb.CatalogException:
            return []
        return [r[0] for r in rows]

    def table_columns(self, table: str) -> list[str]:
        if table not in self._columns_cache:
            with self._lock:
                rows = self._con.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = ? ORDER BY ordinal_position",
                    [table],
                ).fetchall()
            if not rows:
                raise StorageError(f"テーブルがありません: {table}")
            self._columns_cache[table] = [r[0] for r in rows]
        return self._columns_cache[table]

    def table_exists(self, table: str) -> bool:
        with self._lock:
            n = self._con.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
                [table],
            ).fetchone()
        return bool(n and n[0])

    # -- 低レベル -------------------------------------------------------------

    def query(self, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        """SELECT を dict のリストで返す。"""
        with self._lock:
            cur = self._con.execute(sql, list(params) if params else None)
            cols = [d[0] for d in cur.description or []]
            return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]

    def query_one(
        self, sql: str, params: Sequence[Any] | None = None
    ) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        with self._lock:
            row = self._con.execute(sql, list(params) if params else None).fetchone()
        return row[0] if row else None

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        with self._lock:
            self._con.execute(sql, list(params) if params else None)

    def upsert(
        self,
        table: str,
        rows: Iterable[Any],
        *,
        key_columns: Sequence[str] | None = None,
        defaults: Mapping[str, Any] | None = None,
    ) -> int:
        """汎用 upsert。テーブルに存在しないキーは黙って捨てる。

        `key_columns` を省略すると主キーで衝突解決する。
        DEFAULT のない NOT NULL 列が欠けている／NULL なら、DuckDB の
        ConstraintException の前に列名付きで拒否する。
        """
        materialized = _materialize_rows(rows)
        if not materialized:
            return 0
        if self.read_only:
            raise StorageError("読み取り専用の接続では書き込みできません。")

        columns = self.table_columns(table)
        keys = list(key_columns) if key_columns else self._primary_key(table)
        if defaults:
            materialized = [{**dict(defaults), **r} for r in materialized]

        # 全行の和集合を列順にそろえる（欠けている列は NULL）
        used = [c for c in columns if any(c in r for r in materialized)]
        for k in keys:
            if k not in used:
                raise StorageError(f"{table}: 主キー列 {k} が入力にありません。")

        required = self._not_null_required_columns(table)
        omitted = [c for c in required if c not in used]
        if omitted:
            raise StorageError(
                f"{table}: NOT NULL 列が入力にありません: {', '.join(omitted)}"
            )

        col_sql = ", ".join(f'"{c}"' for c in used)
        placeholders = ", ".join("?" for _ in used)
        updatable = [c for c in used if c not in keys]
        if updatable:
            set_sql = ", ".join(f'"{c}" = excluded."{c}"' for c in updatable)
            conflict = f"ON CONFLICT ({', '.join(chr(34) + k + chr(34) for k in keys)}) DO UPDATE SET {set_sql}"
        else:
            conflict = (
                f"ON CONFLICT ({', '.join(chr(34) + k + chr(34) for k in keys)}) DO NOTHING"
            )
        sql = f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders}) {conflict}"

        payload: list[list[Any]] = []
        for r in materialized:
            coerced = [self._coerce(r.get(c) if c in r else None) for c in used]
            nulls = [c for c, value in zip(used, coerced, strict=True) if c in required and value is None]
            if nulls:
                raise StorageError(
                    f"{table}: NOT NULL 列が NULL です: {', '.join(nulls)}"
                )
            payload.append(coerced)
        with self._lock:
            self._con.executemany(sql, payload)
        return len(payload)

    def _not_null_required_columns(self, table: str) -> list[str]:
        """DEFAULT のない NOT NULL 列。省略すると ConstraintException になる。"""
        if table not in self._required_cache:
            with self._lock:
                rows = self._con.execute(
                    "SELECT column_name, is_nullable, column_default "
                    "FROM information_schema.columns "
                    "WHERE table_name = ? ORDER BY ordinal_position",
                    [table],
                ).fetchall()
            self._required_cache[table] = [
                str(name)
                for name, nullable, default in rows
                if str(nullable).upper() == "NO" and default is None
            ]
        return self._required_cache[table]

    def _primary_key(self, table: str) -> list[str]:
        with self._lock:
            rows = self._con.execute(
                "SELECT constraint_column_names FROM duckdb_constraints() "
                "WHERE table_name = ? AND constraint_type = 'PRIMARY KEY'",
                [table],
            ).fetchall()
        if not rows:
            raise StorageError(
                f"{table} に主キーがありません。key_columns を明示してください。"
            )
        return list(rows[0][0])

    @staticmethod
    def _coerce(value: Any) -> Any:
        """Pydantic / Enum / pandas / numpy 由来の値を DuckDB が扱える形にする。

        INTEGER 列に NaN を渡すと `Type DOUBLE with value nan can't be cast
        to INT32` で落ちる。非有限の浮動小数は NULL にする。
        """
        if value is None:
            return None
        cls_name = type(value).__name__
        if cls_name in {"NAType", "NaTType"}:
            return None
        if isinstance(value, dt.datetime):
            # DuckDB TIMESTAMP は naive UTC。tz-aware を渡すと INSERT が落ちる。
            if value.tzinfo is not None:
                return value.astimezone(dt.UTC).replace(tzinfo=None)
            return value
        if isinstance(value, (str, bool)):
            return value
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                return None
            return value
        item = getattr(value, "item", None)
        if callable(item) and not isinstance(value, (bytes, bytearray, memoryview)):
            try:
                native = item()
            except Exception:
                native = None
            else:
                if native is not value:
                    return DuckDBRepo._coerce(native)
        if isinstance(value, dt.date):
            return value
        if isinstance(value, dt.timedelta):
            return value
        enum_value = getattr(value, "value", None)
        if enum_value is not None and not isinstance(value, (Mapping, list, tuple)):
            return DuckDBRepo._coerce(enum_value)
        if isinstance(value, Mapping):
            return {k: DuckDBRepo._coerce(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [DuckDBRepo._coerce(v) for v in value]
        dump = getattr(value, "model_dump", None)
        if callable(dump):
            return DuckDBRepo._coerce(dump(mode="python"))
        return str(value)

    # -- securities -----------------------------------------------------------

    def upsert_securities(self, rows: Iterable[Any]) -> int:
        return self.upsert("securities", rows, defaults={"ingested_at": _now()})

    def get_securities(
        self,
        *,
        market: str | None = None,
        active_only: bool = True,
        tickers: Sequence[str] | None = None,
        as_of: dt.date | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """銘柄マスタ。`as_of` を渡すとその時点で有効な行だけを返す。"""
        where = ["1=1"]
        params: list[Any] = []
        if market:
            where.append("market = ?")
            params.append(market)
        if active_only:
            where.append("is_active")
        if tickers:
            where.append(f"ticker IN ({', '.join('?' for _ in tickers)})")
            params.extend(tickers)
        if as_of:
            where.append("valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)")
            params.extend([as_of, as_of])
        sql = (
            f"SELECT * FROM securities WHERE {' AND '.join(where)} "
            "ORDER BY market, ticker, valid_from DESC"
        )
        if limit:
            sql += f" LIMIT {int(limit)}"
        return self.query(sql, params)

    def read_securities(
        self, *, market: str | None = None, as_of: dt.date | None = None
    ) -> Any:
        import pandas as pd

        return pd.DataFrame(
            self.get_securities(market=market, as_of=as_of, active_only=False)
        )

    def get_security(
        self, ticker: str, market: str, *, as_of: dt.date | None = None
    ) -> dict[str, Any] | None:
        wanted = [ticker]
        if market == "JP" and len(ticker) == 4:
            wanted.append(ticker + "0")
        rows = self.get_securities(
            market=market, tickers=wanted, active_only=False, as_of=as_of
        )
        if not rows:
            return None
        latest: dict[str, dict[str, Any]] = {}
        for row in rows:
            latest.setdefault(str(row["ticker"]), row)
        padded = latest.get(ticker + "0") if market == "JP" and len(ticker) == 4 else None
        if padded is not None:
            name = str(padded.get("name_local") or "").strip()
            if name and name != padded["ticker"]:
                return padded
            if ticker not in latest:
                return padded
        return latest.get(ticker) or padded

    def search_securities(
        self, q: str, *, market: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """ティッカー・名称（日本語 / 英語 / カナ）の部分一致検索。

        `securities` は SCD2（`valid_from` が主キー）なので、収集のたびに
        同じ銘柄が複数行になる。検索は現行の 1 銘柄 1 件だけを返す。
        JP の 4 桁（7203）と J-Quants の 5 桁（72030）も同一銘柄として畳む。
        """
        pattern = f"%{q}%"
        padded = f"{q}0" if len(q) == 4 else q
        canonical_q = q[:-1] if len(q) == 5 and q.endswith("0") else q
        where = [
            "(ticker ILIKE ? OR name_local ILIKE ? OR coalesce(name_en,'') ILIKE ?"
            " OR coalesce(name_kana,'') ILIKE ?)",
            "is_active",
        ]
        params: list[Any] = [pattern, pattern, pattern, pattern]
        if market:
            where.append("market = ?")
            params.append(market)
        canonical = (
            "CASE WHEN market = 'JP' AND length(ticker) = 5 "
            "AND right(ticker, 1) = '0' THEN left(ticker, 4) ELSE ticker END"
        )
        named = (
            "(nullif(trim(coalesce(name_local, '')), '') IS NOT NULL "
            "AND trim(name_local) <> ticker)"
        )
        # QUALIFY で畳んだあと、同じ 5 桁が残っても Python 側で落とす。
        fetch = max(int(limit) * 5, 20)
        rows = self.query(
            f"SELECT * FROM securities WHERE {' AND '.join(where)} "
            f"QUALIFY row_number() OVER ("
            f"PARTITION BY market, {canonical} "
            f"ORDER BY {named} DESC, length(ticker), valid_from DESC"
            f") = 1 "
            "ORDER BY (ticker = ?) DESC, (ticker = ?) DESC, (ticker = ?) DESC, ticker "
            "LIMIT ?",
            [*params, q, padded, canonical_q, fetch],
        )
        return unique_by_issuer(rows)[:limit]

    # -- prices ---------------------------------------------------------------

    def upsert_prices_daily(self, rows: Iterable[Any]) -> int:
        return self.upsert("prices_daily", rows, defaults={"ingested_at": _now()})

    def get_prices_daily(
        self,
        ticker: str,
        market: str,
        *,
        start: dt.date | None = None,
        end: dt.date | None = None,
        limit: int | None = None,
        adjusted: bool = True,
    ) -> list[dict[str, Any]]:
        where = ["ticker = ?", "market = ?"]
        params: list[Any] = [ticker, market]
        if start:
            where.append("trade_date >= ?")
            params.append(start)
        if end:
            where.append("trade_date <= ?")
            params.append(end)
        sql = (
            f"SELECT * FROM prices_daily WHERE {' AND '.join(where)} ORDER BY trade_date"
        )
        if limit:
            sql = (
                f"SELECT * FROM prices_daily WHERE {' AND '.join(where)} "
                f"ORDER BY trade_date DESC LIMIT {int(limit)}"
            )
        rows = self.query(sql, params)
        if not rows and market == "JP" and len(ticker) == 4:
            return self.get_prices_daily(
                ticker + "0", market, start=start, end=end, limit=limit, adjusted=adjusted
            )
        if limit:
            rows.reverse()
        if adjusted:
            for r in rows:
                for field in ("open", "high", "low", "close", "volume"):
                    adj = r.get(f"adj_{field}")
                    if adj is not None:
                        r[field] = adj
        return rows

    def read_prices_daily(
        self,
        *,
        market: str | None = None,
        tickers: list[str] | None = None,
        start: dt.date | None = None,
        end: dt.date | None = None,
    ) -> Any:
        """市場横断の日次価格。Protocol `WarehouseRepo.read_prices_daily` 用。"""
        import pandas as pd

        where = ["1=1"]
        params: list[Any] = []
        if market:
            where.append("market = ?")
            params.append(market)
        if tickers:
            where.append(f"ticker IN ({', '.join('?' for _ in tickers)})")
            params.extend(list(tickers))
        if start:
            where.append("trade_date >= ?")
            params.append(start)
        if end:
            where.append("trade_date <= ?")
            params.append(end)
        rows = self.query(
            f"SELECT * FROM prices_daily WHERE {' AND '.join(where)} "
            "ORDER BY ticker, trade_date",
            params,
        )
        return pd.DataFrame(rows)

    def latest_coverage_date(
        self,
        table: str,
        *,
        market: str | None = None,
        date_col: str | None = None,
    ) -> dt.date | None:
        """テーブルに入っている最新日付。Collector の増分取得に使う。"""
        spec = _COVERAGE_TABLES.get(table)
        if spec is None:
            raise ValueError(f"coverage 対象外のテーブル: {table}")
        column, has_market = spec
        col = date_col or column
        if col != column:
            raise ValueError(f"{table} の日付列は {column} です")
        where = "1=1"
        params: list[Any] = []
        if has_market and market:
            where = "market = ?"
            params.append(market)
        row = self.query_one(
            f"SELECT MAX({col}) AS latest FROM {table} WHERE {where}",
            params,
        )
        if not row:
            return None
        value = row.get("latest")
        if value is None:
            return None
        if isinstance(value, dt.datetime):
            return value.date()
        if isinstance(value, dt.date):
            return value
        text = str(value)
        return dt.date.fromisoformat(text[:10])

    def upsert_prices_live(self, rows: Iterable[Any]) -> int:
        return self.upsert("prices_live", rows, defaults={"ingested_at": _now()})

    def get_latest_live_quote(self, ticker: str, market: str) -> dict[str, Any] | None:
        row = self.query_one(
            "SELECT * FROM prices_live WHERE ticker = ? AND market = ? "
            "ORDER BY trade_date DESC LIMIT 1",
            [ticker, market],
        )
        if row is None and market == "JP" and len(ticker) == 4:
            return self.get_latest_live_quote(ticker + "0", market)
        return row

    def get_latest_close(
        self, ticker: str, market: str, *, as_of: dt.date | None = None
    ) -> dict[str, Any] | None:
        """確定値の直近終値。`as_of` 以前に限定できる（PIT 用）。"""
        params: list[Any] = [ticker, market]
        clause = ""
        if as_of:
            clause = "AND trade_date <= ?"
            params.append(as_of)
        return self.query_one(
            f"SELECT trade_date, close, adj_close, currency, source FROM prices_daily "
            f"WHERE ticker = ? AND market = ? {clause} ORDER BY trade_date DESC LIMIT 1",
            params,
        )

    # -- financials（PIT） -----------------------------------------------------

    def upsert_financials(self, rows: Iterable[Any]) -> int:
        return self.upsert("financials", rows, defaults={"ingested_at": _now()})

    def get_financials_as_of(
        self,
        ticker: str,
        market: str,
        as_of: dt.date,
        *,
        limit: int = 8,
        period_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """`as_of` 時点で**開示済みだった**財務のみを返す（docs/03 §2.4）。

        `filed_at <= as_of` で絞ったうえで (period_end, fiscal_period) ごとに
        最新の `filed_at` を 1 本だけ採用する。バックテストと特徴量生成では
        必ずこの関数を使うこと。`financials_pit` ビューを直接見ると
        `as_of` より後の訂正報告を拾ってリークする。
        """
        params: list[Any] = [ticker, market, as_of]
        clause = ""
        if period_type:
            clause = "AND period_type = ?"
            params.append(period_type)
        rows = self.query(
            f"""
            SELECT * EXCLUDE (rn) FROM (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY period_end, fiscal_period ORDER BY filed_at DESC
                ) AS rn
                FROM financials
                WHERE ticker = ? AND market = ? AND filed_at <= ? {clause}
            ) WHERE rn = 1
            ORDER BY period_end DESC
            LIMIT {int(limit)}
            """,
            params,
        )
        if not rows and market == "JP" and len(ticker) == 4:
            return self.get_financials_as_of(
                ticker + "0", market, as_of, limit=limit, period_type=period_type
            )
        return rows

    def get_latest_financials(
        self, ticker: str, market: str, *, limit: int = 8
    ) -> list[dict[str, Any]]:
        """最新版の財務（PIT ではない。画面表示用）。"""
        rows = self.query(
            "SELECT * EXCLUDE (rn) FROM financials_pit "
            "WHERE ticker = ? AND market = ? ORDER BY period_end DESC LIMIT ?",
            [ticker, market, limit],
        )
        if not rows and market == "JP" and len(ticker) == 4:
            return self.get_latest_financials(ticker + "0", market, limit=limit)
        return rows

    # -- documents ------------------------------------------------------------

    def upsert_documents(self, rows: Iterable[Any]) -> int:
        return self.upsert("documents", rows, defaults={"ingested_at": _now()})

    def get_documents(
        self,
        *,
        ticker: str | None = None,
        market: str | None = None,
        doc_type: str | None = None,
        source: str | None = None,
        since: dt.date | None = None,
        until: dt.date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where = ["1=1"]
        params: list[Any] = []
        if ticker:
            aliases = jp_ticker_aliases(ticker)
            if not aliases:
                where.append("1=0")
            elif len(aliases) == 1:
                where.append("ticker = ?")
                params.append(aliases[0])
            else:
                placeholders = ", ".join("?" for _ in aliases)
                where.append(f"ticker IN ({placeholders})")
                params.extend(aliases)
        for column, value in (
            ("market", market),
            ("doc_type", doc_type),
            ("source", source),
        ):
            if value:
                where.append(f"{column} = ?")
                params.append(value)
        if since:
            where.append("filed_at >= ?")
            params.append(since)
        if until:
            where.append("filed_at <= ?")
            params.append(dt.datetime.combine(until, dt.time.max))
        return self.query(
            f"SELECT * FROM documents WHERE {' AND '.join(where)} "
            f"ORDER BY filed_at DESC LIMIT {int(limit)} OFFSET {int(offset)}",
            params,
        )

    def count_documents(self, **kwargs: Any) -> int:
        kwargs.pop("limit", None)
        kwargs.pop("offset", None)
        rows = self.get_documents(limit=1_000_000, **kwargs)
        return len(rows)

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        return self.query_one("SELECT * FROM documents WHERE doc_id = ?", [doc_id])

    def get_document_text(self, doc_id: str, *, page: int | None = None) -> str | None:
        """抽出済みテキスト、または blob がプレーンテキストならその内容。"""
        row = self.get_document(doc_id)
        if row is None:
            return None
        extracted = row.get("extracted_text")
        if extracted:
            return str(extracted)
        blob = row.get("blob_path")
        if not blob:
            return None
        path = Path(blob)
        if not path.is_file():
            return None
        if path.suffix.lower() in {".txt", ".md", ".html", ".xml", ".json"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            if page is None:
                return text
            return text
        return None

    def search_text(
        self,
        query: str,
        *,
        k: int,
        ticker: str | None = None,
        market: str | None = None,
        as_of: dt.date | None = None,
        doc_types: list[str] | None = None,
    ) -> list[SearchHit]:
        """開示タイトルと本文からキーワード検索する（ハイブリッド RAG の片側）。"""
        import re

        terms = [t.lower() for t in re.findall(r"[0-9A-Za-z一-龥ぁ-んァ-ン]{2,}", query)]
        terms = terms[:8] or ([query.strip().lower()] if query.strip() else [])
        kwargs: dict[str, Any] = {"limit": 80}
        if ticker:
            kwargs["ticker"] = ticker
        if market:
            kwargs["market"] = market
        if as_of is not None:
            kwargs["until"] = as_of
        if doc_types:
            kwargs["doc_type"] = doc_types[0]
        docs = self.get_documents(**kwargs)
        hits: list[SearchHit] = []
        for doc in docs:
            hay = f"{doc.get('title') or ''} {self.get_document_text(str(doc['doc_id'])) or ''}"
            lowered = hay.lower()
            if terms and not any(term in lowered for term in terms):
                continue
            snippet = hay.strip()[:1200]
            if len(snippet) < 20:
                continue
            filed = doc.get("filed_at")
            if as_of is not None and hasattr(filed, "date") and filed.date() > as_of:
                continue
            hits.append(
                SearchHit(
                    chunk_id=f"{doc['doc_id']}:kw",
                    doc_id=str(doc["doc_id"]),
                    text=snippet,
                    score=1.0 / (len(hits) + 1),
                    ticker=doc.get("ticker"),
                    market=doc.get("market"),
                    doc_type=doc.get("doc_type"),
                    filed_at=filed if isinstance(filed, dt.datetime) else None,
                    title=doc.get("title"),
                )
            )
            if len(hits) >= k:
                break
        return hits

    def read_documents(
        self,
        *,
        market: str | None = None,
        tickers: list[str] | None = None,
        filed_from: dt.date | None = None,
        filed_to: dt.date | None = None,
        doc_types: list[str] | None = None,
    ) -> Any:
        import pandas as pd

        mapped: dict[str, Any] = {"market": market, "limit": 10_000}
        if filed_from is not None:
            mapped["since"] = filed_from
        if filed_to is not None:
            mapped["until"] = filed_to
        if doc_types:
            mapped["doc_type"] = doc_types[0]
        if tickers:
            frames = []
            for ticker in tickers:
                frames.append(
                    pd.DataFrame(self.get_documents(ticker=ticker, **mapped) or [])
                )
            return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        mapped = {k: v for k, v in mapped.items() if v is not None}
        return pd.DataFrame(self.get_documents(**mapped) or [])

    def find_summary(
        self,
        *,
        doc_id: str,
        prompt_hash: str | None = None,
        input_hash: str | None = None,
    ) -> dict[str, Any] | None:
        row = self.get_document_summary(doc_id)
        if row is None:
            return None
        if prompt_hash and row.get("prompt_hash") != prompt_hash:
            return None
        if input_hash and row.get("input_hash") != input_hash:
            return None
        return row

    def upsert_document_summaries(self, rows: Iterable[Any]) -> int:
        """LLM 要約の保存。`citations` が空の行は拒否する（docs/03 §2.6）。"""
        materialized = _materialize_rows(rows)
        for r in materialized:
            if not r.get("citations"):
                raise InvariantViolation(
                    f"citations が空の要約は保存できません: doc_id={r.get('doc_id')!r}。"
                    "引用のない要約は検証不能なため（docs/03-data-model.md §2.6）。"
                )
        return self.upsert(
            "document_summaries", materialized, defaults={"computed_at": _now()}
        )

    def get_document_summary(
        self, doc_id: str, *, summary_version: int | None = None
    ) -> dict[str, Any] | None:
        if summary_version is not None:
            return self.query_one(
                "SELECT * FROM document_summaries WHERE doc_id = ? AND summary_version = ?",
                [doc_id, summary_version],
            )
        return self.query_one(
            "SELECT * FROM document_summaries WHERE doc_id = ? "
            "ORDER BY summary_version DESC LIMIT 1",
            [doc_id],
        )

    # -- features / scores ----------------------------------------------------

    def upsert_features_daily(self, rows: Iterable[Any]) -> int:
        return self.upsert("features_daily", rows, defaults={"computed_at": _now()})

    def get_features(
        self,
        ticker: str,
        market: str,
        as_of: dt.date,
        *,
        feature_version: str | None = None,
    ) -> dict[str, Any] | None:
        params: list[Any] = [ticker, market, as_of]
        clause = ""
        if feature_version:
            clause = "AND feature_version = ?"
            params.append(feature_version)
        return self.query_one(
            f"SELECT * FROM features_daily WHERE ticker = ? AND market = ? "
            f"AND as_of <= ? {clause} ORDER BY as_of DESC, feature_version DESC LIMIT 1",
            params,
        )

    def read_features_daily(
        self,
        *,
        as_of: dt.date | None = None,
        start: dt.date | None = None,
        end: dt.date | None = None,
        market: str | None = None,
        feature_version: str | None = None,
        tickers: list[str] | None = None,
    ) -> Any:
        import pandas as pd

        where = ["1=1"]
        params: list[Any] = []
        if market:
            where.append("market = ?")
            params.append(market)
        if as_of:
            where.append("as_of = ?")
            params.append(as_of)
        if start:
            where.append("as_of >= ?")
            params.append(start)
        if end:
            where.append("as_of <= ?")
            params.append(end)
        if feature_version:
            where.append("feature_version = ?")
            params.append(feature_version)
        if tickers:
            where.append(f"ticker IN ({', '.join('?' for _ in tickers)})")
            params.extend(tickers)
        rows = self.query(
            f"SELECT * FROM features_daily WHERE {' AND '.join(where)} "
            "ORDER BY as_of, ticker",
            params,
        )
        return pd.DataFrame(rows)

    def upsert_scores_daily(self, rows: Iterable[Any]) -> int:
        return self.upsert(
            "scores_daily",
            rows,
            defaults={"computed_at": _now(), "feature_version": "v1.0.0"},
        )

    def get_scores(
        self,
        *,
        market: str | None = None,
        as_of: dt.date | None = None,
        tickers: Sequence[str] | None = None,
        weight_set_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "total_score",
        descending: bool = True,
    ) -> list[dict[str, Any]]:
        allowed = {
            "total_score",
            "quant_score",
            "qual_score",
            "quant_rank",
            "ml_pred_h5",
            "ml_pred_h20",
            "as_of",
            "ticker",
        }
        if order_by not in allowed:
            raise StorageError(f"並べ替えに使えない列です: {order_by}")
        where = ["1=1"]
        params: list[Any] = []
        if market:
            where.append("market = ?")
            params.append(market)
        if as_of:
            where.append("as_of = ?")
            params.append(as_of)
        if tickers:
            where.append(f"ticker IN ({', '.join('?' for _ in tickers)})")
            params.extend(tickers)
        if weight_set_id:
            where.append("weight_set_id = ?")
            params.append(weight_set_id)
        direction = "DESC" if descending else "ASC"
        return self.query(
            f"SELECT * FROM scores_daily WHERE {' AND '.join(where)} "
            f"ORDER BY {order_by} {direction} NULLS LAST "
            f"LIMIT {int(limit)} OFFSET {int(offset)}",
            params,
        )

    def latest_score_date(self, market: str | None = None) -> dt.date | None:
        if market:
            return self.scalar(
                "SELECT max(as_of) FROM scores_daily WHERE market = ?", [market]
            )
        return self.scalar("SELECT max(as_of) FROM scores_daily")

    def read_scores_daily(
        self,
        *,
        as_of: dt.date | None = None,
        market: str | None = None,
        weight_set_id: str | None = None,
    ) -> Any:
        import pandas as pd

        rows = self.get_scores(
            market=market,
            as_of=as_of,
            weight_set_id=weight_set_id,
            limit=100_000,
        )
        return pd.DataFrame(rows)

    # -- recommendations ------------------------------------------------------

    def insert_recommendations(self, rows: Iterable[Any]) -> int:
        """推奨の保存。docs/03-data-model.md §2.9 の不変条件を強制する。

        `critic_verdict = 'rejected'` の行も保存する（学習材料になるため）。
        UI に出さないのは読み出し側（`get_recommendations(include_rejected=False)`）の責務。
        """
        materialized = _materialize_rows(rows)
        for r in materialized:
            self._validate_recommendation(r)
        return self.upsert(
            "recommendations",
            materialized,
            key_columns=["rec_id"],
            defaults={"generated_at": _now()},
        )

    def insert_recommendation(self, rec: dict[str, Any]) -> str:
        payload = dict(rec)
        payload.setdefault("rec_id", payload.get("rec_id") or str(uuid.uuid4()))
        self.insert_recommendations([payload])
        return str(payload["rec_id"])

    def update_recommendation(self, rec_id: str, fields: dict[str, Any]) -> int:
        """Critic が verdict と修正後本文を書き戻す。"""
        existing = self.query_one("SELECT * FROM recommendations WHERE rec_id = ?", [rec_id])
        if existing is None:
            return 0
        merged = dict(existing)
        merged.update(fields)
        merged["rec_id"] = rec_id
        return self.upsert("recommendations", [merged], key_columns=["rec_id"])

    @staticmethod
    def _validate_recommendation(r: dict[str, Any]) -> None:
        rec_id = r.get("rec_id")
        bear = (r.get("bear_case_ja") or "").strip()
        if len(bear) < MIN_BEAR_CASE_CHARS:
            raise InvariantViolation(
                f"bear_case_ja が {MIN_BEAR_CASE_CHARS} 文字未満です（rec_id={rec_id!r}）。"
                "弱気論拠のない推奨は保存できません（docs/03-data-model.md §2.9）。"
            )
        if not r.get("source_doc_ids"):
            raise InvariantViolation(
                f"source_doc_ids が空です（rec_id={rec_id!r}）。"
            )
        if not r.get("citations"):
            raise InvariantViolation(f"citations が空です（rec_id={rec_id!r}）。")
        if r.get("expected_ret_lo") is None or r.get("expected_ret_hi") is None:
            raise InvariantViolation(
                f"expected_ret_lo / expected_ret_hi が必要です（rec_id={rec_id!r}）。"
                "点推定のみの提示は禁止（docs/00-overview.md §3）。"
            )
        if not (r.get("invalidation_ja") or "").strip():
            raise InvariantViolation(
                f"invalidation_ja が空です（rec_id={rec_id!r}）。"
            )
        if not (r.get("thesis_ja") or "").strip():
            raise InvariantViolation(f"thesis_ja が空です（rec_id={rec_id!r}）。")
        score = r.get("conviction_score")
        try:
            numeric = float(score)
        except (TypeError, ValueError):
            numeric = float("nan")
        if not math.isfinite(numeric) or numeric < 0.0 or numeric > 1.0:
            raise InvariantViolation(
                f"conviction_score は 0.0..1.0 の有限値が必要です"
                f"（rec_id={rec_id!r}, value={score!r}）。"
            )
        r["conviction_score"] = numeric
        # 不変条件 5: 事前実績が薄い推奨は conviction を low に落とす
        n_prior = r.get("n_prior_samples")
        if r.get("hit_rate_prior") is None or (n_prior or 0) < MIN_PRIOR_SAMPLES_FOR_HIGH_CONVICTION:
            if r.get("conviction") != "low":
                logger.warning(
                    "rec_id=%s: 事前実績が不足（hit_rate_prior=%s, n=%s）のため "
                    "conviction を low に強制します。",
                    rec_id,
                    r.get("hit_rate_prior"),
                    n_prior,
                )
            r["conviction"] = "low"

    def get_recommendations(
        self,
        *,
        as_of: dt.date | None = None,
        market: str | None = None,
        ticker: str | None = None,
        action: str | None = None,
        horizon: str | None = None,
        conviction: str | None = None,
        critic_verdict: str | object | None = _UNSET,
        include_rejected: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where = ["1=1"]
        params: list[Any] = []
        for column, value in (
            ("as_of", as_of),
            ("market", market),
            ("ticker", ticker),
            ("action", action),
            ("horizon", horizon),
            ("conviction", conviction),
        ):
            if value is not None:
                where.append(f"{column} = ?")
                params.append(value)
        if critic_verdict is not _UNSET:
            if critic_verdict is None:
                where.append("critic_verdict IS NULL")
            else:
                where.append("critic_verdict = ?")
                params.append(critic_verdict)
        elif not include_rejected:
            where.append("coalesce(critic_verdict, 'approved') <> 'rejected'")
        return self.query(
            f"SELECT * FROM recommendations WHERE {' AND '.join(where)} "
            f"ORDER BY as_of DESC, conviction_score DESC "
            f"LIMIT {int(limit)} OFFSET {int(offset)}",
            params,
        )

    def count_recommendations(
        self,
        *,
        as_of: dt.date | None = None,
        market: str | None = None,
        include_rejected: bool = False,
    ) -> int:
        where = ["1=1"]
        params: list[Any] = []
        if as_of is not None:
            where.append("as_of = ?")
            params.append(as_of)
        if market:
            where.append("market = ?")
            params.append(market)
        if not include_rejected:
            where.append("coalesce(critic_verdict, 'approved') <> 'rejected'")
        return int(
            self.scalar(
                f"SELECT count(*) FROM recommendations WHERE {' AND '.join(where)}", params
            )
            or 0
        )

    def get_recommendation(self, rec_id: str) -> dict[str, Any] | None:
        return self.query_one(
            "SELECT * FROM recommendations WHERE rec_id = ?", [rec_id]
        )

    def latest_recommendation_date(self, market: str | None = None) -> dt.date | None:
        if market:
            return self.scalar(
                "SELECT max(as_of) FROM recommendations WHERE market = ?", [market]
            )
        return self.scalar("SELECT max(as_of) FROM recommendations")

    def upsert_recommendation_outcomes(self, rows: Iterable[Any]) -> int:
        return self.upsert(
            "recommendation_outcomes", rows, defaults={"evaluated_at": _now()}
        )

    def read_recommendation_outcomes(
        self, *, market: str | None = None, horizon: str | None = None, since: dt.date | None = None
    ) -> Any:
        import pandas as pd

        rows = self.get_recommendation_outcomes(
            market=market, horizon=horizon, since=since, limit=2_000
        )
        return pd.DataFrame(rows)

    def get_recommendation_outcomes(
        self,
        *,
        rec_id: str | None = None,
        market: str | None = None,
        horizon: str | None = None,
        since: dt.date | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        where = ["1=1"]
        params: list[Any] = []
        if rec_id:
            where.append("o.rec_id = ?")
            params.append(rec_id)
        if market:
            where.append("r.market = ?")
            params.append(market)
        if horizon:
            where.append("o.horizon = ?")
            params.append(horizon)
        if since:
            where.append("o.entry_date >= ?")
            params.append(since)
        return self.query(
            f"""
            SELECT o.*, r.ticker, r.market, r.as_of, r.action, r.conviction,
                   r.conviction_score, r.reason_codes
            FROM recommendation_outcomes o
            JOIN recommendations r USING (rec_id)
            WHERE {' AND '.join(where)}
            ORDER BY o.entry_date DESC
            LIMIT {int(limit)}
            """,
            params,
        )

    # -- fx / macro -----------------------------------------------------------

    def upsert_fx_forecasts(self, rows: Iterable[Any]) -> int:
        return self.upsert("fx_forecasts", rows, defaults={"computed_at": _now()})

    def get_fx_forecasts(
        self, pair: str, *, as_of: dt.date | None = None, model_id: str | None = None
    ) -> list[dict[str, Any]]:
        where = ["pair = ?"]
        params: list[Any] = [pair]
        if as_of:
            where.append("as_of = ?")
            params.append(as_of)
        else:
            where.append("as_of = (SELECT max(as_of) FROM fx_forecasts WHERE pair = ?)")
            params.append(pair)
        if model_id:
            where.append("model_id = ?")
            params.append(model_id)
        return self.query(
            f"SELECT * FROM fx_forecasts WHERE {' AND '.join(where)} "
            "ORDER BY horizon_days, model_id",
            params,
        )

    def upsert_macro_series(self, rows: Iterable[Any]) -> int:
        return self.upsert("macro_series", rows, defaults={"ingested_at": _now()})

    def get_macro_as_of(
        self, series_id: str, *, as_of: dt.date, limit: int = 60
    ) -> list[dict[str, Any]]:
        """`as_of` 時点で公表されていた vintage のみを返す（docs/03 §2.12）。"""
        return self.query(
            """
            SELECT * EXCLUDE (rn) FROM (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY observation_date ORDER BY vintage_date DESC
                ) AS rn
                FROM macro_series
                WHERE series_id = ? AND vintage_date <= ?
            ) WHERE rn = 1
            ORDER BY observation_date DESC
            LIMIT ?
            """,
            [series_id, as_of, limit],
        )

    def get_macro_latest(
        self, series_ids: Sequence[str], *, limit_per_series: int = 1
    ) -> list[dict[str, Any]]:
        if not series_ids:
            return []
        placeholders = ", ".join("?" for _ in series_ids)
        return self.query(
            f"""
            SELECT * EXCLUDE (rn) FROM (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY series_id ORDER BY observation_date DESC
                ) AS rn
                FROM macro_series_latest WHERE series_id IN ({placeholders})
            ) WHERE rn <= ?
            ORDER BY series_id, observation_date DESC
            """,
            [*series_ids, limit_per_series],
        )

    # -- runs -----------------------------------------------------------------

    def upsert_model_runs(self, rows: Iterable[Any]) -> int:
        return self.upsert("model_runs", rows, key_columns=["run_id"])

    def get_model_run(self, run_id: str) -> dict[str, Any] | None:
        return self.query_one("SELECT * FROM model_runs WHERE run_id = ?", [run_id])

    def get_model_runs(
        self, *, model_kind: str | None = None, status: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        where = ["1=1"]
        params: list[Any] = []
        if model_kind:
            where.append("model_kind = ?")
            params.append(model_kind)
        if status:
            where.append("status = ?")
            params.append(status)
        return self.query(
            f"SELECT * FROM model_runs WHERE {' AND '.join(where)} "
            f"ORDER BY started_at DESC LIMIT {int(limit)}",
            params,
        )

    def count_model_runs(self, *, model_kind: str | None = None) -> int:
        if model_kind:
            return int(
                self.scalar(
                    "SELECT count(*) FROM model_runs WHERE model_kind = ?", [model_kind]
                )
                or 0
            )
        return int(self.scalar("SELECT count(*) FROM model_runs") or 0)

    def insert_model_run(self, row: dict[str, Any]) -> str:
        payload = dict(row)
        payload.setdefault("run_id", payload.get("run_id") or str(uuid.uuid4()))
        payload.setdefault("model_kind", payload.get("model_kind") or "ranker")
        payload.setdefault("model_version", payload.get("model_version") or "v1")
        payload.setdefault("cv_scheme", payload.get("cv_scheme") or "purged_walk_forward")
        payload.setdefault("purge_days", payload.get("purge_days") or 20)
        payload.setdefault("embargo_days", payload.get("embargo_days") or 5)
        payload.setdefault("feature_version", payload.get("feature_version") or "v1")
        payload.setdefault("feature_list", payload.get("feature_list") or [])
        payload.setdefault(
            "input_snapshot_hash", payload.get("input_snapshot_hash") or "unknown"
        )
        payload.setdefault("started_at", payload.get("started_at") or _now())
        payload.setdefault("status", payload.get("status") or "success")
        self.upsert_model_runs([payload])
        return str(payload["run_id"])

    def upsert_backtest_runs(self, rows: Iterable[Any]) -> int:
        return self.upsert("backtest_runs", rows, key_columns=["backtest_id"])

    def get_backtest_run(self, backtest_id: str) -> dict[str, Any] | None:
        return self.query_one(
            "SELECT * FROM backtest_runs WHERE backtest_id = ?", [backtest_id]
        )

    def get_backtest_runs(
        self, *, market: str | None = None, status: str | None = None, limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where = ["1=1"]
        params: list[Any] = []
        if market:
            where.append("market = ?")
            params.append(market)
        if status:
            where.append("status = ?")
            params.append(status)
        return self.query(
            f"SELECT * FROM backtest_runs WHERE {' AND '.join(where)} "
            f"ORDER BY run_at DESC LIMIT {int(limit)} OFFSET {int(offset)}",
            params,
        )

    def count_backtest_runs(self, *, strategy_name: str | None = None) -> int:
        if strategy_name:
            return int(
                self.scalar(
                    "SELECT count(*) FROM backtest_runs WHERE strategy_name = ?",
                    [strategy_name],
                )
                or 0
            )
        return int(self.scalar("SELECT count(*) FROM backtest_runs") or 0)

    def insert_backtest_run(self, row: dict[str, Any]) -> str:
        payload = dict(row)
        payload.setdefault("backtest_id", payload.get("backtest_id") or str(uuid.uuid4()))
        payload.setdefault("status", payload.get("status") or "finished")
        payload.setdefault("run_at", payload.get("run_at") or _now())
        self.upsert_backtest_runs([payload])
        return str(payload["backtest_id"])

    def _ensure_earnings_dates(self) -> None:
        if self.table_exists("earnings_dates"):
            return
        if self.read_only:
            return
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS earnings_dates (
                ticker VARCHAR NOT NULL,
                market VARCHAR NOT NULL,
                announce_date DATE NOT NULL,
                fiscal_period VARCHAR,
                source VARCHAR,
                ingested_at TIMESTAMP,
                PRIMARY KEY (ticker, market, announce_date)
            )
            """
        )
        self._columns_cache.pop("earnings_dates", None)

    def upsert_earnings_dates(self, df: Any) -> int:
        self._ensure_earnings_dates()
        return self.upsert(
            "earnings_dates",
            df,
            key_columns=["ticker", "market", "announce_date"],
            defaults={"ingested_at": _now()},
        )

    def read_earnings_dates(
        self, *, market: str | None = None, tickers: list[str] | None = None
    ) -> Any:
        import pandas as pd

        if not self.table_exists("earnings_dates"):
            return pd.DataFrame()
        where = ["1=1"]
        params: list[Any] = []
        if market:
            where.append("market = ?")
            params.append(market)
        if tickers:
            where.append(f"ticker IN ({', '.join('?' for _ in tickers)})")
            params.extend(tickers)
        rows = self.query(
            f"SELECT * FROM earnings_dates WHERE {' AND '.join(where)} "
            "ORDER BY announce_date",
            params,
        )
        return pd.DataFrame(rows)

    # -- 品質・鮮度 ------------------------------------------------------------

    def upsert_data_gaps(self, rows: Iterable[Any]) -> int:
        return self.upsert(
            "data_gaps", rows, key_columns=["gap_id"], defaults={"detected_at": _now()}
        )

    def upsert_data_conflicts(self, rows: Iterable[Any]) -> int:
        return self.upsert(
            "data_conflicts",
            rows,
            key_columns=["conflict_id"],
            defaults={"detected_at": _now()},
        )

    def upsert_data_quality_flags(self, rows: Iterable[Any]) -> int:
        return self.upsert(
            "data_quality_flags",
            rows,
            key_columns=["flag_id"],
            defaults={"detected_at": _now()},
        )

    def record_data_gap(
        self,
        *,
        source: str,
        entity: str,
        gap_start: dt.date,
        gap_end: dt.date,
        reason: str,
    ) -> None:
        self.upsert_data_gaps(
            [
                {
                    "gap_id": str(uuid.uuid4()),
                    "source": source,
                    "entity": entity,
                    "gap_start": gap_start,
                    "gap_end": gap_end,
                    "reason": reason,
                }
            ]
        )

    def record_data_quality_flag(
        self,
        *,
        table_name: str,
        entity: str,
        as_of: dt.date,
        flag_code: str,
        detail: str | None = None,
    ) -> None:
        self.upsert_data_quality_flags(
            [
                {
                    "flag_id": str(uuid.uuid4()),
                    "table_name": table_name,
                    "entity": entity,
                    "as_of": as_of,
                    "flag_code": flag_code,
                    "detail": detail,
                }
            ]
        )

    def record_data_conflict(
        self,
        *,
        entity: str,
        field: str,
        as_of: dt.date,
        source_a: str,
        value_a: float | None,
        source_b: str,
        value_b: float | None,
    ) -> None:
        self.upsert_data_conflicts(
            [
                {
                    "conflict_id": str(uuid.uuid4()),
                    "entity": entity,
                    "field": field,
                    "as_of": as_of,
                    "source_a": source_a,
                    "value_a": value_a,
                    "source_b": source_b,
                    "value_b": value_b,
                }
            ]
        )

    def data_freshness(self) -> dict[str, dt.date | None]:
        """`{source: latest_as_of}`。UI ヘッダの鮮度表示に使う。"""
        rows = self.query("SELECT source, latest_as_of FROM data_freshness")
        return {r["source"]: r["latest_as_of"] for r in rows}

    def row_counts(self) -> dict[str, int]:
        """各テーブルの行数（診断用）。"""
        tables = self.query(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_type = 'BASE TABLE' ORDER BY table_name"
        )
        return {
            t["table_name"]: int(
                self.scalar(f'SELECT count(*) FROM "{t["table_name"]}"') or 0
            )
            for t in tables
        }


def _now() -> dt.datetime:
    """タイムゾーン無しの UTC（DuckDB の TIMESTAMP は naive）。"""
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


Market = Literal["JP", "US"]

__all__ = [
    "DuckDBRepo",
    "InvariantViolation",
    "Market",
    "StorageError",
]
