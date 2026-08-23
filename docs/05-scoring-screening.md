# 05. スコアリング・スクリーニング・推奨生成

## 1. 全体の流れ

```
features_daily
     │
     ├─ (1) 外れ値処理（winsorize）
     ├─ (2) セクター中立化 z-score
     ├─ (3) ファクターグループへの集約
     ├─ (4) 重み付き合成 → quant_score (0-100)
     │
     ├─ (5) LightGBM 予測（ml_pred_h5 / h20 + 信頼区間）
     │
     ├─ (6) LLM 定性オーバーレイ → qual_score (-1..+1)
     │
     ├─ (7) total_score の算出
     │
     ├─ (8) 推奨候補の選抜（ユニバースフィルタ + リスク制約）
     ├─ (9) 推奨カードの生成（reason codes / thesis / bear case / 引用）
     └─(10) Critic による検証 → 承認・修正・却下
```

(1)-(4) は Analyst ジョブ、(5) も Analyst、(6) は Researcher、(7)-(9) は Strategist、(10) は Critic が担う（[08-agent-loop.md](08-agent-loop.md)）。

## 2. 前処理

### 2.1 Winsorize（外れ値のクリップ）

```python
def winsorize(s: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    """各日・各市場内で分位点クリップする。除外ではなくクリップにするのは、
    外れ値銘柄を落とすとユニバースが日ごとに変わってしまうため。"""
    lo, hi = s.quantile(lower), s.quantile(upper)
    return s.clip(lo, hi)
```

適用対象は比率系のすべての特徴量。`per` のような分母が小さくなると爆発する指標では特に重要である。1%/99% を既定とし、`packages/core/config/factors.yaml` で変更可能にする。

### 2.2 セクター中立化 z-score

```python
def sector_neutral_zscore(
    df: pd.DataFrame, col: str, *, sector_col: str = "sector_code",
    min_sector_size: int = 8,
) -> pd.Series:
    """同一 as_of・同一セクター内で z-score を取る。
    セクターの構成銘柄が min_sector_size 未満の場合は市場全体で計算する
    （小サンプルの z-score は不安定なため）。
    """
    g = df.groupby([sector_col])[col]
    sizes = g.transform("count")
    z_sector = (df[col] - g.transform("median")) / g.transform(mad_std)
    z_market = (df[col] - df[col].median()) / mad_std(df[col])
    return z_sector.where(sizes >= min_sector_size, z_market).clip(-3, 3)
```

**平均・標準偏差ではなく中央値・MAD（中位絶対偏差）を使う。** 金融データの分布は裾が重く、平均と標準偏差は外れ値に引っ張られる。

```python
def mad_std(s: pd.Series) -> float:
    """MADから標準偏差相当量を推定する。1.4826 は正規分布での換算係数。"""
    return 1.4826 * (s - s.median()).abs().median()
```

**セクター中立化を行う理由**: 業種によってPERやROEの水準が構造的に違う。銀行と製薬のPERを直接比べても意味がない。セクター内での相対位置を見ることで、業種要因ではなく個別要因を捉える。

セクター定義: 日本株は東証33業種コード、米国株は GICS セクター（11分類）。GICSデータが無料で入手できない場合は Finnhub のセクター分類、または SIC コードからのマッピングで代替する `[要検証]`。

### 2.3 符号の統一

すべての z-score を「大きいほど良い」向きに揃える。

| ファクター | 元の特徴量 | 符号 |
| --- | --- | --- |
| バリュー | `earnings_yield`, `fcf_yield`, `dividend_yield` | そのまま（大きいほど割安） |
| バリュー | `pbr`, `psr`, `ev_ebitda` | **反転**（小さいほど割安） |
| モメンタム | `mom_12_1`, `price_to_52w_high` | そのまま |
| クオリティ | `roe`, `roic`, `operating_margin`, `interest_coverage` | そのまま |
| クオリティ | `debt_to_equity`, `accruals_ratio` | **反転** |
| 成長 | `revenue_growth_yoy`, `eps_growth_yoy` | そのまま |
| 低ボラ | `realized_vol_60d`, `max_drawdown_252d`, `beta_market_252d` | **反転** |
| 改定 | `forecast_revision_direction`, `forecast_revision_magnitude` | そのまま |

符号の定義は `packages/core/config/factors.yaml` に一元化する。コード中に符号反転を散らすと必ずどこかで間違える。

## 3. ファクターグループへの集約

`factors.yaml` の構造:

```yaml
factor_groups:
  value:
    members:
      - {feature: earnings_yield, sign: 1,  weight: 0.30}
      - {feature: fcf_yield,      sign: 1,  weight: 0.25}
      - {feature: pbr,            sign: -1, weight: 0.20}
      - {feature: ev_ebitda,      sign: -1, weight: 0.15}
      - {feature: dividend_yield, sign: 1,  weight: 0.10}
  momentum:
    members:
      - {feature: mom_12_1,          sign: 1, weight: 0.45}
      - {feature: mom_6_1,           sign: 1, weight: 0.25}
      - {feature: price_to_52w_high, sign: 1, weight: 0.20}
      - {feature: dist_from_ma200,   sign: 1, weight: 0.10}
  quality:
    members:
      - {feature: roic,             sign: 1,  weight: 0.30}
      - {feature: roe,              sign: 1,  weight: 0.25}
      - {feature: operating_margin, sign: 1,  weight: 0.20}
      - {feature: accruals_ratio,   sign: -1, weight: 0.15}
      - {feature: debt_to_equity,   sign: -1, weight: 0.10}
  growth:
    members:
      - {feature: eps_growth_yoy,     sign: 1, weight: 0.35}
      - {feature: revenue_growth_yoy, sign: 1, weight: 0.35}
      - {feature: revenue_cagr_3y,    sign: 1, weight: 0.30}
  lowvol:
    members:
      - {feature: realized_vol_60d,  sign: -1, weight: 0.40}
      - {feature: max_drawdown_252d, sign: -1, weight: 0.35}
      - {feature: beta_market_252d,  sign: -1, weight: 0.25}
  revision:
    members:
      - {feature: forecast_revision_direction, sign: 1, weight: 0.60}
      - {feature: forecast_revision_magnitude, sign: 1, weight: 0.40}
```

グループ内の集約は「メンバーの z-score の重み付き平均を取り、再度 z-score 化」する。

```python
group_z = zscore(sum(sign_i * w_i * z_i for i in members))
```

グループ内で欠損があるメンバーは重みを再正規化して除外する。ただし**有効メンバーが半分未満のグループは `NULL`** とする（残った1指標でグループを代表させない）。

## 4. quant_score の算出

### 4.1 グループ重み

```yaml
group_weights:
  JP:
    H5:  {value: 0.15, momentum: 0.30, quality: 0.15, growth: 0.10, lowvol: 0.15, revision: 0.15}
    H20: {value: 0.25, momentum: 0.20, quality: 0.20, growth: 0.15, lowvol: 0.10, revision: 0.10}
  US:
    H5:  {value: 0.10, momentum: 0.35, quality: 0.20, growth: 0.15, lowvol: 0.15, revision: 0.05}
    H20: {value: 0.20, momentum: 0.25, quality: 0.25, growth: 0.20, lowvol: 0.05, revision: 0.05}
```

**この初期値は「妥当そうな値」であり、根拠のある最適値ではない。** ここを明記しておくことが重要である。Evaluator が実績に基づいて更新し、`factor_weights` テーブルに新しい `weight_set_id` として記録される（§8）。

H5（短期）でモメンタムの重みを大きく、H20（中期）でバリューを大きくしているのは、効果の発現タイムスパンが異なるという一般的な理解に基づく。これも検証対象である。

### 4.2 合成と正規化

```python
composite = sum(gw[g] * group_z[g] for g in groups)   # 概ね -3..+3
quant_score = 50 + 50 * np.clip(composite / 2.5, -1, 1)  # 0..100
quant_rank = composite.rank(ascending=False, method="min")
quant_percentile = composite.rank(pct=True)
```

0-100 に正規化するのは表示のためである。**内部の計算・順位付けには正規化前の `composite` を使う**（クリップにより情報が失われるため）。

### 4.3 グループ重みの正規化

`group_weights` の合計が 1.0 でない場合は起動時にエラーにする。また、欠損グループがある銘柄では有効グループの重みを再正規化する。ただし有効グループが3つ未満の銘柄はスコアリング対象外とする。

## 5. ML 予測の統合

`ml_pred_h5` / `ml_pred_h20`（[04-analysis-engine.md](04-analysis-engine.md) §3）は `quant_score` とは独立に算出する。両者の関係:

| 用途 | 使うもの |
| --- | --- |
| スクリーナーでの並び替え | `quant_score`（解釈可能で、なぜ上位なのかを説明できる） |
| 推奨候補の選抜 | `quant_score` と `ml_pred` の**両方が上位**であることを条件にする |
| 期待リターンの数値表示 | `ml_pred` + 信頼区間（`quant_score` は期待リターンではないので使わない） |

**両方が上位であることを条件にする理由**: `quant_score` はルールベースで説明可能だが最適化されていない。`ml_pred` は最適化されているが説明が難しい。両者が一致する銘柄は「理屈もあり、データにも裏付けがある」ものであり、片方だけで選ぶより頑健である。

```python
def is_candidate(row) -> bool:
    return (row.quant_percentile >= 0.85          # 上位15%
            and row.ml_pred_h20 > 0               # 期待超過リターンが正
            and row.ml_pred_h20_lo > -0.05)       # 下限が -5% より上（極端な下方リスクを除外）
```

## 6. LLM 定性オーバーレイ

### 6.1 qual_score の定義

`-1.0`（強く否定的）から `+1.0`（強く肯定的）。LLM が開示資料を読んで付与する。詳細なプロンプトは [07-llm-rag.md](07-llm-rag.md)。

| 観点 | 寄与 | 抽出元 |
| --- | --- | --- |
| ガイダンスのトーン | ±0.4 | 決算短信・有報の「経営者による分析」「今後の見通し」 |
| リスク要因の変化 | ±0.2 | 「事業等のリスク」の前期比較。新規リスクの追加は負 |
| 成長ドライバの具体性 | ±0.2 | 定量的な目標があるか、抽象的な表現に留まるか |
| 会計上の懸念 | ±0.2 | 一時要因への依存、引当・のれんの動き、監査意見 |

**重要**: `qual_score` は「LLMが良いと言った」ではなく「開示文書にこう書いてある」の要約でなければならない。すべての寄与に原文引用（`citations`）を必須とする。引用のない寄与は 0 として扱う。

### 6.2 対象銘柄の絞り込み（コスト管理）

全銘柄にLLMを回すとコストが破綻する。以下の優先順で当日の対象を決める。

| 優先度 | 対象 | 上限 |
| --- | --- | --- |
| 1 | 保有銘柄（`positions.is_open = 1`） | 全件 |
| 2 | 当日新規開示があった銘柄（`documents` の新規） | 30件 |
| 3 | ウォッチリスト銘柄 | 全件 |
| 4 | `quant_percentile >= 0.90` の銘柄 | 20件 |
| 5 | 前回のLLM分析から30日以上経過した推奨中の銘柄 | 10件 |

同じ資料への再分析は `document_summaries` のキャッシュで回避される。キャッシュキーは `(doc_id, prompt_hash, input_hash)`。

### 6.3 total_score の算出

```python
def total_score(quant_score: float, qual_score: float | None,
                qual_confidence: float | None) -> float:
    """定性スコアは定量スコアへの調整として作用する（置き換えではない）。"""
    if qual_score is None:
        return quant_score          # LLM分析なしでもスコアは成立する
    # 最大 ±12点の調整。確信度で減衰させる
    adjustment = 12.0 * qual_score * (qual_confidence or 0.5)
    return float(np.clip(quant_score + adjustment, 0, 100))
```

**調整幅を ±12点に限定する理由**: LLMの定性判断が定量スコアを覆すことを避ける。LLMは説明が上手いが、それは正しさとは別である。定量スコアが下位の銘柄がLLMの評価だけで上位に来る経路を作らない。

`qual_score` が `NULL` でもスコアが成立する設計にすることで、LLMのコストキャップに達した日でも機能する（機能縮退）。

## 7. 推奨生成

### 7.1 ユニバースフィルタ

```yaml
universe_filter:
  JP:
    min_adv_20d_jpy: 100_000_000      # 1億円
    min_market_cap_jpy: 30_000_000_000 # 300億円
    exclude_sectors: []
    exclude_recently_listed_days: 250  # 上場1年未満は履歴不足
    max_price_jpy: null
    require_features_complete: true     # n_missing <= 15
  US:
    min_adv_20d_usd: 5_000_000
    min_market_cap_usd: 1_000_000_000
    exclude_otc: true
    exclude_recently_listed_days: 250
```

### 7.2 リスク制約

推奨リストを作る段階で以下を適用する。

| 制約 | 値 | 理由 |
| --- | --- | --- |
| 1日の推奨件数上限 | 10件（設定 `agent.max_recommendations_per_day`） | 情報過多で判断できなくなるのを防ぐ |
| 同一セクターの推奨上限 | 3件 | セクター集中を避ける |
| 既存保有と同一銘柄の重複推奨 | `action='accumulate'` としてのみ許可 | 追加購入の判断材料として提示 |
| 高ボラ銘柄（`realized_vol_60d > 60%`） | `conviction` を1段下げる | |
| 決算発表直前（5営業日以内） | 推奨に「決算前」の警告フラグを立てる | イベントリスクの明示 |
| 市場が高ボラレジーム | 全推奨の `conviction` を1段下げる | [04-analysis-engine.md](04-analysis-engine.md) §5 |

### 7.3 action の決定

| 条件 | action |
| --- | --- |
| `total_score >= 75` かつ `ml_pred_h20 > 0.02` かつ 未保有 | `watch`（新規の注目候補） |
| 上記 かつ 保有中 | `accumulate` |
| 保有中 かつ `total_score <= 35` | `reduce` |
| 保有中 かつ `invalidation` 条件を満たした | `reduce` |
| `total_score <= 25` かつ 未保有 | `avoid`（ウォッチリストにある場合のみ表示） |

`watch` を「買い推奨」と呼ばないのは意図的である。本ツールは判断支援であり、買いを指示しない。UI上のラベルも「注目」「積み増し検討」「縮小検討」「回避」とする。

### 7.4 reason codes

機械可読な短いコードで理由を表す。UIではこれをバッジ表示し、フィルタにも使う。

| コード | 意味 | 発生条件 |
| --- | --- | --- |
| `VAL_CHEAP_VS_SECTOR` | セクター内で割安 | `value_z >= 1.0` |
| `VAL_CHEAP_VS_HISTORY` | 自社の過去水準比で割安 | `per` が過去5年の20パーセンタイル以下 |
| `MOM_STRONG_12M` | 12ヶ月モメンタムが強い | `momentum_z >= 1.0` |
| `MOM_NEAR_52W_HIGH` | 52週高値圏 | `price_to_52w_high >= 0.95` |
| `MOM_ABOVE_MA200` | 200日線上 | `dist_from_ma200 > 0` |
| `QLT_HIGH_ROIC` | 高いROIC | `roic >= 0.12` かつ `quality_z >= 0.5` |
| `QLT_LOW_LEVERAGE` | 低レバレッジ | `debt_to_equity <= 0.3` |
| `QLT_CLEAN_ACCRUALS` | 利益の質が良い | `accruals_ratio <= 0` |
| `GRW_ACCELERATING` | 成長が加速 | 直近YoY > 前四半期YoY |
| `REV_UP_GUIDANCE` | 会社予想の上方修正 | `forecast_revision_direction = +1` |
| `REV_DOWN_GUIDANCE` | 会社予想の下方修正 | `forecast_revision_direction = -1` |
| `VOL_LOW_REGIME` | 低ボラ | `realized_vol_60d` が下位30% |
| `FX_TAILWIND` | 為替が追い風 | `fx_sensitivity_60d` と為替見通しの符号が一致 |
| `FX_HEADWIND` | 為替が逆風 | 上記の逆 |
| `LLM_POSITIVE_GUIDANCE` | 開示文書のトーンが前向き | `guidance_tone = 'positive'` + 引用あり |
| `LLM_NEW_RISK_DISCLOSED` | 新規リスクの開示 | リスク項目の新規追加を検出 |
| `EVENT_EARNINGS_SOON` | 決算発表が近い | 5営業日以内 |
| `DATA_STALE` | データが古い | `latest_as_of` が期待より3営業日以上遅れ |
| `MODEL_LOW_CONFIDENCE` | モデルの直近成績が悪い | 直近20日のRank ICが下位10% |

`DATA_STALE` と `MODEL_LOW_CONFIDENCE` は**ネガティブな情報も reason code として明示する**ためのものである。良い理由だけを並べない。

### 7.5 推奨カードの必須構成要素

`recommendations` テーブル（[03-data-model.md](03-data-model.md) §2.9）の不変条件として強制する。

| 要素 | 必須 | 内容 |
| --- | --- | --- |
| `thesis_ja` | 必須 | 強気論拠。2-4行。数値と引用を含む |
| `bear_case_ja` | **必須（20文字以上）** | 弱気論拠。この推奨が外れるシナリオ |
| `invalidation_ja` | 必須 | 「どうなったらこの見立てを捨てるか」の具体的条件 |
| `reason_codes` | 必須（1件以上） | |
| `conviction` + `conviction_score` | 必須 | |
| `expected_ret` + `_lo` + `_hi` | 必須 | 信頼区間なしは挿入不可 |
| `hit_rate_prior` + `n_prior_samples` | 必須 | 類似条件での過去的中率。`n < 20` なら `conviction = low` に強制 |
| `source_doc_ids` | **必須（1件以上）** | |
| `citations` | **必須（1件以上）** | doc_id + ページ + 原文引用 |
| `data_freshness` | 必須 | 使ったデータの鮮度 |

### 7.6 bear case の生成方針

bear case を「形だけ」にしないため、生成方法を規定する。

1. **定量的な反論**: そのファクターが機能しなかった過去のケースを `recommendation_outcomes` から検索し、「同様の reason code の組み合わせで過去に失敗した事例が n 件ある」と提示する
2. **開示文書からの反論**: RAG で「リスク」「懸念」「不確実性」に関連するチャンクを取得し、LLM に**強気論拠と対立する内容を優先的に**抽出させる
3. **バリュエーションの反論**: 割安と判断した場合、「割安である理由（バリュートラップの可能性）」を検討させる
4. **反対側のファクター**: `quant_score` の構成要素のうち、最も低いグループを明示する（例: 「バリューは上位だがクオリティは下位20%」）

プロンプトでは「bear case を書け」ではなく「**この推奨を却下すべき理由を、開示資料の引用付きで3つ挙げよ**」と指示する。前者は defensive な定型文を生み、後者は具体的な内容を生む。

### 7.7 hit_rate_prior の算出

```sql
-- 類似条件: 同じ市場・同じ horizon・reason_codes の重複が2つ以上
WITH similar AS (
  SELECT o.is_hit, o.excess_return
  FROM recommendations r
  JOIN recommendation_outcomes o ON r.rec_id = o.rec_id
  WHERE r.market = ? AND o.horizon = ?
    AND len(list_intersect(r.reason_codes, ?::VARCHAR[])) >= 2
    AND r.as_of < ?                     -- 未来の実績を使わない
)
SELECT AVG(CAST(is_hit AS DOUBLE)) AS hit_rate,
       COUNT(*) AS n_samples,
       AVG(excess_return) AS avg_excess
FROM similar;
```

`n_samples < 20` の場合は `hit_rate_prior` を親カテゴリ（市場全体）の値にフォールバックし、`conviction` を `low` に強制する。**サンプルが少ないのに高い的中率を表示するのは誤解を招く**ため、母数を必ず併記する（UIでは「的中率 62%（n=34）」の形式）。

運用初期は `recommendation_outcomes` が空である。この期間は `hit_rate_prior = NULL`、`conviction = 'low'` 固定とし、UIには「実績データの蓄積中（推奨開始から n 日）」と表示する。**運用開始直後に高い確信度を出さない**ことが重要である。

## 8. Evaluator による重み更新

詳細は [08-agent-loop.md](08-agent-loop.md) §7。ここではスコアリング側の仕様のみ記す。

### 8.1 更新方法

```python
def refit_weights(outcomes: pd.DataFrame, current: dict[str, float]) -> WeightProposal:
    """各ファクターグループのz-scoreを説明変数、実現超過リターンを目的変数として
    Ridge回帰を行い、係数を正規化して新しい重みとする。
    """
    X = outcomes[["value_z","momentum_z","quality_z","growth_z","lowvol_z","revision_z"]]
    y = outcomes["excess_return"]
    # 正則化を強めにかける。サンプルが少ないため素朴なOLSは不安定
    model = Ridge(alpha=10.0, positive=True).fit(X, y)  # 負の重みを許さない
    raw = model.coef_
    if raw.sum() <= 0:
        return WeightProposal(rejected=True, reason="全係数が非正。更新しない")
    new = raw / raw.sum()
    # 現行からの変化を制限する（1回で大きく動かさない）
    blended = 0.7 * np.array(list(current.values())) + 0.3 * new
    return WeightProposal(weights=blended / blended.sum(), ...)
```

**制約**:

- `positive=True` で負の重みを禁止する。「バリューが低い方が良い」のような符号反転は、サンプル不足による偶然である可能性が高い
- 現行重みとのブレンド（70:30）により、1回の更新で大きく動かさない
- **アウトオブサンプルICが現行を上回らない限り自動適用しない**（既定は承認制。`agent.auto_activate_weights = false`）
- 最低サンプル数 200件（推奨×ホライズン）に達するまで更新を行わない

### 8.2 承認フロー

1. Evaluator が新しい `weight_set_id` を `factor_weights` に `is_active=0` で挿入する
2. モデルラボ画面に「重み更新の提案」として表示する（現行との比較、IC、想定される順位変動の上位10銘柄）
3. 利用者が承認すると `is_active=1` に切り替わり、現行は `deactivated_at` が設定される
4. 切り替え後30日間、新旧両方の重みでスコアを計算し、実績を比較する（A/Bの記録）

## 9. スクリーナー

### 9.1 フィルタ可能な項目

| カテゴリ | 項目 |
| --- | --- |
| 基本 | 市場（JP/US）、セクター、時価総額、売買代金 |
| スコア | `quant_score`、各グループのz-score、`total_score`、`ml_pred_h5/h20` |
| バリュエーション | PER、PBR、EV/EBITDA、配当利回り、FCF利回り |
| クオリティ | ROE、ROIC、営業利益率、D/E |
| 成長 | 売上成長率、EPS成長率、3年CAGR |
| モメンタム | 各期間リターン、52週高値比、200日線乖離 |
| ボラティリティ | 実現ボラ、GARCHボラ、最大DD、ベータ |
| イベント | 直近の開示種別、決算発表予定日までの日数、会社予想改定 |
| 保有状況 | 保有中 / ウォッチリスト / 推奨履歴あり |
| 品質 | データ欠損数、`quality_flags` |

### 9.2 プリセット

| プリセット名 | 条件 |
| --- | --- |
| 割安クオリティ | `value_z >= 1.0` かつ `quality_z >= 0.5` かつ `roic >= 0.10` |
| 上方修正モメンタム | `forecast_revision_direction = 1` かつ `momentum_z >= 0.5` |
| 円安メリット | `fx_sensitivity_60d >= 0.3` かつ 為替見通しが円安方向 |
| 円高メリット | `fx_sensitivity_60d <= -0.3` かつ 為替見通しが円高方向 |
| 低ボラ配当 | `lowvol_z >= 0.5` かつ `dividend_yield >= 0.03` |
| 決算前チェック | 決算発表まで5営業日以内 かつ 保有中またはウォッチリスト |
| 高成長 | `revenue_growth_yoy >= 0.15` かつ `eps_growth_yoy >= 0.15` |
| バリュートラップ注意 | `value_z >= 1.5` かつ `quality_z <= -0.5`（割安だが質が低い） |

「バリュートラップ注意」のような**警戒側のプリセットを用意する**ことが、スクリーナーを「買い候補を探す道具」から「検討材料を集める道具」に変える。

### 9.3 実装上の注意

- スクリーナーのクエリは DuckDB に対して発行する。フィルタ条件はサーバ側で SQL に組み立てる（`packages/core/storage/screener_query.py`）
- 条件の組み合わせ数が多いため、事前計算はしない。ただし `scores_daily` と `features_daily` に適切なインデックスを張る
- 結果は最大500件で打ち切り、それを超える場合は「条件を絞ってください」と表示する
- **フィルタ条件を保存できるようにする**（`settings` の `screener.saved_filters`）。毎回組み立て直すのは実用的でない

## 10. 参照

- 特徴量の定義: [04-analysis-engine.md](04-analysis-engine.md)
- LLM プロンプト設計: [07-llm-rag.md](07-llm-rag.md)
- Evaluator の詳細: [08-agent-loop.md](08-agent-loop.md)
- 画面仕様: [ui/screens/02-recommendations.md](ui/screens/02-recommendations.md), [ui/screens/04-screener.md](ui/screens/04-screener.md)
