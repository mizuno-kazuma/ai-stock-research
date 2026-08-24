"""GARCH(1,1) によるボラティリティ予測（docs/04-analysis-engine.md §1.3.1）。

点推定に加え、予測分散からリターンの信頼区間を必ず返す。
収束しない・定常性を満たさない場合は例外にし、呼び出し側が実現ボラへ
フォールバックする。発散した予測値を静かに使うのが最も危険である。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from packages.core.factors.calendar import TRADING_DAYS_PER_YEAR
from packages.core.models._norm import norm_ppf
from packages.core.models.errors import (
    GarchConvergenceError,
    GarchNonStationaryError,
    InsufficientHistoryError,
)

MIN_OBS = 500
PREFERRED_OBS = 1000
STATIONARITY_CAP = 0.999
QUALITY_FLAG = "GARCH_FALLBACK"
ANNUALIZER = float(np.sqrt(TRADING_DAYS_PER_YEAR))


@dataclass(frozen=True, slots=True)
class GarchResult:
    """1銘柄の GARCH 予測。点推定 + 信頼区間。"""

    vol_1d_ann: float
    vol_20d_ann: float
    vol_1d_ann_lo: float
    vol_1d_ann_hi: float
    ret_1d: float
    ret_1d_lo: float
    ret_1d_hi: float
    ret_20d: float
    ret_20d_lo: float
    ret_20d_hi: float
    alpha: float
    beta: float
    omega: float
    persistence: float
    nu: float | None = None
    loglik: float | None = None
    aic: float | None = None
    quality_flags: tuple[str, ...] = ()


@dataclass
class GarchFit:
    omega: float
    alpha: float
    beta: float
    mu: float
    nu: float
    last_eps2: float
    last_var: float
    loglik: float
    aic: float
    converged: bool


def fit_garch(log_returns: pd.Series | np.ndarray, *, horizon: int = 20) -> GarchResult:
    """GARCH(1,1) を推定し、horizon 日先までの予測を返す。

    百分率スケールで推定する（収束安定化の定石）。
    `arch` があればそれを使い、無ければ numpy の分散ターゲティング推定に落ちる。
    """
    series = _as_1d(log_returns)
    n = int(series.size)
    if n < MIN_OBS:
        raise InsufficientHistoryError(
            f"GARCH 推定には {MIN_OBS} 営業日以上必要です（実際 {n}）"
        )
    if n > PREFERRED_OBS:
        series = series[-PREFERRED_OBS:]
        n = PREFERRED_OBS

    numpy_fit: GarchFit | None = None
    numpy_err: Exception | None = None
    try:
        numpy_fit = _fit_numpy(series)
    except (GarchNonStationaryError, GarchConvergenceError) as exc:
        numpy_err = exc

    if isinstance(numpy_err, GarchNonStationaryError):
        # arch が定常パラメータを返しても、系列が IGARCH なら予測を出さない。
        raise numpy_err

    fit = _fit_with_arch(series)
    if fit is None:
        if numpy_err is not None:
            raise numpy_err
        if numpy_fit is None:
            raise GarchConvergenceError("GARCH を推定できませんでした")
        fit = numpy_fit
    _assert_usable(fit)
    return _forecast(fit, horizon=horizon)


def forecast_with_params(
    log_returns: pd.Series | np.ndarray,
    *,
    omega: float,
    alpha: float,
    beta: float,
    mu: float = 0.0,
    nu: float = 8.0,
    horizon: int = 20,
) -> GarchResult:
    """週次で推定したパラメータを固定し、日次は予測のみ更新する。"""
    series = _as_1d(log_returns)
    if series.size < 2:
        raise InsufficientHistoryError("予測に必要なリターンがありません")
    pct = series * 100.0
    var = float(np.var(pct, ddof=1))
    for r in pct:
        shock = r - mu
        var = omega + alpha * shock * shock + beta * var
        last_eps2 = shock * shock
    fit = GarchFit(
        omega=omega,
        alpha=alpha,
        beta=beta,
        mu=mu,
        nu=nu,
        last_eps2=last_eps2,
        last_var=var,
        loglik=float("nan"),
        aic=float("nan"),
        converged=True,
    )
    _assert_usable(fit)
    return _forecast(fit, horizon=horizon)


def compute_vol_features(
    log_returns: pd.Series | np.ndarray,
    *,
    realized_vol_20d: float | None = None,
    realized_vol_60d: float | None = None,
    horizon: int = 20,
    quality_sink: Any | None = None,
    entity: str = "",
    as_of: date | None = None,
) -> dict[str, Any]:
    """Analyst 用。失敗時は実現ボラへフォールバックし quality_flags を付ける。"""
    flags: list[str] = []
    garch_1d = None
    garch_20d = None
    lo = None
    hi = None
    try:
        result = fit_garch(log_returns, horizon=horizon)
        garch_1d = result.vol_1d_ann
        garch_20d = result.vol_20d_ann
        lo = result.vol_1d_ann_lo
        hi = result.vol_1d_ann_hi
    except (GarchConvergenceError, GarchNonStationaryError, InsufficientHistoryError):
        flags.append(QUALITY_FLAG)
        if quality_sink is not None and as_of is not None:
            quality_sink.record_data_quality_flag(
                table_name="features_daily",
                entity=entity,
                as_of=as_of,
                flag_code=QUALITY_FLAG,
                detail="GARCH failed; using realized vol",
            )
    return {
        "garch_vol_1d": garch_1d,
        "garch_vol_20d": garch_20d,
        "garch_vol_1d_lo": lo,
        "garch_vol_1d_hi": hi,
        "realized_vol_20d": realized_vol_20d,
        "realized_vol_60d": realized_vol_60d,
        "quality_flags": flags,
    }


def _assert_usable(fit: GarchFit) -> None:
    if not fit.converged:
        raise GarchConvergenceError("GARCH が収束しませんでした")
    if fit.alpha < 0 or fit.beta < 0 or fit.omega <= 0:
        raise GarchConvergenceError("GARCH パラメータが非正です")
    if fit.alpha + fit.beta >= STATIONARITY_CAP:
        raise GarchNonStationaryError(
            f"alpha+beta={fit.alpha + fit.beta:.4f} >= {STATIONARITY_CAP}（IGARCH）"
        )


def _forecast(fit: GarchFit, *, horizon: int) -> GarchResult:
    persistence = fit.alpha + fit.beta
    uncond = fit.omega / max(1.0 - persistence, 1e-12)
    variances = np.empty(horizon, dtype=float)
    variances[0] = fit.omega + fit.alpha * fit.last_eps2 + fit.beta * fit.last_var
    for h in range(1, horizon):
        variances[h] = fit.omega + persistence * variances[h - 1]
    # 百分率スケール → 日次リターンの標準偏差
    sigma_1d = float(np.sqrt(max(variances[0], 1e-12)) / 100.0)
    sigma_20 = float(np.sqrt(max(float(np.mean(variances)), 1e-12)) / 100.0)
    vol_1d = sigma_1d * ANNUALIZER
    vol_20d = sigma_20 * ANNUALIZER
    # 信頼区間: Student-t があればそれを、無ければ正規。
    z95 = _t_ppf(0.975, fit.nu) if fit.nu and fit.nu > 2 else 1.959963984540
    z80 = _t_ppf(0.90, fit.nu) if fit.nu and fit.nu > 2 else 1.281551565545
    mu_daily = fit.mu / 100.0
    ret_1d = mu_daily
    ret_20d = mu_daily * horizon
    # ボラ自体の区間は予測分散パスのばらつき + パラメータ不確実性の粗い近似。
    vol_lo = float(np.sqrt(max(np.min(variances), 1e-12)) / 100.0) * ANNUALIZER
    vol_hi = float(np.sqrt(max(np.max(variances), 1e-12)) / 100.0) * ANNUALIZER
    if vol_hi < vol_1d:
        vol_hi = vol_1d * (1.0 + 0.25 * z80 / 1.28)
    if vol_lo > vol_1d:
        vol_lo = vol_1d * max(0.25, 1.0 - 0.25 * z80 / 1.28)
    return GarchResult(
        vol_1d_ann=vol_1d,
        vol_20d_ann=vol_20d,
        vol_1d_ann_lo=vol_lo,
        vol_1d_ann_hi=max(vol_hi, vol_1d),
        ret_1d=ret_1d,
        ret_1d_lo=ret_1d - z95 * sigma_1d,
        ret_1d_hi=ret_1d + z95 * sigma_1d,
        ret_20d=ret_20d,
        ret_20d_lo=ret_20d - z95 * sigma_20 * np.sqrt(horizon),
        ret_20d_hi=ret_20d + z95 * sigma_20 * np.sqrt(horizon),
        alpha=fit.alpha,
        beta=fit.beta,
        omega=fit.omega,
        persistence=persistence,
        nu=fit.nu,
        loglik=fit.loglik,
        aic=fit.aic,
    )


def _t_ppf(p: float, nu: float) -> float:
    """粗い t 分位点。nu が大きいときは正規に近づける。"""
    z = norm_ppf(p)
    if nu is None or not np.isfinite(nu) or nu > 30:
        return z
    # Cornish-Fisher 風の補正（3次まで）。
    return float(z + (z**3 + z) / (4.0 * nu))


def _as_1d(values: pd.Series | np.ndarray) -> np.ndarray:
    arr = np.asarray(pd.Series(values).astype(float), dtype=float)
    arr = arr[np.isfinite(arr)]
    return arr


def _fit_with_arch(series: np.ndarray) -> GarchFit | None:
    try:
        from arch import arch_model  # type: ignore[import-untyped]
    except (ImportError, OSError):
        return None
    am = arch_model(series * 100.0, vol="GARCH", p=1, q=1, dist="t", mean="Constant")
    res = am.fit(disp="off", show_warning=False)
    converged = bool(getattr(res, "convergence_flag", 0) == 0)
    params = res.params
    alpha = float(params.get("alpha[1]", params.iloc[2] if len(params) > 2 else 0.05))
    beta = float(params.get("beta[1]", params.iloc[3] if len(params) > 3 else 0.9))
    omega = float(params.get("omega", params.iloc[1] if len(params) > 1 else 0.01))
    mu = float(params.get("mu", params.iloc[0] if len(params) else 0.0))
    nu = float(params.get("nu", 8.0))
    pct = series * 100.0
    resid = pct - mu
    var = float(np.var(pct, ddof=1))
    for r in resid:
        var = omega + alpha * r * r + beta * var
    last_eps2 = float(resid[-1] ** 2)
    n = len(series)
    k = 5
    loglik = float(getattr(res, "loglikelihood", np.nan))
    aic = float(getattr(res, "aic", 2 * k - 2 * loglik if np.isfinite(loglik) else np.nan))
    return GarchFit(
        omega=omega,
        alpha=alpha,
        beta=beta,
        mu=mu,
        nu=nu,
        last_eps2=last_eps2,
        last_var=var,
        loglik=loglik,
        aic=aic,
        converged=converged,
    )


def _garch_loglik(
    resid: np.ndarray,
    sq: np.ndarray,
    *,
    omega: float,
    alpha: float,
    beta: float,
    var0: float,
) -> tuple[float, float] | None:
    var = np.empty_like(resid)
    var[0] = max(var0, 1e-12)
    for t in range(1, resid.size):
        var[t] = omega + alpha * sq[t - 1] + beta * var[t - 1]
        if var[t] <= 1e-12:
            return None
    ll = float(-0.5 * np.sum(np.log(var) + sq / var))
    if not np.isfinite(ll):
        return None
    return ll, float(var[-1])


def _candidate(
    *,
    omega: float,
    alpha: float,
    beta: float,
    mu: float,
    sq: np.ndarray,
    last_var: float,
    ll: float,
) -> GarchFit:
    k = 4
    return GarchFit(
        omega=float(omega),
        alpha=float(alpha),
        beta=float(beta),
        mu=mu,
        nu=8.0,
        last_eps2=float(sq[-1]),
        last_var=last_var,
        loglik=ll,
        aic=2 * k - 2 * ll,
        converged=True,
    )


def _fit_numpy(series: np.ndarray) -> GarchFit:
    """分散ターゲティング + グリッド探索の QMLE。arch が無い環境用。"""
    pct = series * 100.0
    mu = float(np.mean(pct))
    resid = pct - mu
    sample_var = float(np.var(resid, ddof=1))
    if sample_var <= 0:
        raise GarchConvergenceError("リターン分散が 0 です")

    sq = resid**2
    interior: GarchFit | None = None
    boundary: GarchFit | None = None
    interior_ll = -np.inf
    boundary_ll = -np.inf
    alpha_grid = np.linspace(0.02, 0.30, 15)
    beta_grid = np.linspace(0.65, 0.98, 18)
    for alpha in alpha_grid:
        for beta in beta_grid:
            persistence = float(alpha + beta)
            if persistence >= 1.0:
                omega = 1e-8
            else:
                omega = sample_var * (1.0 - persistence)
            if omega <= 0:
                continue
            got = _garch_loglik(
                resid, sq, omega=omega, alpha=float(alpha), beta=float(beta), var0=sample_var
            )
            if got is None:
                continue
            ll, last_var = got
            cand = _candidate(
                omega=omega,
                alpha=float(alpha),
                beta=float(beta),
                mu=mu,
                sq=sq,
                last_var=last_var,
                ll=ll,
            )
            if persistence >= STATIONARITY_CAP:
                if ll > boundary_ll:
                    boundary_ll = ll
                    boundary = cand
            elif ll > interior_ll:
                interior_ll = ll
                interior = cand

    # 境界（IGARCH）の尤度が内点を上回るなら発散リスクとして拒否する。
    if boundary is not None and (interior is None or boundary_ll >= interior_ll - 0.5):
        raise GarchNonStationaryError(
            f"IGARCH 境界の尤度が内点以上 "
            f"(boundary={boundary_ll:.1f}, interior={interior_ll if interior else float('nan'):.1f})"
        )
    if interior is None:
        raise GarchConvergenceError("GARCH グリッド探索が解を見つけられませんでした")
    if interior.alpha + interior.beta >= STATIONARITY_CAP - 0.002:
        raise GarchNonStationaryError(
            f"推定 persistence={interior.alpha + interior.beta:.4f} が境界に張り付いている"
        )
    return interior
