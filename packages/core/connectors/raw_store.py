"""Raw 層への無加工保存。

docs/01-architecture.md §4.2 の通り、**Raw層を必ず残すことが再現性の根拠**である。
J-Quants 無料プランは 5 req/min なので、正規化のバグ修正のために全銘柄を
再取得すると数時間かかる。Raw層があればその再取得が不要になる。
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from packages.core.connectors.paths import (
    assert_path_is_windows_safe,
    blob_path,
    raw_path,
)


class RawStore:
    """`data/raw/` 配下への書き込みと読み出し。

    書き込みは追記のみ（不変）。同一 `(source, endpoint, dt)` の中で
    連番を自動採番する。
    """

    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)

    # ------------------------------------------------------------------
    def write_json(
        self,
        *,
        source: str,
        endpoint: str,
        as_of: date,
        payload: Any,
        request: dict[str, Any] | None = None,
        fetched_at: datetime | None = None,
        seq: int | None = None,
    ) -> Path:
        """生レスポンスを gzip JSON で保存し、保存先パスを返す。"""
        ts = fetched_at or datetime.now(UTC)
        directory = raw_path(
            self.data_dir,
            source=source,
            endpoint=endpoint,
            dt=as_of,
            fetched_at=ts,
            seq=0,
        ).parent
        directory.mkdir(parents=True, exist_ok=True)
        resolved_seq = seq if seq is not None else self._next_seq(directory)
        path = raw_path(
            self.data_dir,
            source=source,
            endpoint=endpoint,
            dt=as_of,
            fetched_at=ts,
            seq=resolved_seq,
        )
        assert_path_is_windows_safe(path.relative_to(self.data_dir))

        envelope = {
            "source": source,
            "endpoint": endpoint,
            "as_of": as_of.isoformat(),
            "fetched_at": ts.astimezone(UTC).isoformat(),
            "request": request or {},
            "payload": payload,
        }
        # gzip.open のテキストモードは encoding を明示できる。
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump(envelope, fh, ensure_ascii=False)
        return path

    def write_text(
        self,
        *,
        source: str,
        endpoint: str,
        as_of: date,
        text: str,
        fetched_at: datetime | None = None,
        ext: str = "txt.gz",
    ) -> Path:
        """JSON でないテキスト（HTML / CSV）をそのまま残す。"""
        ts = fetched_at or datetime.now(UTC)
        directory = raw_path(
            self.data_dir, source=source, endpoint=endpoint, dt=as_of, fetched_at=ts, seq=0
        ).parent
        directory.mkdir(parents=True, exist_ok=True)
        path = raw_path(
            self.data_dir,
            source=source,
            endpoint=endpoint,
            dt=as_of,
            fetched_at=ts,
            seq=self._next_seq(directory),
            ext=ext,
        )
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def write_blob(self, *, source: str, doc_id: str, content: bytes, ext: str) -> Path:
        """PDF / XBRL ZIP の格納。ファイル名は `doc_id` ベースにする。"""
        path = blob_path(self.data_dir, source=source, doc_id=doc_id, ext=ext)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def blob_exists(self, *, source: str, doc_id: str, ext: str) -> bool:
        return blob_path(self.data_dir, source=source, doc_id=doc_id, ext=ext).exists()

    # ------------------------------------------------------------------
    def read_json(self, path: Path) -> dict[str, Any]:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)
        return data

    def iter_paths(
        self, *, source: str, endpoint: str, as_of: date | None = None
    ) -> Iterator[Path]:
        base = self.data_dir / "raw" / source / endpoint
        if not base.exists():
            return
        pattern = f"dt={as_of:%Y-%m-%d}" if as_of else "dt=*"
        for directory in sorted(base.glob(pattern)):
            yield from sorted(directory.glob("*.json.gz"))

    def replay(
        self, *, source: str, endpoint: str, as_of: date | None = None
    ) -> Iterator[dict[str, Any]]:
        """Raw層から `normalize` を再実行するための読み出し。

        `normalize` がネットワークに触らない設計なので、これだけで
        正規化ロジックのバグ修正を再適用できる。
        """
        for path in self.iter_paths(source=source, endpoint=endpoint, as_of=as_of):
            yield self.read_json(path)

    # ------------------------------------------------------------------
    @staticmethod
    def _next_seq(directory: Path) -> int:
        existing = list(directory.glob("*_*.*"))
        if not existing:
            return 1
        seqs = []
        for path in existing:
            stem = path.name.split(".")[0]
            _, _, tail = stem.rpartition("_")
            if tail.isdigit():
                seqs.append(int(tail))
        return (max(seqs) + 1) if seqs else 1
