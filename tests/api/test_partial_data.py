"""T-API-04: 部分データは 200 + warnings[]。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_partial_data_returns_200_with_warnings(client: TestClient) -> None:
    r = client.get("/api/v1/dashboard?market=JP")
    assert r.status_code == 200
    body = r.json()
    codes = {w["code"] for w in body["warnings"]}
    assert "SECTION_UNAVAILABLE" in codes or "SOURCE_DISABLED" in codes or "SEED_DATA" in codes
    assert "data_freshness" in body["meta"]
    assert any(w["code"] == "SECTION_UNAVAILABLE" for w in body["warnings"])


def test_health_is_not_envelope(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "app_version" in body
