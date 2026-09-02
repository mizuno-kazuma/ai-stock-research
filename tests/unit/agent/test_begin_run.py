"""手動キックは既存の job_runs 行を再利用する（docs/08-agent-loop.md §9.4）。"""

from __future__ import annotations

from datetime import date

from services.agent.deps import begin_run, finish_run
from services.agent.types import JobResult, PipelineResult
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


def test_kick_pipeline_reuses_parent_and_keeps_children(monkeypatch) -> None:
    """手動パイプラインは親1行を再利用し、子ジョブは parent_run_id で残す。"""
    import importlib
    from datetime import UTC, datetime

    from packages.core.config import Settings
    from packages.core.storage import DuckDBRepo, SQLiteRepo
    from services.api.deps import AppState
    from services.api.events import EventBus
    from services.api.runtime import kick_agent_job

    def fake_pipeline(market: str, as_of: date, **kwargs) -> PipelineResult:
        rid = begin_run(
            kwargs["state"],
            job_name="pipeline",
            market=market,
            trigger=kwargs.get("trigger", "manual"),
            run_id=kwargs.get("run_id"),
        )
        child = begin_run(
            kwargs["state"],
            job_name="collector",
            market=market,
            trigger=kwargs.get("trigger", "manual"),
            parent_run_id=rid,
        )
        finish_run(kwargs["state"], child, status="success")
        finish_run(kwargs["state"], rid, status="success", metrics={"jobs": {"collector": "success"}})
        return PipelineResult(
            status="success",
            market=market,
            as_of=as_of,
            run_id=rid,
            jobs={
                "collector": JobResult(
                    job_name="collector",
                    status="success",
                    market=market,
                    as_of=as_of,
                    run_id=child,
                )
            },
            metrics={"jobs": {"collector": "success"}},
        )

    pipeline_mod = importlib.import_module("services.agent.pipeline")
    monkeypatch.setattr(pipeline_mod, "run_pipeline", fake_pipeline)

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
    run_id = sqlite.start_job_run("pipeline", trigger="manual", market="JP")
    kick_agent_job(app_state, job_name="pipeline", run_id=run_id, market="JP")
    parents = [row for row in sqlite.get_job_runs(limit=20) if row.job_name == "pipeline"]
    children = [row for row in sqlite.get_job_runs(limit=20) if row.job_name != "pipeline"]
    assert [row.id for row in parents] == [run_id]
    assert parents[0].status == "success"
    assert len(children) == 1
    assert children[0].parent_run_id == run_id
    duck.close()
    sqlite.close()
