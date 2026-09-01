"""原文 PDF はローカルがあれば返し、無ければ公式サイトへ送る。"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from packages.core.config.settings import Settings
from services.api.main import create_app


def test_document_file_redirects_to_source_url_when_blob_missing(seeded_repos, tmp_path) -> None:
    duck, sqlite, payload = seeded_repos
    duck.upsert_documents(
        [
            {
                "doc_id": "edinet:S100MISS",
                "ticker": "6027",
                "market": "JP",
                "source": "edinet",
                "doc_type": "other_disclosure",
                "title": "自己株券買付状況報告書",
                "filed_at": dt.datetime(2026, 9, 2, 2, 9, 0),
                "source_url": "https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?S100=S100MISS",
                "name_local": "弁護士ドットコム株式会社",
            }
        ]
    )
    application = create_app(
        duck=duck, sqlite=sqlite, payload=payload, settings=Settings(data_dir=tmp_path)
    )
    with TestClient(application, follow_redirects=False) as client:
        r = client.get("/api/v1/documents/edinet:S100MISS/file")
    assert r.status_code == 302
    assert r.headers["location"] == "https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?S100=S100MISS"


def test_document_file_serves_existing_blob(seeded_repos, tmp_path) -> None:
    duck, sqlite, payload = seeded_repos
    blob = tmp_path / "raw" / "edinet" / "blobs" / "S100PDF.pdf"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"%PDF-1.4 test")
    duck.upsert_documents(
        [
            {
                "doc_id": "edinet:S100PDF",
                "ticker": "7203",
                "market": "JP",
                "source": "edinet",
                "doc_type": "quarterly_report",
                "title": "四半期報告書",
                "filed_at": dt.datetime(2026, 8, 22, 16, 0, 0),
                "source_url": "https://example.invalid/S100PDF",
            }
        ]
    )
    application = create_app(
        duck=duck, sqlite=sqlite, payload=payload, settings=Settings(data_dir=tmp_path)
    )
    with TestClient(application) as client:
        r = client.get("/api/v1/documents/edinet:S100PDF/file")
        listed = client.get("/api/v1/documents?market=JP")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content.startswith(b"%PDF-1.4")
    row = next(item for item in listed.json()["data"]["items"] if item["doc_id"] == "edinet:S100PDF")
    assert row["has_local_copy"] is True
