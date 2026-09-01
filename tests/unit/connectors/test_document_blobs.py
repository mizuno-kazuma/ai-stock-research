"""開示 PDF の格納パス解決。"""

from __future__ import annotations

from packages.core.connectors.paths import document_native_id, existing_document_blob


def test_document_native_id_strips_source_prefix() -> None:
    assert document_native_id("edinet:S100XXXX") == "S100XXXX"
    assert document_native_id("S100XXXX") == "S100XXXX"


def test_existing_document_blob_finds_conventional_path(tmp_path) -> None:
    blob = tmp_path / "raw" / "edinet" / "blobs" / "S100XXXX.pdf"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"%PDF-1.4")
    found = existing_document_blob(
        data_dir=tmp_path,
        source="edinet",
        doc_id="edinet:S100XXXX",
    )
    assert found == blob


def test_existing_document_blob_uses_stored_relative_path(tmp_path) -> None:
    blob = tmp_path / "copies" / "doc.pdf"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"%PDF-1.4")
    found = existing_document_blob(
        data_dir=tmp_path,
        source="edinet",
        doc_id="edinet:OTHER",
        stored_path="copies/doc.pdf",
    )
    assert found == blob
