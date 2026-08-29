"""パイプラインの誤中断と実行時間短縮。"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

from packages.core.storage import SQLiteRepo
from services.agent.jobs.collector import coverage_lookback_days
from services.agent.main import _is_process_alive, _resume_interrupted_jobs
from tests.fakes import FakeStateRepo


def test_coverage_lookback_shrinks_when_warehouse_is_current() -> None:
    end = date(2026, 8, 28)
    latest = date(2026, 8, 27)
    days = coverage_lookback_days(90, latest=latest, end=end, overlap_days=5)
    assert days == 6


def test_coverage_lookback_keeps_full_window_when_empty() -> None:
    assert coverage_lookback_days(90, latest=None, end=date(2026, 8, 28)) == 90


def test_live_pid_is_not_interrupted() -> None:
    state = FakeStateRepo()
    run_id = state.create_job_run(job_name="collector", market="JP")
    state._runs[run_id].started_at = datetime.now(UTC) - timedelta(hours=3)
    state._runs[run_id].pid = os.getpid()
    interrupted = _resume_interrupted_jobs(state)
    assert interrupted == []
    assert state.get_job_run(run_id).status == "running"


def test_dead_pid_is_interrupted_without_zombie_resume() -> None:
    state = FakeStateRepo()
    run_id = state.create_job_run(job_name="collector", market="JP")
    state._runs[run_id].started_at = datetime.now(UTC) - timedelta(hours=3)
    state._runs[run_id].pid = 999_999
    with patch("services.agent.main.os.kill", side_effect=ProcessLookupError):
        interrupted = _resume_interrupted_jobs(state)
    assert interrupted == [run_id]
    assert state.get_job_run(run_id).status == "interrupted"
    assert len(state._runs) == 1


def test_missing_pid_is_treated_as_alive() -> None:
    assert _is_process_alive(None) is True
    assert _is_process_alive(os.getpid()) is True


def test_start_job_run_records_pid() -> None:
    state = SQLiteRepo.in_memory()
    run_id = state.start_job_run("collector", market="JP")
    row = state.get_job_run(run_id)
    assert row is not None
    assert row.pid == os.getpid()


def test_mark_interrupted_jobs_on_startup_clears_all_running() -> None:
    state = SQLiteRepo.in_memory()
    run_id = state.start_job_run("pipeline", market="JP")
    ids = state.mark_interrupted_jobs(hours=0)
    assert run_id in ids
    assert state.get_job_run(run_id).status == "interrupted"


def test_select_memory_filters_by_scope() -> None:
    state = SQLiteRepo.in_memory()
    state.upsert_agent_memory(
        memory_id="M1",
        scope="global",
        category="pattern",
        lesson_ja="全体の教訓です。",
        evidence_ja="検証",
        derived_from=["r1"],
        n_observations=20,
        confidence=0.8,
    )
    state.upsert_agent_memory(
        memory_id="M2",
        scope="market",
        scope_value="US",
        category="caveat",
        lesson_ja="米国向け。",
        evidence_ja="検証",
        derived_from=["r2"],
        n_observations=20,
        confidence=0.8,
    )
    picked = state.select_memory(market="JP", sector="S01", ticker="7203")
    ids = {m.memory_id for m in picked}
    assert "M1" in ids
    assert "M2" not in ids


def test_latest_coverage_date_reads_max_trade_date() -> None:
    from packages.core.storage import DuckDBRepo

    duck = DuckDBRepo.in_memory()
    duck.upsert_prices_daily(
        [
            {
                "ticker": "7203",
                "market": "JP",
                "trade_date": date(2026, 8, 26),
                "close": 1.0,
                "adj_close": 1.0,
                "currency": "JPY",
                "source": "jquants",
            },
            {
                "ticker": "7203",
                "market": "JP",
                "trade_date": date(2026, 8, 27),
                "close": 1.1,
                "adj_close": 1.1,
                "currency": "JPY",
                "source": "jquants",
            },
        ]
    )
    assert duck.latest_coverage_date("prices_daily", market="JP") == date(2026, 8, 27)
