"""LLM に渡さない情報のフィルタ（docs/07-llm-rag.md §7）。

保有している事実（is_held）は渡してよい。数量と金額は渡さない。
"""

from __future__ import annotations

from typing import Any

from packages.core.llm.errors import SensitiveDataInPromptError

SENSITIVE_KEYS = {
    "quantity",
    "qty",
    "shares",
    "avg_cost",
    "average_cost",
    "acquisition_price",
    "market_value",
    "position_value",
    "total_assets",
    "cash",
    "cash_balance",
    "nisa",
    "account_type",
    "unrealized_pnl",  # 金額。pct は許可
}


def assert_no_sensitive_data(payload: Any, *, path: str = "") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            lowered = str(key).lower()
            next_path = f"{path}.{key}" if path else str(key)
            if lowered in SENSITIVE_KEYS:
                raise SensitiveDataInPromptError(f"機密キーがプロンプトに含まれています: {next_path}")
            if lowered in {"positions", "portfolio", "trade", "nested", "deep"}:
                assert_no_sensitive_data(value, path=next_path)
            else:
                assert_no_sensitive_data(value, path=next_path)
        return
    if isinstance(payload, list):
        for i, item in enumerate(payload):
            assert_no_sensitive_data(item, path=f"{path}[{i}]")


def redact_portfolio(positions: list[Any]) -> list[dict[str, Any]]:
    """比率のみを渡す。数量・取得単価・評価額は含めない。"""
    values: list[tuple[str, float, float]] = []
    for p in positions:
        if isinstance(p, dict):
            ticker = str(p.get("ticker", ""))
            mv = float(p.get("market_value") or 0.0)
            pnl = float(p.get("unrealized_pnl_pct") or 0.0)
        else:
            ticker = str(getattr(p, "ticker", ""))
            mv = float(getattr(p, "market_value", 0.0) or 0.0)
            pnl = float(getattr(p, "unrealized_pnl_pct", 0.0) or 0.0)
        values.append((ticker, mv, pnl))
    total = sum(v for _, v, _ in values) or 1.0
    return [
        {
            "ticker": ticker,
            "weight_pct": round(mv / total * 100.0, 1),
            "unrealized_pnl_pct": round(pnl, 1),
        }
        for ticker, mv, pnl in values
    ]
