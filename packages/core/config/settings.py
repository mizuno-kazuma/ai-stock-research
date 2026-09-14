"""型付き設定（docs/11-security-ops.md §1.3）。

設定の出所は 3 つに分かれる（docs/01-architecture.md §7）。

| 種別                     | 保存先                          | 本モジュールの扱い |
| ------------------------ | ------------------------------- | ------------------ |
| シークレット             | `.env` / 環境変数               | ここで読む         |
| 構成（コード管理）       | `packages/core/config/*.yaml`   | `models.py`        |
| 実行時設定（利用者変更） | SQLite `settings` テーブル      | `storage/sqlite_repo.py` |

起動時に落とすことを重視する。設定ミスを実行時に発見すると、
数時間のバックフィルの後で気付くことになる。
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]

AuthMode = Literal["none", "token", "passkey"]
JQuantsPlan = Literal["free", "light"]


class EdgarUserAgentNotConfiguredError(RuntimeError):
    """EDGAR を叩こうとしたが User-Agent が未設定。

    SEC は実名と連絡先を含む User-Agent を要求する。空や無効な値で叩くと
    IP ブロックされ、復旧に時間がかかる（docs/11-security-ops.md §1.3）。
    """


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ===== データソース =====
    jquants_api_key: SecretStr = SecretStr("")
    jquants_plan: JQuantsPlan = "light"
    edinet_subscription_key: SecretStr = SecretStr("")
    fred_api_key: SecretStr = SecretStr("")
    # 未設定は None。値を入れる場合は実名 + メールアドレスを必須とする。
    edgar_user_agent: str | None = None
    alpha_vantage_api_key: SecretStr = SecretStr("")
    finnhub_api_key: SecretStr = SecretStr("")
    tdnet_enabled: bool = False

    # ===== LLM =====
    anthropic_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    litellm_log_level: str = "WARNING"
    llm_kill_switch: bool = False

    # ===== ストレージ =====
    data_dir: Path = Field(default_factory=lambda: Path.home() / "ai-stock" / "data")
    # 未指定なら data_dir から導出する（.env での ${DATA_DIR} 展開に頼らない）。
    database_url: str | None = None
    warehouse_path: Path | None = None
    vector_dir: Path | None = None
    backup_dir: Path | None = None
    # DuckDB の実行時上限（docs/15-windows-runtime.md §9.3）。
    duckdb_memory_limit: str | None = "6GB"
    duckdb_threads: int | None = 4
    # Parquet 圧縮（packages.core.storage.parquet_lake が参照する）
    parquet_compression: Literal["zstd", "snappy", "gzip", "none"] = "zstd"
    # Phase B: LanceDB | pgvector | memory
    vector_store_backend: Literal["lancedb", "pgvector", "memory"] = "lancedb"
    # Phase B: Cloudflare R2 / S3 互換（未設定ならローカル DATA_DIR）
    warehouse_uri: str | None = None  # 例: s3://ai-stock/warehouse
    blob_uri: str | None = None  # 例: s3://ai-stock/blobs
    s3_endpoint_url: str | None = None  # 例: https://<accountid>.r2.cloudflarestorage.com
    s3_access_key_id: SecretStr = SecretStr("")
    s3_secret_access_key: SecretStr = SecretStr("")
    s3_region: str = "auto"
    # Fly / コンテナでは DATA_DIR=/data を推奨
    deployment_profile: Literal["local", "cloud"] = "local"

    # ===== アプリ =====
    api_host: str = "0.0.0.0"  # noqa: S104 - WSL2 内で全インターフェースにバインドする
    api_port: int = 8000
    web_port: int = 3000
    auth_mode: AuthMode = "none"
    api_token: SecretStr = SecretStr("")
    cors_origins: str = "http://localhost:3000"
    tz: str = "Asia/Tokyo"
    app_version: str = "0.1.0"

    # ===== コスト上限 =====
    llm_daily_cap_usd: float = 1.0
    llm_monthly_cap_usd: float = 20.0

    # ===== 通知・運用 =====
    notify_webhook_url: str = ""
    notify_enabled: bool = True
    log_level: str = "INFO"
    sentry_dsn: str = ""

    # ------------------------------------------------------------------
    # 検証
    # ------------------------------------------------------------------
    @field_validator("data_dir")
    @classmethod
    def data_dir_not_on_windows_mount(cls, v: Path) -> Path:
        """/mnt/c 配下は I/O が桁違いに遅く、DuckDB/Parquet 処理が実用にならない。

        docs/15-windows-runtime.md §6 / docs/11-security-ops.md §1.3。
        """
        if str(v).startswith("/mnt/"):
            raise ValueError(
                f"DATA_DIR に Windows マウント（{v}）を指定できません。"
                "WSL2 のホーム配下（例: /home/user/ai-stock/data）を使ってください。"
                "詳細: docs/15-windows-runtime.md §6"
            )
        return v

    @field_validator("edgar_user_agent")
    @classmethod
    def edgar_ua_must_have_contact(cls, v: str | None) -> str | None:
        """SEC は実名と連絡先を含む User-Agent を要求する。

        未設定（None）は許可する。API サーバは EDGAR を叩かないため、
        鍵が揃っていなくても起動できる必要がある。実際に EDGAR へ
        アクセスする側は `require_edgar_user_agent()` を通すこと。
        """
        if v is None or not str(v).strip():
            return None
        if "@" not in v or len(v) < 10:
            raise ValueError(
                "EDGAR_USER_AGENT には実名とメールアドレスを含めてください。"
                "例: 'Taro Yamada (taro@example.com)'"
            )
        return v

    @model_validator(mode="after")
    def derive_storage_paths(self) -> Settings:
        if self.warehouse_path is None:
            self.warehouse_path = self.data_dir / "warehouse" / "analytics.duckdb"
        if self.vector_dir is None:
            self.vector_dir = self.data_dir / "vectors"
        if self.backup_dir is None:
            self.backup_dir = self.data_dir.parent / "backups"
        if self.database_url is None:
            self.database_url = f"sqlite+aiosqlite:///{self.state_db_path}"
        if self.deployment_profile == "cloud" and self.auth_mode == "none":
            raise ValueError(
                "deployment_profile=cloud では AUTH_MODE=none は使えません。"
                "AUTH_MODE=token と API_TOKEN を設定してください。"
            )
        if self.auth_mode == "token" and not self.api_token.get_secret_value():
            raise ValueError("AUTH_MODE=token ですが API_TOKEN が空です。")
        return self

    # ------------------------------------------------------------------
    # 派生プロパティ
    # ------------------------------------------------------------------
    @property
    def state_db_path(self) -> Path:
        return self.data_dir / "state.sqlite"

    @property
    def duckdb_path(self) -> Path:
        """DuckDBRepo.open() が読むパス。`warehouse_path` の別名。"""
        assert self.warehouse_path is not None
        return self.warehouse_path

    @property
    def sqlite_path(self) -> Path:
        """SQLite ファイルパス。`state_db_path` の別名。"""
        return self.state_db_path

    @property
    def sync_database_url(self) -> str:
        """SQLAlchemy 同期エンジン用 URL。

        Phase A: sqlite+pysqlite。
        Phase B: DATABASE_URL が Postgres なら postgresql+psycopg に正規化する。
        """
        url = self.database_url or f"sqlite+aiosqlite:///{self.state_db_path.as_posix()}"
        if url.startswith("sqlite+aiosqlite://"):
            return "sqlite+pysqlite://" + url.removeprefix("sqlite+aiosqlite://")
        if url.startswith("sqlite://"):
            return "sqlite+pysqlite://" + url.removeprefix("sqlite://")
        if url.startswith("postgres://"):
            return "postgresql+psycopg://" + url.removeprefix("postgres://")
        if url.startswith("postgresql+asyncpg://"):
            return "postgresql+psycopg://" + url.removeprefix("postgresql+asyncpg://")
        if url.startswith("postgresql://"):
            return "postgresql+psycopg://" + url.removeprefix("postgresql://")
        return url

    @property
    def sqlite_url(self) -> str:
        """後方互換エイリアス。Postgres 利用時も sync_database_url を返す。"""
        return self.sync_database_url

    @property
    def scheduler_database_url(self) -> str:
        """APScheduler SQLAlchemyJobStore 用（同期ドライバ）。"""
        url = self.sync_database_url
        if url.startswith("sqlite+pysqlite://"):
            return "sqlite://" + url.removeprefix("sqlite+pysqlite://")
        if url.startswith("postgresql+psycopg://"):
            return "postgresql+psycopg://" + url.removeprefix("postgresql+psycopg://")
        return url

    @property
    def uses_postgres(self) -> bool:
        return self.sync_database_url.startswith("postgresql")

    @property
    def uses_object_storage(self) -> bool:
        return bool(self.s3_endpoint_url and self.warehouse_uri)

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def warehouse_dir(self) -> Path:
        return self.data_dir / "warehouse"

    @property
    def parquet_dir(self) -> Path:
        return self.warehouse_dir / "parquet"

    @property
    def blob_dir(self) -> Path:
        return self.data_dir / "blobs"

    @property
    def duckdb_temp_dir(self) -> Path:
        """DuckDB のスピル先。

        既定の /tmp は WSL2 では tmpfs（メモリ上）になり、
        大きな集計で結局 OOM になる（docs/15-windows-runtime.md §9.3）。
        """
        return self.data_dir / "duckdb_tmp"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def require_edgar_user_agent(self) -> str:
        if not self.edgar_user_agent:
            raise EdgarUserAgentNotConfiguredError(
                "EDGAR_USER_AGENT が未設定です。.env に実名とメールアドレスを"
                "設定してください。例: 'Taro Yamada (taro@example.com)'"
            )
        return self.edgar_user_agent

    def ensure_directories(self) -> None:
        """データディレクトリ一式を作る。冪等。"""
        for d in (
            self.data_dir,
            self.raw_dir,
            self.warehouse_dir,
            self.parquet_dir,
            self.blob_dir,
            self.duckdb_temp_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)
        if self.vector_dir is not None:
            self.vector_dir.mkdir(parents=True, exist_ok=True)


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """テストで環境変数を差し替えた後に呼ぶ。"""
    get_settings.cache_clear()
