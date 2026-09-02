"""開示一覧は証券マスタの会社名を載せる。"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from packages.core.config.settings import Settings
from services.api.main import create_app


def test_seed_documents_list_includes_company_names(client: TestClient) -> None:
    r = client.get("/api/v1/documents?market=JP")
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    by_ticker = {row["ticker"]: row["name_local"] for row in items}
    assert by_ticker.get("7203") == "トヨタ自動車"
    assert by_ticker.get("6758") == "ソニーグループ"


def test_documents_fill_name_from_securities_when_row_has_none(seeded_repos) -> None:
    duck, sqlite, payload = seeded_repos
    duck.upsert_documents(
        [
            {
                "doc_id": "edinet:NO_NAME",
                "ticker": "72030",
                "market": "JP",
                "source": "edinet",
                "doc_type": "quarterly_report",
                "title": "名称なしの四半期報告書",
                "filed_at": dt.datetime(2026, 8, 22, 16, 0, 0),
                "source_url": "https://example.invalid/NO_NAME",
            }
        ]
    )
    application = create_app(duck=duck, sqlite=sqlite, payload=payload)
    with TestClient(application) as client:
        r = client.get("/api/v1/documents?market=JP")
    assert r.status_code == 200
    nameless = next(row for row in r.json()["data"]["items"] if row["doc_id"] == "edinet:NO_NAME")
    assert nameless["ticker"] == "72030"
    assert nameless["name_local"] == "トヨタ自動車"


def test_documents_fill_name_from_payload_when_not_in_master() -> None:
    from services.api.mapping import documents_from_storage

    class _Duck:
        def get_securities(self, **kwargs):
            return []

    items = documents_from_storage(
        _Duck(),
        [
            {
                "doc_id": "edinet:FILER_ONLY",
                "ticker": "6027",
                "market": "JP",
                "source": "edinet",
                "doc_type": "other_disclosure",
                "title": "自己株券買付状況報告書",
                "filed_at": dt.datetime(2026, 9, 2, 2, 9, 0),
                "source_url": "https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?S100=S100FILER",
                "payload": {"filerName": "弁護士ドットコム株式会社", "docID": "S100FILER"},
            }
        ],
    )
    assert items[0].ticker == "6027"
    assert items[0].name_local == "弁護士ドットコム株式会社"


def test_documents_fill_name_from_json_payload_string() -> None:
    from services.api.mapping import documents_from_storage

    class _Duck:
        def get_securities(self, **kwargs):
            return []

    items = documents_from_storage(
        _Duck(),
        [
            {
                "doc_id": "edinet:S100JSON",
                "ticker": "1887",
                "market": "JP",
                "source": "edinet",
                "doc_type": "large_holding",
                "title": "大量保有報告書",
                "filed_at": dt.datetime(2026, 9, 2, 2, 10, 0),
                "source_url": "",
                "payload": '{"filerName": "日本国土開発株式会社", "docID": "S100JSON"}',
            }
        ],
    )
    assert items[0].name_local == "日本国土開発株式会社"


def test_documents_fill_name_from_four_digit_securities_alias(seeded_repos) -> None:
    duck, sqlite, payload = seeded_repos
    duck.upsert_securities(
        [
            {
                "ticker": "18870",
                "market": "JP",
                "name_local": "日本国土開発",
                "currency": "JPY",
                "valid_from": dt.date(2020, 1, 1),
                "is_active": True,
            }
        ]
    )
    duck.upsert_documents(
        [
            {
                "doc_id": "edinet:S100ALIAS",
                "ticker": "1887",
                "market": "JP",
                "source": "edinet",
                "doc_type": "large_holding",
                "title": "大量保有報告書",
                "filed_at": dt.datetime(2026, 9, 2, 2, 10, 0),
                "source_url": "https://example.invalid/S100ALIAS",
            }
        ]
    )
    application = create_app(duck=duck, sqlite=sqlite, payload=payload)
    with TestClient(application) as client:
        r = client.get("/api/v1/documents?market=JP")
    row = next(item for item in r.json()["data"]["items"] if item["doc_id"] == "edinet:S100ALIAS")
    assert row["ticker"] == "1887"
    assert row["name_local"] == "日本国土開発"


def test_documents_fill_name_from_stored_filer_when_master_missing(seeded_repos) -> None:
    duck, sqlite, payload = seeded_repos
    duck.upsert_documents(
        [
            {
                "doc_id": "edinet:STORED_NAME",
                "ticker": "1887",
                "market": "JP",
                "source": "edinet",
                "doc_type": "other_disclosure",
                "title": "大量保有報告書",
                "filed_at": dt.datetime(2026, 9, 2, 2, 10, 0),
                "source_url": "https://example.invalid/STORED_NAME",
                "name_local": "日本国土開発株式会社",
            }
        ]
    )
    application = create_app(duck=duck, sqlite=sqlite, payload=payload)
    with TestClient(application) as client:
        r = client.get("/api/v1/documents?market=JP")
    row = next(item for item in r.json()["data"]["items"] if item["doc_id"] == "edinet:STORED_NAME")
    assert row["name_local"] == "日本国土開発株式会社"


def test_documents_fill_name_from_edinet_raw(seeded_repos, tmp_path) -> None:
    from datetime import UTC, date, datetime

    from packages.core.connectors.raw_store import RawStore

    duck, sqlite, payload = seeded_repos
    RawStore(tmp_path).write_json(
        source="edinet",
        endpoint="documents",
        as_of=date(2026, 9, 2),
        payload={
            "metadata": {"status": "200"},
            "results": [
                {
                    "docID": "S100RAW",
                    "secCode": "60270",
                    "filerName": "弁護士ドットコム株式会社",
                    "docDescription": "自己株券買付状況報告書",
                }
            ],
        },
        fetched_at=datetime(2026, 9, 2, 2, 0, tzinfo=UTC),
    )
    duck.upsert_documents(
        [
            {
                "doc_id": "edinet:S100RAW",
                "ticker": "6027",
                "market": "JP",
                "source": "edinet",
                "doc_type": "other_disclosure",
                "title": "自己株券買付状況報告書",
                "filed_at": dt.datetime(2026, 9, 2, 2, 9, 0),
                "source_url": "https://example.invalid/S100RAW",
            }
        ]
    )
    application = create_app(
        duck=duck, sqlite=sqlite, payload=payload, settings=Settings(data_dir=tmp_path)
    )
    with TestClient(application) as client:
        r = client.get("/api/v1/documents?market=JP")
    row = next(item for item in r.json()["data"]["items"] if item["doc_id"] == "edinet:S100RAW")
    assert row["name_local"] == "弁護士ドットコム株式会社"
