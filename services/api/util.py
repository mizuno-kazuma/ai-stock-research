"""日時・リスト・JSON の正規化。"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any, Literal
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
#: 設定 `ui.default_market=auto` の切替時刻（docs/ui/screens/10-settings.md）。
AUTO_MARKET_SWITCH_HOUR_JST = 15


def resolve_market(market: str | None, *, now: dt.datetime | None = None) -> Literal["JP", "US"]:
    """クエリの market を API が受け付ける JP / US にする。

    `auto` は日本時間 15 時未満を JP、それ以降を US とする。
    未指定・不明な値は JP。
    """
    if market == "JP" or market == "US":
        return market
    if market == "auto":
        if now is None:
            current = dt.datetime.now(JST)
        elif now.tzinfo is None:
            current = now.replace(tzinfo=JST)
        else:
            current = now.astimezone(JST)
        return "JP" if current.hour < AUTO_MARKET_SWITCH_HOUR_JST else "US"
    return "JP"


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def as_utc(value: dt.datetime | dt.date | str | None) -> dt.datetime | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=dt.UTC)
        return value.astimezone(dt.UTC)
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time.min, tzinfo=dt.UTC)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        try:
            return dt.datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=dt.UTC)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def as_date(value: dt.datetime | dt.date | str | None) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return as_utc(value).date() if value else None  # type: ignore[union-attr]
    if isinstance(value, dt.date):
        return value
    parsed = as_utc(value)
    return parsed.date() if parsed else None


def as_iso(value: dt.datetime | dt.date | str | None) -> str | None:
    parsed = as_utc(value)
    if parsed is None:
        return None
    return parsed.isoformat().replace("+00:00", "Z")


def split_csv(value: str | None) -> list[str] | None:
    if value is None or value == "":
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("[") or text.startswith("{"):
            try:
                loaded = json.loads(text)
            except json.JSONDecodeError:
                return [text]
            if isinstance(loaded, list):
                return loaded
            return [loaded]
        return [text]
    return [value]


def as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(loaded) if isinstance(loaded, dict) else {}
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dict(dump(mode="python"))
    return {}


def parse_range_start(range_key: str, *, as_of: dt.date | None = None) -> dt.date:
    """`1y` / `5y` / `6m` / `3m` / `1m` を開始日に変換する。"""
    end = as_of or dt.date.today()
    mapping = {
        "1m": dt.timedelta(days=31),
        "3m": dt.timedelta(days=93),
        "6m": dt.timedelta(days=186),
        "1y": dt.timedelta(days=365),
        "5y": dt.timedelta(days=365 * 5),
        "max": dt.timedelta(days=365 * 30),
    }
    delta = mapping.get(range_key, dt.timedelta(days=365))
    return end - delta
