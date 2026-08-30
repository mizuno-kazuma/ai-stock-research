"""パイプラインとチェックポイントが job_progress を出すこと。"""

from __future__ import annotations

from datetime import date

from services.agent.checkpoint import with_checkpoint
from services.agent.pipeline import run_pipeline
from services.agent.progress import publish_job_progress, set_shared_bus
from tests.fakes import FakeStateRepo, FakeWarehouse


class _Bus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def publish_nowait(self, event: str, data: dict) -> None:
        self.events.append((event, data))


def test_publish_job_progress_is_noop_without_bus() -> None:
    set_shared_bus(None)
    publish_job_progress(
        job_run_id=1, job_name="pipeline", phase="collector", completed=1, total=6
    )


def test_with_checkpoint_publishes_progress() -> None:
    bus = _Bus()
    set_shared_bus(bus)
    state = FakeStateRepo()
    run_id = state.create_job_run(job_name="researcher", market="JP")
    with_checkpoint(
        state,
        run_id,
        job_name="researcher",
        phase="researcher",
        units=["7203", "6758"],
        fn=lambda _u: None,
    )
    set_shared_bus(None)
    progress = [e for e in bus.events if e[0] == "job_progress"]
    assert len(progress) == 2
    assert progress[-1][1]["completed"] == 2
    assert progress[-1][1]["total"] == 2
    cp = state.load_checkpoint(run_id)
    assert cp is not None
    assert cp["completed"] == 2
    assert cp["total"] == 2


def test_pipeline_publishes_phase_progress() -> None:
    bus = _Bus()
    set_shared_bus(bus)
    warehouse = FakeWarehouse()
    try:
        run_pipeline(
            "JP",
            date(2026, 8, 21),
            state=FakeStateRepo(),
            warehouse=warehouse,
            collector_steps={
                "prices": lambda _m, _d: {"rows": 0, "skipped": True},
            },
        )
    except Exception:
        pass
    set_shared_bus(None)
    names = [e[0] for e in bus.events]
    assert "job_progress" in names
    assert "job_finished" in names
    phases = [e[1].get("phase") for e in bus.events if e[0] == "job_progress"]
    assert "collector" in phases
