"""Phase B の Bearer トークン認証。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from packages.core.config.settings import Settings, reset_settings_cache
from packages.core.storage import DuckDBRepo, SQLiteRepo
from services.api.main import create_app


def _client(tmp_path: Path, **overrides) -> tuple[TestClient, DuckDBRepo, SQLiteRepo]:
    reset_settings_cache()
    settings = Settings(
        data_dir=tmp_path / "data",
        auth_mode="token",
        api_token="test-token",
        **overrides,
    )
    settings.ensure_directories()
    duck = DuckDBRepo.open(settings)
    duck.init_db()
    sqlite = SQLiteRepo.open(settings)
    sqlite.init_db()
    app = create_app(settings=settings, duck=duck, sqlite=sqlite, payload={})
    return TestClient(app), duck, sqlite


def test_token_auth_rejects_missing_bearer(tmp_path: Path) -> None:
    client, duck, sqlite = _client(tmp_path)
    try:
        res = client.get("/api/v1/health")
        assert res.status_code == 401
    finally:
        duck.close()
        sqlite.close()


def test_token_auth_accepts_bearer(tmp_path: Path) -> None:
    client, duck, sqlite = _client(tmp_path)
    try:
        res = client.get("/api/v1/health", headers={"Authorization": "Bearer test-token"})
        assert res.status_code == 200
    finally:
        duck.close()
        sqlite.close()


def test_token_auth_accepts_access_token_query(tmp_path: Path) -> None:
    client, duck, sqlite = _client(tmp_path)
    try:
        res = client.get("/api/v1/health?access_token=test-token")
        assert res.status_code == 200
    finally:
        duck.close()
        sqlite.close()


def test_liveness_bypasses_auth(tmp_path: Path) -> None:
    client, duck, sqlite = _client(tmp_path)
    try:
        res = client.get("/health")
        assert res.status_code == 200
    finally:
        duck.close()
        sqlite.close()
