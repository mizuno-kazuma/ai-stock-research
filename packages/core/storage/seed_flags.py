"""シード表示と本番データの境界（seed.is_seed_data）。

空倉庫の初回起動では `docs/ui/sample-data.json` を出してよい。
Collector が非シードの価格（または推奨）を upsert したらフラグを下ろし、
以降は倉庫を正とする。payload の `_meta` だけでは live 判定しない。
"""

from __future__ import annotations

from typing import Any

SEED_DATA_KEY = "seed.is_seed_data"
LIVE_DATA_KEY = "warehouse.has_live_data"


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def is_serving_seed(state: Any) -> bool:
    """UI / API が sample JSON を本番扱いで出してよいか。"""
    getter = getattr(state, "get_setting", None)
    if not callable(getter):
        return False
    if _as_bool(getter(LIVE_DATA_KEY, False)):
        return False
    return _as_bool(getter(SEED_DATA_KEY, False))


def should_load_seed_payload(state: Any) -> bool:
    return is_serving_seed(state)


def mark_live_ingest(state: Any, *, rows: int = 1) -> bool:
    """Collector が非シード行を upsert したあと呼ぶ。seed 表示を止める。"""
    if rows <= 0:
        return False
    setter = getattr(state, "set_setting", None)
    if not callable(setter):
        return False
    setter(LIVE_DATA_KEY, True)
    setter(SEED_DATA_KEY, False)
    return True
