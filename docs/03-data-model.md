# 03. データモデル（DuckDB / SQLite / LanceDB スキーマ定義）

## 1. 全体方針

| ストア | ファイル | 役割 | ライタ |
| --- | --- | --- | --- |
| DuckDB | `data/warehouse/analytics.duckdb` | 分析用の事実テーブル・特徴量・スコア・推奨 | `services/agent` のみ |
| Parquet | `data/warehouse/parquet/**` | 大きな時系列の外部テーブル、Raw層 | `services/agent` のみ |
| SQLite | `data/state.sqlite` | ジョブ状態、設定、売買日誌、agent_memory、コストログ | `services/agent` と `services/api` の両方 |
| LanceDB | `data/vectors/` | 開示資料チャンクの埋め込み | `services/agent` のみ |

**DuckDB への書き込みは agent プロセスに限定する**（DuckDB は単一ライタ）。`services/api` は `read_only=True` で接続する。SQLite は WAL モード（`PRAGMA journal_mode=WAL`）で両プロセスから使う。

命名規約:

- テーブル名・カラム名は `snake_case`
- 日付は `_date`（`DATE`）、時刻は `_at`（`TIMESTAMP`、UTC保存）
- 真偽値は `is_` / `has_` 接頭辞
- 金額は通貨を別カラム（`currency`）で持ち、数値カラムに通貨名を含めない
- すべてのテーブルに `ingested_at TIMESTAMP` を持たせる

## 2. DuckDB スキーマ

### 2.1 `securities`（銘柄マスタ・履歴あり）

```sql
CREATE TABLE securities (
    ticker            VARCHAR NOT NULL,   -- JP: '7203', '130A' / US: 'AAPL'
    market            VARCHAR NOT NULL,   -- 'JP' | 'US'
    exchange          VARCHAR,            -- 'TSE_PRIME','TSE_STANDARD','TSE_GROWTH','NASDAQ','NYSE'
    name_local        VARCHAR NOT NULL,   -- 'トヨタ自動車'
    name_en           VARCHAR,            -- 'Toyota Motor Corporation'
    sector_code       VARCHAR,            -- JP: 33業種コード / US: GICS セクター
    sector_name       VARCHAR,            -- '輸送用機器'
    industry_name     VARCHAR,
    product_category  VARCHAR,            -- J-Quants 商品区分（'011'=内国株券 等。§2.1a）
    currency          VARCHAR NOT NULL,   -- 'JPY' | 'USD'
    cik               VARCHAR,            -- 米国のみ。10桁ゼロ埋め文字列
    edinet_code       VARCHAR,            -- 日本のみ。'E02144'
    isin              VARCHAR,
    shares_outstanding BIGINT,
    listing_date      DATE,
    delisting_date    DATE,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    valid_from        DATE NOT NULL,      -- この属性が有効な期間の開始
    valid_to          DATE,               -- NULL は現行
    ingested_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (ticker, market, valid_from)
);
CREATE INDEX idx_securities_active ON securities(market, is_active);
```

**履歴を持つ理由**: 社名変更・コード変更・セクター変更が起こる。過去のバックテストで「当時のセクター」を使わないとセクター中立化が壊れる。また上場廃止銘柄を削除すると生存者バイアスが入るため、`delisting_date` を持って残す。

#### 2.1a `product_category`（商品区分）

J-Quants `/equities/master`（`/listed/info`）の `ProdCat`（`ProductCategory`）をそのまま保存する。

| コード | 内容 |
| --- | --- |
| `011` | 内国株券（個別株） |
| `012` | 優先出資証券 |
| `013` | REIT |
| `014` | ETF |
| `021` | 外国株券 |
| `022` | 外国REIT |
| `023` | 外国ETF |
| `024` | 外国株預託証券 |

`UniverseFilter.common_stock_only`（既定 `True`）は `product_category == '011'` 以外（ETF・REIT・優先出資証券・外国株等）を推奨・スクリーナー・バックテストの対象から除外する。値が `NULL`（未収集・米国など対象外市場）の行は除外しない（[05-scoring-screening.md](05-scoring-screening.md) §7.1）。

### 2.2 `prices_daily`（リサーチ用・確定値）

```sql
CREATE TABLE prices_daily (
    ticker            VARCHAR NOT NULL,
    market            VARCHAR NOT NULL,
    trade_date        DATE    NOT NULL,
    open              DOUBLE,
    high              DOUBLE,
    low               DOUBLE,
    close             DOUBLE,
    volume            BIGINT,
    turnover_value    DOUBLE,             -- 売買代金
    adj_open          DOUBLE,             -- 権利調整済み
    adj_high          DOUBLE,
    adj_low           DOUBLE,
    adj_close         DOUBLE,
    adj_volume        BIGINT,
    adjustment_factor DOUBLE DEFAULT 1.0,
    currency          VARCHAR NOT NULL,
    source            VARCHAR NOT NULL,   -- 'jquants' | 'yfinance' | 'finnhub' | 'alpha_vantage'
    quality_flags     VARCHAR[],          -- ['HIGH_LOW_INVERTED','EXTREME_MOVE'] 等
    ingested_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (ticker, market, trade_date)
);
CREATE INDEX idx_prices_daily_date ON prices_daily(trade_date);
```

Parquet パーティション（DuckDB からの外部テーブル参照用）:

```
data/warehouse/parquet/prices_daily/market=JP/year=2026/month=08/part-0000.parquet
```

**パーティションキーに `:` `?` `*` を含めない**（Windows側から同じファイルを触るため）。`market=JP` のような `=` は許容される。

### 2.3 `prices_live`（現在値・参考値。モデル学習禁止）

```sql
CREATE TABLE prices_live (
    ticker            VARCHAR NOT NULL,
    market            VARCHAR NOT NULL,
    trade_date        DATE    NOT NULL,
    close             DOUBLE,
    prev_close        DOUBLE,
    change_pct        DOUBLE,
    volume            BIGINT,
    currency          VARCHAR NOT NULL,
    source            VARCHAR NOT NULL,   -- 'yfinance'
    is_delayed        BOOLEAN NOT NULL DEFAULT TRUE,
    delay_note        VARCHAR,            -- '約15-20分遅延'
    ingested_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (ticker, market, trade_date)
);
```

**このテーブルを `packages/core/models/` および `packages/core/backtest/` から参照することを禁止する。** 違反を検出するテストを CI に置く（[12-testing-validation.md](12-testing-validation.md) の T-LEAK-02）。

### 2.4 `financials`（財務。PIT厳守）

```sql
CREATE TABLE financials (
    ticker            VARCHAR NOT NULL,
    market            VARCHAR NOT NULL,
    period_end        DATE    NOT NULL,   -- 会計期間末日
    fiscal_year       INTEGER NOT NULL,
    fiscal_period     VARCHAR NOT NULL,   -- 'FY' | 'Q1' | 'Q2' | 'Q3' | 'Q4' | 'H1'
    period_type       VARCHAR NOT NULL,   -- 'annual' | 'quarter' | 'ttm'
    filed_at          DATE    NOT NULL,   -- 提出日。PIT の基準
    accession         VARCHAR,            -- US: '0000320193-26-000012'
    doc_id            VARCHAR,            -- JP: EDINET docID

    revenue           DOUBLE,
    operating_income  DOUBLE,
    ordinary_income   DOUBLE,             -- 日本基準の経常利益
    net_income        DOUBLE,
    eps               DOUBLE,
    total_assets      DOUBLE,
    total_equity      DOUBLE,
    total_debt        DOUBLE,
    cash_and_equiv    DOUBLE,
    operating_cf      DOUBLE,
    investing_cf      DOUBLE,
    financing_cf      DOUBLE,
    capex             DOUBLE,
    ebitda            DOUBLE,
    dividend_per_share DOUBLE,
    bps               DOUBLE,

    forecast_revenue  DOUBLE,             -- 会社予想（日本の決算短信）
    forecast_op_income DOUBLE,
    forecast_net_income DOUBLE,
    forecast_eps      DOUBLE,
    forecast_revised_at DATE,             -- 会社予想が最後に改定された日

    accounting_standard VARCHAR,          -- 'JGAAP' | 'IFRS' | 'USGAAP'
    currency          VARCHAR NOT NULL,
    unit_multiplier   INTEGER DEFAULT 1,  -- 元データが百万円単位なら 1000000
    is_restated       BOOLEAN DEFAULT FALSE,
    source            VARCHAR NOT NULL,
    ingested_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (ticker, market, period_end, fiscal_period, filed_at)
);
```

主キーに `filed_at` を含める理由は、**同じ会計期間に対して訂正報告が出る**ため。訂正前後の両方を保持し、PIT ビューで「その時点で最新だったもの」を選ぶ。

PIT ビュー（特徴量計算はこれのみを参照する）:

```sql
CREATE VIEW financials_pit AS
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY ticker, market, period_end, fiscal_period
        ORDER BY filed_at DESC
    ) AS rn
    FROM financials
) WHERE rn = 1;

-- 使用例: 2026-06-30 時点で知り得た情報のみ
-- SELECT * FROM financials WHERE filed_at <= DATE '2026-06-30' ...
```

`financials_pit` は「最新版」を返すビューであり、バックテスト時は必ず `filed_at <= as_of` の条件を追加する。この二段構えを間違えるとリークするため、`packages/core/storage/duckdb_repo.py` に `get_financials_as_of(as_of: date)` という関数を用意し、生SQLを書かせない。

### 2.5 `documents`（開示資料の正規化テーブル）

```sql
CREATE TABLE documents (
    doc_id            VARCHAR NOT NULL PRIMARY KEY,  -- source ごとに一意な合成キー
                                                     -- 'edinet:S100XXXX' 'edgar:0000320193-26-000012'
                                                     -- 'tdnet:20260823-1234'
    ticker            VARCHAR,
    market            VARCHAR NOT NULL,
    name_local        VARCHAR,            -- 提出者名（EDINET filerName 等）。一覧表示用。
                                          -- 証券マスタがある場合は API 側でそちらの名称を優先する。
    source            VARCHAR NOT NULL,   -- 'edinet' | 'tdnet' | 'edgar'
    doc_type          VARCHAR NOT NULL,   -- 下表参照
    form_code         VARCHAR,            -- EDINET docTypeCode / EDGAR form
    title             VARCHAR NOT NULL,   -- 原文タイトル（日本語のまま）
    title_en          VARCHAR,
    fiscal_period     VARCHAR,            -- '2026-Q1' '2026-FY'
    period_end        DATE,
    filed_at          TIMESTAMP NOT NULL,
    disclosed_at      TIMESTAMP,          -- TDnet の開示時刻（15:00 前後かで意味が変わる）
    source_url        VARCHAR NOT NULL,   -- 人間がクリックして開くURL
    pdf_url           VARCHAR,
    xbrl_url          VARCHAR,
    blob_path         VARCHAR,            -- ローカル保存先（相対パス）
    page_count        INTEGER,
    byte_size         BIGINT,
    language          VARCHAR,            -- 'ja' | 'en'
    is_amendment      BOOLEAN DEFAULT FALSE,
    amends_doc_id     VARCHAR,            -- 訂正元
    ingested_at       TIMESTAMP NOT NULL
);
CREATE INDEX idx_documents_ticker ON documents(ticker, market, filed_at DESC);
CREATE INDEX idx_documents_type ON documents(doc_type, filed_at DESC);
```

`ticker` は EDINET では 4 桁（`secCode` の末尾 0 を落とした値、例: `7203`）。
J-Quants の証券マスタと画面は 5 桁（`72030`）のことがある。読み出しは
`jp_ticker_aliases` で両方を同一銘柄として扱う。英字を含む新コード（`130A`）は
パディングしない。

`doc_type` の値域（固定値。追加時は本ドキュメントを更新する）:

| 値 | 意味 | 主なソース |
| --- | --- | --- |
| `annual_report` | 有価証券報告書 / 10-K | EDINET / EDGAR |
| `quarterly_report` | 四半期報告書 / 10-Q | EDINET / EDGAR |
| `semiannual_report` | 半期報告書 | EDINET |
| `earnings_flash` | 決算短信 | TDnet |
| `earnings_presentation` | 決算説明資料 | TDnet |
| `guidance_revision` | 業績予想の修正 | TDnet |
| `dividend_revision` | 配当予想の修正 | TDnet |
| `buyback` | 自己株式の取得 | TDnet |
| `stock_split` | 株式分割 | TDnet |
| `management_change` | 役員異動 | TDnet / EDGAR(8-K) |
| `current_report` | 臨時報告書 / 8-K | EDINET / EDGAR |
| `large_holding` | 大量保有報告書 / SC 13D/G | EDINET / EDGAR |
| `insider_transaction` | Form 4 | EDGAR |
| `proxy` | DEF 14A | EDGAR |
| `other_disclosure` | 上記以外 | 全て |

### 2.6 `document_summaries`（LLM要約のキャッシュ）

```sql
CREATE TABLE document_summaries (
    doc_id            VARCHAR NOT NULL,
    summary_version   INTEGER NOT NULL,   -- プロンプト変更で採番
    model_id          VARCHAR NOT NULL,   -- 'gemini-3.7-flash' 等
    prompt_hash       VARCHAR NOT NULL,   -- プロンプトテンプレートのSHA256（先頭16桁）
    input_hash        VARCHAR NOT NULL,   -- 入力ドキュメントのSHA256（先頭16桁）
    summary_ja        VARCHAR NOT NULL,   -- 3-5行の要約
    key_points        VARCHAR[],          -- 箇条書き
    risk_factors      VARCHAR[],          -- 抽出されたリスク
    guidance_tone     VARCHAR,            -- 'positive'|'neutral'|'cautious'|'negative'
    guidance_evidence VARCHAR,            -- トーン判定の根拠となる原文引用
    qualitative_score DOUBLE,             -- -1.0 .. +1.0
    citations         STRUCT(page INTEGER, quote VARCHAR)[],  -- 引用（必須）
    input_tokens      INTEGER,
    output_tokens     INTEGER,
    cost_usd          DOUBLE,
    computed_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (doc_id, summary_version)
);
```

**キャッシュキーは `(doc_id, prompt_hash, input_hash)`。** 同じ資料に同じプロンプトで2回課金しないことがコスト管理の中核である。`prompt_hash` を含めるため、プロンプトを改善したときだけ再計算される。

`citations` が空配列の行は挿入できない（CHECK制約が DuckDB で使えない場合はリポジトリ層で検証する）。引用のないLLM出力を保存しないことを構造で担保する。

### 2.7 `features_daily`（特徴量）

```sql
CREATE TABLE features_daily (
    ticker            VARCHAR NOT NULL,
    market            VARCHAR NOT NULL,
    as_of             DATE    NOT NULL,   -- この日の終値時点で計算可能な情報のみ

    -- リターン系
    ret_1d            DOUBLE,
    ret_5d            DOUBLE,
    ret_20d           DOUBLE,
    ret_60d           DOUBLE,
    ret_252d          DOUBLE,

    -- モメンタム
    mom_12_1          DOUBLE,             -- 12ヶ月momentumから直近1ヶ月を除外
    mom_6_1           DOUBLE,
    price_to_52w_high DOUBLE,
    dist_from_ma200   DOUBLE,

    -- ボラティリティ
    realized_vol_20d  DOUBLE,             -- 年率化
    realized_vol_60d  DOUBLE,
    garch_vol_1d      DOUBLE,             -- GARCH(1,1) の1日先予測（年率化）
    garch_vol_20d     DOUBLE,
    downside_dev_60d  DOUBLE,
    max_drawdown_252d DOUBLE,
    beta_market_252d  DOUBLE,

    -- テクニカル
    rsi_14            DOUBLE,
    macd              DOUBLE,
    macd_signal       DOUBLE,
    macd_hist         DOUBLE,
    bb_pct_b_20       DOUBLE,
    atr_14            DOUBLE,

    -- 流動性
    adv_20d           DOUBLE,             -- 20日平均売買代金
    turnover_ratio    DOUBLE,             -- 売買代金 / 時価総額
    amihud_illiq      DOUBLE,

    -- バリュエーション
    per               DOUBLE,
    per_forward       DOUBLE,             -- 会社予想ベース
    pbr               DOUBLE,
    psr               DOUBLE,
    ev_ebitda         DOUBLE,
    fcf_yield         DOUBLE,
    dividend_yield    DOUBLE,
    earnings_yield    DOUBLE,

    -- クオリティ
    roe               DOUBLE,
    roic              DOUBLE,
    gross_margin      DOUBLE,
    operating_margin  DOUBLE,
    debt_to_equity    DOUBLE,
    interest_coverage DOUBLE,
    accruals_ratio    DOUBLE,             -- 利益の質（低いほど良い）

    -- 成長
    revenue_growth_yoy DOUBLE,
    eps_growth_yoy    DOUBLE,
    revenue_cagr_3y   DOUBLE,
    forecast_revision_direction INTEGER,  -- -1 | 0 | +1（会社予想の改定方向）
    forecast_revision_magnitude DOUBLE,   -- 改定率

    -- 市場・マクロ連動
    fx_sensitivity_60d DOUBLE,            -- USD/JPY 変化に対する感応度
    sector_relative_ret_20d DOUBLE,

    -- メタ
    market_cap        DOUBLE,
    currency          VARCHAR NOT NULL,
    feature_version   VARCHAR NOT NULL,   -- 'v1.3.0'。定義変更時に採番
    n_missing         INTEGER,            -- 欠損した特徴量の個数
    computed_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (ticker, market, as_of, feature_version)
);
```

**`as_of` の定義を厳格にする**: `as_of = D` の行には、D日の終値までに公開された情報のみを含める。財務は `filed_at <= D`、開示は `filed_at <= D`（TDnetの15時以降の開示は翌営業日扱いとする）。この規則は `packages/core/factors/pit_guard.py` で強制する。

`feature_version` を主キーに含める理由は、特徴量定義を変えたときに過去のモデル結果を再現できるようにするため。

### 2.8 `scores_daily`（合成スコア）

```sql
CREATE TABLE scores_daily (
    ticker            VARCHAR NOT NULL,
    market            VARCHAR NOT NULL,
    as_of             DATE    NOT NULL,

    value_z           DOUBLE,             -- セクター中立化済み z-score
    momentum_z        DOUBLE,
    quality_z         DOUBLE,
    growth_z          DOUBLE,
    lowvol_z          DOUBLE,
    liquidity_z       DOUBLE,
    revision_z        DOUBLE,

    quant_score       DOUBLE,             -- 0-100 に正規化した合成値
    quant_rank        INTEGER,            -- 市場内順位
    quant_percentile  DOUBLE,
    sector_rank       INTEGER,

    qual_score        DOUBLE,             -- -1.0 .. +1.0（LLM由来）
    qual_confidence   DOUBLE,             -- 0.0 .. 1.0
    qual_doc_count    INTEGER,            -- 根拠にした資料数

    total_score       DOUBLE,             -- quant + qual のオーバーレイ後
    ml_pred_h5        DOUBLE,             -- LightGBM の予測（H5、超過リターン期待値）
    ml_pred_h20       DOUBLE,
    ml_pred_h5_lo     DOUBLE,             -- 信頼区間下限（分位点回帰）
    ml_pred_h5_hi     DOUBLE,
    ml_pred_h20_lo    DOUBLE,
    ml_pred_h20_hi    DOUBLE,

    weight_set_id     VARCHAR NOT NULL,   -- 使用した重みセット（Evaluatorが更新する）
    feature_version   VARCHAR NOT NULL,
    model_run_id      VARCHAR,            -- model_runs.run_id
    computed_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (ticker, market, as_of, weight_set_id)
);
```

### 2.9 `recommendations`（推奨カード）

```sql
CREATE TABLE recommendations (
    rec_id            VARCHAR NOT NULL PRIMARY KEY,   -- ULID
    as_of             DATE    NOT NULL,
    ticker            VARCHAR NOT NULL,
    market            VARCHAR NOT NULL,
    action            VARCHAR NOT NULL,   -- 'watch'|'accumulate'|'reduce'|'avoid'
    horizon           VARCHAR NOT NULL,   -- 'H5' | 'H20'
    conviction        VARCHAR NOT NULL,   -- 'low'|'medium'|'high'
    conviction_score  DOUBLE NOT NULL,    -- 0.0 .. 1.0

    thesis_ja         VARCHAR NOT NULL,   -- 強気論拠（2-4行）
    bear_case_ja      VARCHAR NOT NULL,   -- 弱気論拠。空文字列を許さない
    invalidation_ja   VARCHAR NOT NULL,   -- この推奨が無効になる条件
    reason_codes      VARCHAR[] NOT NULL, -- ['VAL_CHEAP_VS_SECTOR','REV_UP_GUIDANCE']

    entry_ref_price   DOUBLE,             -- 参考価格（prices_live 由来）
    entry_ref_source  VARCHAR,
    suggested_size_pct DOUBLE,            -- ポートフォリオに対する比率の目安
    stop_ref_price    DOUBLE,             -- ATRベースの参考ストップ
    target_ref_price  DOUBLE,

    expected_ret      DOUBLE,             -- モデルの点推定
    expected_ret_lo   DOUBLE,             -- 信頼区間下限（必須）
    expected_ret_hi   DOUBLE,             -- 信頼区間上限（必須）
    hit_rate_prior    DOUBLE,             -- 類似条件での過去的中率（必須）
    n_prior_samples   INTEGER,            -- 的中率の母数

    quant_score       DOUBLE,
    qual_score        DOUBLE,
    source_doc_ids    VARCHAR[] NOT NULL, -- 根拠資料。空配列を許さない
    citations         STRUCT(doc_id VARCHAR, page INTEGER, quote VARCHAR)[] NOT NULL,

    data_freshness    STRUCT(source VARCHAR, latest_as_of DATE)[],
    critic_verdict    VARCHAR,            -- 'approved'|'revised'|'rejected'
    critic_notes_ja   VARCHAR,
    memory_ids_used   VARCHAR[],          -- 注入された agent_memory の ID

    llm_model_id      VARCHAR,
    cost_usd          DOUBLE,
    generated_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_rec_asof ON recommendations(as_of DESC, market);
CREATE INDEX idx_rec_ticker ON recommendations(ticker, market, as_of DESC);
```

**リポジトリ層で強制する不変条件**（これらが本ツールの誠実性の担保である）:

1. `bear_case_ja` が空文字列または 20文字未満なら挿入を拒否する
2. `source_doc_ids` が空配列なら挿入を拒否する
3. `citations` が空配列なら挿入を拒否する
4. `expected_ret_lo` / `expected_ret_hi` が NULL なら挿入を拒否する
5. `hit_rate_prior` が NULL、または `n_prior_samples < 20` の場合は `conviction` を `low` に強制する
6. `critic_verdict = 'rejected'` の推奨は UI に出さない（保存はする。学習材料になる）
7. `conviction_score` が NULL、非有限、または 0.0..1.0 の外なら挿入を拒否する

`upsert` は DEFAULT のない NOT NULL 列が欠けている／NULL のとき、DuckDB の ConstraintException より先に列名付きの `StorageError` を返す。

### 2.10 `recommendation_outcomes`（実績。フィードバックループの入力）

```sql
CREATE TABLE recommendation_outcomes (
    rec_id            VARCHAR NOT NULL,
    horizon           VARCHAR NOT NULL,   -- 'H5' | 'H20'
    evaluated_at      TIMESTAMP NOT NULL,
    entry_date        DATE NOT NULL,      -- as_of の翌営業日
    exit_date         DATE NOT NULL,
    entry_price       DOUBLE NOT NULL,    -- prices_daily の始値（現実的な約定想定）
    exit_price        DOUBLE NOT NULL,
    raw_return        DOUBLE NOT NULL,
    benchmark_return  DOUBLE NOT NULL,    -- TOPIX / S&P500
    excess_return     DOUBLE NOT NULL,
    sector_excess_return DOUBLE,
    is_hit            BOOLEAN NOT NULL,   -- action の方向と excess_return の符号が一致
    max_favorable_excursion DOUBLE,       -- 期間中の最大有利変動
    max_adverse_excursion   DOUBLE,       -- 期間中の最大不利変動
    realized_vol      DOUBLE,
    notes_ja          VARCHAR,
    PRIMARY KEY (rec_id, horizon)
);
```

### 2.11 `fx_forecasts`（為替予測）

```sql
CREATE TABLE fx_forecasts (
    pair              VARCHAR NOT NULL,   -- 'USDJPY'
    as_of             DATE    NOT NULL,
    horizon_days      INTEGER NOT NULL,   -- 5 | 20 | 60
    model_id          VARCHAR NOT NULL,   -- 'random_walk'|'arimax_v2'|'vecm_v1'
    point_forecast    DOUBLE NOT NULL,
    ci_lo_80          DOUBLE NOT NULL,
    ci_hi_80          DOUBLE NOT NULL,
    ci_lo_95          DOUBLE NOT NULL,
    ci_hi_95          DOUBLE NOT NULL,
    vol_forecast_ann  DOUBLE,             -- GARCH 由来の年率ボラ
    -- ベースライン比較（統計的誠実性の中核）
    baseline_model_id VARCHAR NOT NULL DEFAULT 'random_walk',
    dm_statistic      DOUBLE,             -- Diebold-Mariano 統計量
    dm_pvalue         DOUBLE,
    beats_baseline    BOOLEAN,            -- dm_pvalue < 0.05 かつ 符号が有利
    rmse_oos_60d      DOUBLE,             -- 直近60営業日のアウトオブサンプルRMSE
    baseline_rmse_oos_60d DOUBLE,
    directional_accuracy_60d DOUBLE,
    computed_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (pair, as_of, horizon_days, model_id)
);
```

**`beats_baseline = FALSE` の場合、UIは「ランダムウォークに対する優位性は確認できていない」と明示表示する。** 点推定だけを見せることを禁止する。

`FxForecastBundle.as_rows()` は上表の列名で出す（`point` / `ci_lo` ではなく `point_forecast` / `ci_lo_80` / `ci_hi_80` / `ci_lo_95` / `ci_hi_95`）。80% と 95% の両方を必ず埋める。

### 2.12 `macro_series`（マクロ指標。vintage あり）

```sql
CREATE TABLE macro_series (
    series_id         VARCHAR NOT NULL,   -- 'DEXJPUS','DGS10','CPIAUCSL'
    observation_date  DATE    NOT NULL,
    vintage_date      DATE    NOT NULL,   -- この値が公表された日（改訂対応）
    value             DOUBLE,
    unit              VARCHAR,
    frequency         VARCHAR,            -- 'D'|'W'|'M'|'Q'
    source            VARCHAR NOT NULL DEFAULT 'fred',
    ingested_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (series_id, observation_date, vintage_date)
);

CREATE VIEW macro_series_latest AS
SELECT series_id, observation_date, value, unit, frequency
FROM (SELECT *, ROW_NUMBER() OVER (
        PARTITION BY series_id, observation_date ORDER BY vintage_date DESC) rn
      FROM macro_series) WHERE rn = 1;
```

バックテストでは `vintage_date <= as_of` で絞る。日次系列（為替・金利）は改訂されないため `vintage_date = observation_date` としてよいが、CPI・失業率・GDPは必ず vintage を使う。

### 2.13 `model_runs`（モデル学習・推論の記録）

```sql
CREATE TABLE model_runs (
    run_id            VARCHAR NOT NULL PRIMARY KEY,   -- ULID
    model_kind        VARCHAR NOT NULL,   -- 'ranker'|'garch'|'arimax'|'vecm'
    model_version     VARCHAR NOT NULL,
    market            VARCHAR,
    horizon           VARCHAR,
    train_start       DATE,
    train_end         DATE,
    valid_start       DATE,
    valid_end         DATE,
    cv_scheme         VARCHAR NOT NULL,   -- 'purged_walk_forward'
    purge_days        INTEGER NOT NULL,
    embargo_days      INTEGER NOT NULL,
    n_folds           INTEGER,
    feature_version   VARCHAR NOT NULL,
    feature_list      VARCHAR[] NOT NULL,
    hyperparams       JSON,
    input_snapshot_hash VARCHAR NOT NULL, -- 入力データのハッシュ（再現性）
    metrics           JSON,               -- {ic, rank_ic, ndcg, sharpe, dsr, ...}
    n_trials          INTEGER,            -- 探索した設定数（DSR の計算に必要）
    artifact_path     VARCHAR,            -- モデルファイルの保存先
    git_commit        VARCHAR,
    started_at        TIMESTAMP NOT NULL,
    finished_at       TIMESTAMP,
    status            VARCHAR NOT NULL    -- 'running'|'success'|'failed'
);
```

`n_trials` を必ず記録する。Deflated Sharpe Ratio の計算に試行回数が必要であり、これを記録しないと多重検定バイアスを定量化できない。

### 2.14 `backtest_runs`

```sql
CREATE TABLE backtest_runs (
    backtest_id       VARCHAR NOT NULL PRIMARY KEY,
    strategy_name     VARCHAR NOT NULL,
    model_run_id      VARCHAR,
    market            VARCHAR NOT NULL,
    period_start      DATE NOT NULL,
    period_end        DATE NOT NULL,
    rebalance_freq    VARCHAR NOT NULL,   -- 'weekly'|'monthly'
    universe_filter   JSON,               -- 流動性・時価総額フィルタ
    n_positions       INTEGER NOT NULL,

    -- 以下3項目は必須引数。デフォルト値を持たせない
    fee_bps           DOUBLE NOT NULL,
    slippage_bps      DOUBLE NOT NULL,
    max_turnover_pct  DOUBLE NOT NULL,

    total_return      DOUBLE,
    cagr              DOUBLE,
    volatility        DOUBLE,
    sharpe            DOUBLE,
    sortino           DOUBLE,
    max_drawdown      DOUBLE,
    calmar            DOUBLE,
    hit_rate          DOUBLE,
    profit_factor     DOUBLE,
    avg_turnover      DOUBLE,
    total_cost_bps    DOUBLE,             -- 累計取引コスト
    benchmark_return  DOUBLE,
    alpha_vs_bench    DOUBLE,
    information_ratio DOUBLE,

    n_trials          INTEGER NOT NULL,   -- DSR 計算用
    deflated_sharpe   DOUBLE,             -- 必須出力
    dsr_pvalue        DOUBLE,
    is_significant    BOOLEAN,            -- dsr_pvalue < 0.05
    equity_curve_path VARCHAR,            -- Parquet
    trades_path       VARCHAR,            -- Parquet
    config            JSON,
    git_commit        VARCHAR,
    run_at            TIMESTAMP NOT NULL
);
```

### 2.15 補助テーブル

```sql
-- データ欠損の記録
CREATE TABLE data_gaps (
    gap_id      VARCHAR PRIMARY KEY,
    source      VARCHAR NOT NULL,
    entity      VARCHAR NOT NULL,   -- ticker や series_id
    gap_start   DATE NOT NULL,
    gap_end     DATE NOT NULL,
    reason      VARCHAR,            -- 'not_found'|'quality_reject'|'rate_limited'
    is_resolved BOOLEAN DEFAULT FALSE,
    detected_at TIMESTAMP NOT NULL
);

-- ソース間の値の食い違い
CREATE TABLE data_conflicts (
    conflict_id     VARCHAR PRIMARY KEY,
    entity          VARCHAR NOT NULL,
    field           VARCHAR NOT NULL,
    as_of           DATE NOT NULL,
    source_a        VARCHAR NOT NULL,
    value_a         DOUBLE,
    source_b        VARCHAR NOT NULL,
    value_b         DOUBLE,
    diff_pct        DOUBLE,
    resolved_source VARCHAR,
    detected_at     TIMESTAMP NOT NULL
);

-- 品質フラグ
CREATE TABLE data_quality_flags (
    flag_id     VARCHAR PRIMARY KEY,
    table_name  VARCHAR NOT NULL,
    entity      VARCHAR NOT NULL,
    as_of       DATE NOT NULL,
    flag_code   VARCHAR NOT NULL,
    detail      VARCHAR,
    detected_at TIMESTAMP NOT NULL
);

-- データ鮮度（UIヘッダ表示用のビュー）
CREATE VIEW data_freshness AS
SELECT 'jquants' AS source, MAX(trade_date) AS latest_as_of
  FROM prices_daily WHERE source = 'jquants'
UNION ALL
SELECT 'yfinance', MAX(trade_date) FROM prices_live
UNION ALL
SELECT 'edinet', MAX(CAST(filed_at AS DATE)) FROM documents WHERE source='edinet'
UNION ALL
SELECT 'edgar', MAX(CAST(filed_at AS DATE)) FROM documents WHERE source='edgar'
UNION ALL
SELECT 'fred', MAX(observation_date) FROM macro_series;
```

## 3. SQLite スキーマ（状態管理）

SQLAlchemy 2.0 の declarative モデルで定義する。**Postgres への移行を接続文字列の変更だけで済ませるため、SQLite 固有の型・関数を使わない。**

### 3.1 `job_runs`

```sql
CREATE TABLE job_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name        TEXT NOT NULL,      -- 'collector_jp','analyst','strategist',...
    market          TEXT,
    trigger         TEXT NOT NULL,      -- 'schedule'|'manual'|'retry'|'resume'
    status          TEXT NOT NULL,      -- 'running'|'success'|'partial'|'failed'|'skipped'
    started_at      TEXT NOT NULL,      -- ISO8601 UTC
    finished_at     TEXT,
    duration_sec    REAL,
    checkpoint      TEXT,               -- JSON。再開位置
    metrics         TEXT,               -- JSON
    error_type      TEXT,
    error_message   TEXT,
    error_traceback TEXT,
    retry_count     INTEGER DEFAULT 0,
    parent_run_id   INTEGER,
    git_commit      TEXT,
    pid             INTEGER             -- 実行プロセス。生存確認に使う
);
CREATE INDEX idx_job_runs_name ON job_runs(job_name, started_at DESC);
```

`checkpoint` の中身の例:

```json
{"phase": "jquants_daily_bars",
 "completed_dates": ["2026-05-01", "2026-05-02"],
 "next_date": "2026-05-05",
 "api_calls_used": 42}
```

**Windows Update による再起動後、`status='running'` のまま残ったレコードを起動時に検出し、`checkpoint` から再開する。** API 起動時は新しいプロセスなので、`running` の行はすべて前プロセスの残骸として `interrupted` にする。15分ごとの `resume_interrupted_jobs` は `pid` が生存していれば触らず、死んでから2時間以上 `running` の行だけを `interrupted` にする。実行しない resume 用の job_run は作らない。

### 3.2 `agent_memory`（フィードバックループの実体）

```sql
CREATE TABLE agent_memory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id       TEXT NOT NULL UNIQUE,   -- ULID
    scope           TEXT NOT NULL,      -- 'global'|'market'|'sector'|'ticker'
    scope_value     TEXT,               -- 'JP' / '輸送用機器' / '7203'
    category        TEXT NOT NULL,      -- 'lesson'|'bias'|'pattern'|'caveat'
    lesson_ja       TEXT NOT NULL,      -- プロンプトに注入される本文
    evidence_ja     TEXT NOT NULL,      -- なぜそう言えるかの根拠
    derived_from    TEXT NOT NULL,      -- JSON: 根拠となった rec_id の配列
    n_observations  INTEGER NOT NULL,   -- 母数
    confidence      REAL NOT NULL,      -- 0.0 .. 1.0
    hit_rate_before REAL,
    hit_rate_after  REAL,               -- この教訓の適用後（効果測定）
    is_active       BOOLEAN NOT NULL DEFAULT 1,
    superseded_by   TEXT,               -- 新しい教訓に置き換えられた場合
    created_at      TEXT NOT NULL,
    last_used_at    TEXT,
    use_count       INTEGER DEFAULT 0,
    review_due_at   TEXT                -- 定期的な見直し期限
);
CREATE INDEX idx_memory_scope ON agent_memory(scope, scope_value, is_active);
```

**運用ルール**:

- プロンプトに注入するのは `is_active=1` かつ `confidence >= 0.6` かつ `n_observations >= 10` のものだけ
- 注入数の上限を 15件（トークン予算の観点）とし、`confidence * log(n_observations)` の降順で選ぶ
- `hit_rate_after` が `hit_rate_before` を下回り続ける教訓は `is_active=0` にする（教訓が有害だった場合の自己修正）
- 90日ごとに全教訓を再評価する（`review_due_at`）

### 3.3 `factor_weights`

```sql
CREATE TABLE factor_weights (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    weight_set_id   TEXT NOT NULL UNIQUE,
    market          TEXT NOT NULL,
    horizon         TEXT NOT NULL,
    weights         TEXT NOT NULL,      -- JSON: {"value":0.25,"momentum":0.30,...}
    fitted_from     TEXT NOT NULL,      -- 学習期間の開始
    fitted_to       TEXT NOT NULL,
    fit_method      TEXT NOT NULL,      -- 'ridge_ic'|'equal'|'manual'
    ic_in_sample    REAL,
    ic_out_of_sample REAL,
    is_active       BOOLEAN NOT NULL DEFAULT 0,
    activated_at    TEXT,
    deactivated_at  TEXT,
    created_by      TEXT NOT NULL,      -- 'evaluator'|'manual'
    created_at      TEXT NOT NULL
);
```

同時に `is_active=1` になれるのは `(market, horizon)` ごとに1つ。Evaluator が新しい重みを提案しても、**アウトオブサンプルICが現行を上回らない限り自動有効化しない**（設定で「自動」「承認制」を切り替え可能。既定は承認制）。

### 3.4 `llm_calls`（コスト管理）

```sql
CREATE TABLE llm_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id         TEXT NOT NULL UNIQUE,
    job_run_id      INTEGER,
    tier            TEXT NOT NULL,      -- 'bulk'|'default'|'deep'
    model_id        TEXT NOT NULL,
    purpose         TEXT NOT NULL,      -- 'doc_summary'|'thesis'|'critic'|'evaluator'|'weekly_review'
    entity          TEXT,               -- ticker や doc_id
    input_tokens    INTEGER NOT NULL,
    output_tokens   INTEGER NOT NULL,
    cached_tokens   INTEGER DEFAULT 0,
    cost_usd        REAL NOT NULL,
    latency_ms      INTEGER,
    was_cache_hit   BOOLEAN DEFAULT 0,
    status          TEXT NOT NULL,      -- 'success'|'error'|'blocked_by_cap'
    error_message   TEXT,
    called_at       TEXT NOT NULL
);
CREATE INDEX idx_llm_calls_date ON llm_calls(called_at);

CREATE TABLE cost_budget (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    period          TEXT NOT NULL,      -- 'daily'|'monthly'
    period_key      TEXT NOT NULL,      -- '2026-08-23' | '2026-08'
    cap_usd         REAL NOT NULL,
    spent_usd       REAL NOT NULL DEFAULT 0,
    is_exceeded     BOOLEAN NOT NULL DEFAULT 0,
    kill_switch_on  BOOLEAN NOT NULL DEFAULT 0,
    updated_at      TEXT NOT NULL,
    UNIQUE (period, period_key)
);
```

### 3.5 `trades` / `positions`（手動売買の記録）

```sql
CREATE TABLE trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT NOT NULL UNIQUE,
    ticker          TEXT NOT NULL,
    market          TEXT NOT NULL,
    side            TEXT NOT NULL,      -- 'buy'|'sell'
    quantity        REAL NOT NULL,
    price           REAL NOT NULL,
    fee             REAL DEFAULT 0,
    currency        TEXT NOT NULL,
    executed_at     TEXT NOT NULL,
    broker          TEXT,               -- 自由記述
    account_type    TEXT,               -- '特定'|'NISA'|'一般'
    linked_rec_id   TEXT,               -- どの推奨に基づいたか（追跡の要）
    thesis_ja       TEXT,               -- 自分の判断理由（入力時に書く）
    emotion_tag     TEXT,               -- 'confident'|'fomo'|'fearful'|'neutral'
    exit_plan_ja    TEXT,
    review_ja       TEXT,               -- 事後レビュー
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE positions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    market          TEXT NOT NULL,
    account_type    TEXT,
    quantity        REAL NOT NULL,
    avg_cost        REAL NOT NULL,
    currency        TEXT NOT NULL,
    opened_at       TEXT NOT NULL,
    closed_at       TEXT,
    is_open         BOOLEAN NOT NULL DEFAULT 1,
    updated_at      TEXT NOT NULL,
    UNIQUE (ticker, market, account_type, opened_at)
);
```

`linked_rec_id` と `emotion_tag` を持つ理由は、**「ツールの推奨の質」と「自分の実行の質」を分離して評価する**ため。推奨が良くても実行が悪ければ成績は出ない。この切り分けができないと改善対象が特定できない。

### 3.6 `settings` / `watchlist` / `alerts`

```sql
CREATE TABLE settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,      -- JSON
    updated_at      TEXT NOT NULL
);
```

既定の設定キー:

| key | 型 | 既定値 | 説明 |
| --- | --- | --- | --- |
| `ui.direction_colors` | string | `"jp"` | `"jp"`（赤=上昇）または `"us"`（緑=上昇） |
| `ui.theme` | string | `"dark"` | `"dark"` / `"light"` / `"system"` |
| `ui.base_currency` | string | `"JPY"` | 評価額の表示通貨 |
| `ui.default_market` | string | `"JP"` | 初期表示市場。`"JP"` / `"US"` / `"auto"`（日本時間15時未満は JP、以降は US） |
| `llm.daily_cap_usd` | number | `1.0` | 日次コスト上限 |
| `llm.monthly_cap_usd` | number | `20.0` | 月次コスト上限 |
| `llm.kill_switch` | boolean | `false` | 全LLM呼び出しの停止 |
| `data.jquants_plan` | string | `"free"` | `"free"` / `"light"` |
| `data.tdnet_enabled` | boolean | `false` | 規約確認後に有効化 |
| `agent.auto_activate_weights` | boolean | `false` | 重み更新の自動適用 |
| `agent.max_recommendations_per_day` | number | `10` | 推奨カードの目標かつ上限。コア候補が足りなければ定量順位で補充する |
| `risk.max_position_pct` | number | `10.0` | 1銘柄あたりの上限比率 |

```sql
CREATE TABLE watchlist (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT NOT NULL,
    market      TEXT NOT NULL,
    list_name   TEXT NOT NULL DEFAULT 'default',
    note_ja     TEXT,
    added_at    TEXT NOT NULL,
    UNIQUE (ticker, market, list_name)
);

CREATE TABLE alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id    TEXT NOT NULL UNIQUE,
    severity    TEXT NOT NULL,      -- 'info'|'warning'|'error'
    category    TEXT NOT NULL,      -- 'data'|'cost'|'model'|'runtime'
    title_ja    TEXT NOT NULL,
    body_ja     TEXT,
    entity      TEXT,
    is_read     BOOLEAN DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE rate_limit_state (
    source          TEXT PRIMARY KEY,
    tokens          REAL NOT NULL,
    last_refill_at  TEXT NOT NULL,
    calls_today     INTEGER NOT NULL DEFAULT 0,
    day_key         TEXT NOT NULL
);

CREATE TABLE backfill_progress (
    step_name       TEXT PRIMARY KEY,
    status          TEXT NOT NULL,      -- 'pending'|'running'|'done'|'failed'
    cursor_value    TEXT,               -- 再開位置
    total_units     INTEGER,
    done_units      INTEGER,
    updated_at      TEXT NOT NULL
);
```

## 4. LanceDB スキーマ（ベクトルストア）

`VectorStore` 抽象の背後に置く。Phase B で pgvector に差し替える。

```python
# packages/core/storage/vector_store.py
class VectorStore(Protocol):
    def upsert(self, chunks: list["DocChunk"]) -> int: ...
    def search(self, query_vec: list[float], *, k: int,
               filters: dict | None = None) -> list["SearchHit"]: ...
    def delete_by_doc(self, doc_id: str) -> int: ...
```

テーブル `doc_chunks` のフィールド:

| フィールド | 型 | 説明 |
| --- | --- | --- |
| `chunk_id` | string | `{doc_id}#{chunk_index}` |
| `doc_id` | string | `documents.doc_id` への参照 |
| `ticker` | string | フィルタ用 |
| `market` | string | フィルタ用 |
| `doc_type` | string | フィルタ用 |
| `filed_at` | timestamp | **鮮度フィルタ用。古い資料を混ぜないために必須** |
| `fiscal_period` | string | フィルタ用 |
| `page_from` | int32 | 引用時のページ番号 |
| `page_to` | int32 | |
| `section` | string | `'事業等のリスク'` `'Item 1A. Risk Factors'` など |
| `text` | string | チャンク本文（日本語のまま） |
| `token_count` | int32 | |
| `embedding` | vector(3072) | 次元は使用モデルに合わせる。`[要検証]` |
| `embedding_model` | string | `'gemini-embedding'` / `'text-embedding-3-small'` |
| `embedding_version` | string | 再埋め込みの管理 |
| `created_at` | timestamp | |

**チャンク分割規則**: 見出し単位を優先し、1チャンク 800-1,200トークン、オーバーラップ 150トークン。日本語の場合は句点で境界を切る。ページ番号を必ず保持する（引用の検証に必要）。

`embedding_model` と `embedding_version` を持つ理由は、埋め込みモデルを変えたときに混在させないため。検索時は同一 `embedding_version` のみを対象にする。

## 5. マイグレーション管理

| ストア | ツール | 方針 |
| --- | --- | --- |
| SQLite | Alembic | 全変更をマイグレーションで管理。Postgres移行時にそのまま使える |
| DuckDB | 自前のバージョン管理テーブル + SQLスクリプト | `packages/core/storage/migrations/duckdb/NNN_description.sql`。`schema_version` テーブルで適用済みを追跡 |
| LanceDB | 再構築 | スキーマ変更時は Raw層から再埋め込み（コストがかかるので慎重に） |

DuckDB のマイグレーションは**前方のみ**（ロールバックを用意しない）。壊れた場合は Raw層からの再構築を正とする。この判断は「Raw層を必ず残す」方針とセットで成立する。

## 6. データ量の見積もり

| データ | 行数 | サイズ |
| --- | --- | --- |
| `prices_daily`（JP 4,000銘柄 × 490日） | 約196万行 | 約120MB（Parquet圧縮後 約25MB） |
| `prices_daily`（US 1,000銘柄 × 1,260日） | 約126万行 | 約80MB |
| `features_daily`（5,000銘柄 × 490日 × 60列） | 約245万行 | 約900MB |
| `financials` | 約10万行 | 約30MB |
| `documents` | 約5万行 | 約20MB |
| Raw層（JSON.gz） | - | 約2GB / 年 |
| PDF blob（有報 + 決算短信） | 約1万件 | 約20GB |
| LanceDB（100万チャンク × 3072次元 float32） | 約100万行 | 約12GB |

合計で 40GB 程度を見込む。**`data/` は必ず WSL2 のホーム配下に置く**（`/mnt/c/` 配下ではI/Oが桁違いに遅く、この規模のParquet/DuckDB処理では致命的になる。[15-windows-runtime.md](15-windows-runtime.md)）。

PDF blob と LanceDB が支配的なので、ディスク容量が厳しい場合は以下の順で削減する。

1. PDF blob を要約後に削除する（`documents.blob_path` を NULL にし、`source_url` から再取得可能にする）
2. LanceDB の対象を直近2年の資料に限定する
3. 埋め込み次元を削減する（`text-embedding-3-small` の 1536次元に切り替え）

## 7. 参照

- データ取得仕様: [02-data-ingestion.md](02-data-ingestion.md)
- 特徴量の定義式: [04-analysis-engine.md](04-analysis-engine.md)
- スコアリング: [05-scoring-screening.md](05-scoring-screening.md)
- API 応答スキーマ: [09-api-spec.md](09-api-spec.md)
