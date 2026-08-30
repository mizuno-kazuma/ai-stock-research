# 08. エージェントループとフィードバックループ

## 1. 6ジョブ構成

```
┌───────────┐   ┌─────────┐   ┌────────────┐   ┌────────────┐   ┌────────┐   ┌───────────┐
│ Collector │──►│ Analyst │──►│ Researcher │──►│ Strategist │──►│ Critic │──►│ Evaluator │
└───────────┘   └─────────┘   └────────────┘   └────────────┘   └────────┘   └───────────┘
     データ収集      特徴量・        LLMによる         推奨候補の        敵対的        実績評価と
                   スコア計算      資料読解         カード生成        レビュー      教訓の更新
                                                                                       │
                                                                                       ▼
                                                                          agent_memory / factor_weights
                                                                                       │
                                                                     ┌─────────────────┘
                                                                     ▼
                                                          次回の Researcher / Strategist の
                                                          プロンプトに注入される
```

**Evaluator が agent_memory と factor_weights を更新し、それが次回の Researcher / Strategist に注入される。これがフィードバックループの実体である。** ここが繋がっていないと「エージェント」ではなく単なるバッチ処理になる。

## 2. スケジュール

APScheduler で定義する。**cron や Windows タスクスケジューラを使わない**（[01-architecture.md](01-architecture.md) §5.2 の D-04）。

```python
# services/agent/main.py
scheduler = BlockingScheduler(timezone="Asia/Tokyo",
                              jobstores={"default": SQLAlchemyJobStore(url=DB_URL)},
                              job_defaults={"coalesce": True, "max_instances": 1,
                                            "misfire_grace_time": 3600})

# 米国市場クローズ後（JST 06:30）
scheduler.add_job(run_pipeline, "cron", day_of_week="tue-sat", hour=6, minute=30,
                  args=["US"], id="pipeline_us")
# 日本市場クローズ後（JST 18:30）
scheduler.add_job(run_pipeline, "cron", day_of_week="mon-fri", hour=18, minute=30,
                  args=["JP"], id="pipeline_jp")
# 週次の深掘りレビュー（土曜 JST 09:00）
scheduler.add_job(run_weekly_review, "cron", day_of_week="sat", hour=9, minute=0,
                  id="weekly_review")
# 月次のモデル再学習（第1土曜 JST 10:00）
scheduler.add_job(run_model_retrain, "cron", day="1-7", day_of_week="sat",
                  hour=10, minute=0, id="model_retrain")
# GARCH 再推定（月曜 JST 07:00）
scheduler.add_job(refit_garch, "cron", day_of_week="mon", hour=7, minute=0,
                  id="garch_refit")
# 日次バックアップ（JST 03:00）。方式は 11-security-ops.md §4
scheduler.add_job(run_daily_backup, "cron", hour=3, minute=0, id="daily_backup")
# 中断ジョブの再開チェック（15分ごと）
scheduler.add_job(resume_interrupted_jobs, "interval", minutes=15,
                  id="resume_check")
```

**設定の意味**:

| 設定 | 値 | 理由 |
| --- | --- | --- |
| `jobstores` | SQLAlchemyJobStore | ジョブ定義を永続化する。プロセス再起動後もスケジュールが失われない |
| `coalesce` | `True` | PCがスリープしていて実行時刻を複数回過ぎた場合、まとめて1回だけ実行する。10回分が一気に走るのを防ぐ |
| `max_instances` | `1` | 同じジョブの並行実行を禁止する。DuckDB は単一ライタなので必須 |
| `misfire_grace_time` | `3600` | 予定時刻から1時間以内なら遅れて実行する。1時間超なら諦める（データが古くなりすぎる） |
| `timezone` | `Asia/Tokyo` | 市場のスケジュールに合わせる。UTC で書くと夏時間で混乱する |

**PCのスリープと Windows Update への対応**: `coalesce=True` と `misfire_grace_time` に加えて、15分ごとの `resume_interrupted_jobs` が中断ジョブを拾う。詳細は §9 と [15-windows-runtime.md](15-windows-runtime.md) §7。

DuckDB は単一ライタのため、**スケジュールは API プロセスに内蔵する**（`services/api/main.py` の `_start_agent_scheduler`）。`ai-stock-agent.service` は API が止まっているときのフォールバックで、DuckDB が使用中なら終了コード 0 で抜ける（`Restart=on-failure`）。

週次深掘り（`weekly_review`）は `deep` 層で直近の推奨と実績をレビューし、教訓候補を `agent_memory` に足す。キーが無ければ集計だけ残して `partial`。月次 `model_retrain` は `train_ranker` で `data/models/ranker_{market}_h20.pkl` を書き、サンプル不足なら成果物を残さない。月曜の `garch_refit` は対象銘柄の GARCH を再推定し、`features_daily.garch_vol_*` を更新する。日次 `daily_backup`（JST 03:00）は SQLite backup API と DuckDB `EXPORT DATABASE` で世代を残す。手動起動は `POST /api/v1/system/backup`（[09-api-spec.md](09-api-spec.md) §2.10、[11-security-ops.md](11-security-ops.md) §4）。

## 3. Collector

### 3.1 責務

外部APIからデータを取得し、Raw層に保存してから Core 層へ正規化・upsert する。詳細は [02-data-ingestion.md](02-data-ingestion.md)。

### 3.2 実行順序と依存

```python
def collector(market: str, as_of: date) -> CollectorResult:
    steps = [
        # (名前, 関数, 必須か)
        ("securities_master", fetch_securities, False),   # 週1回だけ実行
        ("prices",            fetch_prices,     True),    # これが失敗したら以降は無意味
        ("prices_live",       fetch_prices_live, False),
        ("financials",        fetch_financials, False),
        ("documents",         fetch_documents,  False),
        ("macro",             fetch_macro,      False),
        ("earnings_calendar", fetch_earnings_dates, False),
    ]
    results = {}
    for name, fn, required in steps:
        try:
            results[name] = fn(market, as_of)
            checkpoint(name, "done")
        except Exception as e:
            results[name] = StepResult(status="failed", error=e)
            log_and_alert(name, e)
            if required:
                return CollectorResult(status="failed", steps=results)
            # 必須でなければ続行（機能縮退）
    status = "success" if all_ok(results) else "partial"
    return CollectorResult(status=status, steps=results)
```

**`prices` のみを必須ステップとする。** 価格がなければ何も計算できないが、開示資料やマクロが取れなくても定量スコアは作れる。

`documents` が 0 件で、かつ倉庫に既存の開示が無い場合は `partial` とする（空レスポンスを success にしない）。既存カバレッジがある日に新規 0 件なのは正常で success のまま。

### 3.3 出力

- `job_runs` に `status`（`success` / `partial` / `failed`）と `metrics` を記録
- 各ステップの完了を `checkpoint` に記録（再開用）
- 異常があれば `alerts` に記録

## 4. Analyst

### 4.1 責務

1. 特徴量の計算（`features_daily`）
2. GARCH 予測の更新
3. 為替予測（ARIMAX / VECM / ランダムウォーク）と DM検定
4. LightGBM による予測（`ml_pred_h5` / `h20` + 信頼区間）
5. ファクター z-score とスコアの合成（`scores_daily`）
6. レジーム判定

LLM は使わない（純粋な計算処理）。

### 4.2 部分失敗時の振る舞い

| 失敗 | 動作 |
| --- | --- |
| 一部銘柄の特徴量計算が失敗 | その銘柄をスキップし `data_gaps` に記録。他の銘柄は処理する |
| GARCH が収束しない | 実現ボラにフォールバックし `data_quality_flags` に記録 |
| LightGBM モデルファイルが存在しない | `ml_pred` を NULL にし、`quant_score` のみで続行。「モデル未学習」を通知。Analyst 全体は partial にしない |
| 為替スポットが倉庫に無い | 為替予測ステップを skip。Analyst 全体は partial にしない。スポットがあれば外生変数なしでも RW を出す |
| 特徴量の欠損が多い銘柄（`n_missing > 15`） | スコアリング対象外にする |

### 4.3 品質チェック（実行後）

| チェック | 閾値 | 違反時 |
| --- | --- | --- |
| スコアリング対象銘柄数 | 前日比 -20% 以内 | 警告アラート |
| `quant_score` の分布 | 平均 45-55、標準偏差 12-25 | 警告（計算バグの兆候） |
| `ml_pred` の分布 | 平均が ±2% 以内 | 警告（モデルが偏っている） |
| 信頼区間の幅 | 中位値が 5-30% | 警告（極端に狭い場合はリークの疑い） |
| 特徴量の分布ドリフト | KS検定 p < 0.01 の特徴量が3つ以上 | 「モデル再学習を推奨」を通知 |

**信頼区間が極端に狭い場合にリークを疑う**という規則が重要である。予測が異様に正確なら、まず疑うべきはリークである。

## 5. Researcher

### 5.1 責務

LLM を使って開示資料を読解し、定性スコアを算出する。

1. 当日の分析対象銘柄を決定する（[05-scoring-screening.md](05-scoring-screening.md) §6.2 の優先順）
2. 各銘柄の未要約の資料について LLM 要約を生成する（キャッシュミス分のみ）。生成結果は `document_summaries` に upsert する
3. リスク要因の前期比較を行う
4. 銘柄単位の `qual_score` / `qual_confidence` を算出する

### 5.2 銘柄単位の qual_score の集約

複数の資料から1つのスコアを作る。

```python
def aggregate_qual_score(summaries: list[Summary], as_of: date) -> QualResult:
    """資料の鮮度で重み付けした加重平均。古い資料の影響を減衰させる。"""
    if not summaries:
        return QualResult(score=None, confidence=None, doc_count=0)
    weights, scores = [], []
    for s in summaries:
        age_days = (as_of - s.filed_at.date()).days
        # 半減期90日の指数減衰
        recency_w = 0.5 ** (age_days / 90)
        # 資料種別の重み
        type_w = {"earnings_flash": 1.0, "guidance_revision": 1.2,
                  "quarterly_report": 0.9, "annual_report": 0.8,
                  "other_disclosure": 0.3}.get(s.doc_type, 0.3)
        # 引用数が多い（=根拠がしっかりしている）ものを重視
        evidence_w = min(len(s.citations) / 3.0, 1.5)
        weights.append(recency_w * type_w * evidence_w)
        scores.append(s.qualitative_score)
    score = np.average(scores, weights=weights)
    # 確信度は「資料の量と鮮度」から決まる。スコアの大きさとは無関係
    confidence = min(
        0.3 * min(len(summaries) / 3, 1.0)          # 資料数
        + 0.4 * (0.5 ** (min_age_days / 60))        # 最新資料の鮮度
        + 0.3 * (1.0 - score_dispersion),           # 資料間の一貫性
        1.0)
    return QualResult(score=float(np.clip(score, -1, 1)),
                      confidence=float(confidence), doc_count=len(summaries))
```

**`confidence` をスコアの大きさから独立させる**ことが重要である。「強く肯定的」と「確信度が高い」は別の概念である。資料が1件しかないのに強い判断を出す場合、スコアは大きいが確信度は低くなるべきである。

### 5.3 コストキャップ到達時

`CostCapExceeded` を捕捉し、以下を行う。

1. 未処理の銘柄について `qual_score = NULL` とする
2. `job_runs.status = 'partial'`、`metrics.llm_capped = true` を記録
3. `alerts` に「本日のLLM予算に達しました。定性分析は n 銘柄で停止しています」を記録
4. **例外を伝播させず、Strategist に処理を渡す**（定量スコアのみで推奨は生成できる）

## 6. Strategist

### 6.1 責務

1. `total_score` を算出する（[05-scoring-screening.md](05-scoring-screening.md) §6.3）
2. ユニバースフィルタとリスク制約を適用する
3. 推奨候補を選抜する
4. 各候補について LLM で thesis / bear case / invalidation / conviction を生成する
5. reason codes を付与する
6. `hit_rate_prior` を過去実績から算出する
7. `recommendations` テーブルに挿入する（Critic 通過前は `critic_verdict = NULL`）

### 6.2 プロンプトへの注入内容

- 定量データ（全ファクターのz-score、ML予測と信頼区間、主要指標）
- RAG で取得した関連チャンク（8件）。`retrieve`（キーワード検索）が空なら、直近開示の本文抜粋に落とす
- 過去の類似ケースの実績（`hit_rate_prior`、`n_prior_samples`、平均超過リターン）
- **`agent_memory` から選ばれた教訓（最大15件）**

`agent_memory` の選択:

```sql
SELECT memory_id, category, lesson_ja, evidence_ja, n_observations, confidence
FROM agent_memory
WHERE is_active = 1
  AND confidence >= 0.6
  AND n_observations >= 10
  AND (scope = 'global'
       OR (scope = 'market' AND scope_value = :market)
       OR (scope = 'sector' AND scope_value = :sector)
       OR (scope = 'ticker' AND scope_value = :ticker))
ORDER BY confidence * ln(n_observations) DESC
LIMIT 15;
```

注入した `memory_id` は `recommendations.memory_ids_used` に記録する。**これにより「どの教訓を使った推奨が当たったか」を後から追跡でき、教訓自体の有効性を評価できる**（§7.4）。

### 6.3 挿入前の検証

`recommendations` テーブルの不変条件（[03-data-model.md](03-data-model.md) §2.9）をリポジトリ層で検証する。違反した場合は LLM を1回リトライし、それでも違反するなら**その推奨を破棄する**（不完全な推奨をUIに出さない）。検証例外（`InvariantViolation` / `InvariantViolationError`）と保存時の `StorageError`（NOT NULL 欠落など）は銘柄単位で捕捉し、パイプライン全体は落とさない。

カードには `conviction`（low/medium/high）だけでなく `conviction_score`（0.0..1.0）を必ず入れる。定量フォールバックでは `quant_score / 100` を使う。ML 予測はテーブル列 `ml_pred` に書く。

ML 予測区間が無い（モデル未学習）ときは、実現ボラティリティからホライズン幅を作る。それも無ければ ±20% の広いデフォルト区間を入れ、点推定は NULL のままにする。区間なしの推奨は不変条件で挿入できないため、情報の無さを幅で表現する。

スケジュール実行（`run_pipeline_job`）は手動実行と同じく `LLMRouter` と学習済み ranker（`data/models/ranker_{market}_h20.pkl`）を注入する。成果物が無ければ ranker は None で、定量カードのみになる。

## 7. Critic

### 7.1 責務

生成された推奨を敵対的にレビューし、`approved` / `revised` / `rejected` を判定する。

**Critic を独立したジョブにする理由**: 同じLLM呼び出しの中で「論拠を作れ、かつ批判せよ」と指示しても、自分が作ったものを厳しく批判する動機がない。別の呼び出しとして、明確に「弱点を見つけることがあなたの役割である」と指示することで機能する。

### 7.2 機械的検証（LLM の前に実行する）

LLM に渡す前に、コードで検証できるものは検証する。これがコスト削減と信頼性の両方に効く。

```python
def mechanical_checks(rec: Recommendation) -> list[Issue]:
    issues = []

    # (1) 引用の実在性。定量カードの合成引用（quant:）は開示資料ではないので検証しない。
    for c in rec.citations:
        if str(c.doc_id).startswith("quant:"):
            continue
        verdict = verify_citation(c)     # [07-llm-rag.md] §4.5
        if verdict in (CitationVerdict.DOC_NOT_FOUND, CitationVerdict.QUOTE_NOT_FOUND):
            issues.append(Issue("critical", "citation_not_found", detail=str(c)))

    # (2) データ鮮度
    for f in rec.data_freshness:
        expected = expected_latest_as_of(f.source, rec.as_of)
        if (expected - f.latest_as_of).days > 3:
            issues.append(Issue("major", "stale_data", detail=f"{f.source}: {f.latest_as_of}"))

    # (3) 遅延データを現在値に使っていないか
    if rec.entry_ref_source == "jquants" and jquants_plan == "free":
        issues.append(Issue("critical", "delayed_price_as_current"))

    # (4) bear case の実質性（長さと定型文検出）
    if len(rec.bear_case_ja) < 20:
        issues.append(Issue("critical", "empty_bear_case"))
    if any(p in rec.bear_case_ja for p in BOILERPLATE_PATTERNS):
        issues.append(Issue("major", "boilerplate_bear_case"))

    # (5) 確信度と母数の整合
    if rec.conviction != "low" and (rec.n_prior_samples or 0) < 20:
        issues.append(Issue("major", "conviction_without_evidence"))

    # (6) 信頼区間の有無と妥当性
    if rec.expected_ret_lo is None or rec.expected_ret_hi is None:
        issues.append(Issue("critical", "missing_confidence_interval"))
    elif rec.expected_ret_hi - rec.expected_ret_lo < 0.01:
        issues.append(Issue("major", "suspiciously_narrow_ci"))   # リークの疑い

    # (7) PIT 違反。定量カードの合成 ID は資料ではないのでスキップする。
    for doc_id in rec.source_doc_ids:
        if str(doc_id).startswith("quant:"):
            continue
        doc = repo.get_document(doc_id)
        if doc.filed_at.date() > rec.as_of:
            issues.append(Issue("critical", "future_document_cited"))

    # (8) 禁止語
    if any(w in rec.thesis_ja for w in ["必ず", "確実に", "間違いなく"]):
        issues.append(Issue("major", "overconfident_language"))

    return issues
```

`BOILERPLATE_PATTERNS` の例:

```python
BOILERPLATE_PATTERNS = [
    "市場環境の悪化", "予想外の事態", "リスクは限定的", "特にありません",
    "一般的なリスク", "マクロ環境の変化", "地政学リスク",
]
```

これらの語のみで構成された bear case は実質的に無内容である。**ただし単語自体を禁止するのではなく、具体的な数値や資料引用を伴わない場合に警告する**（「地政学リスクにより、当社の中東売上比率18%が影響を受ける可能性」は有効な bear case である）。

### 7.3 LLM による検証

機械的検証で `critical` が出た時点で `rejected` とし、LLM を呼ばない（コスト削減）。`critical` がない場合のみ LLM に渡し、論理の飛躍や bear case の実質性を検証する。プロンプトは [07-llm-rag.md](07-llm-rag.md) §5.4。

### 7.4 判定と後処理

| verdict | 動作 |
| --- | --- |
| `approved` | `critic_verdict='approved'` を記録。UIに表示される |
| `revised` | Critic の `revised_fields`（`thesis_ja` / `bear_case_ja` / `invalidation_ja` / `conviction`）をカード本文に適用して再保存。`critic_notes_ja` に修正内容を記録。母数不足なら conviction は low のまま。UIには修正後のものを表示し、「レビューで修正済み」バッジを付ける |
| `rejected` | `critic_verdict='rejected'` を記録。**UIには表示しないが、テーブルには残す** |

**却下された推奨を残す理由**: これが学習材料になる。「Strategist が生成したが Critic が却下した」パターンを Evaluator が分析し、Strategist のプロンプト改善に繋げる。エージェントコンソール画面では却下分も確認できる（開発者向けの表示）。

### 7.5 却下率の監視

| 却下率 | 解釈 | 対応 |
| --- | --- | --- |
| 0% が続く | Critic が機能していない | プロンプトを見直す。機械的検証が甘い可能性 |
| 10-30% | 正常な範囲 | - |
| 50% 超が続く | Strategist の品質が低い、または Critic が過剰に厳しい | 却下理由の内訳を確認する。`citation_not_found` が多いならRAGの問題、`empty_bear_case` が多いなら thesis プロンプトの問題 |

却下率と却下理由の内訳は `job_runs.metrics` に記録し、エージェントコンソールでグラフ表示する。

## 8. Evaluator（フィードバックループの実体）

### 8.1 責務

1. T+5 / T+20 に到達した過去の推奨について実績を計算する
2. `recommendation_outcomes` に記録する
3. 実績から教訓を抽出し `agent_memory` を更新する
4. ファクター重みの再フィットを提案する（`factor_weights`）
5. 信頼区間のキャリブレーションを評価する
6. モデルの劣化を検出する

### 8.2 実績の計算

```python
def evaluate_outcomes(as_of: date) -> list[Outcome]:
    """as_of 時点で horizon に到達した推奨を評価する。"""
    outcomes = []
    for horizon, days in [("H5", 5), ("H20", 20)]:
        target_as_of = shift_business_days(as_of, -days - 1)
        recs = repo.get_recommendations(as_of=target_as_of, horizon=horizon,
                                        critic_verdict="approved")
        for r in recs:
            # エントリーは as_of の翌営業日の始値（現実的な約定想定）
            entry_date = next_business_day(r.as_of, r.market)
            exit_date = shift_business_days(entry_date, days)
            entry = repo.get_price(r.ticker, entry_date, field="adj_open")
            exit_ = repo.get_price(r.ticker, exit_date, field="adj_open")
            if entry is None or exit_ is None:
                # 価格が取れない（上場廃止、売買停止など）は記録して除外
                repo.record_gap(...)
                continue
            raw_ret = exit_ / entry - 1
            bench_ret = benchmark_return(r.market, entry_date, exit_date)
            # JP: TOPIX / 1306 / 1306.T / ^TOPX の始値。US: SPX / SPY / ^GSPC。
            # 倉庫に指数が無ければ 0 とし、metrics.benchmark_missing を立てる。
            excess = raw_ret - bench_ret
            # 的中判定: action の方向と excess_return の符号が一致するか
            expected_sign = {"watch": 1, "accumulate": 1, "reduce": -1, "avoid": -1}[r.action]
            is_hit = (excess * expected_sign) > 0
            outcomes.append(Outcome(
                rec_id=r.rec_id, horizon=horizon,
                entry_date=entry_date, exit_date=exit_date,
                entry_price=entry, exit_price=exit_,
                raw_return=raw_ret, benchmark_return=bench_ret,
                excess_return=excess, is_hit=is_hit,
                max_favorable_excursion=mfe(r.ticker, entry_date, exit_date, expected_sign),
                max_adverse_excursion=mae(r.ticker, entry_date, exit_date, expected_sign),
            ))
    return outcomes
```

**エントリーを翌営業日の始値にする理由**: `as_of` の終値時点で生成された推奨を、その日の終値で約定することは不可能である。この1ステップのズレを入れないと実績が甘くなる（[04-analysis-engine.md](04-analysis-engine.md) §3.2 と同じ理由）。

`max_adverse_excursion`（期間中の最大不利変動）を記録する理由は、**「最終的に当たったが途中で大きく逆行した」推奨を識別する**ため。実運用では途中で耐えられずに損切りすることがあり、最終結果だけでは実用性が測れない。高値・安値があればそれを使い、無ければ終値で代用する。

ファクター重みの再フィットは実績が H20 で 100 件以上あるときだけ `propose_factor_weights` を呼び、`factor_weights` に `is_active=0`・`created_by=evaluator` で挿入する。自動では有効化しない。

### 8.3 集計指標

| 指標 | 定義 | 用途 |
| --- | --- | --- |
| 全体的中率 | `mean(is_hit)` | ダッシュボードに表示 |
| conviction別的中率 | `conviction` でグループ化 | **high の的中率が low を上回っているか**が確信度の妥当性の検証 |
| reason code別的中率 | reason code でグループ化（複数該当は各々にカウント） | どの理由が有効かの判定。`hit_rate_prior` の算出元 |
| 平均超過リターン | `mean(excess_return)` | 的中率が高くても平均リターンが低い場合がある |
| ペイオフ比 | `mean(excess|hit) / abs(mean(excess|miss))` | 的中率が低くても勝ちが大きければ成立する |
| 信頼区間カバレッジ | 実績が `[lo, hi]` に入った比率 | 想定 60%（q20-q80）と比較 |
| MAE中位値 | `median(max_adverse_excursion)` | 実用性の指標 |
| Critic却下率 | `count(rejected) / count(all)` | Strategist の品質 |

**`conviction` 別の的中率が単調でない場合（high < low）は、確信度の付け方が間違っている。** これは重要な自己診断であり、検出したら `agent_memory` に caveat として記録し、UIに警告を出す。

### 8.4 教訓の抽出と更新

LLM（`default` 層）で教訓を抽出する。プロンプトは [07-llm-rag.md](07-llm-rag.md) §5.5。

```python
def update_memory(new_lessons: list[Lesson], existing: list[Memory]) -> MemoryUpdate:
    added, superseded, deactivated = [], [], []
    for lesson in new_lessons:
        # (1) 最低サンプル数のチェック
        if lesson.n_observations < 10:
            continue
        # (2) 既存の教訓と重複するか
        dup = find_similar_memory(existing, lesson, threshold=0.85)
        if dup:
            if lesson.n_observations > dup.n_observations:
                # より多くの観測に基づく新しい教訓で置き換える
                superseded.append((dup.memory_id, lesson))
            continue
        added.append(lesson)

    # (3) 有害な教訓の無効化
    for m in existing:
        if m.hit_rate_after is not None and m.hit_rate_before is not None:
            if m.hit_rate_after < m.hit_rate_before - 0.05 and m.use_count >= 20:
                deactivated.append(m.memory_id)   # この教訓は成績を悪化させている
    return MemoryUpdate(added=added, superseded=superseded, deactivated=deactivated)
```

### 8.5 教訓自体の有効性評価

`recommendations.memory_ids_used` があるため、「この教訓を使った推奨の的中率」を計算できる。

```sql
-- 教訓 M001 を使った推奨と、使わなかった推奨の的中率を比較する
SELECT
  list_contains(r.memory_ids_used, 'M001') AS used_memory,
  AVG(CAST(o.is_hit AS DOUBLE)) AS hit_rate,
  COUNT(*) AS n
FROM recommendations r
JOIN recommendation_outcomes o ON r.rec_id = o.rec_id
WHERE r.market = 'JP' AND o.horizon = 'H20'
GROUP BY 1;
```

これを `agent_memory.hit_rate_before` / `hit_rate_after` に反映する。厳密なA/B比較ではない（教訓が適用される銘柄には偏りがある）が、**明らかに成績を悪化させている教訓を検出するには十分**である。

**この仕組みがないと、教訓がどんどん溜まって「もっともらしいが役に立たない指示」でプロンプトが埋まる。** 自己修正の経路を持つことが、フィードバックループを機能させる条件である。

### 8.6 教訓の例（期待される出力の具体例）

```json
{
  "scope": "market", "scope_value": "JP", "category": "pattern",
  "lesson_ja": "JP市場のH20で REV_UP_GUIDANCE が立つケースは、同時に MOM_STRONG_12M が立つ場合の的中率が68%（n=31）だが、単独では51%（n=88）。上方修正のみを根拠にした推奨は確信度を上げない。",
  "evidence_ja": "2026-02-01から2026-08-01の推奨119件。REV_UP_GUIDANCE単独: 45勝43敗、平均超過リターン+0.4%。MOM_STRONG_12M併存: 21勝10敗、平均+2.8%。",
  "n_observations": 119, "confidence": 0.72
}
```

```json
{
  "scope": "global", "category": "caveat",
  "lesson_ja": "信頼区間のカバレッジが42%（想定60%）であり、モデルは予測区間を過小に見積もっている。expected_ret の区間は実際より狭いものとして扱うべき。",
  "evidence_ja": "直近90日の推奨214件のうち、実績が[lo,hi]に入ったのは90件（42.1%）。特にボラティリティが上位20%の銘柄で乖離が大きい（カバレッジ31%）。",
  "n_observations": 214, "confidence": 0.85
}
```

```json
{
  "scope": "sector", "scope_value": "銀行業", "category": "bias",
  "lesson_ja": "銀行業ではPBRベースのバリューz-scoreが高い銘柄の的中率が38%（n=24）と低い。金利環境の影響が支配的で、PBRの割安さがリターンに繋がっていない。",
  "evidence_ja": "銀行業の推奨24件中、value_z >= 1.0 のもの9勝15敗。同期間の全セクター平均的中率は54%。",
  "n_observations": 24, "confidence": 0.61
}
```

**「カバレッジが42%（想定60%）」のような自己批判的な教訓が出ることが、このループが正しく機能している証拠である。**

### 8.7 ファクター重みの再フィット

[05-scoring-screening.md](05-scoring-screening.md) §8 の通り。既定は承認制で、自動適用しない。

### 8.8 運用初期（実績がない期間）

推奨開始から60営業日程度は `recommendation_outcomes` が十分に溜まらない。この期間の振る舞い:

| 項目 | 初期の値 |
| --- | --- |
| `hit_rate_prior` | `NULL` |
| `conviction` | `low` 固定 |
| `agent_memory` | 空。プロンプトへの注入なし |
| `factor_weights` | `factors.yaml` の初期値（`weight_set_id='initial'`） |
| UI表示 | 「実績データの蓄積中（推奨開始から n 営業日、評価済み m 件）」 |

**運用開始直後に高い確信度を出さない**ことが重要である。データがないのに自信を表示するのは最も避けたい振る舞いである。

## 9. ジョブの冪等性と再開

### 9.1 冪等性の要件

すべてのジョブは以下を満たす。

1. **同じ入力で2回実行しても結果が変わらない**（upsert のみ、append しない）
2. **途中で中断されても、次回実行時に続きから再開できる**
3. **中断された状態が検出可能である**（`job_runs.status = 'running'` が残る）

### 9.2 チェックポイント

```python
class Checkpoint(BaseModel):
    job_name: str
    phase: str                       # 'collector.prices' など
    completed_units: list[str]       # 完了した単位（日付、ticker）
    next_unit: str | None
    metrics: dict[str, Any]
    updated_at: datetime

def with_checkpoint(job_run_id: int, phase: str, units: list[str], fn):
    """各単位の処理後にチェックポイントを保存する。
    中断されても completed_units から再開できる。"""
    cp = load_checkpoint(job_run_id) or Checkpoint(...)
    for unit in units:
        if unit in cp.completed_units:
            continue                 # 既に完了している
        fn(unit)
        cp.completed_units.append(unit)
        cp.next_unit = next_of(units, unit)
        save_checkpoint(job_run_id, cp)    # 毎回保存（コストは小さい）
```

チェックポイントの粒度:

| ジョブ | 粒度 | 理由 |
| --- | --- | --- |
| Collector（価格） | 営業日単位 | J-Quants は日付単位で取得するため |
| Collector（資料） | doc_id 単位 | ダウンロードの再実行を避ける |
| Analyst（特徴量） | 日付 × 市場単位 | 全銘柄を一括計算するため銘柄単位にできない |
| Researcher | doc_id 単位 | **LLM呼び出しの再実行はコストが直接発生するため最も細かく** |
| Strategist | ticker 単位 | 同上 |
| Critic | rec_id 単位 | 同上 |
| Evaluator | (rec_id, horizon) 単位 | |

### 9.3 中断ジョブの検出と再開

```python
def resume_interrupted_jobs() -> None:
    """15分ごとに実行。Windows Update による再起動などで中断された
    ジョブを検出する。生存中のジョブは誤って中断しない。"""
    stale = repo.find_job_runs(
        status="running",
        started_before=utcnow() - timedelta(hours=2),   # 2時間以上 running
    )
    for run in stale:
        if is_process_alive(run.pid):
            continue                 # まだ動いている（pid 未記録も生存扱い）
        repo.update_job_run(run.id, status="interrupted")
        # 実行しない resume 用の running 行は作らない。
        # 起動時キャッチアップが当日推奨の欠落を見て pipeline を再実行する。
```

`job_runs.pid` に開始時の PID を記録する。`is_process_alive(run.pid)` により、単に時間がかかっているだけのジョブを誤って中断しない。pid が NULL のレガシー行も生存扱いとし、API 起動時に `running` をまとめて `interrupted` にする。

起動時キャッチアップは当日の推奨が無ければ pipeline を走らせる。同じ `parent_run_id` の連鎖で空の running を増やさない。

## 10. ガードレールの一覧

| ガードレール | 実装箇所 | 動作 |
| --- | --- | --- |
| トークン予算（1回の呼び出し） | `LLMRouter.complete` | 入力トークンが上限（bulk: 500K、default: 200K、deep: 800K）を超えたら分割または切り詰め |
| 日次コストキャップ | `CostGuard` | 超過時にキルスイッチを立て、以降のLLM呼び出しを停止 |
| 月次コストキャップ | `CostGuard` | 同上（解除は手動） |
| キルスイッチ | `settings.llm.kill_switch` | UI から即座に全LLM呼び出しを停止できる |
| 引用の必須化 | Pydantic スキーマ + リポジトリ検証 | 引用のないLLM出力を保存しない |
| bear case の必須化 | リポジトリ検証 | 20文字未満の bear case を持つ推奨を挿入しない |
| 信頼区間の必須化 | リポジトリ検証 | 区間のない予測を保存しない |
| 確信度の上限 | Strategist + Critic | `n_prior_samples < 20` なら `conviction = low` に強制 |
| 推奨件数の上限 | Strategist | `agent.max_recommendations_per_day`（既定10） |
| 同一セクター上限 | Strategist | 3件 |
| 並行実行の禁止 | APScheduler `max_instances=1` | DuckDB の単一ライタ制約 |
| 再開の誤発火防止 | `resume_interrupted_jobs` | pid 生存ならスキップ。空の resume 行は作らない |
| API レート制限 | `TokenBucket`（SQLite永続化） | 再起動直後の制限超過を防ぐ |
| PIT 違反の検出 | `assert_pit_safe` | 未来情報の混入時に例外 |
| 遅延データの誤用 | Critic の機械的検証 | `critical` 判定で却下 |

## 11. エージェントコンソール画面での可視化

[ui/screens/08-agent-console.md](ui/screens/08-agent-console.md) に対応。以下を表示する。

- 各ジョブの直近実行状況（成功 / 部分 / 失敗 / 中断）とタイムライン
- 実行中ジョブの進捗（チェックポイントの `completed_units / total`）
- LLMコストの推移（日次・累計、tier別・用途別の内訳）
- Critic の却下率と却下理由の内訳
- `agent_memory` の一覧（有効・無効、confidence、使用回数、効果）
- 手動実行ボタン（ジョブ単位、市場単位）
- キルスイッチのトグル
- `alerts` の一覧

## 12. 参照

- スコアリング: [05-scoring-screening.md](05-scoring-screening.md)
- プロンプト: [07-llm-rag.md](07-llm-rag.md)
- 再起動対応: [15-windows-runtime.md](15-windows-runtime.md) §7
- バックアップ: [11-security-ops.md](11-security-ops.md) §4
- 手動バックアップ API: [09-api-spec.md](09-api-spec.md) §2.10
- 評価ループの実行手順: `.cursor/skills/agent-eval-loop/SKILL.md`
