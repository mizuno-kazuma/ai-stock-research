"""発行体の同一性（JP の 4桁と J-Quants 5桁、SCD2 の履歴行）。

検索・推奨一覧はここを通して 1 発行体 1 件にする。
`7203` と `72030`、同じ `13010` の valid_from 違いも同一とみなす。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, TypeVar

T = TypeVar("T", bound=Mapping[str, Any])


def canonical_jp_ticker(ticker: str) -> str:
    """J-Quants の 5 桁（末尾 0）を 4 桁の発行体コードに戻す。

    新コード（`130A`）は 5 文字でも末尾 0 でなければそのまま。
    """
    value = str(ticker or "").strip()
    if len(value) == 5 and value.endswith("0"):
        return value[:4]
    return value


def jp_ticker_aliases(ticker: str) -> tuple[str, ...]:
    """照会用の 4 桁と J-Quants 5 桁の両方。

    EDINET の `secCode` は末尾 0 を落として 4 桁で保存する。画面と
    証券マスタは 5 桁のことがあるので、読み出しは両方を同一銘柄とする。
    `130A` のような英字コードはパディングしない。
    """
    value = str(ticker or "").strip()
    if not value:
        return ()
    aliases = [value]
    canonical = canonical_jp_ticker(value)
    if canonical not in aliases:
        aliases.append(canonical)
    if canonical.isdigit() and len(canonical) == 4:
        padded = canonical + "0"
        if padded not in aliases:
            aliases.append(padded)
    return tuple(aliases)


def issuer_key(market: str | None, ticker: str | None) -> tuple[str, str]:
    m = str(market or "").strip().upper()
    t = str(ticker or "").strip()
    if m == "JP":
        t = canonical_jp_ticker(t)
    return (m, t)


def _has_name(row: Mapping[str, Any], ticker_key: str) -> bool:
    ticker = str(row.get(ticker_key) or "").strip()
    name = str(row.get("name_local") or "").strip()
    return bool(name) and name != ticker


def unique_by_issuer(
    rows: Iterable[T],
    *,
    market_key: str = "market",
    ticker_key: str = "ticker",
    extra_key: str | None = None,
) -> list[T]:
    """先に来た行を残す。名称がある行は、コードだけの行より優先して入れ替える。

    `extra_key` を渡すと（発行体, その値）で畳む。推奨の horizon 向け。
    """
    best: dict[tuple[str, ...], T] = {}
    order: list[tuple[str, ...]] = []
    for row in rows:
        key: tuple[str, ...] = issuer_key(row.get(market_key), row.get(ticker_key))
        if extra_key is not None:
            key = (*key, str(row.get(extra_key) or ""))
        prev = best.get(key)
        if prev is None:
            best[key] = row
            order.append(key)
            continue
        if _has_name(row, ticker_key) and not _has_name(prev, ticker_key):
            best[key] = row
            continue
        prev_ticker = str(prev.get(ticker_key) or "")
        row_ticker = str(row.get(ticker_key) or "")
        if (
            _has_name(row, ticker_key) == _has_name(prev, ticker_key)
            and len(row_ticker) < len(prev_ticker)
        ):
            best[key] = row
    return [best[k] for k in order]
