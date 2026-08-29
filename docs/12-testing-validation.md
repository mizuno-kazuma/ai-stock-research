# 12. テスト戦略と統計的妥当性の検証

## 1. 方針

本プロジェクトのテストは、通常のソフトウェアテスト（動くこと）に加えて、**統計的な誤りを機械的に検出すること**を目的とする。後者が本章の主眼である。

リークや遅延データの誤用は、テストがなければ「バグとして現れず、良い結果として現れる」。これが最も危険な性質である。したがって、これらを検出するテストを CI に置く。

| 分類 | ID接頭辞 | 目的 |
| --- | --- | --- |
| 単体テスト | T-UNIT | 関数の入出力 |
| リーク検出 | **T-LEAK** | **未来情報の混入を構造的に禁止する** |
| PIT 検証 | **T-PIT** | 時点整合性 |
| データ品質 | T-DQ | 取得データの検証 |
| LLM | T-LLM | プロンプト・スキーマ・引用検証 |
| セキュリティ | T-SEC | シークレット・PII の漏洩防止 |
| 統計 | T-STAT | 検定・指標の実装の正しさ |
| 契約 | T-API | API スキーマの整合 |
| 結合 | T-INT | ジョブパイプライン |
| 環境 | T-ENV | WSL2 / 文字コード / パス |
| E2E | T-E2E | 画面の主要フロー |

## 2. リーク検出テスト（最重要）

### T-LEAK-01: 禁止された交差検証手法の使用を検出

```python
# tests/leak/test_cv_import_ban.py
FORBIDDEN_IMPORTS = [
    "sklearn.model_selection.KFold",
    "sklearn.model_selection.StratifiedKFold",
    "sklearn.model_selection.TimeSeriesSplit",   # purge/embargo がないため禁止
    "sklearn.model_selection.train_test_split",
    "sklearn.model_selection.cross_val_score",
]

def test_models_package_does_not_use_naive_cv():
    """packages/core/models/ 配下で素朴な交差検証を使っていないことを検証する。
    時系列データに KFold を使うと直接リークする。TimeSeriesSplit も
    ラベル期間の purge がないため本プロジェクトでは不十分である。"""
    violations = []
    for py in (CORE / "models").rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "sklearn.model_selection":
                for alias in node.names:
                    if alias.name in {"KFold", "StratifiedKFold", "TimeSeriesSplit",
                                      "train_test_split", "cross_val_score"}:
                        violations.append(f"{py}:{node.lineno} {alias.name}")
    assert not violations, (
        "時系列データに対する素朴な交差検証は禁止されています。"
        "PurgedWalkForwardCV を使ってください。違反:\n" + "\n".join(violations))
```

### T-LEAK-02: `prices_live` のモデルからの参照を検出

```python
# tests/leak/test_prices_live_isolation.py
def test_models_and_backtest_do_not_reference_prices_live():
    """prices_live（yfinance の遅延データ）をモデル学習・バックテストに
    使うことを禁止する。リサーチ用の価格は prices_daily のみ。"""
    violations = []
    for pkg in ["models", "backtest", "factors"]:
        for py in (CORE / pkg).rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), 1):
                if "prices_live" in line and not line.strip().startswith("#"):
                    violations.append(f"{py}:{lineno}")
    assert not violations, (
        "prices_live をモデル・バックテスト・特徴量計算から参照できません。"
        "docs/02-data-ingestion.md §2.2 参照。違反:\n" + "\n".join(violations))
```

### T-LEAK-03: PurgedWalkForwardCV の分割が正しいこと

```python
def test_purged_cv_no_overlap_between_train_and_test():
    """train の最大日付 + purge + embargo < test の最小日付 であること。"""
    dates = pd.bdate_range("2024-01-01", "2026-08-01")
    groups = np.repeat(dates, 100)                      # 各日100銘柄
    cv = PurgedWalkForwardCV(n_splits=5, label_horizon_days=20,
                             embargo_days=5, test_days=60)
    for train_idx, test_idx in cv.split(X=np.zeros(len(groups)), groups=groups):
        train_max = groups[train_idx].max()
        test_min = groups[test_idx].min()
        gap_bdays = np.busday_count(train_max, test_min)
        assert gap_bdays >= 20 + 5, (
            f"purge(20) + embargo(5) の間隔が不足: {gap_bdays}営業日")
        assert len(set(train_idx) & set(test_idx)) == 0, "train と test が重複"
        assert train_max < test_min, "train が test より後の日付を含む"

def test_purged_cv_rejects_missing_groups():
    """groups（日付）なしでの分割を許可しない。"""
    cv = PurgedWalkForwardCV()
    with pytest.raises(ValueError, match="groups"):
        list(cv.split(X=np.zeros(100), groups=None))
```

### T-LEAK-04: 合成データによるリーク検出（最も強力なテスト）

```python
def test_pipeline_finds_no_signal_in_pure_noise():
    """完全にランダムなデータで学習・評価し、Rank IC がゼロ近傍であることを
    確認する。有意な IC が出るならパイプラインにリークがある。

    これはリークを検出する最も確実な方法である。個別の実装を検査するのではなく、
    「信号がないデータから信号を見つけてしまうか」を直接テストする。"""
    rng = np.random.default_rng(42)
    n_days, n_stocks = 750, 200
    # ランダムウォークの価格系列（予測可能な構造を持たない）
    prices = synth_random_walk(n_days, n_stocks, rng)
    features = compute_features(prices)                 # 実際の特徴量計算を通す
    labels = make_label(prices, horizon=20)             # 実際のラベル生成を通す

    cv = PurgedWalkForwardCV(n_splits=5, label_horizon_days=20, embargo_days=5)
    ics = []
    for train_idx, test_idx in cv.split(features, groups=features["as_of"]):
        model = train_ranker(features.iloc[train_idx], labels.iloc[train_idx])
        pred = model.predict(features.iloc[test_idx])
        ics.append(spearmanr(pred, labels.iloc[test_idx]).statistic)

    mean_ic = np.mean(ics)
    t_stat = mean_ic / (np.std(ics) / np.sqrt(len(ics)))
    assert abs(t_stat) < 2.5, (
        f"ノイズデータから有意な予測力が検出されました（IC={mean_ic:.4f}, "
        f"t={t_stat:.2f}）。パイプラインにリークがあります。")
```

**このテストが通ることが、パイプライン全体のリーク不在の最も強い証拠になる。** 個々の関数を検査するテストは見落としが出るが、これは「結果として信号が漏れているか」を直接測る。

### T-LEAK-05: バックテストのエントリータイミング

```python
def test_backtest_entry_is_next_day_open():
    """as_of の終値で計算したシグナルに対し、エントリーが翌営業日の
    始値であることを検証する。同日終値での約定はリークである。"""
    signals = pd.DataFrame({"as_of": [date(2026, 8, 20)], "ticker": ["7203"],
                            "score": [1.0]}).set_index(["as_of", "ticker"])
    result = run_backtest(signals=signals, prices=fixture_prices, market="JP",
                          period=(date(2026, 8, 1), date(2026, 9, 1)),
                          rebalance_freq="weekly", n_positions=1,
                          fee_bps=5.0, slippage_bps=10.0,
                          max_turnover_pct=30.0, n_trials=1,
                          universe_filter=UniverseFilter(), benchmark="TOPIX")
    trade = result.trades.iloc[0]
    assert trade["entry_date"] == date(2026, 8, 21), "翌営業日でない"
    assert trade["entry_price"] == fixture_prices.loc[(date(2026, 8, 21), "7203"), "adj_open"]
```

### T-LEAK-06: バックテストのコスト引数が必須であること

```python
def test_backtest_requires_cost_parameters():
    """fee_bps / slippage_bps / max_turnover_pct / n_trials に
    デフォルト値がないことを検証する。ゼロコストのバックテストを
    うっかり実行できないようにするための構造的制約である。"""
    sig = inspect.signature(run_backtest)
    for name in ["fee_bps", "slippage_bps", "max_turnover_pct", "n_trials"]:
        param = sig.parameters[name]
        assert param.default is inspect.Parameter.empty, \
            f"{name} にデフォルト値があります。必須引数にしてください"
        assert param.kind == inspect.Parameter.KEYWORD_ONLY, \
            f"{name} はキーワード専用引数にしてください"
```

## 3. PIT（時点整合性）テスト

### T-PIT-01: 財務データの PIT フィルタ

```python
def test_financials_pit_uses_filed_at_not_period_end():
    """period_end が as_of より前でも、filed_at が as_of より後なら
    その情報は使えない。end で絞ると1ヶ月分のリークになる。"""
    # 2026-03-31 期末の決算が 2026-05-02 に提出されたケース
    repo.insert_financials(ticker="AAPL", period_end=date(2026, 3, 31),
                           filed_at=date(2026, 5, 2), revenue=1000)
    # as_of = 2026-04-15 の時点では、この決算は未提出
    result = repo.get_financials_as_of(ticker="AAPL", as_of=date(2026, 4, 15))
    assert result.empty, "提出前の財務データが取得されました（リーク）"
    result = repo.get_financials_as_of(ticker="AAPL", as_of=date(2026, 5, 2))
    assert not result.empty, "提出日には取得できるべき"
```

### T-PIT-02: 開示の当日15時ルール（日本株）

```python
@pytest.mark.parametrize("disclosed_at,expected", [
    # 15:00 より前の開示 → 当日から織り込める
    ("2026-08-20T14:59:00+09:00", date(2026, 8, 20)),
    # 15:00 以降の開示 → 翌営業日から
    ("2026-08-20T15:00:00+09:00", date(2026, 8, 21)),
    ("2026-08-20T16:30:00+09:00", date(2026, 8, 21)),
    # 金曜の引け後 → 翌月曜
    ("2026-08-21T17:00:00+09:00", date(2026, 8, 24)),
])
def test_effective_date_respects_market_close(disclosed_at, expected):
    assert effective_date(parse(disclosed_at), market="JP") == expected
```

### T-PIT-03: マクロ統計の vintage

```python
def test_macro_uses_vintage_not_revised_value():
    """CPI などの改訂される統計は、当時公表されていた値を使う。
    改訂後の値を使うとリークになる。"""
    # 2026-04 の CPI: 速報 2.8%（2026-05-10 公表）→ 改訂 3.1%（2026-06-12 公表）
    repo.insert_macro("CPIAUCSL", observation_date=date(2026, 4, 1),
                      vintage_date=date(2026, 5, 10), value=2.8)
    repo.insert_macro("CPIAUCSL", observation_date=date(2026, 4, 1),
                      vintage_date=date(2026, 6, 12), value=3.1)
    v = repo.get_macro_as_of("CPIAUCSL", observation_date=date(2026, 4, 1),
                             as_of=date(2026, 5, 20))
    assert v == 2.8, "改訂後の値が返りました（リーク）"
```

### T-PIT-04: RAG 検索の PIT 制約

```python
def test_rag_excludes_documents_filed_after_as_of():
    """過去の推奨を再現する際、当時存在しなかった資料が検索されないこと。"""
    hits = retrieve("業績見通し", ticker="7203", market="JP",
                    as_of=date(2026, 5, 1), k=10)
    assert all(h.filed_at.date() <= date(2026, 5, 1) for h in hits)
```

### T-PIT-05: 特徴量計算の PIT ガード

```python
def test_pit_guard_raises_on_future_data():
    df = pd.DataFrame({"filed_at": [date(2026, 9, 1)], "value": [1.0]})
    with pytest.raises(PitViolationError):
        assert_pit_safe(df, as_of=date(2026, 8, 23))
```

## 4. データ品質テスト

### T-DQ-01: 価格データの論理検証

```python
@pytest.mark.parametrize("row,should_reject", [
    ({"open": 100, "high": 110, "low": 95,  "close": 105}, False),
    ({"open": 100, "high": 90,  "low": 95,  "close": 105}, True),   # high < low
    ({"open": 100, "high": 110, "low": 95,  "close": 120}, True),   # close > high
    ({"open": 100, "high": 110, "low": 95,  "close": None}, True),  # 欠損
])
def test_price_quality_check(row, should_reject):
    assert bool(validate_price_row(row).rejected) == should_reject
```

### T-DQ-02: 銘柄コードの型

```python
def test_ticker_is_string_not_int():
    """7203 を int で扱うと、先頭ゼロのコードや '130A' のような
    英字を含むコードで壊れる。"""
    df = normalize_jquants_prices(fixture_raw_batch)
    assert df["ticker"].dtype == object
    assert all(isinstance(t, str) for t in df["ticker"])
```

### T-DQ-03: スキーマドリフトの検出

```python
def test_schema_drift_detected_on_unexpected_response():
    """APIのレスポンス構造が変わったときに、静かに壊れずに検出されること。"""
    batch = RawBatch(source="jquants", endpoint="bars/daily", payload={"unexpected": []},
                     as_of=date(2026, 8, 22), fetched_at="...", request={})
    with pytest.raises(SchemaDriftError):
        JQuantsConnector().normalize(batch)
```

### T-DQ-04: 欠損値をゼロ埋めしていないこと

```python
def test_features_do_not_zero_fill_missing():
    """履歴不足の銘柄の特徴量が 0 ではなく NaN であること。
    ゼロ埋めは「平均的な銘柄」という誤情報を注入する。"""
    prices = fixture_prices_short_history(days=30)   # mom_12_1 の計算に不足
    features = compute_features(prices, as_of=date(2026, 8, 22))
    assert features["mom_12_1"].isna().all()
    assert not (features["mom_12_1"] == 0).any()
```

### T-DQ-05: 負のPERを除外していること

```python
def test_negative_per_becomes_null():
    """赤字企業の PER は NULL。負のPERを「超割安」として扱わない。"""
    f = compute_valuation(market_cap=1000, net_income_ttm=-100)
    assert f["per"] is None
    assert f["earnings_yield"] == pytest.approx(-0.1)   # 逆数は負値として有効
```

## 5. 統計実装のテスト

### T-STAT-01: Diebold-Mariano 検定の既知ケース

```python
def test_dm_test_detects_no_difference_for_identical_errors():
    """同一の誤差系列に対して有意差が出ないこと。"""
    e = np.random.default_rng(0).normal(size=200)
    r = diebold_mariano(e, e.copy(), h=5)
    assert r.pvalue > 0.99

def test_dm_test_detects_clear_superiority():
    """明確に優れたモデルに対して有意差が出ること。"""
    rng = np.random.default_rng(0)
    e_good = rng.normal(scale=1.0, size=300)
    e_bad = rng.normal(scale=2.0, size=300)
    r = diebold_mariano(e_good, e_bad, h=1)
    assert r.pvalue < 0.01 and r.better == "model"

def test_dm_test_uses_hac_variance_for_multistep():
    """h > 1 で HAC 分散を使っていること。単純分散だと p 値が過小になる。
    自己相関のある誤差系列で、HAC の方が p 値が大きくなることを確認する。"""
    e1, e2 = ar1_errors(rho=0.7, n=300), ar1_errors(rho=0.7, n=300, scale=1.05)
    p_hac = diebold_mariano(e1, e2, h=20).pvalue
    p_naive = naive_dm_pvalue(e1, e2)
    assert p_hac > p_naive, "HAC 分散が使われていない可能性"
```

### T-STAT-02: Deflated Sharpe Ratio

```python
def test_dsr_decreases_with_more_trials():
    """試行回数が増えると DSR が下がること（多重検定の補正が効いている）。"""
    base = dict(sr_observed=1.5, n_obs=500, skew=-0.2, kurtosis=4.0,
                sr_variance_across_trials=0.25)
    dsr_10 = deflated_sharpe_ratio(**base, n_trials=10).dsr
    dsr_1000 = deflated_sharpe_ratio(**base, n_trials=1000).dsr
    assert dsr_1000 < dsr_10

def test_dsr_flags_insignificant_result():
    """高いシャープレシオでも試行回数が多ければ有意でないと判定すること。"""
    r = deflated_sharpe_ratio(sr_observed=1.2, n_trials=5000, n_obs=250,
                              skew=0.0, kurtosis=3.0,
                              sr_variance_across_trials=0.5)
    assert not r.is_significant
```

### T-STAT-03: GARCH の収束と定常性チェック

```python
def test_garch_raises_on_nonstationary():
    """alpha + beta >= 1 のとき例外を投げ、発散した予測を返さないこと。"""
    series = integrated_garch_series(n=1000)   # IGARCH になる合成データ
    with pytest.raises((GarchNonStationaryError, GarchConvergenceError)):
        fit_garch(series)

def test_garch_falls_back_to_realized_vol():
    """GARCH が失敗した銘柄で、実現ボラにフォールバックし、
    data_quality_flags に記録されること。"""
    result = compute_vol_features(problematic_series)
    assert result["garch_vol_20d"] is None
    assert result["realized_vol_60d"] is not None
    assert "GARCH_FALLBACK" in result["quality_flags"]
```

### T-STAT-04: セクター中立化

```python
def test_sector_neutral_zscore_uses_median_and_mad():
    """外れ値1件で z-score が崩れないこと（平均・標準偏差ではない）。"""
    df = pd.DataFrame({"sector_code": ["A"] * 20,
                       "per": [15.0] * 19 + [10000.0]})   # 1件が極端
    z = sector_neutral_zscore(df, "per")
    # 中央値ベースなので、通常の19件の z が 0 近傍に留まる
    assert abs(z[:19].mean()) < 0.3

def test_small_sector_falls_back_to_market():
    """構成銘柄が min_sector_size 未満のセクターは市場全体で計算すること。"""
    df = pd.DataFrame({"sector_code": ["A"] * 3 + ["B"] * 50, "per": [...]})
    z = sector_neutral_zscore(df, "per", min_sector_size=8)
    assert not z[:3].isna().any()
```

### T-STAT-05: 分位単調性

```python
def test_quantile_returns_are_monotonic_in_backtest():
    """バックテスト結果で、スコア5分位のリターンが概ね単調であること。
    単調でない場合はモデルが機能していないシグナルなので、
    テストとしては警告レベル（xfail 可）とする。"""
    q_returns = backtest_result.quantile_returns
    assert q_returns[4] > q_returns[0], "上位分位が下位分位に劣っている"
```

## 6. LLM テスト

### T-LLM-01: 出力スキーマの検証

```python
def test_doc_summary_rejects_empty_citations():
    """引用が空の出力を保存できないこと。"""
    with pytest.raises(ValidationError):
        DocSummaryOutput(summary_ja="..." * 20, key_points=["a"],
                         risk_factors=[], guidance_tone="neutral",
                         guidance_evidence="...", qualitative_score=0.0,
                         citations=[])                      # 空
```

### T-LLM-02: 引用検証

```python
def test_citation_verification_detects_fabricated_quote():
    """原文に存在しない引用を検出すること。"""
    doc = fixture_document(text="当社の営業利益は前年同期比12.4%増加しました。")
    ok = verify_citation(Citation(doc_id=doc.doc_id, page=1,
                                 quote="営業利益は前年同期比12.4%増加"))
    assert ok == CitationVerdict.VERIFIED
    ng = verify_citation(Citation(doc_id=doc.doc_id, page=1,
                                 quote="来期は営業利益が倍増する見込みです"))
    assert ng == CitationVerdict.QUOTE_NOT_FOUND

def test_citation_verification_tolerates_normalization():
    """全角半角の違いや空白は許容すること（LLMは表記を変えることがある）。"""
    doc = fixture_document(text="営業利益は１２．４％増加")
    ok = verify_citation(Citation(doc_id=doc.doc_id, page=1,
                                 quote="営業利益は12.4%増加"))
    assert ok in (CitationVerdict.VERIFIED, CitationVerdict.VERIFIED_FUZZY)
```

### T-LLM-03: コストキャップ時のフォールバック（重要）

```python
def test_pipeline_continues_when_llm_capped():
    """コストキャップに達しても、定量スコアのみで推奨が生成されること。
    キャップでシステム全体が止まるなら、キャップの意味がない。"""
    cost_guard.force_cap_exceeded()
    result = run_pipeline(market="JP", as_of=date(2026, 8, 22))
    assert result.status == "partial"
    recs = repo.get_recommendations(as_of=date(2026, 8, 22))
    assert len(recs) > 0, "定性分析なしでも推奨は生成されるべき"
    assert all(r.qual_score is None for r in recs)
    assert any(a.category == "cost" for a in repo.get_alerts())
```

### T-LLM-04: bear case の必須化

```python
def test_recommendation_rejects_empty_bear_case():
    with pytest.raises(InvariantViolationError, match="bear_case"):
        repo.insert_recommendation(fixture_rec(bear_case_ja=""))
    with pytest.raises(InvariantViolationError, match="bear_case"):
        repo.insert_recommendation(fixture_rec(bear_case_ja="リスクは限定的です"))  # 20文字未満

def test_critic_rejects_boilerplate_bear_case():
    rec = fixture_rec(bear_case_ja="市場環境の悪化や予想外の事態により、"
                                    "株価が下落する可能性があります。")
    issues = mechanical_checks(rec)
    assert any(i.code == "boilerplate_bear_case" for i in issues)
```

### T-LLM-05: 信頼区間の必須化

```python
def test_recommendation_requires_confidence_interval():
    with pytest.raises(InvariantViolationError, match="confidence_interval"):
        repo.insert_recommendation(fixture_rec(expected_ret_lo=None))
```

### T-LLM-06: 確信度と母数の整合

```python
def test_conviction_forced_to_low_when_few_samples():
    """n_prior_samples < 20 のとき conviction が low に強制されること。"""
    rec = build_recommendation(..., n_prior_samples=8, raw_conviction="high")
    assert rec.conviction == "low"
```

### T-LLM-07: プロンプトのゴールデンテスト

```python
def test_thesis_prompt_renders_expected_structure(snapshot):
    """プロンプトテンプレートの意図しない変更を検出する。
    prompt_hash が変わるとキャッシュが全ミスになるため、
    変更が意図的であることを確認する。"""
    rendered = render_prompt("thesis.jinja", **fixture_context())
    snapshot.assert_match(rendered, "thesis_prompt.txt")
    # 必須の指示が含まれていること
    assert "却下すべき理由を3つ挙げる" in rendered
    assert "「買い」「売り」という語を使わない" in rendered
```

### T-LLM-08: LLM 呼び出しのモック（外部通信をしない）

```python
@pytest.fixture(autouse=True)
def no_real_llm_calls(monkeypatch):
    """テスト中に本物の LLM API を呼ばないことを保証する。
    うっかり課金されるのを防ぐ。"""
    def fail(*a, **kw):
        raise RuntimeError("テスト中に実際のLLM APIを呼び出そうとしました")
    monkeypatch.setattr("litellm.completion", fail)
    monkeypatch.setattr("litellm.acompletion", fail)
```

同様に、外部HTTPアクセス全般を `responses` / `respx` でブロックする。**テストが実際に J-Quants や EDGAR を叩くと、レート制限を消費し、CI が不安定になる。**

## 7. セキュリティテスト

### T-SEC-01: LLM プロンプトへの機密情報の混入

```python
@pytest.mark.parametrize("payload", [
    {"positions": [{"ticker": "7203", "quantity": 100}]},
    {"portfolio": {"total_assets": 5000000}},
    {"trade": {"avg_cost": 3125.0}},
    {"nested": {"deep": {"market_value": 312500}}},
])
def test_sensitive_data_blocked_from_prompt(payload):
    with pytest.raises(SensitiveDataInPromptError):
        assert_no_sensitive_data(payload)

def test_redacted_portfolio_has_only_ratios():
    out = redact_portfolio(fixture_positions())
    for item in out:
        assert set(item.keys()) <= {"ticker", "weight_pct", "unrealized_pnl_pct"}
```

### T-SEC-02: ログへのシークレット漏洩

```python
def test_fred_url_masked_in_logs(caplog):
    """FRED はAPIキーをクエリパラメータで渡すため、URLをログに出すと漏洩する。"""
    with caplog.at_level(logging.DEBUG):
        FredConnector(api_key="secret123").fetch(window)
    assert "secret123" not in caplog.text
    assert "api_key=***" in caplog.text
```

### T-SEC-03: `.env` がコミットされていないこと

```python
def test_no_secrets_in_git_tracked_files():
    tracked = subprocess.run(["git", "ls-files"], capture_output=True,
                             text=True).stdout.splitlines()
    assert ".env" not in tracked
    for f in tracked:
        if f.endswith((".py", ".ts", ".yaml", ".json", ".md")):
            text = Path(f).read_text(encoding="utf-8")
            assert not re.search(r"sk-ant-[\w-]{20,}", text)
            assert not re.search(r"AIza[\w-]{30,}", text)
```

### T-SEC-04: EDGAR User-Agent の必須化

```python
def test_edgar_requires_valid_user_agent():
    with pytest.raises(ValidationError, match="EDGAR_USER_AGENT"):
        Settings(edgar_user_agent="", ...)
    with pytest.raises(ValidationError):
        Settings(edgar_user_agent="bot", ...)      # 連絡先がない
```

## 8. 環境テスト（WSL2 / 文字コード / パス）

### T-ENV-01: 文字コード

```python
def test_all_open_calls_specify_encoding():
    """open() に encoding が明示されていることを検証する。
    日本語ロケール Windows のデフォルトは cp932 で、
    EDINET/TDnet の日本語を読むと UnicodeDecodeError になる。
    PYTHONUTF8=1 だけに頼らず、明示を規約とする。"""
    violations = []
    for py in REPO.rglob("*.py"):
        if any(p in py.parts for p in [".venv", "node_modules", ".git"]):
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "open"):
                mode = get_mode_arg(node)
                if "b" in (mode or ""):
                    continue                       # バイナリモードは対象外
                if not has_kwarg(node, "encoding"):
                    violations.append(f"{py}:{node.lineno}")
    assert not violations, (
        "open() に encoding='utf-8' を明示してください。違反:\n"
        + "\n".join(violations))

def test_japanese_text_roundtrip():
    """日本語を含むテキストの読み書きが壊れないこと。"""
    text = "トヨタ自動車 2026年3月期 第1四半期決算短信〔日本基準〕（連結）"
    p = tmp_path / "test.txt"
    p.write_text(text, encoding="utf-8")
    assert p.read_text(encoding="utf-8") == text
```

Ruff の設定でも機械的に検出する（[15-windows-runtime.md](15-windows-runtime.md) §4）。

```toml
# pyproject.toml
[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "PTH", "PLW1514", "EXE", "ASYNC"]
# PLW1514: unspecified-encoding（open() の encoding 未指定を検出）
# PTH:     flake8-use-pathlib（os.path の代わりに pathlib を使わせる）
```

### T-ENV-02: パスの文字制限

```python
@pytest.mark.parametrize("name,valid", [
    ("prices_daily", True),
    ("market=JP", True),
    ("dt=2026-08-23", True),
    ("run:2026-08-23", False),       # ':' は Windows で使えない
    ("what?", False),
    ("wild*card", False),
    ("con", False),                  # Windows の予約名
    ("aux", False),
])
def test_path_component_validation(name, valid):
    assert is_valid_path_component(name) == valid

def test_parquet_partition_names_are_windows_safe():
    """Parquet のパーティション名に Windows で使えない文字が入らないこと。"""
    for p in (DATA_DIR / "warehouse" / "parquet").rglob("*"):
        for part in p.relative_to(DATA_DIR).parts:
            assert not set(part) & set(':?*<>|"'), f"不正なパス: {p}"
```

### T-ENV-03: pathlib の使用

```python
def test_no_os_path_join():
    """os.path.join ではなく pathlib.Path を使うこと。
    Ruff の PTH ルールで検出するが、テストでも二重に確認する。"""
    violations = grep_repo(r"os\.path\.join\(")
    assert not violations
```

### T-ENV-04: DATA_DIR の位置

```python
def test_data_dir_rejects_windows_mount():
    """/mnt/c 配下は I/O が桁違いに遅く、DuckDB/Parquet 処理が実用にならない。"""
    with pytest.raises(ValidationError, match="Windows マウント"):
        Settings(data_dir=Path("/mnt/c/Users/me/data"), ...)
```

### T-ENV-05: 改行コード

```bash
# .gitattributes が設定されていること
grep -q "^\* text=auto eol=lf" .gitattributes
```

## 9. API 契約テスト

### T-API-01: OpenAPI と TS 型の同期

```yaml
# CI ステップ
- name: Check API types are up to date
  run: |
    uv run python -m services.api.export_openapi > /tmp/openapi.json
    npx openapi-typescript /tmp/openapi.json -o /tmp/api-types.ts
    diff /tmp/api-types.ts apps/web/lib/api-types.ts || \
      (echo "API 型が古くなっています。npm run gen:api を実行してください" && exit 1)
```

### T-API-02: 全レスポンスが Envelope 形式であること

```python
def test_all_endpoints_return_envelope(client):
    """data / warnings / meta を持つこと。UI 側の共通処理が成立する条件。"""
    for path in COLLECTED_GET_PATHS:
        r = client.get(path)
        if r.status_code == 200 and r.headers["content-type"].startswith("application/json"):
            body = r.json()
            assert set(body.keys()) >= {"data", "meta"}
            assert "data_freshness" in body["meta"]
```

### T-API-03: バックテスト API のコスト引数の必須化

```python
def test_backtest_api_rejects_missing_cost_params(client):
    r = client.post("/api/v1/backtests", json={
        "strategy_name": "test", "market": "JP",
        "period_start": "2024-08-01", "period_end": "2026-08-01",
        "rebalance_freq": "monthly", "n_positions": 20,
        # fee_bps, slippage_bps, max_turnover_pct を省略
    })
    assert r.status_code == 422
    assert "fee_bps" in r.text
```

### T-API-04: 部分データが 200 で返ること

```python
def test_partial_data_returns_200_with_warnings(client, broken_tdnet):
    r = client.get("/api/v1/dashboard?market=JP")
    assert r.status_code == 200
    assert any(w["code"] == "SECTION_UNAVAILABLE" for w in r.json()["warnings"])
```

## 10. 結合テスト

### T-INT-01: パイプライン全体（モックデータ）

```python
def test_full_pipeline_with_fixtures():
    """全外部APIをモックし、Collector から Evaluator までを通す。"""
    with mock_all_external_apis(fixture_dir="tests/fixtures/pipeline_20260822"):
        result = run_pipeline(market="JP", as_of=date(2026, 8, 22))
    assert result.status in ("success", "partial")
    assert repo.count_recommendations(as_of=date(2026, 8, 22)) > 0
    for rec in repo.get_recommendations(as_of=date(2026, 8, 22)):
        assert len(rec.bear_case_ja) >= 20
        assert len(rec.citations) >= 1
        assert rec.expected_ret_lo is not None
```

### T-INT-02: チェックポイントからの再開

```python
def test_job_resumes_from_checkpoint():
    """途中で例外を起こし、再実行時に完了済みの単位をスキップすること。
    Windows Update による再起動を模擬する。"""
    with mock_failure_after_n_units(3):
        with pytest.raises(SimulatedCrash):
            run_collector(market="JP", as_of=date(2026, 8, 22))
    cp = load_checkpoint(job_name="collector_jp")
    assert len(cp.completed_units) == 3

    api_calls_before = count_api_calls()
    run_collector(market="JP", as_of=date(2026, 8, 22), checkpoint=cp)
    # 完了済みの3単位分は再取得しない
    assert count_api_calls() - api_calls_before < total_units
```

### T-INT-03: 冪等性

```python
def test_pipeline_is_idempotent():
    """同じ日で2回実行しても結果が変わらないこと。"""
    run_pipeline(market="JP", as_of=date(2026, 8, 22))
    snapshot1 = repo.snapshot_hash(as_of=date(2026, 8, 22))
    run_pipeline(market="JP", as_of=date(2026, 8, 22))
    snapshot2 = repo.snapshot_hash(as_of=date(2026, 8, 22))
    assert snapshot1 == snapshot2
```

### T-INT-04: 機能縮退

```python
@pytest.mark.parametrize("broken_source", ["tdnet", "edinet", "fred", "yfinance"])
def test_pipeline_degrades_gracefully(broken_source):
    """必須でないソースが落ちても推奨が生成されること。"""
    with break_source(broken_source):
        result = run_pipeline(market="JP", as_of=date(2026, 8, 22))
    assert result.status == "partial"
    assert repo.count_recommendations(as_of=date(2026, 8, 22)) > 0

def test_pipeline_fails_when_prices_unavailable():
    """価格が取れない場合は失敗すること（これは必須ソース）。"""
    with break_source("jquants"), break_source("yfinance"):
        result = run_pipeline(market="JP", as_of=date(2026, 8, 22))
    assert result.status == "failed"
```

実装の回帰テストは `tests/unit/agent/test_pipeline_fixes.py`。ML 予測区間が無くても Critic まで到達すること、INTEGER 列の NaN が INSERT で落ちないこと、開示 0 件かつ既存カバレッジ無しは Collector を partial にすること、為替スポット無しだけで Analyst を partial にしないことを固定する。

## 11. E2E テスト（Playwright）

主要フローのみ。全画面を網羅しない。

| ID | フロー |
| --- | --- |
| T-E2E-01 | ダッシュボードが表示され、データ鮮度がヘッダに出る |
| T-E2E-02 | 推奨カードを開くと bear case が表示される（**bear case のない状態が存在しないことの確認**） |
| T-E2E-03 | 銘柄詳細から決算資料をクリックしてPDFが開く |
| T-E2E-04 | スクリーナーで条件を指定して結果が返る |
| T-E2E-05 | 売買記録を入力して一覧に反映される |
| T-E2E-06 | 上昇下落の色設定を切り替えると表示色が変わる |
| T-E2E-07 | オフライン状態で「オフライン表示」バナーが出る |
| T-E2E-08 | 為替画面で「優位性は確認できていません」が表示される（`beats_baseline=false` のとき） |
| T-E2E-09 | モバイル幅でボトムナビゲーションが表示される |
| T-E2E-10 | キルスイッチを ON にすると定性分析の停止表示が出る |

## 12. CI 構成

```yaml
# .github/workflows/ci.yml（Phase A では手動実行でもよい）
jobs:
  lint:
    - uv run ruff check .
    - uv run ruff format --check .
    - uv run mypy packages services
    - npm run lint --workspace apps/web
    - npx tsc --noEmit --project apps/web

  test-python:
    - uv run pytest tests/unit tests/leak tests/pit tests/stat tests/sec tests/env -x
    - uv run pytest tests/integration
    # リーク検出テストは必ず実行する。スキップを許可しない
    - uv run pytest tests/leak --strict-markers -p no:randomly

  contract:
    - uv run python -m services.api.export_openapi > /tmp/openapi.json
    - npx openapi-typescript /tmp/openapi.json -o /tmp/api-types.ts
    - diff /tmp/api-types.ts apps/web/lib/api-types.ts

  test-web:
    - npm test --workspace apps/web
    - npx playwright test
```

### 12.1 テストの実行時間の目標

| 分類 | 目標時間 |
| --- | --- |
| lint | 30秒 |
| 単体 + リーク + PIT + 統計 | 3分 |
| 結合 | 5分 |
| E2E | 3分 |

**T-LEAK-04（合成データによるリーク検出）は実行に1-2分かかるが、これを短縮のために外してはならない。** このテストが最も価値がある。

## 13. カバレッジ目標

| 対象 | 目標 |
| --- | --- |
| `packages/core/factors/` | 90% |
| `packages/core/models/` | 85% |
| `packages/core/backtest/` | 90% |
| `packages/core/connectors/` | 75%（外部API依存のため） |
| `packages/core/llm/` | 80% |
| `services/api/` | 70% |
| `services/agent/` | 70% |
| `apps/web/` | 主要フローのE2Eのみ |

カバレッジ率を目標にすることの限界は理解した上で、**リーク検出とPIT検証のテストは網羅性を重視する**（ここは見落としのコストが大きい）。

## 14. 参照

- 分析手法の詳細: [04-analysis-engine.md](04-analysis-engine.md)
- 運用と監視: [11-security-ops.md](11-security-ops.md)
- 環境固有の検証: [15-windows-runtime.md](15-windows-runtime.md)
- ファクター追加時のチェックリスト: `.cursor/skills/add-analysis-factor/SKILL.md`
