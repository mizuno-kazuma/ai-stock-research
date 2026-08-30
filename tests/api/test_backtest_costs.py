"""T-API-03: バックテスト API はコスト引数を必須にする。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_backtest_api_rejects_missing_cost_params(client: TestClient) -> None:
    r = client.post(
        "/api/v1/backtests",
        json={
            "strategy_name": "test",
            "market": "JP",
            "period_start": "2024-08-01",
            "period_end": "2026-08-01",
            "rebalance_freq": "monthly",
            "n_positions": 20,
        },
    )
    assert r.status_code == 422
    assert "fee_bps" in r.text


def test_backtest_api_rejects_missing_n_trials(client: TestClient) -> None:
    r = client.post(
        "/api/v1/backtests",
        json={
            "strategy_name": "test",
            "market": "JP",
            "period_start": "2024-08-01",
            "period_end": "2026-08-01",
            "rebalance_freq": "monthly",
            "n_positions": 20,
            "fee_bps": 5.0,
            "slippage_bps": 10.0,
            "max_turnover_pct": 30.0,
        },
    )
    assert r.status_code == 422
    assert "n_trials" in r.text


def test_backtest_api_accepts_complete_request(client: TestClient) -> None:
    r = client.post(
        "/api/v1/backtests",
        json={
            "strategy_name": "value_quality_h20",
            "market": "JP",
            "period_start": "2024-08-01",
            "period_end": "2026-08-01",
            "rebalance_freq": "monthly",
            "n_positions": 20,
            "fee_bps": 5.0,
            "slippage_bps": 10.0,
            "max_turnover_pct": 30.0,
            "n_trials": 1,
        },
    )
    assert r.status_code == 202
    body = r.json()
    assert body["data"]["job_run_id"]
    assert "meta" in body
