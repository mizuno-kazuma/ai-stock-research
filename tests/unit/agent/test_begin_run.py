"""手動キックは既存の job_runs 行を再利用する（docs/08-agent-loop.md §9.4）。"""

from __future__ import annotations

from datetime import date

from services.agent.deps import begin_run
from services.agent.types import JobResult
from tests.fakes import FakeStateRepo


def test_begin_run_reuses_existing_run_id() -> None:
    state = FakeStateRepo()
    existing = state.create_job_run(job_name="collector", market="JP", trigger="manual")
    reused = begin_run(
        state,
        job_name="collector",
        market="JP",
        trigger="manual",
        run_id=existing,
    )
    assert reused == existing
    assert len(state._runs) == 1


def test_begin_run_creates_child_under_pipeline_parent() -> None:
    state = FakeStateRepo()
    parent = state.create_job_run(job_name="pipeline", market="JP")
    child = begin_run(
        state, job_name="collector", market="JP", parent_run_id=parent
    )
    assert child != parent
    assert len(state._runs) == 2
    assert state.get_job_run(child).parent_run_id == parent


def test_kick_agent_job_does_not_duplicate_history(monkeypatch) -> None:
    """API が作った行を parent にすると collector がもう1行作ってしまう。"""
    import importlib
    from datetime import UTC, datetime

    from packages.core.config import Settings
    from packages.core.storage import DuckDBRepo, SQLiteRepo
    from services.api.deps import AppState
    from services.api.events import EventBus
    from services.api.runtime import kick_agent_job

    def fake_collector(market: str, as_of: date, **kwargs) -> JobResult:
        rid = begin_run(
            kwargs["state"],
            job_name="collector",
            market=market,
            trigger=kwargs.get("trigger", "manual"),
            parent_run_id=kwargs.get("parent_run_id"),
            run_id=kwargs.get("run_id"),
        )
        return JobResult(
            job_name="collector",
            status="success",
            market=market,
            as_of=as_of,
            run_id=rid,
        )

    collector_mod = importlib.import_module("services.agent.jobs.collector")
    monkeypatch.setattr(collector_mod, "collector", fake_collector)

    sqlite = SQLiteRepo.in_memory()
    sqlite.init_db()
    duck = DuckDBRepo.in_memory()
    duck.init_db()
    app_state = AppState(
        settings=Settings(),
        duck=duck,
        sqlite=sqlite,
        bus=EventBus(),
        started_at=datetime.now(UTC),
    )
    run_id = sqlite.start_job_run("collector_jp", trigger="manual", market="JP")
    kick_agent_job(app_state, job_name="collector_jp", run_id=run_id, market="JP")
    rows = sqlite.get_job_runs(limit=20)
    assert [row.id for row in rows] == [run_id]
    assert rows[0].status == "success"
    duck.close()
    sqlite.close()
