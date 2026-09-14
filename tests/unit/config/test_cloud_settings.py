from __future__ import annotations

import pytest
from pydantic import ValidationError

from packages.core.config.settings import Settings, reset_settings_cache


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_sync_database_url_normalizes_postgres() -> None:
    s = Settings(
        data_dir="/tmp/ai-stock-test-cloud",
        database_url="postgresql://user:pass@host/db",
        auth_mode="token",
        api_token="secret",
    )
    assert s.sync_database_url.startswith("postgresql+psycopg://")
    assert s.uses_postgres is True
    assert s.scheduler_database_url.startswith("postgresql+psycopg://")


def test_cloud_profile_rejects_auth_none() -> None:
    with pytest.raises(ValidationError, match="AUTH_MODE=none"):
        Settings(data_dir="/tmp/ai-stock-test-cloud", deployment_profile="cloud", auth_mode="none")


def test_token_mode_requires_api_token() -> None:
    with pytest.raises(ValidationError, match="API_TOKEN"):
        Settings(data_dir="/tmp/ai-stock-test-cloud", auth_mode="token")


def test_sqlite_url_alias_follows_sync_url() -> None:
    s = Settings(
        data_dir="/tmp/ai-stock-test-cloud",
        database_url="postgres://user:pass@host/db",
        auth_mode="token",
        api_token="secret",
    )
    assert s.sqlite_url == s.sync_database_url
