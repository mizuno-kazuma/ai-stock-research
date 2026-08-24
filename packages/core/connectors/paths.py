"""Windows 互換のパス生成。

WSL2 内で動かすが、同じファイルを Windows 側から触る可能性があるため
`:` `?` `*` などを含めない。詳細は docs/15-windows-runtime.md と
.cursor/skills/add-data-source/references/naming-and-encoding.md。
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

FORBIDDEN_CHARS = frozenset('<>:"/\\|?*')
RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)
MAX_PATH_LEN = 260


def safe_component(value: str) -> str:
    """パス1要素として安全な文字列に変換する。"""
    cleaned = "".join("_" if ch in FORBIDDEN_CHARS or ord(ch) < 32 else ch for ch in value)
    cleaned = cleaned.rstrip(". ")
    if cleaned.upper().split(".")[0] in RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned or "_"


def is_valid_path_component(name: str) -> bool:
    """Windows で使えるパス要素かどうか（T-ENV-02）。"""
    if not name:
        return False
    if set(name) & FORBIDDEN_CHARS:
        return False
    if any(ord(ch) < 32 for ch in name):
        return False
    if name != name.rstrip(". "):
        return False
    return name.upper().split(".")[0] not in RESERVED_NAMES


def timestamp_component(dt: datetime) -> str:
    """コロンを含まない時刻要素（`HHmmss`）。"""
    return dt.strftime("%H%M%S")


def partition_component(key: str, value: str) -> str:
    """`market=JP` のようなパーティション要素。`=` は Windows で許容される。"""
    return f"{safe_component(key)}={safe_component(value)}"


def raw_path(
    data_dir: Path,
    *,
    source: str,
    endpoint: str,
    dt: date,
    fetched_at: datetime,
    seq: int,
    ext: str = "json.gz",
) -> Path:
    """`data/raw/{source}/{endpoint}/dt=YYYY-MM-DD/{HHmmss}_{seq:04d}.{ext}`"""
    return (
        Path(data_dir)
        / "raw"
        / safe_component(source)
        / safe_component(endpoint)
        / f"dt={dt:%Y-%m-%d}"
        / f"{timestamp_component(fetched_at)}_{seq:04d}.{safe_component(ext)}"
    )


def blob_path(data_dir: Path, *, source: str, doc_id: str, ext: str) -> Path:
    """PDF / XBRL ZIP など JSON 以外の格納先。

    `doc_id` に `:` が含まれる（`edinet:S100XXXX`）ため置換が必須。
    日本語タイトルをファイル名に使わない（文字コード事故の温床）。
    """
    safe_id = safe_component(doc_id.replace(":", "_"))
    return Path(data_dir) / "raw" / safe_component(source) / "blobs" / f"{safe_id}.{ext.lstrip('.')}"


def parquet_partition_path(
    data_dir: Path, *, table: str, partitions: dict[str, str], part: int = 0
) -> Path:
    p = Path(data_dir) / "warehouse" / "parquet" / safe_component(table)
    for key, value in partitions.items():
        p = p / partition_component(key, value)
    return p / f"part-{part:04d}.parquet"


def assert_path_is_windows_safe(path: Path) -> None:
    """パス全体を検査する。テストとバッチの両方から呼ぶ。"""
    bad = [part for part in path.parts if not _is_ok_part(part)]
    if bad:
        raise ValueError(f"Windows で使えないパス要素があります: {bad} (path={path})")
    if len(str(path)) > MAX_PATH_LEN:
        raise ValueError(f"パスが {MAX_PATH_LEN} 文字を超えています: {len(str(path))} 文字")


def _is_ok_part(part: str) -> bool:
    # ドライブレターやルート（'C:\\', '/'）は検査対象外。
    if part in ("/", "\\") or (len(part) == 2 and part.endswith(":")):
        return True
    # `market=JP` / `dt=2026-08-23` は '=' を含むが許容する。
    return is_valid_path_component(part)
