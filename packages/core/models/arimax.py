"""為替予測: ランダムウォーク / ARIMAX / VECM と Diebold-Mariano 検定。

docs/04-analysis-engine.md §2。短期予測はランダムウォークに勝つのが極めて
難しい。すべてのモデルは点推定 + 信頼区間を返し、毎日 DM 検定を通す。
通らなければ beats_baseline=False として「優位性なし」と表示する。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

import numpy as np
import pandas as pd

from packages.core.models._norm import norm_cdf, norm_ppf
from packages.core.models.errors import InsufficientHistoryError

Pair = Literal["USDJPY"]
DM_WINDOW = 60


@dataclass(frozen=True, slots=True)
class Forecast:
    """点推定 + 信頼区間。区間なしの予測は作らない。"""

    point: float
    lo: float
    hi: float
    alpha: float = 0.05
    notes: str = ""


@dataclass(frozen=True, slots=True)
class DMResult:
    stat: float
    pvalue: float
    better: Literal["model", "baseline"]
    beats_baseline: bool
    note: str = ""


@dataclass(frozen=True, slots=True)
class FxForecastBundle:
    as_of: date
    pair: str
    horizon: int
    random_walk: Forecast
    arimax: Forecast | None
    vecm: Forecast | None
    dm: DMResult | None
    garch_vol_ann: float | None = None
    directional_accuracy_60d: float | None = None
    notes: str = ""

    def as_rows(self) -> list[dict[str, Any]]:
        rows = []
        for model_id, fc in (
            ("random_walk", self.random_walk),
            ("arimax", self.arimax),
            ("vecm", self.vecm),
        ):
            if fc is None:
                continue
            rows.append(
                {
                    "as_of": self.as_of,
                    "pair": self.pair,
                    "horizon_days": self.horizon,
                    "model_id": model_id,
                    "point": fc.point,
                    "ci_lo": fc.lo,
                    "ci_hi": fc.hi,
                    "alpha": fc.alpha,
                    "beats_baseline": (
                        False
                        if model_id == "random_walk"
                        else bool(self.dm.beats_baseline)
                        if self.dm is not None
                        else False
                    ),
                    "dm_pvalue": None if self.dm is None else self.dm.pvalue,
                    "garch_vol_ann": self.garch_vol_ann,
                    "directional_accuracy_60d": self.directional_accuracy_60d,
                    "notes": fc.notes or self.notes,
                }
            )
        return rows


def random_walk_forecast(
    spot: float,
    *,
    sigma_daily: float,
    horizon: int,
    alpha: float = 0.05,
) -> Forecast:
    """forecast[t+h] = spot[t]、区間は z * sigma * sqrt(h)。"""
    if not np.isfinite(spot) or spot <= 0:
        raise ValueError("spot は正の有限値である必要があります")
    z = float(norm_ppf(1.0 - alpha / 2.0))
    width = z * abs(sigma_daily) * np.sqrt(horizon)
    return Forecast(
        point=float(spot),
        lo=float(spot - width),
        hi=float(spot + width),
        alpha=alpha,
        notes="random_walk: forecast=spot, CI=z*sigma*sqrt(h)",
    )


def diebold_mariano(
    e1: np.ndarray,
    e2: np.ndarray,
    h: int,
    *,
    loss: str = "squared",
    alpha: float = 0.05,
) -> DMResult:
    """e1: 検証モデルの予測誤差, e2: ベースライン(RW)の予測誤差。

    帰無仮説: 両モデルの予測精度は等しい。
    h 期先予測では誤差に系列相関が入るため HAC（Newey-West）分散を使う。
    Harvey-Leybourne-Newbold の小標本補正を適用する。
    """
    a = np.asarray(e1, dtype=float)
    b = np.asarray(e2, dtype=float)
    if a.shape != b.shape:
        raise ValueError("誤差系列の長さが一致しません")
    mask = np.isfinite(a) & np.isfinite(b)
    a, b = a[mask], b[mask]
    n = int(a.size)
    if n < 8:
        return DMResult(
            stat=float("nan"),
            pvalue=float("nan"),
            better="baseline",
            beats_baseline=False,
            note="サンプル不足",
        )
    if loss == "squared":
        d = a**2 - b**2
    elif loss == "absolute":
        d = np.abs(a) - np.abs(b)
    else:
        raise ValueError(f"未知の loss: {loss}")
    d_bar = float(d.mean())
    if np.allclose(d, 0.0):
        return DMResult(stat=0.0, pvalue=1.0, better="baseline", beats_baseline=False)
    lags = max(int(h) - 1, 0)
    gamma0 = float(np.mean((d - d_bar) ** 2))
    gamma_sum = 0.0
    for k in range(1, lags + 1):
        # Bartlett 重みの Newey-West。
        w = 1.0 - k / (lags + 1)
        cov = float(np.mean((d[k:] - d_bar) * (d[:-k] - d_bar)))
        gamma_sum += w * cov
    var_d = (gamma0 + 2.0 * gamma_sum) / n
    if var_d <= 0:
        return DMResult(
            stat=0.0,
            pvalue=1.0,
            better="baseline",
            beats_baseline=False,
            note="非正の分散推定",
        )
    dm = d_bar / np.sqrt(var_d)
    hln = np.sqrt(max((n + 1 - 2 * h + h * (h - 1) / n) / n, 0.0))
    dm_adj = float(dm * hln)
    # t 分布の両側 p 値を正規で近似（n が大きい前提。HLN 補正済み）。
    pvalue = float(2.0 * (1.0 - _t_cdf(abs(dm_adj), df=n - 1)))
    better: Literal["model", "baseline"] = "model" if d_bar < 0 else "baseline"
    beats = bool(pvalue < alpha and better == "model")
    return DMResult(stat=dm_adj, pvalue=pvalue, better=better, beats_baseline=beats)


def naive_dm_pvalue(e1: np.ndarray, e2: np.ndarray) -> float:
    """HAC なしの DM p 値。テストで HAC の方が大きいことを確認するために使う。"""
    a = np.asarray(e1, dtype=float)
    b = np.asarray(e2, dtype=float)
    d = a**2 - b**2
    d_bar = float(d.mean())
    var = float(d.var(ddof=1) / d.size)
    if var <= 0:
        return float("nan")
    z = abs(d_bar / np.sqrt(var))
    return float(2.0 * (1.0 - norm_cdf(z)))


def fit_arimax(
    endog: pd.Series,
    exog: pd.DataFrame | None,
    *,
    horizon: int,
    alpha: float = 0.05,
) -> Forecast:
    """log(USDJPY) に対する ARIMAX(1,1,1)。外生変数の将来値は最終値を保持。

    statsmodels があれば SARIMAX を使い、無ければ差分の OLS（ARX）に落ちる。
    """
    y = pd.to_numeric(endog, errors="coerce").dropna()
    if y.size < 60:
        raise InsufficientHistoryError("ARIMAX には 60 点以上必要です")
    exog_aligned = None
    if exog is not None and not exog.empty:
        exog_aligned = exog.reindex(y.index).ffill()
    try:
        return _fit_sarimax(y, exog_aligned, horizon=horizon, alpha=alpha)
    except Exception:
        return _fit_arx_ols(y, exog_aligned, horizon=horizon, alpha=alpha)


def fit_vecm(
    data: pd.DataFrame,
    *,
    horizon: int,
    alpha: float = 0.05,
    columns: tuple[str, str] = ("log_usdjpy", "rate_diff_10y"),
) -> Forecast | None:
    """Johansen 検定で共和分がある場合のみ VECM を使う。検出されなければ None。"""
    try:
        from statsmodels.tsa.vector_ar.vecm import VECM, coint_johansen
    except (ImportError, OSError):
        return None
    work = data.loc[:, list(columns)].dropna()
    if len(work) < 80:
        return None
    jres = coint_johansen(work.to_numpy(), det_order=0, k_ar_diff=2)
    # trace 統計量が 5% 臨界値を超えるランクを数える。
    rank = int(np.sum(jres.lr1 > jres.cvt[:, 1]))
    if rank == 0:
        return None
    model = VECM(work, k_ar_diff=2, coint_rank=rank, deterministic="ci")
    res = model.fit()
    pred = np.asarray(res.predict(steps=horizon))
    point = float(np.exp(pred[-1, 0])) if columns[0].startswith("log_") else float(pred[-1, 0])
    resid = np.asarray(res.resid)[:, 0]
    sigma = float(np.std(resid, ddof=1))
    z = float(norm_ppf(1.0 - alpha / 2.0))
    width = z * sigma * np.sqrt(horizon)
    lo = float(np.exp(pred[-1, 0] - width)) if columns[0].startswith("log_") else point - width
    hi = float(np.exp(pred[-1, 0] + width)) if columns[0].startswith("log_") else point + width
    return Forecast(point=point, lo=lo, hi=hi, alpha=alpha, notes=f"vecm rank={rank}")


def forecast_fx(
    *,
    as_of: date,
    spot: pd.Series,
    exog: pd.DataFrame | None = None,
    horizon: int = 5,
    pair: str = "USDJPY",
    sigma_garch_daily: float | None = None,
    model_errors: np.ndarray | None = None,
    rw_errors: np.ndarray | None = None,
) -> FxForecastBundle:
    """RW は常に出し、ARIMAX / VECM はデータが揃えば出す。外生欠損時は RW のみ。"""
    spot_clean = pd.to_numeric(spot, errors="coerce").dropna()
    if spot_clean.empty:
        raise InsufficientHistoryError("為替スポットが空です")
    last = float(spot_clean.iloc[-1])
    log_ret = np.diff(np.log(spot_clean.to_numpy()))
    sigma = (
        float(sigma_garch_daily)
        if sigma_garch_daily is not None
        else float(np.std(log_ret[-60:], ddof=1) * last)
        if log_ret.size >= 20
        else float(last * 0.005)
    )
    # random_walk の sigma は水準単位。対数リターン σ * spot。
    rw = random_walk_forecast(last, sigma_daily=sigma, horizon=horizon)
    arimax_fc: Forecast | None = None
    vecm_fc: Forecast | None = None
    notes = []
    if exog is None or exog.empty:
        notes.append("外生変数欠損のためランダムウォークのみ")
    else:
        try:
            log_spot = np.log(spot_clean)
            arimax_fc = fit_arimax(log_spot, exog, horizon=horizon)
            # log 予測を水準に戻す。
            arimax_fc = Forecast(
                point=float(np.exp(arimax_fc.point)),
                lo=float(np.exp(arimax_fc.lo)),
                hi=float(np.exp(arimax_fc.hi)),
                alpha=arimax_fc.alpha,
                notes="exog 将来値は最終値を保持する仮定。" + arimax_fc.notes,
            )
        except Exception as exc:
            notes.append(f"ARIMAX 失敗: {type(exc).__name__}")
        vecm_data = pd.DataFrame({"log_usdjpy": np.log(spot_clean)})
        if "rate_diff_10y" in exog.columns:
            vecm_data["rate_diff_10y"] = exog["rate_diff_10y"].reindex(spot_clean.index)
            vecm_fc = fit_vecm(vecm_data, horizon=horizon)

    dm = None
    if model_errors is not None and rw_errors is not None:
        dm = diebold_mariano(model_errors, rw_errors, h=horizon)

    da = _directional_accuracy(spot_clean, horizon=horizon, window=DM_WINDOW)
    return FxForecastBundle(
        as_of=as_of,
        pair=pair,
        horizon=horizon,
        random_walk=rw,
        arimax=arimax_fc,
        vecm=vecm_fc,
        dm=dm,
        garch_vol_ann=float(sigma / last * np.sqrt(252)) if last else None,
        directional_accuracy_60d=da,
        notes="; ".join(notes),
    )


def _directional_accuracy(spot: pd.Series, *, horizon: int, window: int) -> float | None:
    if spot.size < window + horizon + 1:
        return None
    values = spot.to_numpy(dtype=float)
    hits = []
    start = len(values) - window - horizon
    for i in range(max(start, 0), len(values) - horizon):
        pred_sign = 0.0  # RW は変化なし。方向的中は「動かない」を当てたことにしない。
        realized = values[i + horizon] - values[i]
        # RW の方向的中は定義上ほぼ 0.5 に近づく（符号がランダム）。
        hits.append(1.0 if realized * pred_sign > 0 else 0.0 if realized != 0 else 0.5)
    if not hits:
        return None
    return float(np.mean(hits))


def _fit_sarimax(
    y: pd.Series, exog: pd.DataFrame | None, *, horizon: int, alpha: float
) -> Forecast:
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    model = SARIMAX(
        endog=y.to_numpy(dtype=float),
        exog=None if exog is None else exog.to_numpy(dtype=float),
        order=(1, 1, 1),
        trend="n",
        enforce_stationarity=True,
        enforce_invertibility=True,
    )
    res = model.fit(disp=False)
    if exog is None:
        exog_future = None
    else:
        last = exog.iloc[[-1]].to_numpy(dtype=float)
        exog_future = np.repeat(last, horizon, axis=0)
    fc = res.get_forecast(steps=horizon, exog=exog_future)
    mean = np.asarray(fc.predicted_mean)
    ci = np.asarray(fc.conf_int(alpha=alpha))
    return Forecast(
        point=float(mean[-1]),
        lo=float(ci[-1, 0]),
        hi=float(ci[-1, 1]),
        alpha=alpha,
        notes="exog 将来値は最終値を保持する仮定",
    )


def _fit_arx_ols(
    y: pd.Series, exog: pd.DataFrame | None, *, horizon: int, alpha: float
) -> Forecast:
    """Δy_t = c + φ Δy_{t-1} + β x_t + e。将来の x は最終値保持。"""
    dy = np.diff(y.to_numpy(dtype=float))
    lag = dy[:-1]
    target = dy[1:]
    cols = [np.ones(len(target)), lag]
    if exog is not None:
        x = exog.to_numpy(dtype=float)[2:]
        if x.ndim == 1:
            x = x.reshape(-1, 1)
        n = min(len(target), len(x))
        target = target[-n:]
        cols = [c[-n:] for c in cols]
        cols.append(x[-n:])
    X = np.column_stack(cols)
    beta, *_ = np.linalg.lstsq(X, target, rcond=None)
    resid = target - X @ beta
    sigma = float(np.std(resid, ddof=max(len(beta), 1)))
    last_dy = float(dy[-1])
    last_x = None if exog is None else exog.to_numpy(dtype=float)[-1]
    level = float(y.iloc[-1])
    for _ in range(horizon):
        row = [1.0, last_dy]
        if last_x is not None:
            row.extend(np.atleast_1d(last_x).tolist())
        d_hat = float(np.dot(beta, row[: len(beta)]))
        level = level + d_hat
        last_dy = d_hat
    z = float(norm_ppf(1.0 - alpha / 2.0))
    width = z * sigma * np.sqrt(horizon)
    return Forecast(
        point=level,
        lo=level - width,
        hi=level + width,
        alpha=alpha,
        notes="ARX-OLS fallback（statsmodels なし）。exog 将来値は最終値保持",
    )


def _t_cdf(x: float, df: int) -> float:
    """正規近似 + 自由度補正。scipy なしで DM の p 値を出す。"""
    if df <= 0:
        return norm_cdf(x)
    # 正規への補正: Var(t) = df/(df-2)
    if df > 2:
        scale = np.sqrt(df / (df - 2.0))
        return norm_cdf(x / scale)
    return norm_cdf(x)
