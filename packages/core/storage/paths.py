"""Windows でも使えるパスの組み立て（docs/15-windows-runtime.md §5.3）。

WSL2 内（ext4）では `:` を含むファイル名を作れるが、Windows 側から
`\\wsl.localhost\...` 経由で触ると壊れる。WSL2 内でも Windows 互換の
命名規則を守る。
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

WINDOWS_FORBIDDEN_CHARS = set('<>:"/\\|?*')
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def is_valid_path_component(name: str) -> bool:
    """Windows でも使えるパス要素かを判定する。"""
    if not name or name != name.strip(" ."):
        return False
    if set(name) & WINDOWS_FORBIDDEN_CHARS:
        return False
    if name.split(".")[0].upper() in WINDOWS_RESERVED_NAMES:
        return False
    return all(ord(c) >= 32 for c in name)


def safe_component(name: str) -> str:
    """禁止文字を '_' に置換する。"""
    out = "".join(
        "_" if (c in WINDOWS_FORBIDDEN_CHARS or ord(c) < 32) else c for c in name
    ).strip(" .")
    if out.split(".")[0].upper() in WINDOWS_RESERVED_NAMES:
        out = f"_{out}"
    return out or "_"


def timestamp_component(when: dt.datetime) -> str:
    """日時をパス要素にする。ISO 8601 の ':' を避ける。"""
    return when.strftime("%Y%m%dT%H%M%SZ")


def doc_blob_name(doc_id: str, suffix: str = ".pdf") -> str:
    """`edinet:S100XYZW` → `edinet_S100XYZW.pdf`。"""
    return safe_component(doc_id) + suffix


def raw_path(
    root: Path, source: str, endpoint: str, as_of: dt.date, filename: str
) -> Path:
    """`data/raw/{source}/{endpoint}/dt=YYYY-MM-DD/{filename}`。"""
    return (
        root
        / safe_component(source)
        / safe_component(endpoint)
        / f"dt={as_of:%Y-%m-%d}"
        / safe_component(filename)
    )


def parquet_partition_path(
    root: Path, table: str, *, market: str | None = None, year: int | None = None,
    month: int | None = None,
) -> Path:
    """`parquet/{table}/market=JP/year=2026/month=08`。

    パーティションを深くしすぎない（3階層まで。docs/15-windows-runtime.md §5.6）。
    """
    p = root / safe_component(table)
    if market is not None:
        p = p / f"market={safe_component(market)}"
    if year is not None:
        p = p / f"year={year:04d}"
    if month is not None:
        p = p / f"month={month:02d}"
    return p


def assert_windows_safe(path: Path, *, relative_to: Path | None = None) -> None:
    """パスの各要素が Windows で使えることを検証する。"""
    target = path.relative_to(relative_to) if relative_to else path
    bad = [part for part in target.parts if not is_valid_path_component(part)]
    if bad:
        raise ValueError(
            f"Windows で使えないパス要素が含まれています: {bad}（{path}）。"
            "詳細: docs/15-windows-runtime.md §5"
        )


__all__ = [
    "WINDOWS_FORBIDDEN_CHARS",
    "WINDOWS_RESERVED_NAMES",
    "assert_windows_safe",
    "doc_blob_name",
    "is_valid_path_component",
    "parquet_partition_path",
    "raw_path",
    "safe_component",
    "timestamp_component",
]
