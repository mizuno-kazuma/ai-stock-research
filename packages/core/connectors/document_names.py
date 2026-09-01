"""Raw 層の提出者名を `documents.name_local` に復元する。

EDINET の正規化は `filerName` を `name_local` に載せるが、カラム追加前に
取り込んだ行は NULL のまま残る。DuckDB の upsert は未知列（payload）を
捨てるため、一覧 API は Raw の JSON から名前を拾い直す。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from packages.core.connectors.raw_store import RawStore

logger = logging.getLogger(__name__)


def load_filer_names_from_raw(data_dir: Path | str) -> dict[str, str]:
    """Raw の EDINET / TDnet JSON から `doc_id → 提出者名` を拾う。"""
    store = RawStore(data_dir)
    names: dict[str, str] = {}
    names.update(_edinet_filer_names(store))
    names.update(_tdnet_company_names(store))
    return names


def backfill_document_names_from_raw(warehouse: Any, data_dir: Path | str) -> int:
    """`name_local` が空（またはティッカーそのもの）の開示行を Raw から埋める。"""
    if warehouse is None or not hasattr(warehouse, "execute"):
        return 0
    names = load_filer_names_from_raw(data_dir)
    if not names:
        return 0
    updated = 0
    for doc_id, name in names.items():
        warehouse.execute(
            "UPDATE documents SET name_local = ? WHERE doc_id = ? AND "
            "(name_local IS NULL OR length(trim(cast(name_local AS VARCHAR))) = 0 "
            "OR trim(cast(name_local AS VARCHAR)) = ticker)",
            [name, doc_id],
        )
        updated += 1
    return updated


def ensure_document_names(state: Any) -> dict[str, str]:
    """API プロセス内で一度だけ Raw から会社名を復元し、候補辞書を返す。"""
    cached = getattr(state, "_filer_names_from_raw", None)
    if isinstance(cached, dict):
        return cached
    names: dict[str, str] = {}
    data_dir = getattr(getattr(state, "settings", None), "data_dir", None)
    if data_dir is None:
        state._filer_names_from_raw = names
        return names
    try:
        duck = getattr(state, "duck", None)
        if duck is not None:
            backfill_document_names_from_raw(duck, data_dir)
        names = load_filer_names_from_raw(data_dir)
    except Exception:
        logger.exception("Raw からの提出者名復元に失敗しました")
        names = {}
    state._filer_names_from_raw = names
    return names


def _edinet_filer_names(store: RawStore) -> dict[str, str]:
    from packages.core.connectors.edinet import _result_rows

    names: dict[str, str] = {}
    for envelope in store.replay(source="edinet", endpoint="documents"):
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            continue
        for row in _result_rows(payload):
            if not isinstance(row, dict):
                continue
            native = str(row.get("docID") or row.get("docId") or "").strip()
            filer = str(row.get("filerName") or "").strip()
            if native and filer:
                names[f"edinet:{native}"] = filer
    return names


def _tdnet_company_names(store: RawStore) -> dict[str, str]:
    names: dict[str, str] = {}
    for envelope in store.replay(source="tdnet", endpoint="disclosures"):
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            continue
        rows = payload.get("disclosures") or []
        if not isinstance(rows, list):
            continue
        as_of = str(envelope.get("as_of") or "").replace("-", "")
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            company = str(row.get("company_name") or row.get("name") or "").strip()
            seq = row.get("seq", index)
            try:
                seq_n = int(seq)
            except (TypeError, ValueError):
                seq_n = index
            if as_of and company:
                names[f"tdnet:{as_of}-{seq_n:04d}"] = company
    return names
