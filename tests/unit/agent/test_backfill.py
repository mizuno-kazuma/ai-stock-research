"""初回バックフィルの中断・再開。"""

from __future__ import annotations

from datetime import date

from services.agent.jobs.backfill import BACKFILL_STEPS, backfill
from tests.fakes import FakeStateRepo, FakeWarehouse


def test_backfill_runs_all_steps_and_marks_done() -> None:
    state = FakeStateRepo()
    calls: list[tuple[str, str]] = []

    def _step(market: str, as_of: date) -> dict:
        calls.append((market, as_of.isoformat()))
        return {"rows": 1}

    steps = {name: _step for _, name in BACKFILL_STEPS}
    result = backfill(
        "JP",
        date(2026, 8, 28),
        state=state,
        warehouse=FakeWarehouse(),
        steps=steps,
    )
    assert result.status == "success"
    assert state.get_backfill_progress("JP.securities_master")["status"] == "done"
    assert state.get_backfill_progress("US.prices")["status"] == "done"


def test_backfill_resumes_from_done_steps() -> None:
    state = FakeStateRepo()
    state.save_backfill_progress("JP.securities_master", status="done")
    state.save_backfill_progress("JP.macro", status="done")
    seen: list[str] = []

    def _step(market: str, as_of: date) -> dict:
        seen.append(f"{market}.prices" if False else market)
        return {"rows": 1}

    # 呼ばれたステップ名を記録するため、ステップごとに関数を分ける
    named: dict = {}
    for _mkt, name in BACKFILL_STEPS:
        def _fn(market: str, as_of: date, step=name) -> dict:
            seen.append(f"{market}.{step}")
            return {"rows": 1}

        named[name] = _fn

    result = backfill(
        "JP",
        date(2026, 8, 28),
        state=state,
        warehouse=FakeWarehouse(),
        steps=named,
    )
    assert result.status == "success"
    assert "JP.securities_master" not in seen
    assert "JP.macro" not in seen
    assert any(item.endswith(".prices") for item in seen)


def test_backfill_stops_on_failure_and_can_retry() -> None:
    state = FakeStateRepo()

    def boom(market: str, as_of: date) -> dict:
        raise RuntimeError("rate limited")

    steps = {name: boom for _, name in BACKFILL_STEPS}
    failed = backfill(
        "JP",
        date(2026, 8, 28),
        state=state,
        warehouse=FakeWarehouse(),
        steps=steps,
    )
    assert failed.status == "failed"
    assert state.get_backfill_progress("JP.securities_master")["status"] == "failed"

    recovered = {"n": 0}

    def ok(market: str, as_of: date) -> dict:
        recovered["n"] += 1
        return {"rows": 2}

    retry_steps = {name: ok for _, name in BACKFILL_STEPS}
    # 失敗したステップは done ではないので再実行される
    again = backfill(
        "JP",
        date(2026, 8, 28),
        state=state,
        warehouse=FakeWarehouse(),
        steps=retry_steps,
    )
    assert again.status == "success"
    assert recovered["n"] > 0
