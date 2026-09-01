"""開示一覧は証券マスタの会社名を載せる。"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

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
