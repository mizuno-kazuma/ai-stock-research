# 09. REST API 仕様

## 1. 全体規約

| 項目 | 規約 |
| --- | --- |
| ベースURL | `http://<host>:8000/api/v1` |
| 形式 | JSON（`application/json; charset=utf-8`） |
| 日付 | `YYYY-MM-DD`（ISO 8601） |
| 日時 | ISO 8601 UTC（`2026-08-23T09:30:00Z`）。**UIでのタイムゾーン変換はクライアント側で行う** |
| 数値 | 比率は小数（`0.0823` = 8.23%）。**パーセント値を数値として返さない**（単位の混在を避ける） |
| 通貨 | 金額フィールドには必ず `currency` を併記 |
| 命名 | `snake_case`（Python 側と揃える。TS 型は自動生成されるので変換不要） |
| ページネーション | `limit` / `offset` + `total` を返す |
| エラー | RFC 7807 (Problem Details) 準拠 |
| 認証 | Phase A: なし（Tailscale の tailnet 内のみ到達可能）。Phase B: Bearer トークン |
| OpenAPI | `/api/v1/openapi.json` で公開。TS 型を `openapi-typescript` で生成 |
| CORS | Phase A では `http://localhost:3000` と Tailscale ホスト名を許可 |

### 1.1 エラーレスポンス

```json
{
  "type": "https://example.invalid/problems/data-not-ready",
  "title": "データが未生成です",
  "status": 409,
  "detail": "2026-08-23 の JP 市場のスコアはまだ計算されていません。直近の利用可能日は 2026-08-22 です。",
  "instance": "/api/v1/scores?market=JP&as_of=2026-08-23",
  "latest_available_as_of": "2026-08-22"
}
```

主なエラー型:

| type | status | 発生条件 |
| --- | --- | --- |
| `validation-error` | 422 | パラメータ不正 |
| `not-found` | 404 | 銘柄・資料が存在しない |
| `data-not-ready` | 409 | 指定日のデータが未生成。`latest_available_as_of` を返す |
| `partial-data` | 200 | **エラーにしない。** レスポンスに `warnings` 配列を入れる |
| `cost-cap-exceeded` | 429 | LLM のオンデマンド呼び出しがキャップ超過 |
| `upstream-unavailable` | 503 | 外部APIが応答しない（オンデマンド取得時） |
| `internal-error` | 500 | |

### 1.2 部分データの表現

**部分失敗をエラーにしない**という設計判断が重要である。あるセクションのデータが欠けても、他が表示できるなら 200 で返し、警告を添える。

```json
{
  "data": { "...": "..." },
  "warnings": [
    {"code": "STALE_DATA", "source": "jquants",
     "message_ja": "J-Quantsのデータが12週遅延しています（最新: 2026-05-31）",
     "severity": "info"},
    {"code": "SECTION_UNAVAILABLE", "section": "qualitative",
     "message_ja": "本日のLLM予算に達したため定性分析はありません",
     "severity": "warning"}
  ],
  "meta": {
    "as_of": "2026-08-22",
    "computed_at": "2026-08-22T09:35:12Z",
    "data_freshness": [
      {"source": "jquants", "latest_as_of": "2026-05-31"},
      {"source": "yfinance", "latest_as_of": "2026-08-22"},
      {"source": "edinet", "latest_as_of": "2026-08-22"}
    ]
  }
}
```

`meta.data_freshness` は**全エンドポイントの共通レスポンスに含める**。UIヘッダの鮮度表示に使う。

## 2. エンドポイント一覧

### 2.1 ダッシュボード

```
GET /api/v1/dashboard?market=JP&as_of=2026-08-22
```

`market` は `JP` / `US` / `auto`。`auto` は日本時間15時未満を `JP`、それ以降を `US` に解決する（設定キー `ui.default_market` と同じ規則）。レスポンスの `data.market` は常に `JP` または `US`。


レスポンス:

```json
{
  "data": {
    "as_of": "2026-08-22",
    "market_summary": {
      "benchmark": {"symbol": "TOPIX", "close": 2843.21, "change_pct": 0.0062},
      "advance_decline": {"advancing": 1420, "declining": 2180, "unchanged": 210},
      "vol_regime": {"level": "elevated", "percentile": 0.78,
                     "message_ja": "ボラティリティは過去5年の78パーセンタイル。推奨の確信度を1段下げています"},
      "correlation_regime": {"avg_pairwise_corr_60d": 0.41, "level": "normal"}
    },
    "fx": {
      "pair": "USDJPY", "spot": 152.34, "change_pct": -0.0031,
      "forecast_h20": {
        "point": 151.80, "ci_lo_80": 146.20, "ci_hi_80": 157.40,
        "beats_baseline": false,
        "note_ja": "ランダムウォークに対する優位性は確認できていません（DM検定 p=0.31）"
      }
    },
    "top_recommendations": [ /* RecommendationSummary の配列。最大5件。発行体あたり1件 */ ],
    "portfolio_snapshot": {
      "n_positions": 8, "unrealized_pnl_pct": 0.0412,
      "day_change_pct": -0.0083, "currency": "JPY",
      "top_movers": [{"ticker": "6758", "change_pct": 0.0231}]
    },
    "new_filings_count": 34,
    "watchlist_filings": [ /* 保有・ウォッチリスト銘柄の今週の開示 */ ],
    "model_health": {
      "rank_ic_20d": 0.041, "rank_ic_percentile_1y": 0.62,
      "status": "normal",
      "coverage_rate": 0.42,
      "coverage_note_ja": "信頼区間のカバレッジが想定60%に対し42%。区間は実際より狭い可能性があります"
    },
    "alerts": [ /* 未読アラート */ ],
    "job_status": {"last_run": "2026-08-22T09:35:12Z", "status": "partial",
                   "failed_steps": ["tdnet"]}
  },
  "warnings": [],
  "meta": { "...": "..." }
}
```

`new_filings_count` と `watchlist_filings` の対象期間は `as_of` を含む暦週（月曜始まり、
`as_of` 当日を含む）。画面ラベルは「今週の開示」。対象週に開示が無いときは件数 0・一覧は空。
期間外の資料で埋めない。シード（`docs/ui/sample-data.json`）の `_meta.as_of` は 2026-08-22 なので、
その週は 5 件、翌週（例: 2026-08-29）は 0 件になる。

### 2.2 推奨

```
GET /api/v1/recommendations
    ?market=JP
    &as_of=2026-08-22           # 省略時は最新のスコア日、なければ最新の推奨日
    &horizon=H20                # カード結合時に優先するホライズン。既定 H20
    &sector=輸送用機器
    &min_score=70
    &pred_sign=positive         # positive | negative
    &reason_code=VAL_CHEAP_VS_SECTOR
    &has_card=false
    &action=watch,accumulate
    &conviction=medium,high
    &critic_verdict=approved,revised
    &include_rejected=true      # 既定 true。false でもスコア行としては残す
    &sort=total_score
    &limit=50&offset=0
```

レスポンスはユニバース行（`RecommendationFeedItem`）の配列。カードがある銘柄だけ `card` にフルの `RecommendationCard` が入る。カードがなくても `name_local` と `total_score` / `quant_score` は入る。

```json
{
  "data": {
    "items": [{
      "ticker": "7203", "market": "JP", "as_of": "2026-08-22",
      "name_local": "トヨタ自動車", "sector_name": "輸送用機器",
      "display_tier": "core",
      "total_score": 81.7, "quant_score": 78.4,
      "ml_pred_h20": 0.024, "ml_pred_h20_lo": -0.031, "ml_pred_h20_hi": 0.079,
      "reason_codes": ["VAL_CHEAP_VS_SECTOR", "REV_UP_GUIDANCE"],
      "critic_verdict": "approved",
      "rec_id": "01J8XKQ3M4N5P6R7S8T9V0W1X2",
      "action": "watch", "horizon": "H20", "conviction": "medium",
      "card": { "...": "RecommendationCard" }
    }, {
      "ticker": "6501", "market": "JP", "as_of": "2026-08-22",
      "name_local": "日立製作所", "sector_name": "電気機器",
      "display_tier": "score_only",
      "total_score": 88.7, "quant_score": 88.7,
      "reason_codes": ["QLT_HIGH_ROIC"],
      "critic_verdict": null, "rec_id": null, "card": null
    }],
    "total": 142,
    "universe_size": 1994,
    "filled_count": 0,
    "limit": 50,
    "offset": 0
  }
}
```

ダッシュボード `top_recommendations` も同じ `RecommendationFeedItem`。既定で 10 件（`universe_size` がそれ未満ならその件数）。詳細は [05-scoring-screening.md](05-scoring-screening.md) §7.8。

単一取得 `GET /api/v1/recommendations/{rec_id}` と、一覧の `card` フィールドは従来の `RecommendationCard` である。

レスポンス（`RecommendationCard`）:

```json
{
  "data": {
    "items": [{
      "rec_id": "01J8XKQ3M4N5P6R7S8T9V0W1X2",
      "as_of": "2026-08-22",
      "ticker": "7203", "market": "JP",
      "name_local": "トヨタ自動車", "name_en": "Toyota Motor Corporation",
      "sector_name": "輸送用機器",
      "action": "watch", "horizon": "H20",
      "conviction": "medium", "conviction_score": 0.58,

      "thesis_ja": "セクター内でバリューz=1.42と割安圏にあり、直近の四半期決算で通期営業利益予想を4兆8,000億円から5兆1,000億円へ上方修正した（決算短信p.3）。ROIC 11.8%はセクター中位の8.2%を上回る。ML予測はH20で超過リターン+2.4%を示す。",
      "bear_case_ja": "第一に、クオリティz=-0.21でセクター下位40%にあり、割安さが質の低さを反映したバリュートラップの可能性がある。第二に、決算資料で「北米市場においては競合他社の価格政策により競争環境が厳しさを増しており」（有報p.12）と新たに記載され、前期にはなかったリスクが開示された。第三に、REV_UP_GUIDANCE単独を根拠とした過去の推奨はH20の的中率51%（n=88）にとどまり、これだけでは優位性が乏しい。",
      "invalidation_ja": "次回四半期で北米販売台数が前年同期比マイナスに転じた場合、または通期営業利益予想が5兆円を下回る水準へ再修正された場合、この見立ては無効とする。",

      "reason_codes": ["VAL_CHEAP_VS_SECTOR", "REV_UP_GUIDANCE", "QLT_HIGH_ROIC", "FX_TAILWIND"],

      "expected_ret": 0.024,
      "expected_ret_lo": -0.031,
      "expected_ret_hi": 0.079,
      "hit_rate_prior": 0.58,
      "n_prior_samples": 34,

      "quant_score": 78.4,
      "quant_rank": 142, "quant_percentile": 0.964,
      "qual_score": 0.42, "qual_confidence": 0.66, "qual_doc_count": 3,
      "total_score": 81.7,

      "factor_scores": {
        "value": 1.42, "momentum": 0.68, "quality": -0.21,
        "growth": 0.55, "lowvol": 0.33, "revision": 1.85
      },

      "entry_ref_price": 3125.0, "entry_ref_source": "yfinance",
      "entry_ref_note_ja": "参考値（約15-20分遅延）",
      "stop_ref_price": 2890.0, "target_ref_price": 3420.0,
      "suggested_size_pct": 4.0, "currency": "JPY",

      "source_doc_ids": ["tdnet:20260428-0113", "edinet:S100XYZW", "edinet:S100ABCD"],
      "citations": [
        {"doc_id": "tdnet:20260428-0113", "page": 3,
         "quote": "通期の連結営業利益予想を5兆1,000億円に修正いたします"},
        {"doc_id": "edinet:S100XYZW", "page": 12,
         "quote": "北米市場においては競合他社の価格政策により競争環境が厳しさを増しており"}
      ],

      "data_freshness": [
        {"source": "jquants", "latest_as_of": "2026-05-31"},
        {"source": "yfinance", "latest_as_of": "2026-08-22"}
      ],
      "critic_verdict": "approved",
      "critic_notes_ja": "引用3件すべて検証済み。bear caseに具体的な数値と資料引用があり実質的。確信度はn=34に対して妥当。",
      "flags": ["EVENT_EARNINGS_SOON"],
      "generated_at": "2026-08-22T09:32:41Z"
    }],
    "total": 6
  },
  "warnings": [],
  "meta": { "...": "..." }
}
```

```
GET  /api/v1/recommendations/{rec_id}          # 単一取得（全フィールド）
GET  /api/v1/recommendations/{rec_id}/outcome  # 実績（horizon 到達後）
POST /api/v1/recommendations/{rec_id}/feedback # 利用者のフィードバック
```

```json
// POST /recommendations/{rec_id}/feedback
{"verdict": "agree", "note_ja": "北米の懸念は同意。ただし為替の追い風が上回ると判断"}
// verdict: "agree" | "disagree" | "acted_on" | "ignored"
```

利用者のフィードバックは `agent_memory` の材料になる。「利用者が繰り返し disagree する reason code」は教訓として記録される。

### 2.3 スコアとスクリーナー

```
GET /api/v1/scores?market=JP&as_of=2026-08-22&ticker=7203
POST /api/v1/screener
```

スクリーナーは条件が複雑なため POST を使う。

```json
// POST /api/v1/screener
{
  "market": "JP",
  "as_of": "2026-08-22",
  "filters": [
    {"field": "quant_score",  "op": "gte", "value": 70},
    {"field": "value_z",      "op": "gte", "value": 1.0},
    {"field": "roic",         "op": "gte", "value": 0.10},
    {"field": "adv_20d",      "op": "gte", "value": 100000000},
    {"field": "sector_code",  "op": "in",  "value": ["3050", "3100"]},
    {"field": "forecast_revision_direction", "op": "eq", "value": 1}
  ],
  "sort": [{"field": "quant_score", "dir": "desc"}],
  "columns": ["ticker", "name_local", "quant_score", "value_z", "quality_z",
              "per", "pbr", "roic", "ml_pred_h20", "realized_vol_60d"],
  "limit": 100, "offset": 0
}
```

`op` の値域: `eq` / `ne` / `gt` / `gte` / `lt` / `lte` / `in` / `not_in` / `between` / `is_null` / `is_not_null`

レスポンスには `truncated: true` を含める（500件で打ち切った場合）。

```
GET    /api/v1/screener/presets              # プリセット一覧
GET    /api/v1/screener/saved                # 保存済みフィルタ
POST   /api/v1/screener/saved                # フィルタを保存
DELETE /api/v1/screener/saved/{id}
```

### 2.4 銘柄詳細

```
GET /api/v1/stocks/{market}/{ticker}
GET /api/v1/stocks/{market}/{ticker}/prices?range=1y&series=research|live
GET /api/v1/stocks/{market}/{ticker}/financials?periods=8
GET /api/v1/stocks/{market}/{ticker}/features?as_of=2026-08-22
GET /api/v1/stocks/{market}/{ticker}/documents?doc_type=annual_report&limit=20
GET /api/v1/stocks/{market}/{ticker}/recommendations   # この銘柄の推奨履歴と実績
GET /api/v1/stocks/{market}/{ticker}/peers             # 同セクターの比較銘柄
```

`prices` の `series` パラメータで**リサーチ用（J-Quants）と現在値（yfinance）を明示的に分離する**。混同を防ぐため、レスポンスに必ず `source` と `is_delayed` を含める。

```json
{
  "data": {
    "series": "research", "source": "jquants",
    "is_delayed": true, "delay_note_ja": "無料プランのため12週遅延",
    "latest_as_of": "2026-05-31",
    "bars": [{"date": "2026-05-29", "open": 3080, "high": 3120, "low": 3065,
              "close": 3110, "volume": 8234100, "adj_close": 3110}]
  }
}
```

```
GET /api/v1/stocks/search?q=トヨタ&market=JP&limit=10
```

検索は銘柄コード・日本語名・英語名の前方一致と部分一致。日本語のカナ・漢字の両方でヒットするようにする（`securities` に `name_kana` を追加してもよい）。

`securities` は SCD2 のため同一コードが複数行になり、J-Quants は JP を 5 桁（`13010`）で返す。検索結果は発行体あたり 1 件に畳む（現行行・名称がある行を優先。4 桁と末尾 0 の 5 桁は同一銘柄）。

### 2.5 決算資料

```
GET /api/v1/documents
    ?market=JP&doc_type=guidance_revision
    &filed_from=2026-08-20&filed_to=2026-08-23
    &held_only=false&watchlist_only=false
    &has_summary=true
    &limit=50&offset=0

GET /api/v1/documents/{doc_id}
GET /api/v1/documents/{doc_id}/file?disposition=inline    # PDF バイナリ
GET /api/v1/documents/{doc_id}/summary
POST /api/v1/documents/{doc_id}/summary                   # オンデマンド要約生成
GET /api/v1/documents/{doc_id}/chunks?section=risk_factors
```

`POST /documents/{doc_id}/summary` は LLM を呼ぶため、コストキャップに達している場合は 429 を返す。

```json
// 429 レスポンス
{
  "type": "https://example.invalid/problems/cost-cap-exceeded",
  "title": "LLM予算の上限に達しています",
  "status": 429,
  "detail": "本日の使用額 $1.02 が上限 $1.00 に達しました。設定から上限を変更できます。",
  "spent_today_usd": 1.02, "daily_cap_usd": 1.00,
  "resets_at": "2026-08-24T00:00:00+09:00"
}
```

### 2.6 為替・マクロ

```
GET /api/v1/fx/USDJPY?as_of=2026-08-22
GET /api/v1/fx/USDJPY/history?range=5y
GET /api/v1/macro/series?ids=DGS10,DEXJPUS,CPIAUCSL&range=5y
GET /api/v1/macro/rate-differential?range=5y   # 日米金利差と為替の関係
```

為替のレスポンスには**必ず全モデルの予測とベースライン比較を含める**。

```json
{
  "data": {
    "pair": "USDJPY", "as_of": "2026-08-22", "spot": 152.34,
    "forecasts": [
      {"horizon_days": 5, "model_id": "random_walk",
       "point": 152.34, "ci_lo_80": 149.10, "ci_hi_80": 155.58,
       "ci_lo_95": 147.42, "ci_hi_95": 157.26,
       "is_baseline": true},
      {"horizon_days": 5, "model_id": "arimax_v2",
       "point": 152.61, "ci_lo_80": 149.30, "ci_hi_80": 155.92,
       "ci_lo_95": 147.55, "ci_hi_95": 157.67,
       "is_baseline": false,
       "dm_statistic": -0.42, "dm_pvalue": 0.676, "beats_baseline": false,
       "rmse_oos_60d": 1.284, "baseline_rmse_oos_60d": 1.271,
       "directional_accuracy_60d": 0.483,
       "verdict_ja": "ランダムウォークに対する優位性は確認できていません（DM検定 p=0.68）。参考程度に扱ってください。"}
    ],
    "vol_forecast": {"garch_vol_1d_ann": 0.0912, "garch_vol_20d_ann": 0.0987,
                     "persistence": 0.962},
    "cointegration": {"tested_pairs": ["log_usdjpy", "rate_diff_10y"],
                      "rank": 0, "detected": false,
                      "note_ja": "直近5年では共和分関係が検出されないため、VECMは使用していません"},
    "rate_differential": {"us_10y": 4.21, "jp_10y": 1.48, "diff": 2.73,
                          "percentile_5y": 0.71}
  }
}
```

`verdict_ja` を API 側で生成する。**UIが判定ロジックを持たないようにする**ことで、「優位性がないのに強気に表示する」実装ミスを構造的に防ぐ。

### 2.7 モデルラボ

```
GET  /api/v1/models/runs?kind=ranker&limit=20
GET  /api/v1/models/runs/{run_id}
GET  /api/v1/models/runs/{run_id}/feature-importance
GET  /api/v1/models/runs/{run_id}/ic-timeseries
GET  /api/v1/models/health                        # 直近の Rank IC、劣化検出
GET  /api/v1/backtests?limit=20
GET  /api/v1/backtests/{backtest_id}
GET  /api/v1/backtests/{backtest_id}/equity-curve
GET  /api/v1/backtests/{backtest_id}/trades?limit=200
POST /api/v1/backtests                            # 新規バックテスト実行（非同期）
GET  /api/v1/factor-weights?market=JP&horizon=H20
POST /api/v1/factor-weights/{weight_set_id}/activate   # 提案された重みを承認
```

`POST /api/v1/backtests` のリクエストは**コストパラメータを必須にする**。

```json
{
  "strategy_name": "value_quality_h20",
  "market": "JP",
  "period_start": "2024-08-01", "period_end": "2026-08-01",
  "rebalance_freq": "monthly",
  "n_positions": 20,
  "fee_bps": 5.0,
  "slippage_bps": 10.0,
  "max_turnover_pct": 30.0,
  "signal_source": {"type": "quant_score", "weight_set_id": "ws_20260801_a"},
  "universe_filter": {"min_adv_20d": 100000000, "min_market_cap": 30000000000}
}
```

`fee_bps` / `slippage_bps` / `max_turnover_pct` が欠けている場合は 422 を返す。**API レベルでもデフォルト値を持たせない**（[04-analysis-engine.md](04-analysis-engine.md) §4.1 と同じ理由）。

レスポンスは `202 Accepted` + `job_run_id`。完了は SSE または polling で確認する。

### 2.8 エージェント

```
GET  /api/v1/agent/jobs?limit=50
GET  /api/v1/agent/jobs/{job_run_id}
POST /api/v1/agent/jobs/{job_name}/run     # 手動実行
POST /api/v1/agent/jobs/{job_run_id}/cancel
DELETE /api/v1/agent/jobs                  # 完了した実行履歴を削除（実行中は残す）
GET  /api/v1/agent/memory?scope=market&scope_value=JP&is_active=true
PATCH /api/v1/agent/memory/{memory_id}     # 有効化・無効化・編集
DELETE /api/v1/agent/memory/{memory_id}
GET  /api/v1/agent/cost?period=daily&days=30
GET  /api/v1/agent/critic-stats?days=30    # 却下率と理由の内訳
GET  /api/v1/agent/events                  # SSE によるジョブ進捗のリアルタイム配信
```

`POST /api/v1/agent/jobs/{job_name}/run` の `job_name` は次のいずれか。未知の値は 422。

`collector` / `collector_jp` / `collector_us` / `analyst` / `researcher` / `strategist` / `critic` / `evaluator` / `weekly_review` / `model_retrain` / `garch_refit`

日次 6 ジョブに加え、土曜の `weekly_review`、第1土曜の `model_retrain`、月曜の `garch_refit` を手動でも起動できる。`backtest` はこのパスでは受け付けず、`POST /api/v1/backtests` を使う。

手動実行は `job_runs` を1行だけ作る。API が先に作った行をジョブ本体が再利用する（[08-agent-loop.md](08-agent-loop.md) §9.4）。`GET /api/v1/agent/jobs` に同じ実行が2件出てはいけない。

SSE のイベント形式:

```
event: job_progress
data: {"job_run_id": 1284, "job_name": "collector_jp", "phase": "prices",
       "completed": 42, "total": 61, "eta_sec": 228}

event: job_finished
data: {"job_run_id": 1284, "status": "partial", "duration_sec": 412,
       "failed_steps": ["tdnet"]}

event: alert
data: {"severity": "warning", "category": "cost",
       "title_ja": "LLMの日次予算の80%に達しました"}
```

### 2.9 ポートフォリオ・売買日誌

```
GET    /api/v1/portfolio
GET    /api/v1/portfolio/positions
GET    /api/v1/portfolio/performance?range=1y
GET    /api/v1/trades?limit=100&offset=0
POST   /api/v1/trades
PATCH  /api/v1/trades/{trade_id}
DELETE /api/v1/trades/{trade_id}
POST   /api/v1/trades/import               # CSV インポート
GET    /api/v1/trades/analysis             # 推奨連動の実績分析
```

```json
// POST /api/v1/trades
{
  "ticker": "7203", "market": "JP",
  "side": "buy", "quantity": 100, "price": 3125.0, "fee": 275.0,
  "currency": "JPY", "executed_at": "2026-08-22T00:15:00Z",
  "broker": "楽天証券", "account_type": "特定",
  "linked_rec_id": "01J8XKQ3M4N5P6R7S8T9V0W1X2",
  "thesis_ja": "上方修正と割安さを評価。北米の競争環境は懸念だが為替の追い風が上回ると判断",
  "emotion_tag": "confident",
  "exit_plan_ja": "3,420円で半分、2,890円割れで全部撤退"
}
```

`GET /api/v1/trades/analysis` は「推奨の質」と「実行の質」を分離して返す。

```json
{
  "data": {
    "recommendation_quality": {
      "n_recommendations": 214, "hit_rate": 0.542,
      "avg_excess_return": 0.0081,
      "by_conviction": {"low": 0.51, "medium": 0.56, "high": 0.61},
      "monotonic": true,
      "note_ja": "確信度が高いほど的中率が高く、確信度の付け方は妥当です"
    },
    "execution_quality": {
      "n_trades": 42, "n_from_recommendation": 31, "n_discretionary": 11,
      "hit_rate_from_rec": 0.581, "hit_rate_discretionary": 0.364,
      "avg_slippage_vs_ref_bps": 18.4,
      "avg_holding_days": 24.1, "planned_holding_days": 20.0,
      "by_emotion_tag": {"confident": 0.61, "fomo": 0.29, "fearful": 0.44, "neutral": 0.55},
      "note_ja": "fomo タグの取引の的中率が29%と著しく低く、この心理状態での売買を控えることが最も効果的な改善点です"
    }
  }
}
```

**`by_emotion_tag` の分析が実用上最も価値がある可能性が高い。** ツールの推奨の質より、自分の実行の癖の方が成績への影響が大きいことが多い。

### 2.10 ウォッチリスト・設定・アラート

```
GET    /api/v1/watchlist?list_name=default
POST   /api/v1/watchlist
DELETE /api/v1/watchlist/{market}/{ticker}
GET    /api/v1/settings
PATCH  /api/v1/settings
GET    /api/v1/alerts?is_read=false&limit=50
POST   /api/v1/alerts/{alert_id}/read
POST   /api/v1/alerts/read-all
GET    /api/v1/system/health
GET    /api/v1/system/freshness
POST   /api/v1/system/backup
```

`POST /api/v1/system/backup` がバックアップ起動の正である。画面仕様
（[ui/screens/10-settings.md](ui/screens/10-settings.md)）も同じパスを参照する。
食い違う場合は本節のパスとフィールド名を優先する。実装は
`services/agent/jobs/backup.py`（[11-security-ops.md](11-security-ops.md) §4）。

- メソッド: `POST`
- パス: `/api/v1/system/backup`
- クエリ / ボディ: なし
- レスポンス: Envelope。`data` はジョブ開始時点の確認（実ファイルはバックグラウンドで書く）

```json
// POST /api/v1/system/backup
{
  "data": {
    "ok": true,
    "job_name": "backup",
    "job_run_id": 42,
    "status": "running",
    "backup_dir": "/home/user/ai-stock/backups",
    "message_ja": "バックアップを開始しました。"
  },
  "warnings": [],
  "meta": {
    "as_of": "2026-08-30",
    "computed_at": "2026-08-29T18:00:00Z",
    "data_freshness": []
  }
}
```

バックアップ先は設定キー `backup_dir`（環境変数 `BACKUP_DIR`、既定は
`data_dir` の親配下 `backups/`）。生成物は `{BACKUP_DIR}/{YYYYMMDD}_{HHMMSS}/`
で、`state.sqlite`（sqlite3 backup API）、`warehouse/`（DuckDB `EXPORT DATABASE`）、
`raw/`、`config/` を含む。保持は日次7・週次（日曜）4・月次6。
スケジュールは毎日 JST 03:00（[08-agent-loop.md](08-agent-loop.md) §2）。


```json
// PATCH /api/v1/settings
{"ui.direction_colors": "jp", "llm.daily_cap_usd": 1.5, "llm.kill_switch": false}
```

`GET /api/v1/system/health`:

```json
{
  "data": {
    "status": "degraded",
    "components": [
      {"name": "duckdb",  "status": "ok"},
      {"name": "sqlite",  "status": "ok"},
      {"name": "lancedb", "status": "ok"},
      {"name": "scheduler", "status": "ok", "next_run": "2026-08-23T09:30:00Z"},
      {"name": "jquants", "status": "ok",  "last_success": "2026-08-22T09:31:00Z"},
      {"name": "tdnet",   "status": "failed", "last_success": "2026-08-19T09:31:00Z",
       "message_ja": "3日連続で取得に失敗しています"},
      {"name": "llm",     "status": "capped", "spent_today_usd": 1.02}
    ],
    "disk": {"data_dir_gb": 38.2, "free_gb": 142.8},
    "uptime_sec": 184320
  }
}
```

## 3. Pydantic スキーマの共有

`packages/schemas` に Pydantic モデルを置き、FastAPI のレスポンスモデルとして使う。TypeScript 型は OpenAPI から生成する。

```bash
# apps/web の package.json スクリプト
"gen:api": "openapi-typescript http://localhost:8000/api/v1/openapi.json -o lib/api-types.ts"
```

**この生成を CI で実行し、差分があれば失敗させる。** API を変えたのにフロントの型を更新し忘れる事故を防ぐ。

主要な共有モデル:

```python
class Meta(BaseModel):
    as_of: date
    computed_at: datetime
    data_freshness: list[DataFreshness]

class Warning_(BaseModel):
    code: str
    message_ja: str
    severity: Literal["info", "warning", "error"]
    source: str | None = None
    section: str | None = None

class Envelope[T](BaseModel):
    data: T
    warnings: list[Warning_] = []
    meta: Meta
```

すべてのレスポンスを `Envelope` で包む。フロント側は `warnings` を一律で表示する共通コンポーネントを持てばよい。

## 4. キャッシュとパフォーマンス

| エンドポイント | キャッシュ | TTL |
| --- | --- | --- |
| `/dashboard` | サーバ側メモリ | 5分 |
| `/recommendations` | サーバ側メモリ | 5分 |
| `/scores`, `/screener` | なし（クエリが多様） | - |
| `/stocks/{}/prices` | HTTP `Cache-Control: max-age=300` | 5分 |
| `/documents/{}/file` | HTTP `Cache-Control: max-age=31536000, immutable` | 1年（資料は不変） |
| `/documents/{}/summary` | サーバ側 DB キャッシュ | 永続 |
| `/fx/{}` | サーバ側メモリ | 5分 |
| `/system/health` | なし | - |
| `/system/backup` | なし | - |

TanStack Query 側の設定:

```ts
// staleTime を長めにする。日次バッチのデータなので頻繁な再取得は不要
const defaultOptions = {
  queries: {
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    retry: 2,
    refetchOnWindowFocus: false,   // モバイルでの無駄な通信を避ける
  },
};
```

重いクエリ（スクリーナー、バックテスト）は事前計算せず、その場で DuckDB に発行する。**DuckDB への接続は読み取り専用**（`read_only=True`）にし、agent プロセスの書き込みと競合しないようにする。

## 5. Phase B での認証

Phase A では認証を持たない（Tailscale の tailnet 内のみ到達可能）。Phase B でクラウドに出す際に追加する。

| 方式 | 適用 |
| --- | --- |
| パスキー（WebAuthn） | 単一利用者向け。パスワードレスで最も安全 |
| Bearer トークン | API 直叩き用（長期トークンを1つ発行） |

認証ミドルウェアを追加するだけで済むよう、**すべてのエンドポイントを `Depends(get_current_user)` を差し込める形で書く**（Phase A では常に固定ユーザーを返すダミー実装）。

```python
# services/api/deps.py
async def get_current_user(request: Request) -> User:
    if settings.auth_mode == "none":
        return User(id="local", name="local")     # Phase A
    return await verify_token(request)             # Phase B
```

## 6. 参照

- データモデル: [03-data-model.md](03-data-model.md)
- エージェントループとスケジュール: [08-agent-loop.md](08-agent-loop.md) §2
- PWA とモバイル配信: [10-mobile-pwa.md](10-mobile-pwa.md)
- バックアップ方式と保持世代: [11-security-ops.md](11-security-ops.md) §4
- 画面仕様: [ui/](ui/)（設定画面の Data source は本節の `POST /api/v1/system/backup` を正とする）
