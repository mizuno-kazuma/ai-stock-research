"""analyst / strategist が毎回失敗していた経路と、失敗理由の API 露出。"""

from __future__ import annotations

from datetime import UTC, date, datetime

from packages.core.storage import DuckDBRepo, SQLiteRepo
from services.agent.deps import require_not_failed
from services.agent.main import _adapt_state
from services.api.mapping import job_from_row
from services.api.runtime import _payload_from_result
from services.agent.types import JobResult, StepResult


def test_latest_job_run_does_not_require_started_at_to_match_as_of() -> None:
    """JST 早朝は started_at(UTC) の日付と as_of がずれる。前段を見失ってはいけない。"""
    state = SQLiteRepo.in_memory()
    state.init_db()
    run_id = state.start_job_run("collector", trigger="manual", market="JP")
    state.update_job_run(run_id, status="success", finished=True)
    found = state.latest_job_run("collector", market="JP", on_date=date(2020, 1, 1))
    assert found is not None
    assert found.id == run_id


def test_require_not_failed_finds_collector_across_date_mismatch() -> None:
    sqlite = SQLiteRepo.in_memory()
    sqlite.init_db()
    run_id = sqlite.start_job_run("collector", trigger="manual", market="JP")
    sqlite.update_job_run(run_id, status="success", finished=True)
    adapted = _adapt_state(sqlite)
    run = require_not_failed(
        adapted, job_name="collector", market="JP", on_date=date(2026, 8, 28), required=True
    )
    assert run is not None


def test_job_from_row_exposes_error_and_failed_steps() -> None:
    state = SQLiteRepo.in_memory()
    state.init_db()
    run_id = state.start_job_run("analyst", trigger="manual", market="JP")
    state.update_job_run(
        run_id,
        status="failed",
        finished=True,
        error_type="UpstreamFailed",
        error_message="collector がまだ実行されていません",
        metrics={"failed_steps": ["scores"], "step_errors": {"scores": "特徴量が空"}},
    )
    job = job_from_row(state.get_job_run(run_id))
    assert job.error_message == "collector がまだ実行されていません"
    assert job.failed_steps == ["scores"]
    assert job.output_summary_ja == "collector がまだ実行されていません"
    assert job.label_ja == "分析"


def test_job_from_row_maps_no_scores_reason() -> None:
    state = SQLiteRepo.in_memory()
    state.init_db()
    run_id = state.start_job_run("strategist", trigger="manual", market="JP")
    state.update_job_run(
        run_id,
        status="failed",
        finished=True,
        metrics={"reason": "no_scores"},
    )
    job = job_from_row(state.get_job_run(run_id))
    assert job.error_message == "スコアがありません。先に分析ジョブを成功させてください。"
    assert job.output_summary_ja == job.error_message
    assert job.label_ja == "推奨生成"


def test_payload_from_result_copies_step_errors() -> None:
    result = JobResult(
        job_name="analyst",
        status="failed",
        market="JP",
        as_of=date(2026, 8, 27),
        run_id=9,
        error="特徴量が空",
        steps={"scores": StepResult(status="failed", error="特徴量が空")},
        metrics={"n_features": 0},
    )
    status, metrics, error_type, error_message, failed_steps = _payload_from_result(result)
    assert status == "failed"
    assert failed_steps == ["scores"]
    assert error_message == "特徴量が空"
    assert error_type == "JobFailed"
    assert metrics["failed_steps"] == ["scores"]
    assert metrics["inner_run_id"] == 9


def test_payload_from_pipeline_result_uses_child_job_failures() -> None:
    from services.agent.types import PipelineResult

    result = PipelineResult(
        status="failed",
        market="JP",
        as_of=date(2026, 8, 27),
        run_id=3,
        jobs={
            "collector": JobResult(
                job_name="collector",
                status="failed",
                market="JP",
                as_of=date(2026, 8, 27),
                error="prices failed",
            )
        },
        metrics={"failed_at": "collector"},
    )
    status, metrics, error_type, error_message, failed_steps = _payload_from_result(result)
    assert status == "failed"
    assert failed_steps == ["collector"]
    assert metrics["failed_steps"] == ["collector"]
    assert error_type == "JobFailed"
    assert error_message == "collector: prices failed"


def test_upsert_features_accepts_tzaware_computed_at() -> None:
    duck = DuckDBRepo.in_memory()
    duck.init_db()
    n = duck.upsert_features_daily(
        [
            {
                "ticker": "7203",
                "market": "JP",
                "as_of": date(2026, 8, 27),
                "currency": "JPY",
                "feature_version": "v1.0.0",
                "computed_at": datetime.now(UTC),
                "n_missing": 0,
            }
        ]
    )
    assert n == 1


def test_upsert_scores_fills_feature_version() -> None:
    duck = DuckDBRepo.in_memory()
    duck.init_db()
    n = duck.upsert_scores_daily(
        [
            {
                "ticker": "7203",
                "market": "JP",
                "as_of": date(2026, 8, 27),
                "weight_set_id": "default",
            }
        ]
    )
    assert n == 1
