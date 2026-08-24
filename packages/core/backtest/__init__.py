"""バックテスト（Purged Walk-Forward 前提、コスト必須、DSR 必須）。"""

from packages.core.backtest.costs import participation_slippage_bps, round_trip_cost_bps
from packages.core.backtest.dsr import DSRResult, deflated_sharpe_ratio
from packages.core.backtest.engine import BacktestError, BacktestResult, run_backtest
from packages.core.backtest.metrics import (
    Drawdown,
    annualize_return,
    calmar_ratio,
    information_ratio,
    max_drawdown,
    sharpe_ratio,
    sortino_ratio,
)

__all__ = [
    "BacktestError",
    "BacktestResult",
    "DSRResult",
    "Drawdown",
    "annualize_return",
    "calmar_ratio",
    "deflated_sharpe_ratio",
    "information_ratio",
    "max_drawdown",
    "participation_slippage_bps",
    "round_trip_cost_bps",
    "run_backtest",
    "sharpe_ratio",
    "sortino_ratio",
]
