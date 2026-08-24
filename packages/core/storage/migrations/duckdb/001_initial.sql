-- 001_initial.sql
-- docs/03-data-model.md §2 の DuckDB スキーマをそのまま起こしたもの。
-- DuckDB のマイグレーションは前方のみ（ロールバックを用意しない）。
-- 壊れた場合は Raw 層からの再構築を正とする。
--
-- 注: DuckDB の CREATE INDEX は ASC/DESC の指定を受け付けないため、
-- docs の `... DESC` は落としてある（ART インデックスは順序を持たない）。

-- ---------------------------------------------------------------------------
-- 2.1 securities（銘柄マスタ・履歴あり）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS securities (
    ticker            VARCHAR NOT NULL,
    market            VARCHAR NOT NULL,
    exchange          VARCHAR,
    name_local        VARCHAR NOT NULL,
    name_en           VARCHAR,
    name_kana         VARCHAR,
    sector_code       VARCHAR,
    sector_name       VARCHAR,
    industry_name     VARCHAR,
    currency          VARCHAR NOT NULL,
    cik               VARCHAR,
    edinet_code       VARCHAR,
    isin              VARCHAR,
    shares_outstanding BIGINT,
    trading_unit      INTEGER,
    listing_date      DATE,
    delisting_date    DATE,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    valid_from        DATE NOT NULL,
    valid_to          DATE,
    ingested_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (ticker, market, valid_from)
);
CREATE INDEX IF NOT EXISTS idx_securities_active ON securities(market, is_active);

-- ---------------------------------------------------------------------------
-- 2.2 prices_daily（リサーチ用・確定値）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prices_daily (
    ticker            VARCHAR NOT NULL,
    market            VARCHAR NOT NULL,
    trade_date        DATE    NOT NULL,
    open              DOUBLE,
    high              DOUBLE,
    low               DOUBLE,
    close             DOUBLE,
    volume            BIGINT,
    turnover_value    DOUBLE,
    adj_open          DOUBLE,
    adj_high          DOUBLE,
    adj_low           DOUBLE,
    adj_close         DOUBLE,
    adj_volume        BIGINT,
    adjustment_factor DOUBLE DEFAULT 1.0,
    currency          VARCHAR NOT NULL,
    source            VARCHAR NOT NULL,
    quality_flags     VARCHAR[],
    ingested_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (ticker, market, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_prices_daily_date ON prices_daily(trade_date);

-- ---------------------------------------------------------------------------
-- 2.3 prices_live（現在値・参考値。モデル学習禁止）
--     packages/core/models/ と packages/core/backtest/ から参照しないこと。
--     違反は T-LEAK-02 で検出する。
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prices_live (
    ticker            VARCHAR NOT NULL,
    market            VARCHAR NOT NULL,
    trade_date        DATE    NOT NULL,
    open              DOUBLE,
    high              DOUBLE,
    low               DOUBLE,
    close             DOUBLE,
    prev_close        DOUBLE,
    change_pct        DOUBLE,
    volume            BIGINT,
    currency          VARCHAR NOT NULL,
    source            VARCHAR NOT NULL,
    is_delayed        BOOLEAN NOT NULL DEFAULT TRUE,
    delay_note        VARCHAR,
    quoted_at         TIMESTAMP,
    ingested_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (ticker, market, trade_date)
);

-- ---------------------------------------------------------------------------
-- 2.4 financials（財務。PIT厳守）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS financials (
    ticker            VARCHAR NOT NULL,
    market            VARCHAR NOT NULL,
    period_end        DATE    NOT NULL,
    fiscal_year       INTEGER NOT NULL,
    fiscal_period     VARCHAR NOT NULL,
    period_type       VARCHAR NOT NULL,
    filed_at          DATE    NOT NULL,
    accession         VARCHAR,
    doc_id            VARCHAR,

    revenue           DOUBLE,
    operating_income  DOUBLE,
    ordinary_income   DOUBLE,
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

    forecast_revenue  DOUBLE,
    forecast_op_income DOUBLE,
    forecast_net_income DOUBLE,
    forecast_eps      DOUBLE,
    forecast_revised_at DATE,

    accounting_standard VARCHAR,
    currency          VARCHAR NOT NULL,
    unit_multiplier   INTEGER DEFAULT 1,
    is_restated       BOOLEAN DEFAULT FALSE,
    source            VARCHAR NOT NULL,
    ingested_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (ticker, market, period_end, fiscal_period, filed_at)
);

-- 「最新版」を返すビュー。バックテスト時は必ず filed_at <= as_of を追加する。
-- 生 SQL を書かせないため duckdb_repo.get_financials_as_of() を使うこと。
CREATE OR REPLACE VIEW financials_pit AS
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY ticker, market, period_end, fiscal_period
        ORDER BY filed_at DESC
    ) AS rn
    FROM financials
) WHERE rn = 1;

-- ---------------------------------------------------------------------------
-- 2.5 documents
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    doc_id            VARCHAR NOT NULL PRIMARY KEY,
    ticker            VARCHAR,
    market            VARCHAR NOT NULL,
    source            VARCHAR NOT NULL,
    doc_type          VARCHAR NOT NULL,
    form_code         VARCHAR,
    title             VARCHAR NOT NULL,
    title_en          VARCHAR,
    fiscal_period     VARCHAR,
    period_end        DATE,
    filed_at          TIMESTAMP NOT NULL,
    disclosed_at      TIMESTAMP,
    source_url        VARCHAR NOT NULL,
    pdf_url           VARCHAR,
    xbrl_url          VARCHAR,
    blob_path         VARCHAR,
    page_count        INTEGER,
    byte_size         BIGINT,
    language          VARCHAR,
    is_amendment      BOOLEAN DEFAULT FALSE,
    amends_doc_id     VARCHAR,
    ingested_at       TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_ticker ON documents(ticker, market, filed_at);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(doc_type, filed_at);

-- ---------------------------------------------------------------------------
-- 2.6 document_summaries（LLM要約のキャッシュ）
--     citations が空の行は挿入しない（リポジトリ層で検証する）。
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_summaries (
    doc_id            VARCHAR NOT NULL,
    summary_version   INTEGER NOT NULL,
    model_id          VARCHAR NOT NULL,
    prompt_hash       VARCHAR NOT NULL,
    input_hash        VARCHAR NOT NULL,
    headline_ja       VARCHAR,
    summary_ja        VARCHAR NOT NULL,
    key_points        VARCHAR[],
    risk_factors      VARCHAR[],
    guidance_tone     VARCHAR,
    guidance_evidence VARCHAR,
    tone_rationale_ja VARCHAR,
    qualitative_score DOUBLE,
    citations         STRUCT(page INTEGER, quote VARCHAR)[],
    input_tokens      INTEGER,
    output_tokens     INTEGER,
    cost_usd          DOUBLE,
    computed_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (doc_id, summary_version)
);

-- ---------------------------------------------------------------------------
-- 2.7 features_daily
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS features_daily (
    ticker            VARCHAR NOT NULL,
    market            VARCHAR NOT NULL,
    as_of             DATE    NOT NULL,

    ret_1d            DOUBLE,
    ret_5d            DOUBLE,
    ret_20d           DOUBLE,
    ret_60d           DOUBLE,
    ret_252d          DOUBLE,

    mom_12_1          DOUBLE,
    mom_6_1           DOUBLE,
    price_to_52w_high DOUBLE,
    dist_from_ma200   DOUBLE,

    realized_vol_20d  DOUBLE,
    realized_vol_60d  DOUBLE,
    garch_vol_1d      DOUBLE,
    garch_vol_20d     DOUBLE,
    downside_dev_60d  DOUBLE,
    max_drawdown_252d DOUBLE,
    beta_market_252d  DOUBLE,

    rsi_14            DOUBLE,
    macd              DOUBLE,
    macd_signal       DOUBLE,
    macd_hist         DOUBLE,
    bb_pct_b_20       DOUBLE,
    atr_14            DOUBLE,

    adv_20d           DOUBLE,
    turnover_ratio    DOUBLE,
    amihud_illiq      DOUBLE,

    per               DOUBLE,
    per_forward       DOUBLE,
    pbr               DOUBLE,
    psr               DOUBLE,
    ev_ebitda         DOUBLE,
    fcf_yield         DOUBLE,
    dividend_yield    DOUBLE,
    earnings_yield    DOUBLE,

    roe               DOUBLE,
    roic              DOUBLE,
    gross_margin      DOUBLE,
    operating_margin  DOUBLE,
    debt_to_equity    DOUBLE,
    interest_coverage DOUBLE,
    accruals_ratio    DOUBLE,

    revenue_growth_yoy DOUBLE,
    eps_growth_yoy    DOUBLE,
    revenue_cagr_3y   DOUBLE,
    forecast_revision_direction INTEGER,
    forecast_revision_magnitude DOUBLE,

    fx_sensitivity_60d DOUBLE,
    sector_relative_ret_20d DOUBLE,

    market_cap        DOUBLE,
    currency          VARCHAR NOT NULL,
    feature_version   VARCHAR NOT NULL,
    n_missing         INTEGER,
    computed_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (ticker, market, as_of, feature_version)
);

-- ---------------------------------------------------------------------------
-- 2.8 scores_daily
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scores_daily (
    ticker            VARCHAR NOT NULL,
    market            VARCHAR NOT NULL,
    as_of             DATE    NOT NULL,

    value_z           DOUBLE,
    momentum_z        DOUBLE,
    quality_z         DOUBLE,
    growth_z          DOUBLE,
    lowvol_z          DOUBLE,
    liquidity_z       DOUBLE,
    revision_z        DOUBLE,

    quant_score       DOUBLE,
    quant_rank        INTEGER,
    quant_percentile  DOUBLE,
    sector_rank       INTEGER,

    qual_score        DOUBLE,
    qual_confidence   DOUBLE,
    qual_doc_count    INTEGER,

    total_score       DOUBLE,
    ml_pred_h5        DOUBLE,
    ml_pred_h20       DOUBLE,
    ml_pred_h5_lo     DOUBLE,
    ml_pred_h5_hi     DOUBLE,
    ml_pred_h20_lo    DOUBLE,
    ml_pred_h20_hi    DOUBLE,

    weight_set_id     VARCHAR NOT NULL,
    feature_version   VARCHAR NOT NULL,
    model_run_id      VARCHAR,
    computed_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (ticker, market, as_of, weight_set_id)
);
CREATE INDEX IF NOT EXISTS idx_scores_asof ON scores_daily(market, as_of);

-- ---------------------------------------------------------------------------
-- 2.9 recommendations
--     不変条件はリポジトリ層（duckdb_repo.insert_recommendations）で強制する。
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recommendations (
    rec_id            VARCHAR NOT NULL PRIMARY KEY,
    as_of             DATE    NOT NULL,
    ticker            VARCHAR NOT NULL,
    market            VARCHAR NOT NULL,
    action            VARCHAR NOT NULL,
    horizon           VARCHAR NOT NULL,
    conviction        VARCHAR NOT NULL,
    conviction_score  DOUBLE NOT NULL,

    thesis_ja         VARCHAR NOT NULL,
    bear_case_ja      VARCHAR NOT NULL,
    invalidation_ja   VARCHAR NOT NULL,
    reason_codes      VARCHAR[] NOT NULL,

    entry_ref_price   DOUBLE,
    entry_ref_source  VARCHAR,
    entry_ref_note_ja VARCHAR,
    suggested_size_pct DOUBLE,
    stop_ref_price    DOUBLE,
    target_ref_price  DOUBLE,
    currency          VARCHAR,

    expected_ret      DOUBLE,
    expected_ret_lo   DOUBLE,
    expected_ret_hi   DOUBLE,
    hit_rate_prior    DOUBLE,
    n_prior_samples   INTEGER,

    quant_score       DOUBLE,
    quant_rank        INTEGER,
    quant_percentile  DOUBLE,
    qual_score        DOUBLE,
    qual_confidence   DOUBLE,
    qual_doc_count    INTEGER,
    total_score       DOUBLE,
    ml_pred           DOUBLE,
    factor_scores     STRUCT(
                          value DOUBLE, momentum DOUBLE, quality DOUBLE,
                          growth DOUBLE, lowvol DOUBLE, liquidity DOUBLE,
                          revision DOUBLE
                      ),

    source_doc_ids    VARCHAR[] NOT NULL,
    citations         STRUCT(doc_id VARCHAR, page INTEGER, quote VARCHAR)[] NOT NULL,

    data_freshness    STRUCT(source VARCHAR, latest_as_of VARCHAR)[],
    critic_verdict    VARCHAR,
    critic_notes_ja   VARCHAR,
    memory_ids_used   VARCHAR[],
    flags             VARCHAR[],

    llm_model_id      VARCHAR,
    cost_usd          DOUBLE,
    generated_at      TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rec_asof ON recommendations(as_of, market);
CREATE INDEX IF NOT EXISTS idx_rec_ticker ON recommendations(ticker, market, as_of);

-- ---------------------------------------------------------------------------
-- 2.10 recommendation_outcomes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recommendation_outcomes (
    rec_id            VARCHAR NOT NULL,
    horizon           VARCHAR NOT NULL,
    evaluated_at      TIMESTAMP NOT NULL,
    entry_date        DATE NOT NULL,
    exit_date         DATE NOT NULL,
    entry_price       DOUBLE NOT NULL,
    exit_price        DOUBLE NOT NULL,
    raw_return        DOUBLE NOT NULL,
    benchmark_return  DOUBLE NOT NULL,
    excess_return     DOUBLE NOT NULL,
    sector_excess_return DOUBLE,
    is_hit            BOOLEAN NOT NULL,
    max_favorable_excursion DOUBLE,
    max_adverse_excursion   DOUBLE,
    realized_vol      DOUBLE,
    notes_ja          VARCHAR,
    PRIMARY KEY (rec_id, horizon)
);

-- ---------------------------------------------------------------------------
-- 2.11 fx_forecasts
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fx_forecasts (
    pair              VARCHAR NOT NULL,
    as_of             DATE    NOT NULL,
    horizon_days      INTEGER NOT NULL,
    model_id          VARCHAR NOT NULL,
    point_forecast    DOUBLE NOT NULL,
    ci_lo_80          DOUBLE NOT NULL,
    ci_hi_80          DOUBLE NOT NULL,
    ci_lo_95          DOUBLE NOT NULL,
    ci_hi_95          DOUBLE NOT NULL,
    vol_forecast_ann  DOUBLE,
    baseline_model_id VARCHAR NOT NULL DEFAULT 'random_walk',
    dm_statistic      DOUBLE,
    dm_pvalue         DOUBLE,
    beats_baseline    BOOLEAN,
    rmse_oos_60d      DOUBLE,
    baseline_rmse_oos_60d DOUBLE,
    directional_accuracy_60d DOUBLE,
    n_validation      INTEGER,
    is_baseline       BOOLEAN DEFAULT FALSE,
    computed_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (pair, as_of, horizon_days, model_id)
);

-- ---------------------------------------------------------------------------
-- 2.12 macro_series（vintage あり）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS macro_series (
    series_id         VARCHAR NOT NULL,
    observation_date  DATE    NOT NULL,
    vintage_date      DATE    NOT NULL,
    value             DOUBLE,
    unit              VARCHAR,
    frequency         VARCHAR,
    label_ja          VARCHAR,
    source            VARCHAR NOT NULL DEFAULT 'fred',
    ingested_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (series_id, observation_date, vintage_date)
);

CREATE OR REPLACE VIEW macro_series_latest AS
SELECT series_id, observation_date, value, unit, frequency, label_ja
FROM (SELECT *, ROW_NUMBER() OVER (
        PARTITION BY series_id, observation_date ORDER BY vintage_date DESC) rn
      FROM macro_series) WHERE rn = 1;

-- ---------------------------------------------------------------------------
-- 2.13 model_runs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_runs (
    run_id            VARCHAR NOT NULL PRIMARY KEY,
    model_kind        VARCHAR NOT NULL,
    model_version     VARCHAR NOT NULL,
    market            VARCHAR,
    horizon           VARCHAR,
    train_start       DATE,
    train_end         DATE,
    valid_start       DATE,
    valid_end         DATE,
    cv_scheme         VARCHAR NOT NULL,
    purge_days        INTEGER NOT NULL,
    embargo_days      INTEGER NOT NULL,
    n_folds           INTEGER,
    feature_version   VARCHAR NOT NULL,
    feature_list      VARCHAR[] NOT NULL,
    hyperparams       JSON,
    input_snapshot_hash VARCHAR NOT NULL,
    metrics           JSON,
    n_trials          INTEGER,
    fold_rank_ic      DOUBLE[],
    fold_ic_std       DOUBLE,
    artifact_path     VARCHAR,
    git_commit        VARCHAR,
    started_at        TIMESTAMP NOT NULL,
    finished_at       TIMESTAMP,
    status            VARCHAR NOT NULL
);

-- ---------------------------------------------------------------------------
-- 2.14 backtest_runs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS backtest_runs (
    backtest_id       VARCHAR NOT NULL PRIMARY KEY,
    strategy_name     VARCHAR NOT NULL,
    model_run_id      VARCHAR,
    market            VARCHAR NOT NULL,
    period_start      DATE NOT NULL,
    period_end        DATE NOT NULL,
    rebalance_freq    VARCHAR NOT NULL,
    universe_filter   JSON,
    n_positions       INTEGER NOT NULL,

    fee_bps           DOUBLE NOT NULL,
    slippage_bps      DOUBLE NOT NULL,
    max_turnover_pct  DOUBLE NOT NULL,

    status            VARCHAR NOT NULL DEFAULT 'finished',
    total_return      DOUBLE,
    cagr              DOUBLE,
    annualized_return DOUBLE,
    benchmark_annualized DOUBLE,
    excess_return     DOUBLE,
    volatility        DOUBLE,
    sharpe            DOUBLE,
    sortino           DOUBLE,
    max_drawdown      DOUBLE,
    max_drawdown_period_ja VARCHAR,
    calmar            DOUBLE,
    hit_rate          DOUBLE,
    monthly_hit_rate  DOUBLE,
    n_months          INTEGER,
    profit_factor     DOUBLE,
    avg_turnover      DOUBLE,
    realized_turnover_pct DOUBLE,
    total_cost_bps    DOUBLE,
    cost_drag_annual  DOUBLE,
    gross_annualized_return DOUBLE,
    benchmark_return  DOUBLE,
    alpha_vs_bench    DOUBLE,
    information_ratio DOUBLE,
    skew              DOUBLE,
    kurtosis          DOUBLE,

    n_trials          INTEGER NOT NULL,
    deflated_sharpe   DOUBLE,
    dsr_pvalue        DOUBLE,
    is_significant    BOOLEAN,
    significance_ja   VARCHAR,
    progress_pct      DOUBLE,
    elapsed_sec       DOUBLE,
    eta_sec           DOUBLE,
    error_ja          VARCHAR,
    equity_curve_path VARCHAR,
    trades_path       VARCHAR,
    config            JSON,
    git_commit        VARCHAR,
    run_at            TIMESTAMP NOT NULL
);

-- ---------------------------------------------------------------------------
-- 2.15 補助テーブル
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS data_gaps (
    gap_id      VARCHAR PRIMARY KEY,
    source      VARCHAR NOT NULL,
    entity      VARCHAR NOT NULL,
    gap_start   DATE NOT NULL,
    gap_end     DATE NOT NULL,
    reason      VARCHAR,
    is_resolved BOOLEAN DEFAULT FALSE,
    detected_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS data_conflicts (
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

CREATE TABLE IF NOT EXISTS data_quality_flags (
    flag_id     VARCHAR PRIMARY KEY,
    table_name  VARCHAR NOT NULL,
    entity      VARCHAR NOT NULL,
    as_of       DATE NOT NULL,
    flag_code   VARCHAR NOT NULL,
    detail      VARCHAR,
    detected_at TIMESTAMP NOT NULL
);

-- データ鮮度（UIヘッダ表示用のビュー）
CREATE OR REPLACE VIEW data_freshness AS
SELECT 'jquants' AS source, MAX(trade_date) AS latest_as_of
  FROM prices_daily WHERE source = 'jquants'
UNION ALL
SELECT 'yfinance', MAX(trade_date) FROM prices_live
UNION ALL
SELECT 'edinet', MAX(CAST(filed_at AS DATE)) FROM documents WHERE source='edinet'
UNION ALL
SELECT 'tdnet', MAX(CAST(filed_at AS DATE)) FROM documents WHERE source='tdnet'
UNION ALL
SELECT 'edgar', MAX(CAST(filed_at AS DATE)) FROM documents WHERE source='edgar'
UNION ALL
SELECT 'fred', MAX(observation_date) FROM macro_series;
