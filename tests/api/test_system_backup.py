"""POST /api/v1/system/backup は Envelope を返す。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from packages.core.config import Settings
from packages.core.storage import DuckDBRepo, SQLiteRepo
from services.api.main import create_app


def test_system_backup_route_returns_envelope(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", backup_dir=tmp_path / "backups")
    settings.ensure_directories()
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    duck = DuckDBRepo.open(settings)
    duck.init_db()
    sqlite = SQLiteRepo.open(settings)
    sqlite.init_db()
    app = create_app(settings=settings, duck=duck, sqlite=sqlite, payload={})
    with TestClient(app) as client:
        r = client.post("/api/v1/system/backup")
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body.keys()) >= {"data", "warnings", "meta"}
        data = body["data"]
        assert data["ok"] is True
        assert data["job_name"] == "backup"
        assert data["job_run_id"]
        assert data["backup_dir"] == str(settings.backup_dir)
        jobs = client.get("/api/v1/agent/jobs?limit=20")
        backup_jobs = [item for item in jobs.json()["data"]["items"] if item["job_name"] == "backup"]
        assert len(backup_jobs) == 1
        assert backup_jobs[0]["job_run_id"] == data["job_run_id"]
        backups = list(settings.backup_dir.iterdir()) if settings.backup_dir.exists() else []
        assert any(p.is_dir() for p in backups)
    duck.close()
    sqlite.close()
