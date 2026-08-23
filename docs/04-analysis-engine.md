# 04. 分析エンジン仕様

## 0. 本章の基本姿勢

**予測は当たらない前提で設計する。** これは謙遜ではなく実装上の制約である。以下を守る。

1. すべての予測に**信頼区間**と**過去の的中率**を併記する。点推定だけをUIに出す経路を作らない
2. すべてのモデルに**ベースライン**を用意し、統計検定で優位性を示せない限り「優位性なし」と表示する
3. リークを防ぐ検証手法（Purged Walk-Forward CV + embargo）以外を使わない
4. バックテストの取引コストをオプションにしない（必須引数とする）
5. 探索した試行回数を記録し、Deflated Sharpe Ratio で多重検定バイアスを開示する

## 1. 特徴量の定義

`packages/core/factors/` に定義する。すべての特徴量は `as_of` 時点で入手可能な情報のみから計算する。`features_daily` テーブルへ格納（スキーマは [03-data-model.md](03-data-model.md) §2.7）。

### 1.1 PIT ガード

特徴量計算の入口で必ず以下を通す。

```python
# packages/core/factors/pit_guard.py
def assert_pit_safe(df: pd.DataFrame, as_of: date) -> None:
    """as_of より後の情報が混入していないことを検証する。"""
    if "filed_at" in df and (df["filed_at"] > as_of).any():
        raise PitViolationError(...)
    if "trade_date" in df and (df["trade_date"] > as_of).any():
        raise PitViolationError(...)
    if "vintage_date" in df and (df["vintage_date"] > as_of).any():
        raise PitViolationError(...)
```

加えて、日本の開示は**15:00（大引け）以降に出たものを翌営業日扱い**とする。

```python
def effective_date(disclosed_at: datetime, market: str) -> date:
    """開示時刻から、その情報を織り込める最初の営業日を返す。"""
    tz = "Asia/Tokyo" if market == "JP" else "America/New_York"
    local = disclosed_at.astimezone(ZoneInfo(tz))
    cutoff = time(15, 0) if market == "JP" else time(16, 0)
    d = local.date()
    return next_business_day(d, market) if local.time() >= cutoff else d
```

この処理を省くと「決算発表当日の終値で決算内容を知っていた」というリークが入る。日本株のバックテストで実際によくある誤りである。

### 1.2 リターン・モメンタム

| 特徴量 | 定義式 | 備考 |
| --- | --- | --- |
| `ret_Nd` | `adj_close[t] / adj_close[t-N] - 1` | N = 1, 5, 20, 60, 252 |
| `mom_12_1` | `adj_close[t-21] / adj_close[t-252] - 1` | **直近1ヶ月を除外する**（短期反転効果を排除するのが標準実装） |
| `mom_6_1` | `adj_close[t-21] / adj_close[t-126] - 1` | |
| `price_to_52w_high` | `adj_close[t] / max(adj_close[t-252:t])` | 52週高値からの位置。1.0に近いほど強い |
| `dist_from_ma200` | `adj_close[t] / SMA200[t] - 1` | |
| `sector_relative_ret_20d` | `ret_20d - median(ret_20d)` （同セクター内） | |

欠損規則: 必要な履歴長が足りない銘柄（新規上場など）は `NULL` とし、ゼロ埋めしない。ゼロ埋めは「平均的な銘柄」という誤った情報を注入する。

### 1.3 ボラティリティ

| 特徴量 | 定義式 |
| --- | --- |
| `realized_vol_20d` | `std(log_ret[t-19:t]) * sqrt(252)` |
| `realized_vol_60d` | `std(log_ret[t-59:t]) * sqrt(252)` |
| `downside_dev_60d` | `std(min(log_ret, 0)[t-59:t]) * sqrt(252)` |
| `max_drawdown_252d` | `min(adj_close[t] / cummax(adj_close[t-251:t]) - 1)` |
| `beta_market_252d` | `cov(ret, ret_bench) / var(ret_bench)`（252日、ベンチはTOPIX / S&P500） |
| `atr_14` | Wilder の ATR（14日） |
| `garch_vol_1d`, `garch_vol_20d` | GARCH(1,1) の予測（下記 §1.3.1） |

#### 1.3.1 GARCH(1,1) によるボラ予測

`arch` ライブラリを使用する。銘柄別に推定するのは計算コストが高いため、以下の方針を取る。

- **推定対象**: 保有銘柄 + 推奨候補上位100銘柄 + 主要指数 + USD/JPY のみ。全銘柄には実現ボラを使う
- **推定頻度**: 週1回（月曜）。日次では前週のパラメータで予測のみ更新する
- **データ長**: 直近1,000営業日（不足する場合は500日以上あれば推定、それ未満は `NULL`）
- **分布**: Student-t（金融時系列は正規分布では裾が足りない）

```python
from arch import arch_model

def fit_garch(log_returns: pd.Series) -> GarchResult:
    # 百分率スケールにするのは収束を安定させるための定石
    am = arch_model(log_returns * 100, vol="GARCH", p=1, q=1, dist="t", mean="Constant")
    res = am.fit(disp="off", show_warning=False)
    # 収束チェック。収束していないパラメータは使わない
    if not res.convergence_flag == 0:
        raise GarchConvergenceError(...)
    # 定常性チェック: alpha + beta < 1
    alpha, beta = res.params["alpha[1]"], res.params["beta[1]"]
    if alpha + beta >= 0.999:
        raise GarchNonStationaryError(...)  # IGARCH 状態。予測が発散する
    fc = res.forecast(horizon=20, reindex=False)
    return GarchResult(
        vol_1d_ann=np.sqrt(fc.variance.iloc[0, 0]) / 100 * np.sqrt(252),
        vol_20d_ann=np.sqrt(fc.variance.iloc[0, :].mean()) / 100 * np.sqrt(252),
        alpha=alpha, beta=beta, persistence=alpha + beta,
        loglik=res.loglikelihood, aic=res.aic,
    )
```

**収束しない・定常性を満たさない場合は例外にし、実現ボラにフォールバックする。** 発散した予測値を静かに使うのが最も危険である。フォールバックが発生したことは `data_quality_flags` に記録する。

GARCH の使い道は「ボラが上がりそうか下がりそうか」の判定である。**ボラ予測はリターン予測より当たる**（ボラのクラスタリングは頑健な経験則）ため、ポジションサイズの調整に使う価値がある。逆に、これをリターン予測の代替として使ってはならない。

### 1.4 テクニカル

| 特徴量 | 定義 |
| --- | --- |
| `rsi_14` | Wilder の RSI（14日） |
| `macd` | `EMA12 - EMA26` |
| `macd_signal` | `EMA9(macd)` |
| `macd_hist` | `macd - macd_signal` |
| `bb_pct_b_20` | `(close - lower) / (upper - lower)`、`upper/lower = SMA20 ± 2σ` |

テクニカル指標はモメンタムと強く相関するため、合成スコアでは重複計上を避ける（§3 の相関チェック）。**テクニカル単独での予測力は極めて弱いという前提で扱い**、主にエントリータイミングの参考情報としてUIに出す。

### 1.5 流動性

| 特徴量 | 定義 |
| --- | --- |
| `adv_20d` | `mean(turnover_value[t-19:t])`（20日平均売買代金） |
| `turnover_ratio` | `turnover_value / market_cap` |
| `amihud_illiq` | `mean(abs(ret_1d) / turnover_value)` × スケール調整 |

流動性はスコアの構成要素というより**ユニバースフィルタ**として使う。個人の資金規模でも、`adv_20d` が小さい銘柄はスリッページで優位性が消える。既定フィルタ: 日本株は `adv_20d >= 1億円`、米国株は `adv_20d >= 500万USD`。

### 1.6 バリュエーション

| 特徴量 | 定義式 | 注意点 |
| --- | --- | --- |
| `per` | `market_cap / net_income_ttm` | 赤字（分母が負）の場合は `NULL`。負のPERは意味を持たない |
| `per_forward` | `market_cap / forecast_net_income` | 日本の決算短信の会社予想を使う |
| `pbr` | `market_cap / total_equity` | 負の純資産は `NULL` |
| `psr` | `market_cap / revenue_ttm` | |
| `ev_ebitda` | `(market_cap + total_debt - cash) / ebitda_ttm` | EBITDA が負の場合は `NULL` |
| `fcf_yield` | `(operating_cf - capex)_ttm / market_cap` | |
| `dividend_yield` | `dividend_per_share_ttm / close` | |
| `earnings_yield` | `net_income_ttm / market_cap` | PER の逆数。ランキングでは PER より扱いやすい（赤字を負値として連続的に扱える） |

**負値・ゼロ除算の扱いを明示する理由**: ここを雑にすると赤字企業が「超割安」として上位に来る。ランキングでは PER ではなく `earnings_yield` を使い、赤字は負値として自然に下位に落ちるようにする。PER は表示用にのみ使う。

**TTM（過去12ヶ月）の計算**: 四半期データを4期合計する。ただし四半期の欠損がある場合は `NULL` とし、年次データで代用しない（期間の不一致が入る）。日本企業の四半期は累計値で開示されることがあるため、`financials.period_type` を見て累計/単独を判別する処理を入れる。

### 1.7 クオリティ

| 特徴量 | 定義式 |
| --- | --- |
| `roe` | `net_income_ttm / avg(total_equity)` |
| `roic` | `(operating_income_ttm * (1 - tax_rate)) / (total_debt + total_equity - cash)` |
| `gross_margin` | `(revenue - cogs) / revenue` |
| `operating_margin` | `operating_income / revenue` |
| `debt_to_equity` | `total_debt / total_equity` |
| `interest_coverage` | `operating_income / interest_expense` |
| `accruals_ratio` | `(net_income - operating_cf) / total_assets` |

`accruals_ratio` は**利益の質**を測る。値が大きい（利益が現金を伴っていない）銘柄は将来のリターンが低い傾向があるという経験的知見があり、クオリティ因子として符号を反転して使う。

`tax_rate` は実効税率を財務から算出（`tax_expense / pretax_income`）。異常値（0未満または60%超）の場合は国別の標準値（日本30%、米国21%）を使う。

### 1.8 成長・改定

| 特徴量 | 定義式 |
| --- | --- |
| `revenue_growth_yoy` | `revenue_ttm / revenue_ttm[-4Q] - 1` |
| `eps_growth_yoy` | `eps_ttm / eps_ttm[-4Q] - 1` |
| `revenue_cagr_3y` | `(revenue_ttm / revenue_ttm[-12Q])^(1/3) - 1` |
| `forecast_revision_direction` | 会社予想営業利益の前回開示比: 上方 `+1` / 変更なし `0` / 下方 `-1` |
| `forecast_revision_magnitude` | `forecast_op_income_new / forecast_op_income_prev - 1` |

**会社予想の改定方向は日本株で特に有効な因子である。** 日本企業は会社予想を開示する義務があり、その改定は市場に対して情報価値を持つ。TDnet の `guidance_revision` 検出、または `financials.forecast_op_income` の差分検出のどちらでも取得できる（[02-data-ingestion.md](02-data-ingestion.md) §6.3）。

### 1.9 為替感応度

```python
# 直近60営業日での、USD/JPY 変化率に対する銘柄リターンの回帰係数
fx_sensitivity_60d = OLS(stock_ret_1d[-60:], usdjpy_ret_1d[-60:]).params[0]
```

輸出企業（円安で恩恵）と輸入・内需企業（円高で恩恵）を区別するために使う。為替見通しと組み合わせて「円安シナリオで有利な銘柄」を抽出する用途（スクリーナー画面のプリセット）。

### 1.10 欠損値の扱い（方針の明示）

| 状況 | 扱い |
| --- | --- |
| 履歴が不足（新規上場） | `NULL`。ゼロ埋め・平均埋めを禁止する |
| 分母が負またはゼロ（PER等） | `NULL` |
| 財務が未提出 | `NULL` |
| LightGBM への入力 | **`NULL` をそのまま渡す**（LightGBM は欠損を扱える。無理に埋めない方が良い） |
| z-score 計算時 | 欠損は順位付けから除外し、`n_missing` をカウントする |
| `n_missing > 15`（60特徴量中） | その銘柄をその日のスコアリング対象から除外する |

## 2. 為替予測（USD/JPY）

### 2.1 前提の明示

**為替の短期予測は、学術的にランダムウォークに勝つのが極めて難しい領域である**（Meese-Rogoff パズルとして知られる）。したがって本ツールの為替モジュールの第一の目的は「当てること」ではなく、以下である。

1. **ボラティリティの見通し**を出す（これはリターン予測より当たる）
2. 金利差との乖離を可視化し、**現在の水準が歴史的にどこにあるか**を示す
3. モデルがランダムウォークに勝てているかを毎日測定し、**勝てていないことを正直に表示する**

### 2.2 ベースライン: ランダムウォーク

```
forecast[t+h] = spot[t]
ci_lo/hi = spot[t] ± z * sigma_garch * sqrt(h)
```

これが `model_id = 'random_walk'` として `fx_forecasts` に常に記録される。他のモデルはこれとの比較で評価される。

### 2.3 ARIMAX（金利差を外生変数とする）

```python
# 目的変数: log(USDJPY) の差分
# 外生変数: 日米金利差、その差分、実質金利差
exog = pd.DataFrame({
    "rate_diff_2y":  us_dgs2 - jp_2y,
    "rate_diff_10y": us_dgs10 - jp_10y,
    "d_rate_diff_10y": (us_dgs10 - jp_10y).diff(),
    "real_rate_diff": (us_dgs10 - us_cpi_yoy) - (jp_10y - jp_cpi_yoy),
})
model = sm.tsa.SARIMAX(
    endog=np.log(usdjpy), exog=exog,
    order=(1, 1, 1), trend="n",
    enforce_stationarity=True, enforce_invertibility=True,
)
res = model.fit(disp=False)
fc = res.get_forecast(steps=h, exog=exog_future)   # exog_future は最終値を保持する仮定
ci = fc.conf_int(alpha=0.05)
```

**注意事項**:

- 外生変数の将来値が必要になる。金利差の将来値は不明なので「最終値を保持」という仮定を置く。この仮定を `fx_forecasts.notes` に明記する。これは事実上「金利差が変わらなければこうなる」という条件付き予測である
- `order` の選択は AIC ではなく**アウトオブサンプル性能**で選ぶ。AIC での選択はインサンプル過剰適合を招く
- マクロ変数は `vintage_date <= as_of` で絞る（改訂後の値を使うと未来情報のリークになる）

### 2.4 VECM（共和分がある場合）

金利差と為替に共和分関係が検出された場合のみ使う。

```python
from statsmodels.tsa.vector_ar.vecm import coint_johansen, VECM

# Johansen 検定で共和分ランクを判定
jres = coint_johansen(data[["log_usdjpy", "rate_diff_10y"]], det_order=0, k_ar_diff=2)
rank = determine_rank(jres, significance=0.05)
if rank == 0:
    # 共和分なし。VECM を使わない（無理に当てはめると誤った長期均衡を仮定する）
    return None
vecm = VECM(data, k_ar_diff=2, coint_rank=rank, deterministic="ci").fit()
```

**共和分が検出されない場合は VECM を使わない。** 「長期均衡があるはず」という前提を勝手に置いてはいけない。日本のゼロ金利期間を含むサンプルでは関係が構造変化している可能性が高く、検定結果は期間依存である。この不安定性そのものを記録し、UI（為替・マクロ画面）で「共和分関係: 直近5年では検出されず」のように表示する。

### 2.5 Diebold-Mariano 検定（必須）

すべての為替モデルは毎日この検定を通す。通らなければ「優位性なし」と表示する。

```python
def diebold_mariano(e1: np.ndarray, e2: np.ndarray, h: int,
                    loss: str = "squared") -> DMResult:
    """e1: 検証モデルの予測誤差, e2: ベースライン(RW)の予測誤差
    帰無仮説: 両モデルの予測精度は等しい
    """
    d = (e1**2 - e2**2) if loss == "squared" else (np.abs(e1) - np.abs(e2))
    d_bar = d.mean()
    n = len(d)
    # h期先予測では誤差に系列相関が入るため HAC 分散を使う（Newey-West）
    gamma = [np.cov(d[:-k], d[k:])[0, 1] if k > 0 else d.var(ddof=0)
             for k in range(h)]
    var_d = (gamma[0] + 2 * sum(gamma[1:])) / n
    if var_d <= 0:
        return DMResult(stat=np.nan, pvalue=np.nan, note="非正の分散推定")
    dm = d_bar / np.sqrt(var_d)
    # Harvey-Leybourne-Newbold の小標本補正
    hln = np.sqrt((n + 1 - 2*h + h*(h-1)/n) / n)
    dm_adj = dm * hln
    pvalue = 2 * (1 - stats.t.cdf(abs(dm_adj), df=n - 1))
    return DMResult(stat=dm_adj, pvalue=pvalue,
                    better=("model" if d_bar < 0 else "baseline"))
```

**HAC分散（Newey-West）を使うことが重要**である。h期先予測の誤差は重なり合うため系列相関を持ち、単純な分散推定ではp値が過小になり「勝っている」と誤判定する。

判定ルール:

| 条件 | `beats_baseline` | UI表示 |
| --- | --- | --- |
| `pvalue < 0.05` かつ `better == "model"` | `TRUE` | 「ランダムウォークに対して統計的に有意（p=0.03）」 |
| `pvalue >= 0.05` | `FALSE` | 「ランダムウォークに対する優位性は確認できていません」 |
| `pvalue < 0.05` かつ `better == "baseline"` | `FALSE` | 「ランダムウォークに劣後しています。このモデルは参考程度に扱ってください」 |

評価窓は直近60営業日のローリング。**期間を選んで良い結果を報告することを避けるため、窓の長さは設定で固定し、都度変えない。**

### 2.6 為替モジュールの出力

`fx_forecasts` テーブル（[03-data-model.md](03-data-model.md) §2.11）。UIには以下を必ずセットで表示する。

- 点推定と 80% / 95% 信頼区間（ファンチャート）
- 直近60日の方向的中率（`directional_accuracy_60d`）
- DM検定の結果と、勝っていない場合の明示的な文言
- GARCH由来のボラ見通し
- 金利差との散布図（現在位置をハイライト）

## 3. 株価のクロスセクショナル・ランキング

### 3.1 問題設定

「明日の株価」を当てるのではなく、**「同じ日の銘柄群の中で、相対的にどれが強いか」を順位付けする**。これがクロスセクショナル・アプローチであり、市場全体の方向を当てる必要がないため個人でも取り組みやすい。

| 項目 | 設定 |
| --- | --- |
| 目的変数 | H5: 5営業日先の超過リターン、H20: 20営業日先の超過リターン |
| 超過リターンの定義 | `stock_ret - sector_median_ret`（セクター中立）。ベンチマーク超過も別途計算 |
| 学習単位 | 日付をグループとするランキング学習（LightGBM `lambdarank`）、または回帰（`regression`）+ 日次でのz-score化 |
| ユニバース | 流動性フィルタ通過後の銘柄。JP/US で別モデル |
| 学習頻度 | 月1回（第1営業日）。日次は推論のみ |
| 予測の出力 | 点推定 + 分位点回帰による 20/80パーセンタイル |

**回帰 + 日次z-score化を既定とする。** `lambdarank` は順位のみを学習するため、「どの程度の差か」が失われる。ポジションサイズの決定には期待リターンの大きさが必要なので、回帰の方が扱いやすい。

### 3.2 目的変数の作り方

```python
def make_label(prices: pd.DataFrame, as_of: date, horizon: int) -> pd.Series:
    """as_of の翌営業日の始値で買い、horizon 営業日後の始値で売る前提のリターン。
    終値ベースにしないのは、終値時点で計算した特徴量に基づいて終値で
    約定するのが不可能だからである（これは頻出するリーク）。
    """
    entry = prices.loc[next_bd(as_of), "adj_open"]
    exit_ = prices.loc[shift_bd(as_of, horizon + 1), "adj_open"]
    return exit_ / entry - 1
```

**エントリーを翌営業日の始値にする理由**: `as_of` の終値までの情報で計算した特徴量に基づいて `as_of` の終値で約定することは物理的に不可能である。この1ステップのズレを入れないバックテストは必ず良い結果を出し、実運用で再現しない。

### 3.3 Purged Walk-Forward CV（唯一許可する検証手法）

```
時間軸 →
[--------- train ---------][purge][embargo][--- test ---]
                            ^^^^^^^ ^^^^^^^
                            ラベル期間分  系列相関対策の余白
```

```python
# packages/core/models/cv.py
class PurgedWalkForwardCV(BaseCrossValidator):
    """時系列のWalk-Forward分割。学習末尾からラベル期間分をpurgeし、
    さらにembargoを空けてtestを開始する。
    """
    def __init__(self, n_splits: int = 6, label_horizon_days: int = 20,
                 embargo_days: int = 5, test_days: int = 60,
                 min_train_days: int = 504):
        ...

    def split(self, X, y=None, groups=None):
        # groups は as_of の日付列であることを要求する
        if groups is None:
            raise ValueError("groups（as_of日付）は必須。日付なしの分割を許可しない")
        dates = np.sort(pd.unique(groups))
        for i in range(self.n_splits):
            test_end   = len(dates) - i * self.test_days
            test_start = test_end - self.test_days
            purge_end  = test_start - self.embargo_days
            train_end  = purge_end - self.label_horizon_days
            if train_end < self.min_train_days:
                break
            yield (idx_of(dates[:train_end]),
                   idx_of(dates[test_start:test_end]))
```

**パラメータの根拠**:

| パラメータ | 値 | 理由 |
| --- | --- | --- |
| `label_horizon_days` | H5なら5、H20なら20 | 学習データの末尾サンプルのラベルは未来を見ている。ラベル期間分を除外しないと直接リークする |
| `embargo_days` | 5 | purge だけでは、系列相関のある特徴量（20日移動平均など）を通じた間接的なリークが残る。安全側に営業日1週間分空ける |
| `min_train_days` | 504（約2年） | これ未満では季節性・レジームの多様性が不足する |
| `n_splits` | 6 | J-Quants無料プランの2年履歴では 6分割が上限に近い。Light（5年）なら12分割にする |
| `test_days` | 60（約3ヶ月） | 短すぎると評価が不安定、長すぎると分割数が減る |

**通常の `KFold` / `TimeSeriesSplit` を使わせない仕組み**: `packages/core/models/` 内で `sklearn.model_selection.KFold` を import した場合に失敗するテストを CI に置く（[12-testing-validation.md](12-testing-validation.md) の T-LEAK-01）。

### 3.4 LightGBM の設定

```python
params = {
    "objective": "regression",
    "metric": "rmse",
    "learning_rate": 0.03,
    "num_leaves": 31,
    "min_data_in_leaf": 200,       # 過剰適合抑制。財務データの粒度に対して大きめに取る
    "feature_fraction": 0.7,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l1": 0.1,
    "lambda_l2": 1.0,
    "max_depth": 6,
    "verbosity": -1,
    "seed": 42,
    "deterministic": True,          # 再現性のため必須
    "force_col_wise": True,
}
# 早期停止は各foldのtestで行う（これはリークではない。ただしfold間で
# best_iteration が大きくばらつく場合はモデルが不安定というシグナル）
```

**ハイパーパラメータ探索の方針**: 探索は行うが、**試行回数を必ず記録する**（`model_runs.n_trials`）。探索範囲を広げるほど Deflated Sharpe Ratio は厳しくなる。探索は Optuna で最大50試行までに制限し、それ以上は「探索しすぎ」と判断する。これは計算資源の制約ではなく、多重検定バイアスを抑えるための意図的な制限である。

### 3.5 分位点回帰による信頼区間

点推定だけでは信頼区間が出せないため、同じ特徴量で3つのモデルを学習する。

```python
models = {
    "mean": lgb.train({**params, "objective": "regression"}, ...),
    "q20":  lgb.train({**params, "objective": "quantile", "alpha": 0.2}, ...),
    "q80":  lgb.train({**params, "objective": "quantile", "alpha": 0.8}, ...),
}
# scores_daily.ml_pred_h5 = mean, ml_pred_h5_lo = q20, ml_pred_h5_hi = q80
```

学習コストは3倍になるが、**信頼区間なしの予測をUIに出さないという要件**を満たすために必要である。q20/q80 は 60%予測区間に相当する。

### 3.6 評価指標

| 指標 | 定義 | 目標値の目安 |
| --- | --- | --- |
| Rank IC | 各日の予測値と実現リターンの Spearman 相関の平均 | 0.03 以上あれば実用的 |
| Rank IC の t統計量 | `mean(IC) / std(IC) * sqrt(n_days)` | 2.0 以上 |
| IC の勝率 | IC > 0 だった日の比率 | 55% 以上 |
| 上位分位のスプレッド | 上位20% と下位20% の平均リターン差 | 年率換算で手数料を上回るか |
| 分位単調性 | 5分位のリターンが単調に並ぶか | 単調でない場合はモデルを疑う |

**Rank IC 0.03 は低く見えるが、これがクロスセクショナル予測の現実的な水準である。** 0.10 を超える結果が出た場合は、まずリークを疑うこと。この閾値を仕様に書いておく理由は、良すぎる結果に飛びつくのを防ぐためである。

### 3.7 特徴量の相関チェック

合成スコアで同じ情報を重複計上しないため、学習前に相関行列を確認する。

- `|corr| > 0.85` のペアは片方を落とす（VIFも参照）
- 落とす基準: 単独のRank ICが低い方、または計算が不安定な方
- 相関行列は `model_runs.metrics` に保存し、モデルラボ画面でヒートマップ表示する

## 4. バックテスト

### 4.1 API 設計（コストを必須引数にする）

```python
# packages/core/backtest/engine.py
def run_backtest(
    *,
    signals: pd.DataFrame,          # index=(as_of, ticker), col='score'
    prices: pd.DataFrame,           # prices_daily 由来（prices_live 禁止）
    market: str,
    period: tuple[date, date],
    rebalance_freq: Literal["weekly", "monthly"],
    n_positions: int,
    fee_bps: float,                 # 必須。デフォルト値を持たせない
    slippage_bps: float,            # 必須
    max_turnover_pct: float,        # 必須
    n_trials: int,                  # 必須。DSR 計算に使う
    universe_filter: UniverseFilter,
    benchmark: str,
) -> BacktestResult:
    ...
```

**`fee_bps` / `slippage_bps` / `max_turnover_pct` / `n_trials` にデフォルト値を持たせない。** キーワード専用引数にして、呼び出し側が必ず明示的に値を渡すよう強制する。デフォルト値を持たせると「とりあえずゼロ」で回してしまい、コスト込みでは成立しない戦略を良いものと誤認する。

### 4.2 コスト前提の推奨値

| 項目 | 日本株 | 米国株 | 根拠 |
| --- | --- | --- | --- |
| `fee_bps` | 5 | 1 | ネット証券の手数料水準。実際の口座の料率に合わせて設定する |
| `slippage_bps` | 10（大型）/ 30（中小型） | 5 / 20 | 成行の想定。`adv_20d` に対する注文サイズの比率で調整する |
| `max_turnover_pct` | 30（月次） | 30 | これを超えるリバランスは実行不能とみなす |

スリッページはサイズ依存にする。

```python
def slippage_bps(order_value: float, adv_20d: float, base_bps: float) -> float:
    """注文サイズが平均売買代金に対して大きいほどスリッページが増える。
    平方根モデル（市場インパクトの標準的な近似）。
    """
    participation = order_value / max(adv_20d, 1.0)
    return base_bps * (1 + 3 * np.sqrt(participation))
```

### 4.3 出力指標（すべて必須）

`backtest_runs` テーブル（[03-data-model.md](03-data-model.md) §2.14）に格納。

| 指標 | 備考 |
| --- | --- |
| `total_return`, `cagr`, `volatility` | |
| `sharpe`, `sortino`, `calmar` | 無リスク利子率は該当期間の実勢（FRED の DFF / 日本は0）を使う |
| `max_drawdown` | ドローダウン期間の開始・終了日も記録する |
| `hit_rate`, `profit_factor` | |
| `avg_turnover`, `total_cost_bps` | **コストが総リターンの何割を食っているかを必ず表示する** |
| `alpha_vs_bench`, `information_ratio` | |
| `deflated_sharpe`, `dsr_pvalue`, `is_significant` | 下記 §4.4 |

### 4.4 Deflated Sharpe Ratio（必須出力）

複数の戦略・パラメータを試すと、偶然に高いシャープレシオを持つものが必ず見つかる。DSR はこのバイアスを補正する。

```python
def deflated_sharpe_ratio(
    sr_observed: float,      # 観測されたシャープレシオ（年率）
    n_trials: int,           # 試した戦略・パラメータの総数
    n_obs: int,              # 観測数（日数）
    skew: float,             # リターン分布の歪度
    kurtosis: float,         # 尖度
    sr_variance_across_trials: float,  # 試行間のSRの分散
) -> DSRResult:
    # 期待される最大SR（試行回数を考慮した「偶然の最大値」）
    e = np.euler_gamma
    sr_expected_max = np.sqrt(sr_variance_across_trials) * (
        (1 - e) * stats.norm.ppf(1 - 1/n_trials)
        + e * stats.norm.ppf(1 - 1/(n_trials * np.e))
    )
    # 非正規性を考慮したSRの標準誤差
    sr_std = np.sqrt(
        (1 - skew * sr_observed + ((kurtosis - 1) / 4) * sr_observed**2) / (n_obs - 1)
    )
    dsr = stats.norm.cdf((sr_observed - sr_expected_max) / sr_std)
    return DSRResult(
        dsr=dsr,                       # 「本物である確率」に相当
        expected_max_sr=sr_expected_max,
        is_significant=dsr > 0.95,
    )
```

**運用ルール**:

- `n_trials` は正直に数える。「試したけど記録しなかった」設定も含める。`model_runs` / `backtest_runs` の件数を自動集計してこれに充てる
- `dsr <= 0.95` の戦略は「有意でない」として扱い、UIには「試行回数を考慮すると、この結果は偶然の可能性があります（DSR=0.72）」と表示する
- DSR が低い戦略を採用してはならないという規則にはしない（採用は人間の判断）。ただし**低いという事実を隠さない**

### 4.5 バックテストで禁止する行為（チェックリスト）

これは `.cursor/skills/run-backtest/SKILL.md` のチェックリストと対応する。

| 禁止事項 | 検出方法 |
| --- | --- |
| `prices_live` を価格ソースに使う | 型チェック + CI テスト |
| 当日終値でシグナル計算し当日終値で約定 | エントリーは必ず翌営業日始値。エンジン側で強制 |
| 上場廃止銘柄を除外したユニバース | `securities` に `delisting_date` を持ち、当時存在した銘柄で構成する |
| 手数料・スリッページをゼロにする | 必須引数なので構造的に不可能 |
| 期間を変えて良い結果を選ぶ | `backtest_runs` に全試行を記録し、`n_trials` に反映する |
| 改訂後のマクロ値を使う | `vintage_date <= as_of` の強制 |
| 財務の `period_end` で PIT 判定する | `filed_at` を使う。`financials_pit` ビューの利用を強制 |
| 生存者バイアスのあるユニバース | 同上 |
| インサンプルのハイパーパラメータで全期間評価 | Purged Walk-Forward CV のみ許可 |

## 5. レジーム検出（補助的な位置付け）

市場環境の変化を検出し、モデルの信頼度を調整する。**予測に使うのではなく、「今はモデルが効きにくい環境である」ことを示すために使う。**

| 指標 | 定義 | 使い方 |
| --- | --- | --- |
| ボラティリティ・レジーム | 市場のGARCHボラの過去5年パーセンタイル | 高ボラ時（80パーセンタイル超）は推奨の確信度を1段下げる |
| 相関レジーム | 銘柄間平均相関（60日） | 高相関時はクロスセクショナル戦略が効きにくい。UIに警告 |
| モデル劣化検出 | 直近20日のRank ICが過去1年の下位10%以下 | 「モデルの直近パフォーマンスが劣化しています」を表示 |
| 特徴量ドリフト | 主要特徴量の分布のKS検定（学習期間 vs 直近） | p < 0.01 の特徴量が3つ以上でモデル再学習を推奨 |

レジーム判定を予測に組み込まないのは、**レジーム自体の予測が困難で、組み込むと自由度が増えて過剰適合するため**である。検出は「注意喚起」に留める。

## 6. 計算スケジュールとコスト

| 処理 | 頻度 | 所要時間 | 備考 |
| --- | --- | --- | --- |
| 特徴量計算（全銘柄） | 日次 | 約8分 | DuckDBのウィンドウ関数中心。pandas に落とすのは最小限 |
| GARCH 推定 | 週次 | 約5分 | 対象を絞っているため |
| GARCH 予測更新 | 日次 | 約20秒 | パラメータ固定 |
| ARIMAX / VECM | 日次 | 約1分 | USD/JPY のみ |
| DM検定 | 日次 | 約5秒 | |
| LightGBM 学習 | 月次 | 約20分 | JP/US × H5/H20 × 3分位 = 12モデル |
| LightGBM 推論 | 日次 | 約30秒 | |
| バックテスト（1構成） | 手動 | 約2分 | |

## 7. 参照

- スコアリングと推奨生成: [05-scoring-screening.md](05-scoring-screening.md)
- 検証の詳細とテスト: [12-testing-validation.md](12-testing-validation.md)
- 新規ファクター追加手順: `.cursor/skills/add-analysis-factor/SKILL.md`
- バックテスト実行手順: `.cursor/skills/run-backtest/SKILL.md`
