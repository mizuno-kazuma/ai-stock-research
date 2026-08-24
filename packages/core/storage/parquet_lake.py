"""Parquet レイク（docs/03-data-model.md §1、docs/15-windows-runtime.md §5.6）。

Raw 層（`data/raw/`）と正規化 Parquet（`data/parquet/`）を扱う。
DuckDB は Parquet を直接読めるので、大きな時系列は Parquet に置いて
DuckDB から `read_parquet()` する構成でよい。

パーティションは 3 階層まで。パーティションキーに `:` `?` `*` を含めない
（Windows 側から同じファイルを触るため）。
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
import logging
import shutil
from collections.abc import Iterable, Sequence
from dataclasses import fields as dc_fields
from dataclasses import is_dataclass
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa
import pyarrow.dataset as pads
import pyarrow.parquet as pq

from packages.core.config import Settings, get_settings

from .paths import assert_windows_safe, parquet_partition_path, raw_path, safe_component

logger = logging.getLogger(__name__)

Compression = Literal["zstd", "snappy", "gzip", "none"]


class ParquetLake:
    """`data/parquet/` 配下の読み書き。"""

    def __init__(
        self,
        root: str | Path,
        *,
        compression: Compression = "zstd",
        raw_root: str | Path | None = None,
    ) -> None:
        self.root = Path(root)
        self.raw_root = Path(raw_root) if raw_root else self.root.parent / "raw"
        self.compression = compression
        self.root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def open(cls, settings: Settings | None = None) -> ParquetLake:
        s = settings or get_settings()
        return cls(
            s.parquet_dir, compression=s.parquet_compression, raw_root=s.raw_dir
        )

    # -- 正規化 Parquet --------------------------------------------------------

    def table_dir(self, table: str) -> Path:
        return self.root / safe_component(table)

    def write(
        self,
        table: str,
        rows: Iterable[Any] | pa.Table,
        *,
        market: str | None = None,
        year: int | None = None,
        month: int | None = None,
        basename: str = "part-000.parquet",
        overwrite: bool = True,
    ) -> Path:
        """1 パーティション分を書き出す。返り値は書いたファイルのパス。"""
        arrow = rows if isinstance(rows, pa.Table) else _to_arrow(rows)
        directory = parquet_partition_path(
            self.root, table, market=market, year=year, month=month
        )
        assert_windows_safe(directory, relative_to=self.root.parent)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / safe_component(basename)
        if target.exists() and not overwrite:
            raise FileExistsError(target)
        pq.write_table(
            arrow,
            target,
            compression=None if self.compression == "none" else self.compression,
        )
        logger.debug("Parquet 書き出し: %s (%d 行)", target, arrow.num_rows)
        return target

    def write_partitioned(
        self,
        table: str,
        rows: Iterable[Any] | pa.Table,
        *,
        partition_cols: Sequence[str] = ("market",),
        existing_data_behavior: str = "overwrite_or_ignore",
    ) -> Path:
        """Hive パーティションでデータセットとして書き出す。"""
        arrow = rows if isinstance(rows, pa.Table) else _to_arrow(rows)
        directory = self.table_dir(table)
        directory.mkdir(parents=True, exist_ok=True)
        pads.write_dataset(
            arrow,
            directory,
            format="parquet",
            partitioning=pads.partitioning(
                pa.schema([arrow.schema.field(c) for c in partition_cols]),
                flavor="hive",
            ),
            existing_data_behavior=existing_data_behavior,
            file_options=pads.ParquetFileFormat().make_write_options(
                compression=None if self.compression == "none" else self.compression
            ),
        )
        return directory

    def read(
        self,
        table: str,
        *,
        columns: Sequence[str] | None = None,
        filters: list[tuple[str, str, Any]] | None = None,
    ) -> pa.Table:
        """テーブル全体（またはフィルタ済み）を読む。"""
        directory = self.table_dir(table)
        if not directory.exists():
            raise FileNotFoundError(
                f"Parquet テーブルがありません: {directory}"
            )
        dataset = pads.dataset(directory, format="parquet", partitioning="hive")
        return dataset.to_table(
            columns=list(columns) if columns else None,
            filter=_build_filter(filters) if filters else None,
        )

    def glob_pattern(self, table: str) -> str:
        """DuckDB の `read_parquet()` に渡すパターン。"""
        return (self.table_dir(table) / "**" / "*.parquet").as_posix()

    def exists(self, table: str) -> bool:
        directory = self.table_dir(table)
        return directory.exists() and any(directory.rglob("*.parquet"))

    def list_tables(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_dir())

    def drop(self, table: str) -> bool:
        directory = self.table_dir(table)
        if not directory.exists():
            return False
        shutil.rmtree(directory)
        return True

    # -- Raw 層 ----------------------------------------------------------------

    def write_raw(
        self,
        source: str,
        endpoint: str,
        as_of: dt.date,
        filename: str,
        payload: bytes | str | dict[str, Any] | list[Any],
        *,
        compress: bool = True,
    ) -> Path:
        """API 応答を無加工で保存する（docs/01-architecture.md §2 Raw 層）。

        Raw を残すのは、スキーマ変更や解釈ミスがあっても再構築できるようにするため。
        """
        if isinstance(payload, (dict, list)):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        elif isinstance(payload, str):
            data = payload.encode("utf-8")
        else:
            data = payload

        if compress and not filename.endswith(".gz"):
            filename += ".gz"
        target = raw_path(self.raw_root, source, endpoint, as_of, filename)
        assert_windows_safe(target, relative_to=self.raw_root.parent)
        target.parent.mkdir(parents=True, exist_ok=True)
        if compress:
            with gzip.open(target, "wb") as fh:
                fh.write(data)
        else:
            target.write_bytes(data)
        return target

    def read_raw(self, path: str | Path) -> bytes:
        p = Path(path)
        if p.suffix == ".gz":
            with gzip.open(p, "rb") as fh:
                return fh.read()
        return p.read_bytes()

    def raw_files(
        self, source: str, endpoint: str, *, as_of: dt.date | None = None
    ) -> list[Path]:
        base = self.raw_root / safe_component(source) / safe_component(endpoint)
        if not base.exists():
            return []
        if as_of:
            base = base / f"dt={as_of:%Y-%m-%d}"
            if not base.exists():
                return []
        return sorted(p for p in base.rglob("*") if p.is_file())

    def disk_usage_bytes(self) -> dict[str, int]:
        """`{'parquet': ..., 'raw': ...}`。容量監視に使う。"""

        def _size(path: Path) -> int:
            if not path.exists():
                return 0
            return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())

        return {"parquet": _size(self.root), "raw": _size(self.raw_root)}


def _to_arrow(rows: Iterable[Any]) -> pa.Table:
    materialized = [
        r if isinstance(r, dict) else _row_to_dict(r) for r in rows
    ]
    if not materialized:
        raise ValueError("空の行リストは書き出せません。")
    return pa.Table.from_pylist(materialized)


def _row_to_dict(row: Any) -> dict[str, Any]:
    dump = getattr(row, "model_dump", None)
    if callable(dump):
        return dict(dump(mode="python"))
    if is_dataclass(row) and not isinstance(row, type):
        return {f.name: getattr(row, f.name) for f in dc_fields(row)}
    if hasattr(row, "__dict__"):
        return dict(vars(row))
    raise TypeError(f"行に変換できません: {type(row)!r}")


def _build_filter(filters: list[tuple[str, str, Any]]) -> pads.Expression:
    expr: pads.Expression | None = None
    for column, op, value in filters:
        field = pads.field(column)
        match op:
            case "=" | "==":
                clause = field == value
            case "!=":
                clause = field != value
            case ">":
                clause = field > value
            case ">=":
                clause = field >= value
            case "<":
                clause = field < value
            case "<=":
                clause = field <= value
            case "in":
                clause = field.isin(value)
            case _:
                raise ValueError(f"未対応の演算子です: {op}")
        expr = clause if expr is None else (expr & clause)
    assert expr is not None
    return expr


__all__ = ["Compression", "ParquetLake"]
