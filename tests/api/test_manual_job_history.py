"""手動実行の job_runs は1行だけ増える（docs/12-testing-validation.md T-INT-05）。"""

from __future__ import annotations

from fastapi.testclient import TestClient


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
