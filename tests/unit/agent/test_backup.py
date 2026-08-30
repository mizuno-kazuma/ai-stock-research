"""バックアップジョブ（docs/11-security-ops.md §4）。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from packages.core.config import Settings
from packages.core.storage import DuckDBRepo, SQLiteRepo
from services.agent.jobs.backup import (
    BackupRefusedError,
    backup_sqlite,
    copy_live_sqlite,
    daily_backup,
    prune_old_backups,
)
from tests.fakes import FakeStateRepo

JST = ZoneInfo("Asia/Tokyo")


def _settings(tmp_path: Path) -> Settings:
    data = tmp_path / "data"
    backups = tmp_path / "backups"
    settings = Settings(data_dir=data, backup_dir=backups)
    settings.ensure_directories()
    backups.mkdir(parents=True, exist_ok=True)
    return settings


def test_backup_creates_files_and_uses_sqlite_backup_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    with SQLiteRepo.open(settings) as state:
        state.init_db()
        state.set_setting("ui.theme", "dark")
    duck = DuckDBRepo.open(settings)
    duck.init_db()
    duck.upsert_prices_daily(
        [
            {
                "ticker": "7203",
                "market": "JP",
                "trade_date": "2026-08-28",
                "close": 3000.0,
                "currency": "JPY",
                "source": "jquants",
            }
        ]
    )
    (settings.raw_dir / "jquants").mkdir(parents=True, exist_ok=True)
    (settings.raw_dir / "jquants" / "sample.json").write_text("{}", encoding="utf-8")

    called: list[tuple[Path, Path]] = []
    original = backup_sqlite

    def _wrapped(src: Path, dest: Path) -> None:
        called.append((src, dest))
        return original(src, dest)

    monkeypatch.setattr("services.agent.jobs.backup.backup_sqlite", _wrapped)

    fake = FakeStateRepo()
    result = daily_backup(
        "JP",
        as_of=datetime(2026, 8, 30, tzinfo=JST).date(),
        state=fake,
        warehouse=duck,
        settings=settings,
        backup_dir=settings.backup_dir,
        now=datetime(2026, 8, 30, 3, 0, tzinfo=JST),
        trigger="manual",
    )
    duck.close()
    assert result.status == "success"
    dest = Path(result.metrics["path"])
    assert dest.is_dir()
    assert (dest / "state.sqlite").is_file()
    assert (dest / "warehouse").is_dir()
    assert any((dest / "warehouse").rglob("*"))
    assert (dest / "raw" / "jquants" / "sample.json").is_file()
    assert len(called) == 1
    assert called[0][1].name == "state.sqlite"
    with sqlite3.connect(dest / "state.sqlite") as con:
        row = con.execute("SELECT value FROM settings WHERE key = 'ui.theme'").fetchone()
        assert row is not None


def test_naive_cp_of_live_sqlite_is_refused(tmp_path: Path) -> None:
    src = tmp_path / "state.sqlite"
    dest = tmp_path / "copied.sqlite"
    with sqlite3.connect(src) as con:
        con.execute("CREATE TABLE t (id INTEGER)")
        con.execute("INSERT INTO t VALUES (1)")
    with pytest.raises(BackupRefusedError, match="backup API"):
        copy_live_sqlite(src, dest, method="cp")
    assert not dest.exists()
    backup_sqlite(src, dest)
    assert dest.is_file()


def test_prune_keeps_daily_weekly_monthly_policy(tmp_path: Path) -> None:
    root = tmp_path / "backups"
    root.mkdir()
    stamps: list[str] = []
    current = datetime(2026, 5, 3, 3, 0, tzinfo=JST)  # Sunday
    end = datetime(2026, 8, 30, 3, 0, tzinfo=JST)
    while current <= end:
        name = current.strftime("%Y%m%d_%H%M%S")
        (root / name).mkdir()
        (root / name / "marker.txt").write_text(name, encoding="utf-8")
        stamps.append(name)
        current = current + timedelta(days=1)

    removed = prune_old_backups(root, keep_daily=7, keep_weekly=4, keep_monthly=6)
    remaining = sorted(p.name for p in root.iterdir() if p.is_dir())
    last7 = stamps[-7:]
    assert set(last7) <= set(remaining)
    sundays = [s for s in stamps if datetime.strptime(s, "%Y%m%d_%H%M%S").weekday() == 6]
    assert set(sundays[-4:]) <= set(remaining)
    by_month: dict[str, str] = {}
    for name in stamps:
        by_month[name[:6]] = name
    monthly = [by_month[k] for k in sorted(by_month)[-6:]]
    assert set(monthly) <= set(remaining)
    assert removed
    assert set(remaining).isdisjoint(removed)
