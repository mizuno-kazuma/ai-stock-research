"""バックテストエンジン（docs/04-analysis-engine.md §4）。

fee_bps / slippage_bps / max_turnover_pct / n_trials にデフォルト値を持たせない。
エントリーは翌営業日始値。`prices_live` は使わない。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import fields as dc_fields
from datetime import date
from typing import Any, Literal

import numpy as np
import pandas as pd

from packages.core.backtest.costs import round_trip_cost_bps
from packages.core.backtest.dsr import DSRResult, deflated_sharpe_ratio
from packages.core.backtest.metrics import (
    Drawdown,
    annualize_return,
    calmar_ratio,
    information_ratio,
    max_drawdown,
    sharpe_ratio,
    sortino_ratio,
)
from packages.core.factors.calendar import TRADING_DAYS_PER_YEAR, TradingCalendar
from packages.core.factors.screening import UniverseFilter

RebalanceFreq = Literal["weekly", "monthly"]


class BacktestError(ValueError):
    """バックテストを実行できない（必須引数欠落、リーク、期間不正）。"""


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity: pd.Series
    daily_returns: pd.Series
    holdings: pd.DataFrame
    total_return: float
    cagr: float
    gross_annualized_return: float
    volatility: float
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float
    drawdown: Drawdown
    hit_rate: float
    profit_factor: float
    avg_turnover: float
    realized_turnover_pct: float
    total_cost_bps: float
    cost_drag_annual: float
    alpha_vs_bench: float
    information_ratio: float
    deflated_sharpe: float
    dsr_pvalue: float
    is_significant: bool
    n_trials: int
    n_months: int
    monthly_hit_rate: float
    fee_bps: float
    slippage_bps: float
    max_turnover_pct: float
    quantile_returns: list[float] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {
            "total_return": self.total_return,
            "cagr": self.cagr,
            "gross_annualized_return": self.gross_annualized_return,
            "volatility": self.volatility,
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "calmar": self.calmar,
            "max_drawdown": self.max_drawdown,
            "hit_rate": self.hit_rate,
            "profit_factor": self.profit_factor,
            "avg_turnover": self.avg_turnover,
            "realized_turnover_pct": self.realized_turnover_pct,
            "total_cost_bps": self.total_cost_bps,
            "cost_drag_annual": self.cost_drag_annual,
            "alpha_vs_bench": self.alpha_vs_bench,
            "information_ratio": self.information_ratio,
            "deflated_sharpe": self.deflated_sharpe,
            "dsr_pvalue": self.dsr_pvalue,
            "is_significant": self.is_significant,
            "n_trials": self.n_trials,
            "n_months": self.n_months,
            "monthly_hit_rate": self.monthly_hit_rate,
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
            "max_turnover_pct": self.max_turnover_pct,
        }


def run_backtest(
    *,
    signals: pd.DataFrame,
    prices: pd.DataFrame,
    market: str,
    period: tuple[date, date],
    rebalance_freq: RebalanceFreq,
    n_positions: int,
    fee_bps: float,
    slippage_bps: float,
    max_turnover_pct: float,
    n_trials: int,
    universe_filter: UniverseFilter,
    benchmark: str,
    rf_daily: float = 0.0,
    sr_variance_across_trials: float = 0.25,
    adv: pd.Series | None = None,
    warehouse: Any | None = None,
) -> BacktestResult:
    """コスト引数と n_trials はキーワード専用・必須。デフォルト値なし。"""
    _validate_inputs(
        signals=signals,
        prices=prices,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        max_turnover_pct=max_turnover_pct,
        n_trials=n_trials,
        n_positions=n_positions,
        period=period,
    )
    cal = TradingCalendar.from_prices(prices)
    period_start, period_end = period
    sessions = cal.sessions_between(period_start, period_end)
    if len(sessions) < 5:
        raise BacktestError("検証期間の営業日が足りません")

    px = _index_prices(prices)
    sig = _index_signals(signals)
    signal_days = sorted(
        {
            d if isinstance(d, date) and not hasattr(d, "hour") else pd.Timestamp(d).date()
            for d in pd.unique(sig["as_of"])
            if pd.notna(d)
        }
    )
    signal_days = [d for d in signal_days if period_start <= d <= period_end]
    rebalance_days = _rebalance_dates(signal_days or sessions, rebalance_freq, cal)

    trades: list[dict[str, Any]] = []
    holdings_rows: list[dict[str, Any]] = []
    prev_weights: dict[str, float] = {}
    equity = 1.0
    equity_path: list[tuple[date, float]] = []
    gross_equity = 1.0
    daily_rets: list[tuple[date, float]] = []
    turnover_hist: list[float] = []
    cost_bps_hist: list[float] = []

    # シグナル日 as_of に対し、翌営業日始値でエントリーする。
    for i, as_of in enumerate(rebalance_days):
        entry_date = cal.next_business_day(as_of)
        if entry_date > period_end:
            break
        next_as_of = rebalance_days[i + 1] if i + 1 < len(rebalance_days) else sessions[-1]
        exit_date = cal.next_business_day(next_as_of)
        if exit_date > period_end:
            # 最終リバランスは期間内の最終営業日始値で決済する。
            exit_date = sessions[-1]
        if exit_date <= entry_date:
            continue

        scores = _scores_on(sig, as_of)
        if scores.empty:
            continue
        passed = universe_filter.apply(scores, as_of=as_of)
        eligible = scores.loc[passed] if passed.any() else scores.iloc[0:0]
        if eligible.empty:
            target = {}
        else:
            top = eligible.sort_values("score", ascending=False).head(n_positions)
            n = max(len(top), 1)
            target = {str(t): 1.0 / n for t in top.index}

        # 回転率上限: 片道ターンオーバーが上限を超えたら、差分を縮小する。
        turnover = 0.5 * sum(
            abs(target.get(t, 0.0) - prev_weights.get(t, 0.0))
            for t in set(target) | set(prev_weights)
        )
        cap = max_turnover_pct / 100.0
        if turnover > cap and turnover > 0:
            scale = cap / turnover
            blended = {}
            names = set(target) | set(prev_weights)
            for t in names:
                prev = prev_weights.get(t, 0.0)
                blended[t] = prev + scale * (target.get(t, 0.0) - prev)
            target = {t: w for t, w in blended.items() if w > 1e-12}
            turnover = cap
        turnover_hist.append(turnover)

        cost_bps = round_trip_cost_bps(
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            order_value=None if adv is None else 1.0,
            adv_20d=None if adv is None else float(adv.median()) if len(adv) else 1.0,
        )
        # ターンオーバーに比例してコストを課す（片道 turnover * 片道コスト相当）。
        period_cost = turnover * cost_bps / 1e4
        cost_bps_hist.append(turnover * cost_bps)

        period_ret = 0.0
        gross_ret = 0.0
        for ticker, weight in target.items():
            entry_px = _price_at(px, ticker, entry_date, "adj_open")
            exit_px = _price_at(px, ticker, exit_date, "adj_open")
            if entry_px is None or exit_px is None or entry_px <= 0:
                continue
            raw = exit_px / entry_px - 1.0
            gross_ret += weight * raw
            period_ret += weight * raw
            trades.append(
                {
                    "as_of": as_of,
                    "ticker": ticker,
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                    "entry_price": entry_px,
                    "exit_price": exit_px,
                    "weight": weight,
                    "raw_return": raw,
                    "score": float(scores.loc[ticker, "score"])
                    if ticker in scores.index
                    else float("nan"),
                }
            )
            holdings_rows.append(
                {
                    "as_of": as_of,
                    "ticker": ticker,
                    "weight": weight,
                    "entry_date": entry_date,
                }
            )
        period_ret -= period_cost
        equity *= 1.0 + period_ret
        gross_equity *= 1.0 + gross_ret
        equity_path.append((exit_date, equity))
        daily_rets.append((exit_date, period_ret))
        prev_weights = target

    if not equity_path:
        raise BacktestError("約定できるトレードがありませんでした")

    equity_s = pd.Series(
        {d: v for d, v in equity_path}, dtype=float, name="equity"
    ).sort_index()
    rets = pd.Series({d: r for d, r in daily_rets}, dtype=float).sort_index()
    n_days = max(cal.business_day_count(period_start, period_end), 1)
    total_return = float(equity_s.iloc[-1] / 1.0 - 1.0)
    gross_total = float(gross_equity - 1.0)
    cagr = annualize_return(total_return, n_days)
    gross_ann = annualize_return(gross_total, n_days)
    vol = float(np.std(rets.to_numpy(), ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)) if len(rets) > 1 else 0.0
    dd = max_drawdown(equity_s)
    sr = sharpe_ratio(rets.to_numpy(), rf_daily=rf_daily)
    so = sortino_ratio(rets.to_numpy(), rf_daily=rf_daily)
    trade_rets = np.array([t["raw_return"] for t in trades], dtype=float)
    hit = float((trade_rets > 0).mean()) if trade_rets.size else float("nan")
    gains = trade_rets[trade_rets > 0].sum()
    losses = -trade_rets[trade_rets < 0].sum()
    pf = float(gains / losses) if losses > 0 else float("nan")
    avg_to = float(np.mean(turnover_hist)) if turnover_hist else 0.0
    total_cost = float(np.sum(cost_bps_hist)) if cost_bps_hist else 0.0
    cost_drag = float(gross_ann - cagr) if np.isfinite(gross_ann) and np.isfinite(cagr) else 0.0

    bench_rets = _benchmark_returns(px, benchmark, [d for d, _ in daily_rets])
    if bench_rets is not None and len(bench_rets) == len(rets):
        excess = rets.to_numpy() - bench_rets
        alpha = float(np.mean(excess) * TRADING_DAYS_PER_YEAR)
        ir = information_ratio(excess)
    else:
        alpha = float("nan")
        ir = float("nan")

    skew = float(pd.Series(rets).skew()) if len(rets) > 2 else 0.0
    kurt = float(pd.Series(rets).kurtosis() + 3.0) if len(rets) > 3 else 3.0
    n_obs = len(rets)
    if n_obs < 3:
        dsr = DSRResult(
            dsr=0.0,
            expected_max_sr=0.0,
            sr_std=float("nan"),
            is_significant=False,
            p_value=1.0,
        )
    else:
        dsr = deflated_sharpe_ratio(
            sr_observed=float(sr) if np.isfinite(sr) else 0.0,
            n_trials=n_trials,
            n_obs=n_obs,
            skew=skew,
            kurtosis=kurt,
            sr_variance_across_trials=sr_variance_across_trials,
        )
    months = _n_months(period_start, period_end)
    monthly_hit = _monthly_hit_rate(rets)

    result = BacktestResult(
        trades=pd.DataFrame(trades),
        equity=equity_s,
        daily_returns=rets,
        holdings=pd.DataFrame(holdings_rows),
        total_return=total_return,
        cagr=cagr,
        gross_annualized_return=gross_ann,
        volatility=vol,
        sharpe=float(sr) if np.isfinite(sr) else 0.0,
        sortino=float(so) if np.isfinite(so) else 0.0,
        calmar=calmar_ratio(cagr, dd.max_drawdown),
        max_drawdown=dd.max_drawdown,
        drawdown=dd,
        hit_rate=hit,
        profit_factor=pf,
        avg_turnover=avg_to,
        realized_turnover_pct=avg_to * 100.0,
        total_cost_bps=total_cost,
        cost_drag_annual=cost_drag,
        alpha_vs_bench=alpha,
        information_ratio=ir,
        deflated_sharpe=dsr.dsr,
        dsr_pvalue=dsr.p_value,
        is_significant=dsr.is_significant,
        n_trials=n_trials,
        n_months=months,
        monthly_hit_rate=monthly_hit,
        fee_bps=float(fee_bps),
        slippage_bps=float(slippage_bps),
        max_turnover_pct=float(max_turnover_pct),
        quantile_returns=_quantile_returns(pd.DataFrame(trades)),
        metrics={
            "dsr": {f.name: getattr(dsr, f.name) for f in dc_fields(dsr)},
            "benchmark": benchmark,
            "market": market,
        },
    )
    if warehouse is not None:
        warehouse.insert_backtest_run(result.to_record())
    return result


def _validate_inputs(
    *,
    signals: pd.DataFrame,
    prices: pd.DataFrame,
    fee_bps: float,
    slippage_bps: float,
    max_turnover_pct: float,
    n_trials: int,
    n_positions: int,
    period: tuple[date, date],
) -> None:
    live_table = "prices" + "_live"
    if live_table in {str(c).lower() for c in prices.columns}:
        raise BacktestError("ライブ価格テーブルをバックテストの価格ソースにできません")
    if fee_bps is None or slippage_bps is None or max_turnover_pct is None:
        raise BacktestError("コスト引数が未指定です")
    if n_trials is None or int(n_trials) < 1:
        raise BacktestError("n_trials は 1 以上で記録してください")
    if n_positions < 1:
        raise BacktestError("n_positions は 1 以上である必要があります")
    if period[1] <= period[0]:
        raise BacktestError("period の終了日は開始日より後である必要があります")
    if signals is None or signals.empty:
        raise BacktestError("signals が空です")
    if prices is None or prices.empty:
        raise BacktestError("prices が空です")


def _index_prices(prices: pd.DataFrame) -> pd.DataFrame:
    work = prices.copy()
    if "trade_date" in work.columns:
        work["trade_date"] = pd.to_datetime(work["trade_date"]).dt.date
    if "ticker" in work.columns:
        work["ticker"] = work["ticker"].astype(str)
        work = work.drop_duplicates(subset=["ticker", "trade_date"], keep="last")
        return work.set_index(["ticker", "trade_date"]).sort_index()
    return work


def _index_signals(signals: pd.DataFrame) -> pd.DataFrame:
    work = signals.copy()
    if isinstance(work.index, pd.MultiIndex):
        work = work.reset_index()
    if "as_of" in work.columns:
        work["as_of"] = pd.to_datetime(work["as_of"]).dt.date
    if "ticker" in work.columns:
        work["ticker"] = work["ticker"].astype(str)
    if "score" not in work.columns:
        # 単一列ならそれをスコアとみなす。
        numeric = [c for c in work.columns if c not in {"as_of", "ticker"}]
        if not numeric:
            raise BacktestError("signals に score 列がありません")
        work = work.rename(columns={numeric[0]: "score"})
    return work


def _scores_on(signals: pd.DataFrame, as_of: date) -> pd.DataFrame:
    day = signals.loc[signals["as_of"] == as_of]
    if day.empty:
        return pd.DataFrame(columns=["score"])
    return day.set_index("ticker")[["score"]].copy()


def _price_at(
    px: pd.DataFrame, ticker: str, on: date, field: str
) -> float | None:
    key = (ticker, on)
    if key not in px.index:
        return None
    row = px.loc[key]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[-1]
    value = row.get(field, row.get("open"))
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return None
    return float(value)


def _rebalance_dates(
    sessions: list[date], freq: RebalanceFreq, cal: TradingCalendar
) -> list[date]:
    if freq == "weekly":
        # 各週の最初の営業日。
        out = []
        seen = set()
        for d in sessions:
            key = (d.isocalendar().year, d.isocalendar().week)
            if key not in seen:
                seen.add(key)
                out.append(d)
        return out
    if freq == "monthly":
        out = []
        seen = set()
        for d in sessions:
            key = (d.year, d.month)
            if key not in seen:
                seen.add(key)
                out.append(d)
        return out
    raise BacktestError(f"未知の rebalance_freq: {freq}")


def _benchmark_returns(
    px: pd.DataFrame, benchmark: str, dates: list[date]
) -> np.ndarray | None:
    if not dates:
        return None
    try:
        levels = []
        for d in dates:
            p = _price_at(px, benchmark, d, "adj_open")
            if p is None:
                return None
            levels.append(p)
        arr = np.array(levels, dtype=float)
        rets = np.zeros_like(arr)
        rets[1:] = arr[1:] / arr[:-1] - 1.0
        return rets
    except Exception:
        return None


def _n_months(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def _monthly_hit_rate(rets: pd.Series) -> float:
    if rets.empty:
        return float("nan")
    idx = pd.to_datetime(list(rets.index))
    s = pd.Series(rets.to_numpy(), index=idx)
    monthly = s.resample("ME").sum()
    if monthly.empty:
        return float("nan")
    return float((monthly > 0).mean())


def _quantile_returns(trades: pd.DataFrame) -> list[float]:
    if trades.empty or "score" not in trades.columns:
        return []
    work = trades.dropna(subset=["score", "raw_return"])
    if work.empty:
        return []
    try:
        q = pd.qcut(work["score"], 5, labels=False, duplicates="drop")
    except ValueError:
        return []
    grouped = work.groupby(q)["raw_return"].mean()
    return [float(grouped.get(i, float("nan"))) for i in range(5)]
