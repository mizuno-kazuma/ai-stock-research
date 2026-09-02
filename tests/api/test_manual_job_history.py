"""手動実行の job_runs は単体1行、パイプラインは親1行（docs/12-testing-validation.md T-INT-05 / T-INT-06）。"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from services.agent.deps import begin_run, finish_run
from services.agent.types import JobResult, PipelineResult


def test_manual_job_run_creates_one_history_row(client: TestClient, seeded_repos) -> None:
    _, sqlite, _ = seeded_repos
    before = {row.id for row in sqlite.get_job_runs(limit=200)}
    created = client.post("/api/v1/agent/jobs/evaluator/run")
    assert created.status_code == 200, created.text
    run_id = created.json()["data"]["job_run_id"]
    after = [row for row in sqlite.get_job_runs(limit=200) if row.id not in before]
    assert [row.id for row in after] == [run_id]
    listed = client.get("/api/v1/agent/jobs?limit=200")
    assert listed.status_code == 200, listed.text
    new_items = [j for j in listed.json()["data"]["items"] if j["job_run_id"] not in before]
    assert len(new_items) == 1
    assert new_items[0]["job_run_id"] == run_id
    assert new_items[0]["job_name"] == "evaluator"
    assert new_items[0]["trigger"] == "manual"


def test_manual_pipeline_run_creates_parent_and_children(client: TestClient, seeded_repos, monkeypatch) -> None:
    import importlib

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

    monkeypatch.setattr(importlib.import_module("services.agent.pipeline"), "run_pipeline", fake_pipeline)
    _, sqlite, _ = seeded_repos
    before = {row.id for row in sqlite.get_job_runs(limit=200)}
    created = client.post("/api/v1/agent/jobs/pipeline/run?market=JP")
    assert created.status_code == 200, created.text
    run_id = created.json()["data"]["job_run_id"]
    after = [row for row in sqlite.get_job_runs(limit=200) if row.id not in before]
    parents = [row for row in after if row.job_name == "pipeline"]
    children = [row for row in after if row.job_name != "pipeline"]
    assert [row.id for row in parents] == [run_id]
    assert children
    assert all(row.parent_run_id == run_id for row in children)
    listed = client.get("/api/v1/agent/jobs?limit=200")
    new_items = [j for j in listed.json()["data"]["items"] if j["job_run_id"] not in before]
    pipeline_items = [j for j in new_items if j["job_name"] == "pipeline"]
    assert len(pipeline_items) == 1
    assert pipeline_items[0]["job_run_id"] == run_id
    assert pipeline_items[0]["label_ja"] == "パイプライン"

