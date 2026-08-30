"""ベクトルストア（docs/03-data-model.md §4）。

`VectorStore` Protocol の背後に LanceDB を置く。Phase B で pgvector に
差し替えられるよう、実装依存の型を外に漏らさない。

LanceDB が未インストール／未初期化でも API が起動できるように、
インメモリ実装（`InMemoryVectorStore`）を用意してある。検索精度は
総当たりコサイン類似度で、件数が少ないテスト用途を想定している。
"""

from __future__ import annotations

import datetime as dt
import logging
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from packages.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

DOC_CHUNKS_TABLE = "doc_chunks"


@dataclass(slots=True)
class DocChunk:
    """`doc_chunks` の 1 行（docs/03-data-model.md §4）。

    `page_from` / `page_to` は引用の検証に必要なので必須扱いにしている。
    """

    chunk_id: str
    doc_id: str
    text: str
    embedding: list[float]
    market: str
    ticker: str | None = None
    doc_type: str | None = None
    filed_at: dt.datetime | None = None
    fiscal_period: str | None = None
    page_from: int | None = None
    page_to: int | None = None
    section: str | None = None
    token_count: int | None = None
    embedding_model: str = "unknown"
    embedding_version: str = "v1"
    created_at: dt.datetime = field(
        default_factory=lambda: dt.datetime.now(dt.UTC).replace(tzinfo=None)
    )

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SearchHit:
    """検索結果 1 件。`score` はコサイン類似度（大きいほど近い）。"""

    chunk_id: str
    doc_id: str
    text: str
    score: float
    ticker: str | None = None
    market: str | None = None
    doc_type: str | None = None
    filed_at: dt.datetime | None = None
    page_from: int | None = None
    page_to: int | None = None
    section: str | None = None


@runtime_checkable
class VectorStore(Protocol):
    """docs/03-data-model.md §4 の抽象。"""

    def upsert(self, chunks: list[DocChunk]) -> int: ...

    def search(
        self, query_vec: list[float], *, k: int, filters: dict[str, Any] | None = None
    ) -> list[SearchHit]: ...

    def delete_by_doc(self, doc_id: str) -> int: ...

    def count(self) -> int: ...


class InMemoryVectorStore:
    """テストと LanceDB 未導入時のフォールバック。"""

    def __init__(self) -> None:
        self._rows: dict[str, DocChunk] = {}

    def upsert(self, chunks: list[DocChunk]) -> int:
        for c in chunks:
            self._rows[c.chunk_id] = c
        return len(chunks)

    def search(
        self, query_vec: list[float], *, k: int, filters: dict[str, Any] | None = None
    ) -> list[SearchHit]:
        candidates = [c for c in self._rows.values() if _matches(c, filters)]
        scored = [(_cosine(query_vec, c.embedding), c) for c in candidates]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [_to_hit(c, score) for score, c in scored[:k]]

    def delete_by_doc(self, doc_id: str) -> int:
        targets = [cid for cid, c in self._rows.items() if c.doc_id == doc_id]
        for cid in targets:
            del self._rows[cid]
        return len(targets)

    def count(self) -> int:
        return len(self._rows)

    def list_by_doc(self, doc_id: str) -> list[DocChunk]:
        return [c for c in self._rows.values() if c.doc_id == doc_id]


class LanceDBVectorStore:
    """LanceDB 実装。`lancedb` が入っていないと生成時に失敗する。"""

    def __init__(self, path: str | Path, *, table_name: str = DOC_CHUNKS_TABLE) -> None:
        try:
            import lancedb  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - 依存未導入時のみ
            raise RuntimeError(
                "lancedb がインストールされていません。"
                "`uv sync --extra vector` を実行するか、InMemoryVectorStore を使ってください。"
            ) from exc
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.table_name = table_name
        self._db = lancedb.connect(str(self.path))

    def _table(self, create_from: list[dict[str, Any]] | None = None) -> Any:
        names = self._db.table_names()
        if self.table_name in names:
            return self._db.open_table(self.table_name)
        if create_from is None:
            return None
        return self._db.create_table(self.table_name, data=create_from)

    def upsert(self, chunks: list[DocChunk]) -> int:
        if not chunks:
            return 0
        rows = [c.to_row() for c in chunks]
        table = self._table(create_from=rows)
        if table is None:  # pragma: no cover - create_from を渡しているので到達しない
            return 0
        chunk_ids = [c.chunk_id for c in chunks]
        if table.count_rows() and len(rows) <= len(chunk_ids):
            quoted = ", ".join(f"'{cid}'" for cid in chunk_ids)
            table.delete(f"chunk_id IN ({quoted})")
            table.add(rows)
        return len(rows)

    def search(
        self, query_vec: list[float], *, k: int, filters: dict[str, Any] | None = None
    ) -> list[SearchHit]:
        table = self._table()
        if table is None:
            return []
        query = table.search(query_vec).limit(k)
        where = _lance_where(filters)
        if where:
            query = query.where(where)
        hits: list[SearchHit] = []
        for row in query.to_list():
            # LanceDB は距離（小さいほど近い）を返すので類似度に直す
            distance = float(row.get("_distance", 0.0))
            hits.append(
                SearchHit(
                    chunk_id=row["chunk_id"],
                    doc_id=row["doc_id"],
                    text=row["text"],
                    score=1.0 - distance,
                    ticker=row.get("ticker"),
                    market=row.get("market"),
                    doc_type=row.get("doc_type"),
                    filed_at=row.get("filed_at"),
                    page_from=row.get("page_from"),
                    page_to=row.get("page_to"),
                    section=row.get("section"),
                )
            )
        return hits

    def delete_by_doc(self, doc_id: str) -> int:
        table = self._table()
        if table is None:
            return 0
        before = table.count_rows()
        table.delete(f"doc_id = '{doc_id}'")
        return before - table.count_rows()

    def count(self) -> int:
        table = self._table()
        return int(table.count_rows()) if table is not None else 0

    def list_by_doc(self, doc_id: str) -> list[DocChunk]:
        table = self._table()
        if table is None:
            return []
        try:
            raw = table.to_pandas() if hasattr(table, "to_pandas") else None
        except Exception:
            return []
        if raw is None:
            return []
        try:
            subset = raw.loc[raw["doc_id"].astype(str) == str(doc_id)]
        except Exception:
            return []
        out: list[DocChunk] = []
        for rec in subset.to_dict(orient="records"):
            try:
                out.append(
                    DocChunk(
                        chunk_id=str(rec.get("chunk_id") or ""),
                        doc_id=str(rec.get("doc_id") or doc_id),
                        text=str(rec.get("text") or ""),
                        embedding=list(rec.get("embedding") or []),
                        market=str(rec.get("market") or ""),
                        ticker=rec.get("ticker"),
                        doc_type=rec.get("doc_type"),
                        filed_at=rec.get("filed_at"),
                        fiscal_period=rec.get("fiscal_period"),
                        page_from=rec.get("page_from"),
                        page_to=rec.get("page_to"),
                        section=rec.get("section"),
                        token_count=rec.get("token_count"),
                    )
                )
            except Exception:
                continue
        return out


def get_vector_store(
    settings: Settings | None = None, *, allow_fallback: bool = True
) -> VectorStore:
    """設定に従ってベクトルストアを返す。

    LanceDB が使えない環境では `InMemoryVectorStore` に落とす
    （検索機能は劣化するが API は起動できる）。
    """
    s = settings or get_settings()
    backend = str(getattr(s, "vector_store_backend", "lancedb") or "lancedb")
    if backend == "memory":
        return InMemoryVectorStore()
    path = getattr(s, "lancedb_path", None) or getattr(s, "vector_dir", None)
    if path is None:
        path = Path(getattr(s, "data_dir", Path("data"))) / "vectors"
    try:
        return LanceDBVectorStore(path)
    except Exception:
        if not allow_fallback:
            raise
        logger.warning(
            "LanceDB を初期化できないため InMemoryVectorStore にフォールバックします。"
            "全文検索の再現性は保証されません。"
        )
        return InMemoryVectorStore()


def _matches(chunk: DocChunk, filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True
    for key, expected in filters.items():
        if expected is None:
            continue
        actual = getattr(chunk, key, None)
        if isinstance(expected, dict):
            if "$lte" in expected and not _cmp_lte(actual, expected["$lte"]):
                return False
            if "$gte" in expected and not _cmp_gte(actual, expected["$gte"]):
                return False
            if "$in" in expected and actual not in expected["$in"]:
                return False
            continue
        if isinstance(expected, (list, tuple, set)):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _cmp_lte(actual: Any, limit: Any) -> bool:
    if actual is None:
        return False
    a = _as_date(actual)
    b = _as_date(limit)
    if a is not None and b is not None:
        return a <= b
    return actual <= limit


def _cmp_gte(actual: Any, limit: Any) -> bool:
    if actual is None:
        return False
    a = _as_date(actual)
    b = _as_date(limit)
    if a is not None and b is not None:
        return a >= b
    return actual >= limit


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _to_hit(chunk: DocChunk, score: float) -> SearchHit:
    return SearchHit(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        text=chunk.text,
        score=score,
        ticker=chunk.ticker,
        market=chunk.market,
        doc_type=chunk.doc_type,
        filed_at=chunk.filed_at,
        page_from=chunk.page_from,
        page_to=chunk.page_to,
        section=chunk.section,
    )


def _lance_where(filters: dict[str, Any] | None) -> str | None:
    if not filters:
        return None
    clauses: list[str] = []
    for key, value in filters.items():
        if value is None:
            continue
        if isinstance(value, dict):
            if "$lte" in value:
                clauses.append(f"{key} <= {_lance_literal(value['$lte'])}")
            if "$gte" in value:
                clauses.append(f"{key} >= {_lance_literal(value['$gte'])}")
            if "$in" in value:
                quoted = ", ".join(_lance_literal(v) for v in value["$in"])
                clauses.append(f"{key} IN ({quoted})")
            continue
        if isinstance(value, (list, tuple, set)):
            quoted = ", ".join(_lance_literal(v) for v in value)
            clauses.append(f"{key} IN ({quoted})")
        else:
            clauses.append(f"{key} = {_lance_literal(value)}")
    return " AND ".join(clauses) if clauses else None


def _lance_literal(value: Any) -> str:
    if isinstance(value, datetime):
        return f"'{value.isoformat()}'"
    if isinstance(value, date):
        return f"'{value.isoformat()}'"
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def chunk_id_for(doc_id: str, chunk_index: int) -> str:
    """`{doc_id}#{chunk_index}`（docs/03-data-model.md §4）。"""
    return f"{doc_id}#{chunk_index}"


__all__ = [
    "DOC_CHUNKS_TABLE",
    "DocChunk",
    "InMemoryVectorStore",
    "LanceDBVectorStore",
    "SearchHit",
    "VectorStore",
    "chunk_id_for",
    "get_vector_store",
]
