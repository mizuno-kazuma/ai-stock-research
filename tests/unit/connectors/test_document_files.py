"""EDINET の PDF 保存と Raw からの会社名復元。"""

from __future__ import annotations

from datetime import date

import pandas as pd

from packages.core.connectors.base import tag_table
from packages.core.connectors.document_names import (
    backfill_document_names_from_raw,
    load_filer_names_from_raw,
)
from packages.core.connectors.edinet import EdinetConnector
from packages.core.connectors.raw_store import RawStore
from packages.core.storage import DuckDBRepo


def test_load_filer_names_from_raw_edinet(tmp_path) -> None:
    RawStore(tmp_path).write_json(
        source="edinet",
        endpoint="documents",
        as_of=date(2026, 9, 2),
        payload={
            "metadata": {"status": "200"},
            "results": [
                {
                    "docID": "S100FILER",
                    "secCode": "60270",
                    "filerName": "弁護士ドットコム株式会社",
                }
            ],
        },
    )
    names = load_filer_names_from_raw(tmp_path)
    assert names["edinet:S100FILER"] == "弁護士ドットコム株式会社"


def test_backfill_document_names_from_raw(tmp_path) -> None:
    RawStore(tmp_path).write_json(
        source="edinet",
        endpoint="documents",
        as_of=date(2026, 9, 2),
        payload={
            "metadata": {"status": "200"},
            "results": [
                {
                    "docID": "S100FILER",
                    "secCode": "60270",
                    "filerName": "弁護士ドットコム株式会社",
                }
            ],
        },
    )
    with DuckDBRepo.in_memory() as duck:
        duck.upsert_documents(
            [
                {
                    "doc_id": "edinet:S100FILER",
                    "ticker": "6027",
                    "market": "JP",
                    "source": "edinet",
                    "doc_type": "other_disclosure",
                    "title": "自己株券買付状況報告書",
                    "filed_at": "2026-09-02T02:09:00",
                    "source_url": "https://example.invalid/S100FILER",
                }
            ]
        )
        backfill_document_names_from_raw(duck, tmp_path)
        row = duck.get_document("edinet:S100FILER")
        assert row is not None
        assert row["name_local"] == "弁護士ドットコム株式会社"


def test_persist_document_blobs_sets_blob_path(tmp_path, monkeypatch) -> None:
    with DuckDBRepo.in_memory() as duck:
        connector = EdinetConnector(
            data_dir=tmp_path,
            env={"EDINET_SUBSCRIPTION_KEY": "test-key"},
            require_enabled=True,
            warehouse=duck,
        )
        monkeypatch.setattr(connector.http, "get_bytes", lambda *a, **k: b"%PDF-1.4 blob")
        frame = tag_table(
            pd.DataFrame(
                [
                    {
                        "doc_id": "edinet:S100PDF",
                        "ticker": "7203",
                        "market": "JP",
                        "source": "edinet",
                        "doc_type": "quarterly_report",
                        "title": "四半期報告書",
                        "filed_at": "2026-08-22T16:00:00",
                        "source_url": "https://example.invalid/S100PDF",
                        "should_download": True,
                    }
                ]
            ),
            "documents",
        )
        duck.upsert_documents(frame.to_dict(orient="records"))
        stored = connector.persist_document_blobs(frame)
        connector.close()
        assert stored == 1
        row = duck.get_document("edinet:S100PDF")
        assert row is not None
        assert row["blob_path"]
        assert (tmp_path / "raw" / "edinet" / "blobs" / "S100PDF.pdf").is_file()
