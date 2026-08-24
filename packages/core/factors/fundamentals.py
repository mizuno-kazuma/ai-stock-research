"""財務由来の特徴量（バリュエーション / クオリティ / 成長 / 会社予想改定）。

docs/04-analysis-engine.md §1.6-§1.8 に対応する。

PIT の要点:
- `filed_at <= as_of` で絞る。`period_end` で絞ってはいけない（提出は期末の
  1-3ヶ月後であり、期末日で絞ると未来情報になる）。
- 同一会計期間に訂正報告が出るため、`filed_at` が最大の行を採用する。
- TTM は単独四半期を4期合計する。四半期が欠けたら `NULL`。年次で代用しない
  （期間の不一致が入る）。

負値・ゼロ除算の扱いを明示するのは、雑にすると赤字企業が「超割安」として上位に
来るため。ランキングでは PER ではなく `earnings_yield` を使い、赤字は負値として
自然に下位に落ちるようにする。PER は表示用にのみ使う。
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

#: 期間の流れを表す項目。TTM では合計する。
FLOW_COLUMNS = (
    "revenue",
    "operating_income",
    "ordinary_income",
    "net_income",
    "eps",
    "operating_cf",
    "investing_cf",
    "financing_cf",
    "capex",
    "ebitda",
    "cogs",
    "interest_expense",
    "tax_expense",
    "pretax_income",
    "dividend_per_share",
)
#: 時点の残高を表す項目。TTM では合計せず最新値を使う。
STOCK_COLUMNS = (
    "total_assets",
    "total_equity",
    "total_debt",
    "cash_and_equiv",
    "bps",
)
FORECAST_COLUMNS = (
    "forecast_revenue",
    "forecast_op_income",
    "forecast_net_income",
    "forecast_eps",
)

QUARTER_ORDER = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "H1": 2, "FY": 4}
#: 実効税率が異常なときの国別標準値（docs §1.7）。
DEFAULT_TAX_RATE = {"JP": 0.30, "US": 0.21}


def pit_financials(financials: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """`as_of` 時点で知り得た財務のみを、期間ごとに最新版1件だけ返す。

    docs/03-data-model.md §2.4 の `financials_pit` ビュー相当を pandas 側で再現する。
    ストレージ層の `get_financials_as_of()` を使う場合でも、二重に絞って害はない。
    """
    if financials.empty:
        return financials.copy()
    work = financials.copy()
    work["filed_at"] = pd.to_datetime(work["filed_at"], errors="coerce").dt.date
    work["period_end"] = pd.to_datetime(work["period_end"], errors="coerce").dt.date
    work = work.loc[work["filed_at"].notna() & (work["filed_at"] <= as_of)]
    if work.empty:
        return work
    work["ticker"] = work["ticker"].astype(str)
    work = work.sort_values(["ticker", "period_end", "fiscal_period", "filed_at"], kind="mergesort")
    keys = ["ticker", "period_end", "fiscal_period"]
    return work.groupby(keys, as_index=False, sort=False).tail(1).reset_index(drop=True)


def to_standalone_quarters(financials: pd.DataFrame) -> pd.DataFrame:
    """累計開示（日本の決算短信）を単独四半期に変換する。

    `period_type == 'cumulative'` の行は同一 `fiscal_year` の直前四半期を引く。
    `annual` は通期累計なので Q4 相当として扱う。
    """
    if financials.empty:
        return financials.copy()
    work = financials.copy()
    work["_q"] = work["fiscal_period"].map(QUARTER_ORDER).astype("float")
    work = work.loc[work["_q"].notna()].copy()
    if work.empty:
        return work.drop(columns=["_q"])
    if "fiscal_year" not in work.columns:
        work["fiscal_year"] = pd.to_datetime(work["period_end"]).dt.year
    work["fiscal_year"] = pd.to_numeric(work["fiscal_year"], errors="coerce")
    work = work.sort_values(["ticker", "fiscal_year", "_q"], kind="mergesort")

    flow_cols = [c for c in FLOW_COLUMNS if c in work.columns]
    is_cumulative = work["period_type"].isin(["cumulative", "annual"])
    grouped = work.groupby(["ticker", "fiscal_year"], sort=False)
    for col in flow_cols:
        values = pd.to_numeric(work[col], errors="coerce")
        # 同一年度内の直前四半期の累計値を引く（Q1 は引かない）。
        prev = values.groupby([work["ticker"], work["fiscal_year"]], sort=False).shift(1)
        prev_q = grouped["_q"].shift(1)
        # 直前四半期が連続していない場合は差分を取れないので NULL にする。
        contiguous = (work["_q"] - prev_q) == 1
        standalone = values.where(~is_cumulative | (work["_q"] == 1))
        diffed = (values - prev).where(is_cumulative & contiguous)
        work[col] = standalone.combine_first(diffed)
    # `eps` と `dividend_per_share` の差分は意味が薄いが、TTM 合計との整合のため同処理。
    work["fiscal_period"] = work["_q"].map({1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"})
    work["period_type"] = "quarter"
    return work.drop(columns=["_q"]).reset_index(drop=True)


def compute_ttm(quarters: pd.DataFrame, *, min_quarters: int = 4) -> pd.DataFrame:
    """単独四半期を4期合計して TTM を作る。

    四半期の欠損がある場合は `NULL`。年次データで代用しない。
    """
    if quarters.empty:
        return pd.DataFrame(index=pd.Index([], name="ticker"))
    work = quarters.sort_values(["ticker", "period_end"], kind="mergesort")
    flow_cols = [c for c in FLOW_COLUMNS if c in work.columns]
    stock_cols = [c for c in STOCK_COLUMNS if c in work.columns]

    rows: list[dict[str, object]] = []
    for ticker, chunk in work.groupby("ticker", sort=False):
        tail = chunk.tail(min_quarters)
        row: dict[str, object] = {"ticker": str(ticker)}
        enough = len(tail) >= min_quarters
        for col in flow_cols:
            values = pd.to_numeric(tail[col], errors="coerce")
            row[f"{col}_ttm"] = (
                float(values.sum()) if enough and values.notna().all() else np.nan
            )
        latest = chunk.iloc[-1]
        for col in stock_cols:
            row[col] = pd.to_numeric(pd.Series([latest.get(col)]), errors="coerce").iloc[0]
        # 平均自己資本（ROE 用）。4期前の残高が取れないときは最新値で代用しない。
        if "total_equity" in chunk.columns and len(chunk) >= min_quarters:
            equity = pd.to_numeric(chunk["total_equity"], errors="coerce").tail(min_quarters)
            row["avg_total_equity"] = (
                float(equity.mean()) if equity.notna().all() else np.nan
            )
        else:
            row["avg_total_equity"] = np.nan
        for col in [*FORECAST_COLUMNS, "market", "accounting_standard", "currency"]:
            if col in chunk.columns:
                row[col] = latest.get(col)
        row["latest_period_end"] = latest.get("period_end")
        row["latest_filed_at"] = latest.get("filed_at")
        row["n_quarters"] = int(len(tail))
        rows.append(row)
    out = pd.DataFrame(rows).set_index("ticker")
    return out


def _ttm_at_offset(quarters: pd.DataFrame, offset_quarters: int) -> pd.DataFrame:
    """`offset_quarters` 期前を末尾とする TTM。成長率の分母に使う。"""
    if quarters.empty:
        return pd.DataFrame(index=pd.Index([], name="ticker"))
    work = quarters.sort_values(["ticker", "period_end"], kind="mergesort")
    parts: list[pd.DataFrame] = []
    for _, chunk in work.groupby("ticker", sort=False):
        if len(chunk) > offset_quarters:
            parts.append(chunk.iloc[: len(chunk) - offset_quarters])
        else:
            parts.append(chunk.iloc[0:0])
    trimmed = pd.concat(parts, ignore_index=True) if parts else work.iloc[0:0]
    if trimmed.empty:
        return pd.DataFrame(index=pd.Index([], name="ticker"))
    return compute_ttm(trimmed)


def _safe_div(num: pd.Series, den: pd.Series, *, require_positive_den: bool = False) -> pd.Series:
    numerator = pd.to_numeric(num, errors="coerce")
    denominator = pd.to_numeric(den, errors="coerce").replace(0.0, np.nan)
    if require_positive_den:
        denominator = denominator.where(denominator > 0)
    return numerator / denominator


def compute_valuation(
    ttm: pd.DataFrame, *, market_cap: pd.Series, close: pd.Series
) -> pd.DataFrame:
    """バリュエーション指標。分母が非正のものは `NULL`。"""
    if ttm.empty:
        return pd.DataFrame(index=pd.Index([], name="ticker"))
    caps = pd.to_numeric(market_cap.reindex(ttm.index), errors="coerce")
    caps = caps.where(caps > 0)
    px = pd.to_numeric(close.reindex(ttm.index), errors="coerce").where(lambda s: s > 0)
    out = pd.DataFrame(index=ttm.index)

    net_income = pd.to_numeric(ttm.get("net_income_ttm"), errors="coerce")
    # 赤字（分母が負）の PER は意味を持たないので NULL。表示用のみ。
    out["per"] = _safe_div(caps, net_income, require_positive_den=True)
    out["per_forward"] = _safe_div(
        caps, ttm.get("forecast_net_income", pd.Series(index=ttm.index, dtype=float)),
        require_positive_den=True,
    )
    out["pbr"] = _safe_div(caps, ttm.get("total_equity"), require_positive_den=True)
    out["psr"] = _safe_div(caps, ttm.get("revenue_ttm"), require_positive_den=True)

    total_debt = pd.to_numeric(ttm.get("total_debt"), errors="coerce")
    cash = pd.to_numeric(ttm.get("cash_and_equiv"), errors="coerce")
    ev = caps + total_debt.fillna(0.0) - cash.fillna(0.0)
    out["ev_ebitda"] = _safe_div(ev, ttm.get("ebitda_ttm"), require_positive_den=True)

    ocf = pd.to_numeric(ttm.get("operating_cf_ttm"), errors="coerce")
    capex = pd.to_numeric(ttm.get("capex_ttm"), errors="coerce")
    out["fcf_yield"] = _safe_div(ocf - capex.abs(), caps)
    out["dividend_yield"] = _safe_div(ttm.get("dividend_per_share_ttm"), px)
    # PER の逆数。赤字を負値として連続的に扱えるのでランキングに使う。
    out["earnings_yield"] = _safe_div(net_income, caps)
    return out


def effective_tax_rate(ttm: pd.DataFrame, market: str) -> pd.Series:
    """`tax_expense / pretax_income`。異常値は国別標準値に置き換える。"""
    default = DEFAULT_TAX_RATE.get(market, 0.30)
    if ttm.empty:
        return pd.Series(dtype="float64")
    rate = _safe_div(ttm.get("tax_expense_ttm"), ttm.get("pretax_income_ttm"))
    if rate.isna().all():
        return pd.Series(default, index=ttm.index, dtype="float64")
    valid = rate.between(0.0, 0.60, inclusive="both")
    return rate.where(valid, default)


def compute_quality(ttm: pd.DataFrame, *, market: str = "JP") -> pd.DataFrame:
    if ttm.empty:
        return pd.DataFrame(index=pd.Index([], name="ticker"))
    out = pd.DataFrame(index=ttm.index)
    net_income = pd.to_numeric(ttm.get("net_income_ttm"), errors="coerce")
    revenue = pd.to_numeric(ttm.get("revenue_ttm"), errors="coerce")
    op_income = pd.to_numeric(ttm.get("operating_income_ttm"), errors="coerce")

    out["roe"] = _safe_div(net_income, ttm.get("avg_total_equity"), require_positive_den=True)
    tax_rate = effective_tax_rate(ttm, market)
    invested = (
        pd.to_numeric(ttm.get("total_debt"), errors="coerce").fillna(0.0)
        + pd.to_numeric(ttm.get("total_equity"), errors="coerce")
        - pd.to_numeric(ttm.get("cash_and_equiv"), errors="coerce").fillna(0.0)
    )
    out["roic"] = _safe_div(op_income * (1.0 - tax_rate), invested, require_positive_den=True)
    cogs = pd.to_numeric(ttm.get("cogs_ttm"), errors="coerce")
    out["gross_margin"] = _safe_div(revenue - cogs, revenue, require_positive_den=True)
    out["operating_margin"] = _safe_div(op_income, revenue, require_positive_den=True)
    out["debt_to_equity"] = _safe_div(
        ttm.get("total_debt"), ttm.get("total_equity"), require_positive_den=True
    )
    out["interest_coverage"] = _safe_div(
        op_income, pd.to_numeric(ttm.get("interest_expense_ttm"), errors="coerce").abs()
    )
    # 利益の質。値が大きい（利益が現金を伴っていない）銘柄は将来リターンが低い。
    out["accruals_ratio"] = _safe_div(
        net_income - pd.to_numeric(ttm.get("operating_cf_ttm"), errors="coerce"),
        ttm.get("total_assets"),
        require_positive_den=True,
    )
    return out


def compute_growth(quarters: pd.DataFrame) -> pd.DataFrame:
    """YoY 成長率と3年 CAGR。"""
    current = compute_ttm(quarters)
    if current.empty:
        return pd.DataFrame(index=pd.Index([], name="ticker"))
    prior_4q = _ttm_at_offset(quarters, 4)
    prior_12q = _ttm_at_offset(quarters, 12)
    out = pd.DataFrame(index=current.index)

    def growth(col: str, base: pd.DataFrame) -> pd.Series:
        now = pd.to_numeric(current.get(col), errors="coerce")
        then = pd.to_numeric(base.get(col), errors="coerce")
        if then is None:
            return pd.Series(np.nan, index=current.index, dtype="float64")
        then = then.reindex(current.index)
        # 分母が非正の成長率は解釈できない（赤字からの回復は別扱い）。
        return now / then.where(then > 0) - 1.0

    out["revenue_growth_yoy"] = growth("revenue_ttm", prior_4q)
    out["eps_growth_yoy"] = growth("eps_ttm", prior_4q)
    rev_now = pd.to_numeric(current.get("revenue_ttm"), errors="coerce")
    rev_3y = pd.to_numeric(prior_12q.get("revenue_ttm"), errors="coerce")
    if rev_3y is None:
        out["revenue_cagr_3y"] = np.nan
    else:
        rev_3y = rev_3y.reindex(current.index).where(lambda s: s > 0)
        out["revenue_cagr_3y"] = (rev_now / rev_3y) ** (1.0 / 3.0) - 1.0
    return out


def compute_forecast_revision(financials: pd.DataFrame) -> pd.DataFrame:
    """会社予想営業利益の前回開示比。

    会社予想の改定方向は日本株で特に有効な因子。日本企業は会社予想を開示する義務が
    あり、その改定は市場に対して情報価値を持つ。
    """
    columns = ["forecast_revision_direction", "forecast_revision_magnitude"]
    if financials.empty or "forecast_op_income" not in financials.columns:
        return pd.DataFrame(columns=columns, index=pd.Index([], name="ticker"))
    work = financials.copy()
    work["ticker"] = work["ticker"].astype(str)
    work["filed_at"] = pd.to_datetime(work["filed_at"], errors="coerce").dt.date
    work = work.loc[work["filed_at"].notna()]
    work = work.sort_values(["ticker", "filed_at"], kind="mergesort")
    rows: list[dict[str, object]] = []
    for ticker, chunk in work.groupby("ticker", sort=False):
        forecasts = pd.to_numeric(chunk["forecast_op_income"], errors="coerce").dropna()
        if len(forecasts) < 2:
            rows.append(
                {
                    "ticker": ticker,
                    "forecast_revision_direction": np.nan,
                    "forecast_revision_magnitude": np.nan,
                }
            )
            continue
        new, prev = float(forecasts.iloc[-1]), float(forecasts.iloc[-2])
        # 前回予想が非正だと比率が符号反転して解釈不能になるため NULL にする。
        magnitude = new / prev - 1.0 if prev > 0 else np.nan
        direction = 0
        if np.isfinite(magnitude):
            # 開示単位の丸めで微小な差が出るため 0.5% 未満は「変更なし」とみなす。
            if magnitude > 0.005:
                direction = 1
            elif magnitude < -0.005:
                direction = -1
        rows.append(
            {
                "ticker": ticker,
                "forecast_revision_direction": direction,
                "forecast_revision_magnitude": magnitude,
            }
        )
    return pd.DataFrame(rows).set_index("ticker")


def compute_fundamentals(
    financials: pd.DataFrame,
    as_of: date,
    *,
    market_cap: pd.Series,
    close: pd.Series,
    market: str = "JP",
) -> pd.DataFrame:
    """財務由来の特徴量を一括計算する。入力は PIT で絞る前でもよい。"""
    pit = pit_financials(financials, as_of)
    if pit.empty:
        return pd.DataFrame(index=pd.Index([], name="ticker"))
    quarters = to_standalone_quarters(pit)
    ttm = compute_ttm(quarters)
    if ttm.empty:
        return pd.DataFrame(index=pd.Index([], name="ticker"))
    parts = [
        compute_valuation(ttm, market_cap=market_cap, close=close),
        compute_quality(ttm, market=market),
        compute_growth(quarters),
        compute_forecast_revision(pit).reindex(ttm.index),
    ]
    out = pd.concat(parts, axis=1)
    out["latest_filed_at"] = ttm["latest_filed_at"]
    return out
