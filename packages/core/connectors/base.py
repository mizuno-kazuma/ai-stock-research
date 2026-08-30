"""Connector 抽象。

docs/02-data-ingestion.md §1.1。設計上の制約は以下の3点で、
これを守ることが無料枠のレート制限下での再現性を担保する。

1. `fetch` は保存のみを行い、加工しない
2. `normalize` はネットワークに触らない（Raw層から再実行可能にするため）
3. `upsert` は冪等
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from packages.core.connectors.errors import SchemaDriftError, SourceDisabledError
from packages.core.connectors.http import HttpClient, RetryPolicy
from packages.core.connectors.rate_limit import TokenBucket
from packages.core.connectors.raw_store import RawStore
from packages.core.connectors.sources_config import (
    SourceConfig,
    SourcesConfig,
    default_sources_config,
)


class FetchWindow(BaseModel):
    """取得対象の期間。ページネーションは `cursor` で継続する。"""

    start: date
    end: date
    cursor: str | None = None

    def business_days(self) -> list[date]:
        """期間内の営業日（土日除外）。祝日は考慮しない。

        祝日カレンダーを持たないため「取得したが空だった日」が発生するが、
        J-Quants は日付単位で叩く前提なので1リクエスト分の無駄で済む。
        """
        return [d.date() for d in pd.bdate_range(self.start, self.end)]


class RawBatch(BaseModel):
    """API の生レスポンス1件。加工前の状態を保持する。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    source: str
    endpoint: str
    as_of: date
    fetched_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    request: dict[str, Any] = Field(default_factory=dict)
    payload: Any = None
    next_cursor: str | None = None
    raw_path: str | None = None

    def content_hash(self) -> str:
        """入力ハッシュ（LLM要約キャッシュや冪等性の判定に使う）。"""
        blob = json.dumps(self.payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class Checkpoint(BaseModel):
    """再開位置。`job_runs.checkpoint` に JSON で保存される。"""

    job_name: str = ""
    phase: str = ""
    completed_units: list[str] = Field(default_factory=list)
    next_unit: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def mark_done(self, unit: str) -> None:
        if unit not in self.completed_units:
            self.completed_units.append(unit)
        self.updated_at = datetime.now(UTC)

    def is_done(self, unit: str) -> bool:
        return unit in self.completed_units

    def bump(self, key: str, amount: int = 1) -> None:
        self.metrics[key] = int(self.metrics.get(key, 0)) + amount


class Connector(ABC):
    """すべてのデータソースが実装するインターフェース。"""

    source: str = ""
    rate_limit_per_min: int = 60
    max_retries: int = 5

    @abstractmethod
    def fetch(self, window: FetchWindow, **kwargs: Any) -> Iterator[RawBatch]:
        """外部APIを叩き、生レスポンスをそのまま yield する。加工は禁止。"""

    @abstractmethod
    def normalize(self, batch: RawBatch) -> pd.DataFrame:
        """RawBatch を Core 層のスキーマに合わせた DataFrame に変換する。

        ネットワークアクセスをしてはならない。
        """

    @abstractmethod
    def upsert(self, df: pd.DataFrame) -> int:
        """対象テーブルへ upsert する。戻り値は影響行数。冪等であること。"""

    @abstractmethod
    def checkpoint(self) -> Checkpoint:
        """次回の再開位置を返す。"""


class HttpConnector(Connector):
    """HTTP ベースのコネクタ共通処理。

    レート制限・リトライ・Raw層保存・チェックポイントをここで一元化する。
    サブクラスは `_endpoints` と `normalize` / `upsert` を書くだけでよい。
    """

    #: `normalize` で必須とするトップレベルのキー。欠けていれば schema_drift。
    required_payload_keys: dict[str, tuple[str, ...]] = {}

    def __init__(
        self,
        *,
        data_dir: Path | str,
        warehouse: Any = None,
        state: Any = None,
        sources: SourcesConfig | None = None,
        http: HttpClient | None = None,
        raw_store: RawStore | None = None,
        env: dict[str, str] | None = None,
        require_enabled: bool = True,
    ) -> None:
        self.sources = sources or default_sources_config()
        self.config: SourceConfig = self.sources.for_source(self.source)
        if require_enabled and not self.config.enabled:
            raise SourceDisabledError(
                f"{self.source} は sources.yaml で enabled: false になっています"
            )
        self.warehouse = warehouse
        self.state = state
        self.env = env
        self.data_dir = Path(data_dir)
        self.raw = raw_store or RawStore(self.data_dir)
        self.rate_limit_per_min = int(
            self.config.get("rate_limit_per_min")
            or float(self.config.get("rate_limit_per_sec", 1)) * 60
        )
        retry_cfg = self.config.get("retry") or {}
        self._checkpoint = Checkpoint(job_name=f"collector.{self.source}", phase=self.source)
        self._http = http or HttpClient(
            source=self.source,
            bucket=TokenBucket.from_config(
                self.source,
                self.config.raw,
                store=state if state is not None else None,
            ),
            retry=RetryPolicy(
                max_attempts=int(retry_cfg.get("max_attempts", self.max_retries)),
                backoff_base_sec=float(retry_cfg.get("backoff_base_sec", 4.0)),
            ),
            timeout=self.config.timeout,
            default_headers=self.auth_headers(),
        )

    # ------------------------------------------------------------------
    def auth_headers(self) -> dict[str, str]:
        """認証ヘッダ。クエリ認証のソースでは空を返す。"""
        auth = self.config.get("auth") or {}
        if auth.get("kind") != "header":
            return {}
        secret = self.config.secret(self.env)
        if not secret:
            # キーが無い環境でも import と初期化は通す。実際の fetch 時に
            # 401 として扱われる（あるいはサブクラスが事前検証する）。
            return {}
        return {str(auth["header_name"]): secret}

    def auth_params(self) -> dict[str, str]:
        auth = self.config.get("auth") or {}
        if auth.get("kind") != "query":
            return {}
        secret = self.config.secret(self.env)
        if not secret:
            return {}
        return {str(auth["param_name"]): secret}

    @property
    def http(self) -> HttpClient:
        return self._http

    def checkpoint(self) -> Checkpoint:
        return self._checkpoint

    def set_checkpoint(self, checkpoint: Checkpoint | dict[str, Any] | None) -> None:
        if checkpoint is None:
            return
        self._checkpoint = (
            checkpoint if isinstance(checkpoint, Checkpoint) else Checkpoint(**checkpoint)
        )

    # ------------------------------------------------------------------
    def make_batch(
        self,
        *,
        endpoint: str,
        as_of: date,
        payload: Any,
        request: dict[str, Any] | None = None,
        next_cursor: str | None = None,
        persist: bool = True,
    ) -> RawBatch:
        """生レスポンスを Raw層に保存し `RawBatch` を組み立てる。

        `request` はマスク済みのものを渡すこと（キーを保存しない）。
        """
        fetched_at = datetime.now(UTC)
        raw_file: Path | None = None
        if persist:
            raw_file = self.raw.write_json(
                source=self.source,
                endpoint=endpoint,
                as_of=as_of,
                payload=payload,
                request=request or {},
                fetched_at=fetched_at,
            )
        return RawBatch(
            source=self.source,
            endpoint=endpoint,
            as_of=as_of,
            fetched_at=fetched_at.isoformat(),
            request=request or {},
            payload=payload,
            next_cursor=next_cursor,
            raw_path=str(raw_file) if raw_file else None,
        )

    def assert_payload_shape(self, batch: RawBatch) -> None:
        """レスポンス構造の検証。想定外なら `SchemaDriftError`。

        「静かに壊れる」ことを防ぐための最低限の検査。
        """
        expected = self.required_payload_keys.get(batch.endpoint)
        if not expected:
            return
        payload = batch.payload
        if not isinstance(payload, dict):
            raise SchemaDriftError(
                f"{self.source}/{batch.endpoint}: dict を期待しましたが "
                f"{type(payload).__name__} でした",
                source=self.source,
                endpoint=batch.endpoint,
            )
        missing = [key for key in expected if key not in payload]
        if missing:
            raise SchemaDriftError(
                f"{self.source}/{batch.endpoint}: 想定キーが欠けています {missing}。"
                "APIの仕様変更の可能性があります",
                source=self.source,
                endpoint=batch.endpoint,
            )

    # ------------------------------------------------------------------
    def upsert(self, df: pd.DataFrame) -> int:
        """既定実装。`target_table` に応じた warehouse のメソッドへ委譲する。"""
        table = str(df.attrs.get("table", ""))
        if table in {"prices_daily", "prices_live"}:
            from packages.core.connectors.quality import persist_price_quality

            persist_price_quality(
                self.warehouse,
                source=getattr(self, "source", "") or "",
                table_name=table or "prices_daily",
                accepted=df,
                rejected=df.attrs.get("rejected"),
            )
        if df.empty:
            return 0
        table = str(df.attrs.get("table", ""))
        if not table:
            raise ValueError("DataFrame.attrs['table'] が設定されていません")
        if self.warehouse is None:
            return 0
        method = {
            "securities": "upsert_securities",
            "prices_daily": "upsert_prices_daily",
            "prices_live": "upsert_prices_live",
            "financials": "upsert_financials",
            "documents": "upsert_documents",
            "macro_series": "upsert_macro_series",
            "earnings_dates": "upsert_earnings_dates",
        }.get(table)
        if method is None:
            raise ValueError(f"未知の対象テーブル: {table}")
        return int(getattr(self.warehouse, method)(df))

    def close(self) -> None:
        self._http.close()


def tag_table(df: pd.DataFrame, table: str) -> pd.DataFrame:
    """`upsert` の宛先テーブルを DataFrame に埋め込む。"""
    df.attrs["table"] = table
    return df


def now_utc() -> datetime:
    return datetime.now(UTC)
