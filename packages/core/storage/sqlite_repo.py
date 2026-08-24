"""SQLite（状態管理）のモデルとリポジトリ（docs/03-data-model.md §3）。

SQLAlchemy 2.0 の declarative モデルで定義する。Postgres への移行を
接続文字列の変更だけで済ませるため、**SQLite 固有の型・関数は使わない**。
時刻はすべて ISO8601 UTC 文字列（TEXT）で保存する。
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Self

from sqlalchemy import (
    Boolean,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    func,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)
from sqlalchemy.pool import StaticPool

from packages.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    """`2026-08-24T02:23:00Z` 形式（docs/09-api-spec.md §2 の時刻表現）。"""
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads(value: str | None, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base。"""


class JobRun(Base):
    """バッチ実行の記録（docs/03 §3.1）。"""

    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[str | None] = mapped_column(String(8))
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[str] = mapped_column(Text, nullable=False)
    finished_at: Mapped[str | None] = mapped_column(Text)
    duration_sec: Mapped[float | None] = mapped_column(Float)
    checkpoint: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[str | None] = mapped_column(Text)
    error_type: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    error_traceback: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    parent_run_id: Mapped[int | None] = mapped_column(Integer)
    git_commit: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (Index("idx_job_runs_name", "job_name", "started_at"),)


class AgentMemory(Base):
    """エージェントの教訓（docs/03 §3.2）。"""

    __tablename__ = "agent_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    memory_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_value: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    lesson_ja: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ja: Mapped[str] = mapped_column(Text, nullable=False)
    derived_from: Mapped[str] = mapped_column(Text, nullable=False)
    n_observations: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    hit_rate_before: Mapped[float | None] = mapped_column(Float)
    hit_rate_after: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    superseded_by: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_used_at: Mapped[str | None] = mapped_column(Text)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    review_due_at: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("idx_memory_scope", "scope", "scope_value", "is_active"),)


class FactorWeight(Base):
    """ファクター合成重み（docs/03 §3.3）。"""

    __tablename__ = "factor_weights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    weight_set_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    horizon: Mapped[str] = mapped_column(String(8), nullable=False)
    weights: Mapped[str] = mapped_column(Text, nullable=False)
    fitted_from: Mapped[str] = mapped_column(Text, nullable=False)
    fitted_to: Mapped[str] = mapped_column(Text, nullable=False)
    fit_method: Mapped[str] = mapped_column(String(16), nullable=False)
    ic_in_sample: Mapped[float | None] = mapped_column(Float)
    ic_out_of_sample: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    activated_at: Mapped[str | None] = mapped_column(Text)
    deactivated_at: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class LlmCall(Base):
    """LLM 呼び出しの記録（docs/03 §3.4）。"""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    job_run_id: Mapped[int | None] = mapped_column(Integer)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    entity: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    was_cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    called_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("idx_llm_calls_date", "called_at"),)


class CostBudget(Base):
    """コスト上限とキルスイッチ（docs/03 §3.4）。"""

    __tablename__ = "cost_budget"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(16), nullable=False)
    period_key: Mapped[str] = mapped_column(String(16), nullable=False)
    cap_usd: Mapped[float] = mapped_column(Float, nullable=False)
    spent_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_exceeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    kill_switch_on: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (UniqueConstraint("period", "period_key", name="uq_cost_budget"),)


class Trade(Base):
    """手動売買の記録（docs/03 §3.5）。"""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    executed_at: Mapped[str] = mapped_column(Text, nullable=False)
    broker: Mapped[str | None] = mapped_column(String(64))
    account_type: Mapped[str | None] = mapped_column(String(16))
    linked_rec_id: Mapped[str | None] = mapped_column(String(64))
    thesis_ja: Mapped[str | None] = mapped_column(Text)
    emotion_tag: Mapped[str | None] = mapped_column(String(16))
    exit_plan_ja: Mapped[str | None] = mapped_column(Text)
    review_ja: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("idx_trades_ticker", "ticker", "market", "executed_at"),)


class Position(Base):
    """保有ポジション（docs/03 §3.5）。"""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    account_type: Mapped[str | None] = mapped_column(String(16))
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    avg_cost: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    opened_at: Mapped[str] = mapped_column(Text, nullable=False)
    closed_at: Mapped[str | None] = mapped_column(Text)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "ticker", "market", "account_type", "opened_at", name="uq_positions"
        ),
    )


class Setting(Base):
    """設定（docs/03 §3.6）。値は JSON 文字列。"""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class WatchlistItem(Base):
    """ウォッチリスト（docs/03 §3.6）。"""

    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    list_name: Mapped[str] = mapped_column(String(32), nullable=False, default="default")
    note_ja: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("ticker", "market", "list_name", name="uq_watchlist"),
    )


class Alert(Base):
    """通知（docs/03 §3.6）。"""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    title_ja: Mapped[str] = mapped_column(Text, nullable=False)
    body_ja: Mapped[str | None] = mapped_column(Text)
    entity: Mapped[str | None] = mapped_column(String(64))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class RateLimitState(Base):
    """レート制限のトークンバケット状態（docs/03 §3.6）。"""

    __tablename__ = "rate_limit_state"

    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    tokens: Mapped[float] = mapped_column(Float, nullable=False)
    last_refill_at: Mapped[str] = mapped_column(Text, nullable=False)
    calls_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    day_key: Mapped[str] = mapped_column(String(16), nullable=False)


class BackfillProgress(Base):
    """バックフィルの再開位置（docs/03 §3.6）。"""

    __tablename__ = "backfill_progress"

    step_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    cursor_value: Mapped[str | None] = mapped_column(Text)
    total_units: Mapped[int | None] = mapped_column(Integer)
    done_units: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


# docs/03-data-model.md §3.6「既定の設定キー」
DEFAULT_SETTINGS: dict[str, Any] = {
    "ui.direction_colors": "jp",
    "ui.theme": "dark",
    "ui.base_currency": "JPY",
    "ui.default_market": "JP",
    "llm.daily_cap_usd": 1.0,
    "llm.monthly_cap_usd": 20.0,
    "llm.kill_switch": False,
    "data.jquants_plan": "free",
    "data.tdnet_enabled": False,
    "agent.auto_activate_weights": False,
    "agent.max_recommendations_per_day": 10,
    "risk.max_position_pct": 10.0,
}

SETTING_TYPES: dict[str, type] = {
    "ui.direction_colors": str,
    "ui.theme": str,
    "ui.base_currency": str,
    "ui.default_market": str,
    "llm.daily_cap_usd": float,
    "llm.monthly_cap_usd": float,
    "llm.kill_switch": bool,
    "data.jquants_plan": str,
    "data.tdnet_enabled": bool,
    "agent.auto_activate_weights": bool,
    "agent.max_recommendations_per_day": int,
    "risk.max_position_pct": float,
}

# ジョブが 6 時間以上 running のままなら中断とみなす（docs/03 §3.1）
STALE_JOB_HOURS = 6


class SQLiteRepo:
    """SQLite への読み書き。セッションは都度作って閉じる。"""

    def __init__(self, url_or_path: str | Path) -> None:
        url = str(url_or_path)
        if not url.startswith("sqlite") and not url.startswith("postgresql"):
            path = Path(url)
            path.parent.mkdir(parents=True, exist_ok=True)
            url = f"sqlite+pysqlite:///{path.as_posix()}"
        self.url = url
        engine_kwargs: dict[str, Any] = {"future": True, "echo": False}
        if ":memory:" in url:
            engine_kwargs["connect_args"] = {"check_same_thread": False}
            engine_kwargs["poolclass"] = StaticPool
        self.engine: Engine = create_engine(url, **engine_kwargs)
        if url.startswith("sqlite"):
            _configure_sqlite(self.engine)
        self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    @classmethod
    def open(cls, settings: Settings | None = None) -> Self:
        s = settings or get_settings()
        return cls(s.sqlite_url)

    @classmethod
    def in_memory(cls) -> Self:
        repo = cls("sqlite+pysqlite:///:memory:")
        repo.init_db()
        return repo

    def close(self) -> None:
        self.engine.dispose()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self._session_factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    # -- スキーマ ------------------------------------------------------------

    def init_db(self, *, seed_defaults: bool = True) -> None:
        """テーブルを作成し、既定の設定を入れる。冪等。"""
        Base.metadata.create_all(self.engine)
        if seed_defaults:
            self.ensure_default_settings()

    def ensure_default_settings(self) -> int:
        """未設定のキーだけ既定値で埋める。既存値は上書きしない。"""
        added = 0
        with self.session() as s:
            existing = {row[0] for row in s.execute(select(Setting.key)).all()}
            for key, value in DEFAULT_SETTINGS.items():
                if key not in existing:
                    s.add(Setting(key=key, value=_json_dumps(value), updated_at=utc_now_iso()))
                    added += 1
        return added

    # -- settings -------------------------------------------------------------

    def get_settings_dict(self) -> dict[str, Any]:
        """全設定を `{key: 値}` で返す（値は JSON デコード済み）。"""
        with self.session() as s:
            rows = s.execute(select(Setting)).scalars().all()
        out = dict(DEFAULT_SETTINGS)
        out.update({r.key: _json_loads(r.value) for r in rows})
        return out

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.session() as s:
            row = s.get(Setting, key)
        if row is None:
            return DEFAULT_SETTINGS.get(key, default)
        return _json_loads(row.value, default)

    def set_settings(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """複数キーをまとめて更新する。返り値は更新後の全設定。"""
        now = utc_now_iso()
        with self.session() as s:
            for key, value in values.items():
                row = s.get(Setting, key)
                if row is None:
                    s.add(Setting(key=key, value=_json_dumps(value), updated_at=now))
                else:
                    row.value = _json_dumps(value)
                    row.updated_at = now
        return self.get_settings_dict()

    def set_setting(self, key: str, value: Any) -> None:
        """単一キーの更新。`StateRepo` 契約用。"""
        self.set_settings({key: value})

    # -- job_runs -------------------------------------------------------------

    def start_job_run(
        self,
        job_name: str,
        *,
        trigger: str = "manual",
        market: str | None = None,
        parent_run_id: int | None = None,
        git_commit: str | None = None,
    ) -> int:
        with self.session() as s:
            row = JobRun(
                job_name=job_name,
                market=market,
                trigger=trigger,
                status="running",
                started_at=utc_now_iso(),
                parent_run_id=parent_run_id,
                git_commit=git_commit,
            )
            s.add(row)
            s.flush()
            return int(row.id)

    def update_job_run(
        self,
        run_id: int,
        *,
        status: str | None = None,
        checkpoint: Mapping[str, Any] | None = None,
        metrics: Mapping[str, Any] | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        error_traceback: str | None = None,
        finished: bool = False,
    ) -> None:
        with self.session() as s:
            row = s.get(JobRun, run_id)
            if row is None:
                raise KeyError(f"job_run が見つかりません: {run_id}")
            if status:
                row.status = status
            if checkpoint is not None:
                row.checkpoint = _json_dumps(dict(checkpoint))
            if metrics is not None:
                row.metrics = _json_dumps(dict(metrics))
            if error_type:
                row.error_type = error_type
            if error_message:
                row.error_message = error_message
            if error_traceback:
                row.error_traceback = error_traceback
            if finished:
                row.finished_at = utc_now_iso()
                started = _parse_iso(row.started_at)
                if started:
                    row.duration_sec = (
                        dt.datetime.now(dt.UTC) - started
                    ).total_seconds()

    def get_job_run(self, run_id: int) -> JobRun | None:
        with self.session() as s:
            return s.get(JobRun, run_id)

    def get_job_runs(
        self,
        *,
        job_name: str | None = None,
        status: str | None = None,
        since: str | None = None,
        limit: int = 50,
    ) -> list[JobRun]:
        stmt = select(JobRun)
        if job_name:
            stmt = stmt.where(JobRun.job_name == job_name)
        if status:
            stmt = stmt.where(JobRun.status == status)
        if since:
            stmt = stmt.where(JobRun.started_at >= since)
        stmt = stmt.order_by(JobRun.started_at.desc(), JobRun.id.desc()).limit(limit)
        with self.session() as s:
            return list(s.execute(stmt).scalars().all())

    def latest_job_run(
        self,
        job_name: str | None = None,
        *,
        market: str | None = None,
        on_date: dt.date | None = None,
    ) -> JobRun | None:
        if not job_name:
            return None
        rows = self.get_job_runs(job_name=job_name, limit=200)
        if market is not None:
            rows = [r for r in rows if r.market == market]
        if on_date is not None:
            target = on_date.isoformat()
            matched: list[JobRun] = []
            for row in rows:
                started = _parse_iso(row.started_at)
                if started is None:
                    continue
                if started.date().isoformat() == target:
                    matched.append(row)
            rows = matched
        return rows[0] if rows else None

    def create_job_run(
        self,
        *,
        job_name: str,
        market: str | None = None,
        trigger: str = "schedule",
        parent_run_id: int | None = None,
    ) -> int:
        return self.start_job_run(
            job_name, trigger=trigger, market=market, parent_run_id=parent_run_id
        )

    def record_job_run(
        self,
        run_id: int,
        *,
        status: str,
        metrics: Mapping[str, Any] | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        error_traceback: str | None = None,
    ) -> None:
        self.update_job_run(
            run_id,
            status=status,
            metrics=metrics,
            error_type=error_type,
            error_message=error_message,
            error_traceback=error_traceback,
            finished=True,
        )

    def find_job_runs(
        self,
        *,
        status: str | None = None,
        started_before: dt.datetime | None = None,
    ) -> list[JobRun]:
        rows = self.get_job_runs(status=status, limit=500)
        if started_before is None:
            return rows
        cutoff = started_before
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=dt.UTC)
        out: list[JobRun] = []
        for row in rows:
            started = _parse_iso(row.started_at)
            if started is None:
                continue
            if started.tzinfo is None:
                started = started.replace(tzinfo=dt.UTC)
            if started < cutoff:
                out.append(row)
        return out

    def save_checkpoint(self, run_id: int, checkpoint: Mapping[str, Any]) -> None:
        self.update_job_run(run_id, checkpoint=checkpoint)

    def load_checkpoint(self, run_id: int) -> dict[str, Any] | None:
        row = self.get_job_run(run_id)
        if row is None or not row.checkpoint:
            return None
        loaded = _json_loads(row.checkpoint)
        return loaded if isinstance(loaded, dict) else None

    def find_interrupted_jobs(self, *, hours: int = STALE_JOB_HOURS) -> list[JobRun]:
        """`running` のまま放置されたジョブ（Windows Update 後の再起動など）。

        docs/03-data-model.md §3.1。API 起動時に呼んで `interrupted` に倒す。
        """
        cutoff = (
            dt.datetime.now(dt.UTC) - dt.timedelta(hours=hours)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        stmt = select(JobRun).where(
            JobRun.status == "running", JobRun.started_at < cutoff
        )
        with self.session() as s:
            return list(s.execute(stmt).scalars().all())

    def mark_interrupted_jobs(self, *, hours: int = STALE_JOB_HOURS) -> list[int]:
        """中断ジョブを `interrupted` にする。戻り値は対象 run_id。"""
        stale = self.find_interrupted_jobs(hours=hours)
        ids = [int(r.id) for r in stale]
        for run_id in ids:
            self.update_job_run(
                run_id,
                status="interrupted",
                error_type="interrupted",
                error_message=(
                    "起動時に running のまま検出されました"
                    "（再起動またはプロセス強制終了の可能性）。"
                ),
            )
        if ids:
            logger.warning("中断ジョブを検出しました: %s", ids)
        return ids

    # -- llm_calls / cost -----------------------------------------------------

    def record_llm_call(self, **kwargs: Any) -> int:
        kwargs.setdefault("called_at", utc_now_iso())
        with self.session() as s:
            row = LlmCall(**kwargs)
            s.add(row)
            s.flush()
            return int(row.id)

    def insert_llm_call(self, call: Any) -> None:
        if isinstance(call, Mapping):
            payload = dict(call)
        else:
            payload = {
                "call_id": call.call_id,
                "tier": call.tier,
                "model_id": call.model_id,
                "purpose": call.purpose,
                "input_tokens": call.input_tokens,
                "output_tokens": call.output_tokens,
                "cost_usd": call.cost_usd,
                "status": call.status,
                "called_at": call.called_at,
                "job_run_id": getattr(call, "job_run_id", None),
                "entity": getattr(call, "entity", None),
                "cached_tokens": getattr(call, "cached_tokens", 0),
                "latency_ms": getattr(call, "latency_ms", None),
                "was_cache_hit": getattr(call, "was_cache_hit", False),
                "error_message": getattr(call, "error_message", None),
            }
        called = payload.get("called_at")
        if hasattr(called, "isoformat"):
            iso = called.isoformat()
            payload["called_at"] = iso.replace("+00:00", "Z") if iso.endswith("+00:00") else iso
        allowed = {
            "call_id",
            "tier",
            "model_id",
            "purpose",
            "input_tokens",
            "output_tokens",
            "cost_usd",
            "status",
            "called_at",
            "job_run_id",
            "entity",
            "cached_tokens",
            "latency_ms",
            "was_cache_hit",
            "error_message",
        }
        self.record_llm_call(**{k: v for k, v in payload.items() if k in allowed})

    def sum_llm_cost(self, *, period: str, period_key: str) -> float:
        if period == "day":
            summary = self.llm_cost_summary(day_key=period_key, month_key=period_key[:7])
            return float(summary.get("spent_today_usd") or 0.0)
        summary = self.llm_cost_summary(day_key=f"{period_key}-01", month_key=period_key)
        return float(summary.get("spent_month_usd") or 0.0)

    def get_budget(self, *, period: str, period_key: str) -> dict[str, Any] | None:
        row = self.get_cost_budget(period, period_key)
        if row is None:
            return None
        return {
            "spent_usd": getattr(row, "spent_usd", 0.0),
            "kill_switch_on": getattr(row, "kill_switch_on", False),
            "cap_usd": getattr(row, "cap_usd", 0.0),
        }

    def add_spend(self, *, period: str, period_key: str, amount_usd: float) -> float:
        row = self.get_cost_budget(period, period_key)
        current = float(getattr(row, "spent_usd", 0.0) or 0.0) if row else 0.0
        cap = float(getattr(row, "cap_usd", 0.0) or 0.0) if row else 0.0
        new = current + float(amount_usd)
        self.upsert_cost_budget(period, period_key, cap_usd=cap or 1.0, spent_usd=new)
        return new

    def set_kill_switch(self, *, period: str, period_key: str, on: bool) -> None:
        row = self.get_cost_budget(period, period_key)
        cap = float(getattr(row, "cap_usd", 1.0) or 1.0) if row else 1.0
        spent = float(getattr(row, "spent_usd", 0.0) or 0.0) if row else 0.0
        self.upsert_cost_budget(
            period, period_key, cap_usd=cap, spent_usd=spent, kill_switch_on=on
        )

    def llm_cost_summary(self, *, day_key: str, month_key: str) -> dict[str, Any]:
        """日次・月次の消費額と上限。UI の `/costs` に対応する。"""
        with self.session() as s:
            spent_today = (
                s.execute(
                    select(func.coalesce(func.sum(LlmCall.cost_usd), 0.0)).where(
                        LlmCall.called_at >= f"{day_key}T00:00:00Z",
                        LlmCall.called_at <= f"{day_key}T23:59:59Z",
                        LlmCall.status == "success",
                    )
                ).scalar()
                or 0.0
            )
            spent_month = (
                s.execute(
                    select(func.coalesce(func.sum(LlmCall.cost_usd), 0.0)).where(
                        LlmCall.called_at >= f"{month_key}-01T00:00:00Z",
                        LlmCall.called_at < f"{month_key}-32",
                        LlmCall.status == "success",
                    )
                ).scalar()
                or 0.0
            )
            by_purpose = s.execute(
                select(
                    LlmCall.purpose,
                    func.count(LlmCall.id),
                    func.coalesce(func.sum(LlmCall.cost_usd), 0.0),
                )
                .where(LlmCall.called_at >= f"{month_key}-01T00:00:00Z")
                .group_by(LlmCall.purpose)
            ).all()
            by_model = s.execute(
                select(
                    LlmCall.model_id,
                    func.count(LlmCall.id),
                    func.coalesce(func.sum(LlmCall.cost_usd), 0.0),
                )
                .where(LlmCall.called_at >= f"{month_key}-01T00:00:00Z")
                .group_by(LlmCall.model_id)
            ).all()
            cache_hits = (
                s.execute(
                    select(func.count(LlmCall.id)).where(
                        LlmCall.was_cache_hit.is_(True),
                        LlmCall.called_at >= f"{month_key}-01T00:00:00Z",
                    )
                ).scalar()
                or 0
            )
            total_calls = (
                s.execute(
                    select(func.count(LlmCall.id)).where(
                        LlmCall.called_at >= f"{month_key}-01T00:00:00Z"
                    )
                ).scalar()
                or 0
            )
        return {
            "spent_today_usd": round(float(spent_today), 6),
            "spent_month_usd": round(float(spent_month), 6),
            "by_purpose": [
                {"purpose": p, "calls": int(c), "cost_usd": round(float(v), 6)}
                for p, c, v in by_purpose
            ],
            "by_model": [
                {"model_id": m, "calls": int(c), "cost_usd": round(float(v), 6)}
                for m, c, v in by_model
            ],
            "cache_hit_rate": (float(cache_hits) / total_calls) if total_calls else None,
            "n_calls_month": int(total_calls),
        }

    def get_cost_budget(self, period: str, period_key: str) -> CostBudget | None:
        with self.session() as s:
            return s.execute(
                select(CostBudget).where(
                    CostBudget.period == period, CostBudget.period_key == period_key
                )
            ).scalar_one_or_none()

    def upsert_cost_budget(
        self,
        period: str,
        period_key: str,
        *,
        cap_usd: float,
        spent_usd: float | None = None,
        kill_switch_on: bool | None = None,
    ) -> None:
        with self.session() as s:
            row = s.execute(
                select(CostBudget).where(
                    CostBudget.period == period, CostBudget.period_key == period_key
                )
            ).scalar_one_or_none()
            if row is None:
                row = CostBudget(
                    period=period,
                    period_key=period_key,
                    cap_usd=cap_usd,
                    spent_usd=spent_usd or 0.0,
                    updated_at=utc_now_iso(),
                )
                s.add(row)
            else:
                row.cap_usd = cap_usd
                if spent_usd is not None:
                    row.spent_usd = spent_usd
                row.updated_at = utc_now_iso()
            if kill_switch_on is not None:
                row.kill_switch_on = kill_switch_on
            row.is_exceeded = row.spent_usd >= row.cap_usd

    # -- trades / positions ---------------------------------------------------

    def insert_trade(self, **kwargs: Any) -> Trade:
        now = utc_now_iso()
        kwargs.setdefault("created_at", now)
        kwargs.setdefault("updated_at", now)
        with self.session() as s:
            row = Trade(**kwargs)
            s.add(row)
            s.flush()
            s.refresh(row)
            return row

    def update_trade(self, trade_id: str, **changes: Any) -> Trade | None:
        with self.session() as s:
            row = s.execute(
                select(Trade).where(Trade.trade_id == trade_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            for key, value in changes.items():
                if value is not None and hasattr(row, key):
                    setattr(row, key, value)
            row.updated_at = utc_now_iso()
            s.flush()
            s.refresh(row)
            return row

    def delete_trade(self, trade_id: str) -> bool:
        with self.session() as s:
            row = s.execute(
                select(Trade).where(Trade.trade_id == trade_id)
            ).scalar_one_or_none()
            if row is None:
                return False
            s.delete(row)
            return True

    def get_trade(self, trade_id: str) -> Trade | None:
        with self.session() as s:
            return s.execute(
                select(Trade).where(Trade.trade_id == trade_id)
            ).scalar_one_or_none()

    def get_trades(
        self,
        *,
        ticker: str | None = None,
        market: str | None = None,
        since: str | None = None,
        until: str | None = None,
        linked_rec_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Trade]:
        stmt = select(Trade)
        if ticker:
            stmt = stmt.where(Trade.ticker == ticker)
        if market:
            stmt = stmt.where(Trade.market == market)
        if since:
            stmt = stmt.where(Trade.executed_at >= since)
        if until:
            stmt = stmt.where(Trade.executed_at <= until)
        if linked_rec_id:
            stmt = stmt.where(Trade.linked_rec_id == linked_rec_id)
        stmt = stmt.order_by(Trade.executed_at.desc()).limit(limit).offset(offset)
        with self.session() as s:
            return list(s.execute(stmt).scalars().all())

    def count_trades(self, **kwargs: Any) -> int:
        kwargs.pop("limit", None)
        kwargs.pop("offset", None)
        return len(self.get_trades(limit=1_000_000, **kwargs))

    def get_positions(self, *, open_only: bool = True) -> list[Position]:
        stmt = select(Position)
        if open_only:
            stmt = stmt.where(Position.is_open.is_(True))
        with self.session() as s:
            return list(s.execute(stmt.order_by(Position.ticker)).scalars().all())

    def upsert_position(self, **kwargs: Any) -> Position:
        kwargs.setdefault("updated_at", utc_now_iso())
        with self.session() as s:
            stmt = select(Position).where(
                Position.ticker == kwargs["ticker"],
                Position.market == kwargs["market"],
                Position.account_type == kwargs.get("account_type"),
                Position.opened_at == kwargs["opened_at"],
            )
            row = s.execute(stmt).scalar_one_or_none()
            if row is None:
                row = Position(**kwargs)
                s.add(row)
            else:
                for key, value in kwargs.items():
                    setattr(row, key, value)
            s.flush()
            s.refresh(row)
            return row

    # -- watchlist ------------------------------------------------------------

    def get_watchlist(self, list_name: str | None = None) -> list[WatchlistItem]:
        stmt = select(WatchlistItem)
        if list_name:
            stmt = stmt.where(WatchlistItem.list_name == list_name)
        with self.session() as s:
            return list(
                s.execute(stmt.order_by(WatchlistItem.added_at.desc())).scalars().all()
            )

    def add_to_watchlist(
        self,
        ticker: str,
        market: str,
        *,
        list_name: str = "default",
        note_ja: str | None = None,
    ) -> WatchlistItem:
        with self.session() as s:
            stmt = select(WatchlistItem).where(
                WatchlistItem.ticker == ticker,
                WatchlistItem.market == market,
                WatchlistItem.list_name == list_name,
            )
            row = s.execute(stmt).scalar_one_or_none()
            if row is None:
                row = WatchlistItem(
                    ticker=ticker,
                    market=market,
                    list_name=list_name,
                    note_ja=note_ja,
                    added_at=utc_now_iso(),
                )
                s.add(row)
            elif note_ja is not None:
                row.note_ja = note_ja
            s.flush()
            s.refresh(row)
            return row

    def remove_from_watchlist(
        self, ticker: str, market: str, *, list_name: str = "default"
    ) -> bool:
        with self.session() as s:
            row = s.execute(
                select(WatchlistItem).where(
                    WatchlistItem.ticker == ticker,
                    WatchlistItem.market == market,
                    WatchlistItem.list_name == list_name,
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            s.delete(row)
            return True

    # -- alerts ---------------------------------------------------------------

    def add_alert(
        self,
        *,
        alert_id: str,
        severity: str,
        category: str,
        title_ja: str,
        body_ja: str | None = None,
        entity: str | None = None,
    ) -> Alert:
        with self.session() as s:
            row = Alert(
                alert_id=alert_id,
                severity=severity,
                category=category,
                title_ja=title_ja,
                body_ja=body_ja,
                entity=entity,
                created_at=utc_now_iso(),
            )
            s.add(row)
            s.flush()
            s.refresh(row)
            return row

    def create_alert(
        self,
        *,
        severity: str,
        category: str,
        title_ja: str,
        body_ja: str | None = None,
        entity: str | None = None,
        alert_id: str | None = None,
    ) -> None:
        from ulid import ULID

        self.add_alert(
            alert_id=alert_id or str(ULID()),
            severity=severity,
            category=category,
            title_ja=title_ja,
            body_ja=body_ja,
            entity=entity,
        )

    def get_alerts(
        self, *, unread_only: bool = False, limit: int = 50
    ) -> list[Alert]:
        stmt = select(Alert)
        if unread_only:
            stmt = stmt.where(Alert.is_read.is_(False))
        with self.session() as s:
            return list(
                s.execute(stmt.order_by(Alert.created_at.desc()).limit(limit))
                .scalars()
                .all()
            )

    def mark_alert_read(self, alert_id: str) -> bool:
        with self.session() as s:
            row = s.execute(
                select(Alert).where(Alert.alert_id == alert_id)
            ).scalar_one_or_none()
            if row is None:
                return False
            row.is_read = True
            return True

    def mark_all_alerts_read(self) -> int:
        with self.session() as s:
            rows = list(
                s.execute(select(Alert).where(Alert.is_read.is_(False))).scalars().all()
            )
            for row in rows:
                row.is_read = True
            return len(rows)

    def count_alerts(self, *, unread_only: bool = False) -> int:
        stmt = select(func.count(Alert.id))
        if unread_only:
            stmt = stmt.where(Alert.is_read.is_(False))
        with self.session() as s:
            return int(s.execute(stmt).scalar() or 0)

    # -- agent_memory ---------------------------------------------------------

    def get_agent_memories(
        self,
        *,
        scope: str | None = None,
        scope_value: str | None = None,
        active_only: bool = True,
        min_confidence: float | None = None,
        min_observations: int | None = None,
        limit: int = 100,
    ) -> list[AgentMemory]:
        stmt = select(AgentMemory)
        if scope:
            stmt = stmt.where(AgentMemory.scope == scope)
        if scope_value:
            stmt = stmt.where(AgentMemory.scope_value == scope_value)
        if active_only:
            stmt = stmt.where(AgentMemory.is_active.is_(True))
        if min_confidence is not None:
            stmt = stmt.where(AgentMemory.confidence >= min_confidence)
        if min_observations is not None:
            stmt = stmt.where(AgentMemory.n_observations >= min_observations)
        stmt = stmt.order_by(AgentMemory.confidence.desc()).limit(limit)
        with self.session() as s:
            return list(s.execute(stmt).scalars().all())

    def upsert_agent_memory(self, **kwargs: Any) -> AgentMemory:
        kwargs.setdefault("created_at", utc_now_iso())
        if isinstance(kwargs.get("derived_from"), (list, tuple)):
            kwargs["derived_from"] = _json_dumps(list(kwargs["derived_from"]))
        with self.session() as s:
            row = s.execute(
                select(AgentMemory).where(
                    AgentMemory.memory_id == kwargs["memory_id"]
                )
            ).scalar_one_or_none()
            if row is None:
                row = AgentMemory(**kwargs)
                s.add(row)
            else:
                for key, value in kwargs.items():
                    setattr(row, key, value)
            s.flush()
            s.refresh(row)
            return row

    def get_agent_memory(self, memory_id: str) -> AgentMemory | None:
        with self.session() as s:
            return s.execute(
                select(AgentMemory).where(AgentMemory.memory_id == memory_id)
            ).scalar_one_or_none()

    def delete_agent_memory(self, memory_id: str) -> bool:
        with self.session() as s:
            row = s.execute(
                select(AgentMemory).where(AgentMemory.memory_id == memory_id)
            ).scalar_one_or_none()
            if row is None:
                return False
            s.delete(row)
            return True

    # -- factor_weights -------------------------------------------------------

    def get_active_weight_set(self, market: str, horizon: str) -> FactorWeight | None:
        with self.session() as s:
            return s.execute(
                select(FactorWeight).where(
                    FactorWeight.market == market,
                    FactorWeight.horizon == horizon,
                    FactorWeight.is_active.is_(True),
                )
            ).scalar_one_or_none()

    def get_weight_set(self, weight_set_id: str) -> FactorWeight | None:
        with self.session() as s:
            return s.execute(
                select(FactorWeight).where(FactorWeight.weight_set_id == weight_set_id)
            ).scalar_one_or_none()

    def list_weight_sets(
        self, *, market: str | None = None, horizon: str | None = None
    ) -> list[FactorWeight]:
        stmt = select(FactorWeight)
        if market:
            stmt = stmt.where(FactorWeight.market == market)
        if horizon:
            stmt = stmt.where(FactorWeight.horizon == horizon)
        stmt = stmt.order_by(FactorWeight.created_at.desc())
        with self.session() as s:
            return list(s.execute(stmt).scalars().all())

    def upsert_weight_set(self, **kwargs: Any) -> FactorWeight:
        kwargs.setdefault("created_at", utc_now_iso())
        if isinstance(kwargs.get("weights"), Mapping):
            kwargs["weights"] = _json_dumps(dict(kwargs["weights"]))
        with self.session() as s:
            row = s.execute(
                select(FactorWeight).where(
                    FactorWeight.weight_set_id == kwargs["weight_set_id"]
                )
            ).scalar_one_or_none()
            if row is None:
                row = FactorWeight(**kwargs)
                s.add(row)
            else:
                for key, value in kwargs.items():
                    setattr(row, key, value)
            s.flush()
            s.refresh(row)
            return row

    def activate_weight_set(self, weight_set_id: str) -> bool:
        """`(market, horizon)` ごとに 1 つだけ有効にする（docs/03 §3.3）。"""
        with self.session() as s:
            target = s.execute(
                select(FactorWeight).where(
                    FactorWeight.weight_set_id == weight_set_id
                )
            ).scalar_one_or_none()
            if target is None:
                return False
            others = s.execute(
                select(FactorWeight).where(
                    FactorWeight.market == target.market,
                    FactorWeight.horizon == target.horizon,
                    FactorWeight.is_active.is_(True),
                )
            ).scalars().all()
            for row in others:
                row.is_active = False
                row.deactivated_at = utc_now_iso()
            target.is_active = True
            target.activated_at = utc_now_iso()
            return True

    # -- rate limit / backfill ------------------------------------------------

    def get_rate_limit_state(self, source: str) -> RateLimitState | None:
        with self.session() as s:
            return s.get(RateLimitState, source)

    def load_rate_limit_state(self, source: str) -> RateLimitState | None:
        return self.get_rate_limit_state(source)

    def save_rate_limit_state(
        self, source: str, *, tokens: float, calls_today: int, day_key: str
    ) -> None:
        with self.session() as s:
            row = s.get(RateLimitState, source)
            if row is None:
                s.add(
                    RateLimitState(
                        source=source,
                        tokens=tokens,
                        last_refill_at=utc_now_iso(),
                        calls_today=calls_today,
                        day_key=day_key,
                    )
                )
            else:
                row.tokens = tokens
                row.last_refill_at = utc_now_iso()
                row.calls_today = calls_today
                row.day_key = day_key

    def get_backfill_progress(self, step_name: str) -> BackfillProgress | None:
        with self.session() as s:
            return s.get(BackfillProgress, step_name)

    def save_backfill_progress(
        self,
        step_name: str,
        *,
        status: str,
        cursor_value: str | None = None,
        total_units: int | None = None,
        done_units: int | None = None,
    ) -> None:
        with self.session() as s:
            row = s.get(BackfillProgress, step_name)
            if row is None:
                s.add(
                    BackfillProgress(
                        step_name=step_name,
                        status=status,
                        cursor_value=cursor_value,
                        total_units=total_units,
                        done_units=done_units,
                        updated_at=utc_now_iso(),
                    )
                )
            else:
                row.status = status
                if cursor_value is not None:
                    row.cursor_value = cursor_value
                if total_units is not None:
                    row.total_units = total_units
                if done_units is not None:
                    row.done_units = done_units
                row.updated_at = utc_now_iso()


def _configure_sqlite(engine: Engine) -> None:
    """WAL と外部キーを有効にする（docs/15-windows-runtime.md §5.5）。"""

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn: Any, _record: Any) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()


def _parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def to_dict(row: Any, *, json_fields: Sequence[str] = ()) -> dict[str, Any]:
    """SQLAlchemy モデルを dict にする（JSON 文字列列はデコードする）。"""
    out = {
        c.name: getattr(row, c.name) for c in row.__table__.columns  # type: ignore[union-attr]
    }
    for field in json_fields:
        if field in out:
            out[field] = _json_loads(out[field])
    return out


__all__ = [
    "DEFAULT_SETTINGS",
    "SETTING_TYPES",
    "STALE_JOB_HOURS",
    "AgentMemory",
    "Alert",
    "BackfillProgress",
    "Base",
    "CostBudget",
    "FactorWeight",
    "JobRun",
    "LlmCall",
    "Position",
    "RateLimitState",
    "SQLiteRepo",
    "Setting",
    "Trade",
    "WatchlistItem",
    "to_dict",
    "utc_now_iso",
]
