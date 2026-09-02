"""日次バックアップ（docs/11-security-ops.md §4）。

SQLite は backup API（cp 禁止）。DuckDB は EXPORT DATABASE。
Raw と config はコピー。保持は日次7 / 週次4 / 月次6。
"""

from __future__ import annotations

import logging
import re
import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from packages.core.config import Settings, get_settings
from packages.core.interfaces.storage import JobRunRepo, WarehouseRepo
from services.agent.deps import begin_run, finish_run
from services.agent.types import JobResult, StepResult

logger = logging.getLogger(__name__)

JST = ZoneInfo("Asia/Tokyo")
KEEP_DAILY = 7
KEEP_WEEKLY = 4
KEEP_MONTHLY = 6
_BACKUP_NAME = re.compile(r"^(\d{8})_(\d{6})$")
REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "packages" / "core" / "config"


class BackupRefusedError(ValueError):
    """ライブ SQLite を素のコピーで取ろうとしたときの拒否。"""


def parse_backup_stamp(name: str) -> datetime | None:
    match = _BACKUP_NAME.match(name)
    if match is None:
        return None
    return datetime.strptime(f"{match.group(1)}_{match.group(2)}", "%Y%m%d_%H%M%S").replace(
        tzinfo=JST
    )


def backup_sqlite(src: Path, dest: Path) -> None:
    """sqlite3 の backup API だけを使う。`cp` / shutil.copy2 は使わない。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(src)) as source, sqlite3.connect(str(dest)) as target:
        source.backup(target)


def copy_live_sqlite(src: Path, dest: Path, *, method: str = "backup_api") -> None:
    """ライブ SQLite の複製。`cp` / shutil は明示的に拒否する。"""
    if method in {"cp", "copy", "shutil", "shutil.copy2"}:
        raise BackupRefusedError(
            "ライブ SQLite の素のコピー（cp / shutil.copy2）は WAL を壊す可能性がある。"
            "sqlite3 の backup API を使うこと（docs/11-security-ops.md §4.2）。"
        )
    backup_sqlite(src, dest)


def export_duckdb(warehouse: Any, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    sql = f"EXPORT DATABASE '{dest_dir.as_posix()}' (FORMAT PARQUET)"
    execute = getattr(warehouse, "execute", None)
    if callable(execute):
        execute(sql)
        return
    path = getattr(warehouse, "path", None)
    if path is None or str(path) in {":memory:", "memory"}:
        return
    import duckdb

    with duckdb.connect(str(path), read_only=True) as con:
        con.execute(sql)


def copy_tree(src: Path, dest: Path) -> int:
    if not src.exists():
        dest.mkdir(parents=True, exist_ok=True)
        return 0
    shutil.copytree(src, dest, dirs_exist_ok=True)
    return sum(1 for p in dest.rglob("*") if p.is_file())


def dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def prune_old_backups(
    backup_root: Path,
    *,
    keep_daily: int = KEEP_DAILY,
    keep_weekly: int = KEEP_WEEKLY,
    keep_monthly: int = KEEP_MONTHLY,
) -> list[str]:
    """保持ポリシー外の世代を削除する。返り値は削除したディレクトリ名。"""
    stamped: list[tuple[datetime, Path]] = []
    if not backup_root.exists():
        return []
    for child in backup_root.iterdir():
        if not child.is_dir():
            continue
        stamp = parse_backup_stamp(child.name)
        if stamp is None:
            continue
        stamped.append((stamp, child))
    stamped.sort(key=lambda item: item[0])
    keep: set[Path] = set()
    keep.update(path for _ts, path in stamped[-keep_daily:])
    sundays = [(ts, path) for ts, path in stamped if ts.weekday() == 6]
    keep.update(path for _ts, path in sundays[-keep_weekly:])
    by_month: dict[str, Path] = {}
    for ts, path in stamped:
        by_month[ts.strftime("%Y-%m")] = path
    for key in sorted(by_month)[-keep_monthly:]:
        keep.add(by_month[key])
    removed: list[str] = []
    for _ts, path in stamped:
        if path in keep:
            continue
        shutil.rmtree(path)
        removed.append(path.name)
    return removed


def daily_backup(
    market: str = "JP",
    as_of: date | None = None,
    *,
    state: JobRunRepo | None = None,
    warehouse: WarehouseRepo | None = None,
    trigger: str = "schedule",
    parent_run_id: int | None = None,
    run_id: int | None = None,
    settings: Settings | None = None,
    backup_dir: Path | None = None,
    now: datetime | None = None,
) -> JobResult:
    cfg = settings or get_settings()
    day = as_of or (now.date() if now is not None else datetime.now(JST).date())
    if state is not None:
        run_id = begin_run(
            state,
            job_name="backup",
            market=market,
            trigger=trigger,
            parent_run_id=parent_run_id,
            run_id=run_id,
        )
    else:
        run_id = None
    steps: dict[str, StepResult] = {}
    stamp = (now or datetime.now(JST)).strftime("%Y%m%d_%H%M%S")
    root = Path(backup_dir or cfg.backup_dir or (cfg.data_dir.parent / "backups"))
    dest = root / stamp
    dest.mkdir(parents=True, exist_ok=True)
    try:
        sqlite_src = Path(cfg.state_db_path)
        sqlite_dest = dest / "state.sqlite"
        if sqlite_src.exists():
            copy_live_sqlite(sqlite_src, sqlite_dest, method="backup_api")
            steps["sqlite"] = StepResult(status="success", metrics={"path": str(sqlite_dest)})
        else:
            steps["sqlite"] = StepResult(status="skipped", error="state.sqlite がありません")

        warehouse_dest = dest / "warehouse"
        if warehouse is not None:
            export_duckdb(warehouse, warehouse_dest)
            steps["duckdb"] = StepResult(status="success", metrics={"path": str(warehouse_dest)})
        elif Path(cfg.duckdb_path).exists():
            import duckdb

            warehouse_dest.mkdir(parents=True, exist_ok=True)
            with duckdb.connect(str(cfg.duckdb_path), read_only=True) as con:
                con.execute(f"EXPORT DATABASE '{warehouse_dest.as_posix()}' (FORMAT PARQUET)")
            steps["duckdb"] = StepResult(status="success", metrics={"path": str(warehouse_dest)})
        else:
            steps["duckdb"] = StepResult(status="skipped", error="DuckDB がありません")

        raw_n = copy_tree(Path(cfg.raw_dir), dest / "raw")
        steps["raw"] = StepResult(status="success", metrics={"files": raw_n})
        cfg_n = copy_tree(CONFIG_DIR, dest / "config")
        steps["config"] = StepResult(status="success", metrics={"files": cfg_n})

        removed = prune_old_backups(root)
        size = dir_size_bytes(dest)
        metrics: dict[str, Any] = {
            "path": str(dest),
            "size_bytes": size,
            "stamp": stamp,
            "pruned": removed,
            "keep_daily": KEEP_DAILY,
            "keep_weekly": KEEP_WEEKLY,
            "keep_monthly": KEEP_MONTHLY,
        }
        status = "success"
        if steps["sqlite"].status == "skipped" and steps["duckdb"].status == "skipped":
            status = "partial"
        if state is not None and run_id is not None:
            finish_run(state, run_id, status=status, metrics=metrics)
        return JobResult(
            job_name="backup",
            status=status,
            market=market,
            as_of=day,
            run_id=run_id,
            steps=steps,
            metrics=metrics,
        )
    except Exception as exc:
        logger.exception("バックアップに失敗しました")
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        if state is not None and run_id is not None:
            finish_run(state, run_id, status="failed", metrics={"path": str(dest)}, error=exc)
        return JobResult(
            job_name="backup",
            status="failed",
            market=market,
            as_of=day,
            run_id=run_id,
            steps=steps,
            metrics={"path": str(dest)},
            error=f"{type(exc).__name__}: {exc}",
        )
