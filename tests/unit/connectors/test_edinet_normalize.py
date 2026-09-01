"""EDINET 書類一覧の正規化。"""

from __future__ import annotations

from datetime import date

import pytest

from packages.core.connectors.base import RawBatch
from packages.core.connectors.edinet import EdinetConnector, _result_rows
from packages.core.connectors.errors import AuthError, TransientError


def _connector(tmp_path) -> EdinetConnector:
    return EdinetConnector(
        data_dir=tmp_path,
        env={"EDINET_SUBSCRIPTION_KEY": "test-key"},
        require_enabled=True,
    )


def test_normalize_keeps_rows_when_submit_datetime_missing(tmp_path) -> None:
    connector = _connector(tmp_path)
    batch = RawBatch(
        source="edinet",
        endpoint="documents",
        as_of=date(2026, 8, 27),
        payload={
            "metadata": {"status": "200"},
            "results": [
                {
                    "docID": "S100TEST",
                    "secCode": "72030",
                    "docTypeCode": "140",
                    "docDescription": None,
                    "submitDateTime": None,
                    "filerName": "トヨタ自動車株式会社",
                }
            ],
        },
    )
    frame = connector.normalize(batch)
    connector.close()
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["doc_id"] == "edinet:S100TEST"
    assert row["ticker"] == "7203"
    assert row["name_local"] == "トヨタ自動車株式会社"
    assert row["title"] == "edinet:S100TEST"
    assert str(row["filed_at"])[:10] == "2026-08-27"
    assert row["source_url"] == "https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?S100TEST"
    assert "wzek0130" not in str(row["source_url"]).lower()
    assert "S100=" not in str(row["source_url"])


def test_result_rows_reads_results_key() -> None:
    assert _result_rows({"results": [{"docID": "A"}]}) == [{"docID": "A"}]
    assert _result_rows({"metadata": {"status": "200"}, "results": []}) == []


def test_get_documents_json_rejects_non_200_metadata(tmp_path, monkeypatch) -> None:
    connector = _connector(tmp_path)

    def fake_get_json(url, *, params=None, endpoint=""):
        return {"metadata": {"status": "400", "message": "Bad Request"}, "results": []}

    monkeypatch.setattr(connector.http, "get_json", fake_get_json)
    with pytest.raises(TransientError, match=r"metadata.status=400"):
        connector._get_documents_json(date(2026, 8, 27), "2")
    connector.close()


def test_auth_header_is_ocp_apim_subscription_key(tmp_path) -> None:
    connector = _connector(tmp_path)
    headers = connector.auth_headers()
    connector.close()
    assert headers["Ocp-Apim-Subscription-Key"] == "test-key"
    assert "Subscription-Key" not in headers


def test_get_documents_json_rejects_apim_401_body(tmp_path, monkeypatch) -> None:
    """HTTP 200 でも本文 StatusCode=401 は空一覧ではなく認証失敗。"""
    connector = _connector(tmp_path)

    def fake_get_json(url, *, params=None, endpoint=""):
        return {
            "StatusCode": 401,
            "message": "Access denied due to invalid subscription key.",
        }

    monkeypatch.setattr(connector.http, "get_json", fake_get_json)
    with pytest.raises(AuthError, match="StatusCode=401"):
        connector._get_documents_json(date(2026, 8, 27), "2")
    connector.close()


def test_persist_document_blobs_skips_metadata_only_and_saves_pdf(tmp_path, monkeypatch) -> None:
    import pandas as pd

    class Warehouse:
        def __init__(self) -> None:
            self.rows: list[dict] = []

        def upsert_documents(self, rows):
            self.rows.extend(list(rows))
            return len(self.rows)

    warehouse = Warehouse()
    connector = EdinetConnector(
        data_dir=tmp_path,
        warehouse=warehouse,
        env={"EDINET_SUBSCRIPTION_KEY": "test-key"},
        require_enabled=True,
    )
    monkeypatch.setattr(connector.http, "get_bytes", lambda url, *, endpoint="": b"%PDF-1.4")
    frame = pd.DataFrame(
        [
            {
                "doc_id": "edinet:S100PDF",
                "ticker": "7203",
                "market": "JP",
                "source": "edinet",
                "doc_type": "quarterly_report",
                "title": "四半期報告書",
                "filed_at": date(2026, 8, 22),
                "source_url": "https://example.invalid/S100PDF",
                "should_download": True,
            },
            {
                "doc_id": "edinet:S100HOLD",
                "ticker": "1887",
                "market": "JP",
                "source": "edinet",
                "doc_type": "large_holding",
                "title": "大量保有報告書",
                "filed_at": date(2026, 8, 22),
                "source_url": "https://example.invalid/S100HOLD",
                "should_download": False,
            },
        ]
    )
    stored = connector.persist_document_blobs(frame)
    connector.close()
    assert stored == 1
    assert len(warehouse.rows) == 1
    assert warehouse.rows[0]["doc_id"] == "edinet:S100PDF"
    assert warehouse.rows[0]["blob_path"].endswith("S100PDF.pdf")

