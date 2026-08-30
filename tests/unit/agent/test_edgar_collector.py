"""Collector の米国経路に EDGAR を配線する（F04）。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from packages.core.connectors.base import RawBatch, tag_table
from services.agent.jobs.collector import builtin_connector_steps, collector
from tests.fakes import FakeStateRepo, FakeWarehouse


class _FakeEdgar:
    delay_weeks = 0
    fetches: list[dict] = []
    normalized: list[RawBatch] = []
    upserted: list[pd.DataFrame] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def fetch(self, window, **extra):  # type: ignore[no-untyped-def]
        _FakeEdgar.fetches.append({"window": window, **extra})
        yield RawBatch(
            source="edgar",
            endpoint=str(extra.get("endpoint") or "submissions"),
            as_of=window.end,
            payload={"ok": True},
            request={"ciks": extra.get("ciks")},
        )

    def normalize(self, batch: RawBatch) -> pd.DataFrame:
        _FakeEdgar.normalized.append(batch)
        return tag_table(pd.DataFrame([{"doc_id": "edgar:1", "ticker": "AAPL"}]), "documents")

    def upsert(self, frame: pd.DataFrame) -> int:
        _FakeEdgar.upserted.append(frame)
        return len(frame)

    def close(self) -> None:
        return None


def _reset_fake() -> None:
    _FakeEdgar.fetches = []
    _FakeEdgar.normalized = []
    _FakeEdgar.upserted = []


def _settings(tmp_path: Path, ua: str | None) -> object:
    from packages.core.config import Settings

    return Settings(data_dir=tmp_path / "data", edgar_user_agent=ua)


def test_us_documents_calls_edgar_when_configured(tmp_path: Path, monkeypatch) -> None:
    _reset_fake()
    settings = _settings(tmp_path, "Taro Yamada (taro@example.com)")
    monkeypatch.setattr("packages.core.config.get_settings", lambda: settings)
    monkeypatch.setattr("packages.core.connectors.get_connector", lambda name: _FakeEdgar)
    warehouse = FakeWarehouse()
    warehouse.securities = pd.DataFrame(
        [{"ticker": "AAPL", "market": "US", "cik": "0000320193"}]
    )
    steps = builtin_connector_steps(warehouse=warehouse, state=FakeStateRepo())
    metrics = steps["documents"]("US", date(2026, 8, 28))
    assert metrics.get("skipped") is not True
    assert metrics.get("rows") == 1
    assert _FakeEdgar.fetches
    assert _FakeEdgar.fetches[0]["endpoint"] == "submissions"
    assert _FakeEdgar.fetches[0]["ciks"] == ["0000320193"]
    assert _FakeEdgar.normalized
    assert _FakeEdgar.upserted


def test_us_financials_calls_edgar_companyfacts(tmp_path: Path, monkeypatch) -> None:
    _reset_fake()
    settings = _settings(tmp_path, "Taro Yamada (taro@example.com)")
    monkeypatch.setattr("packages.core.config.get_settings", lambda: settings)
    monkeypatch.setattr("packages.core.connectors.get_connector", lambda name: _FakeEdgar)
    warehouse = FakeWarehouse()
    warehouse.securities = pd.DataFrame(
        [{"ticker": "AAPL", "market": "US", "cik": "0000320193"}]
    )
    steps = builtin_connector_steps(warehouse=warehouse, state=FakeStateRepo())
    metrics = steps["financials"]("US", date(2026, 8, 28))
    assert metrics.get("rows") == 1
    assert _FakeEdgar.fetches[0]["endpoint"] == "companyfacts"


def test_us_documents_skips_when_user_agent_missing(tmp_path: Path, monkeypatch) -> None:
    _reset_fake()
    settings = _settings(tmp_path, None)
    monkeypatch.setattr("packages.core.config.get_settings", lambda: settings)
    called = {"n": 0}

    def _boom(name: str) -> type:
        called["n"] += 1
        raise AssertionError("UA 未設定で edgar を呼んではいけない")

    monkeypatch.setattr("packages.core.connectors.get_connector", _boom)
    warehouse = FakeWarehouse()
    warehouse.securities = pd.DataFrame(
        [{"ticker": "AAPL", "market": "US", "cik": "0000320193"}]
    )
    steps = builtin_connector_steps(warehouse=warehouse, state=FakeStateRepo())
    metrics = steps["documents"]("US", date(2026, 8, 28))
    assert metrics["skipped"] is True
    assert metrics["reason"] == "edgar_user_agent_missing"
    assert called["n"] == 0
    result = collector(
        "US",
        date(2026, 8, 28),
        state=FakeStateRepo(),
        warehouse=warehouse,
        steps=steps,
    )
    assert result.steps["documents"].status == "success"
    assert result.status != "failed"


def test_us_documents_skips_when_cik_missing(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path, "Taro Yamada (taro@example.com)")
    monkeypatch.setattr("packages.core.config.get_settings", lambda: settings)
    steps = builtin_connector_steps(warehouse=FakeWarehouse(), state=FakeStateRepo())
    metrics = steps["documents"]("US", date(2026, 8, 28))
    assert metrics["skipped"] is True
    assert metrics["reason"] == "cik_missing"
