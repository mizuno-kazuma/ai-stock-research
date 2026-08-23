---
name: add-analysis-factor
description: 新しい特徴量（ファクター）や予測モデルを追加・変更する手順と、リーク（未来情報の混入）検証チェックリスト。特徴量の as_of 定義、セクター中立化、欠損値の扱い、Purged Walk-Forward での検証、Rank IC の妥当性確認までを扱う。新ファクターの追加、既存ファクターの定義変更、予測モデルの差し替え、Rank IC が急に改善したときの検証に使う。
---

# ファクター・予測モデルの追加

このスキルの目的の半分は「追加する」ことだが、もう半分は**追加した結果が良すぎたときに疑う**こと
にある。Rank IC が 0.10 を超えたら成果ではなくリークを疑う。ここを飛ばすと、実運用で再現しない
バックテストの上に推奨を組み上げてしまう。

関連仕様: [04-analysis-engine.md](../../../docs/04-analysis-engine.md)、
[05-scoring-screening.md](../../../docs/05-scoring-screening.md)、
[12-testing-validation.md](../../../docs/12-testing-validation.md)

## 手順

### 1. 仕様を先に書く

コードより先に、以下を `docs/04-analysis-engine.md` に追記できる形で確定させる。

| 項目 | 例 |
| --- | --- |
| ファクターID | `rev_guidance_op_3m` |
| 日本語ラベル | 予想改定（営業利益・3ヶ月） |
| 所属グループ | `revision` |
| 定義（数式） | `(op_forecast_t - op_forecast_{t-63d}) / abs(op_forecast_{t-63d})` |
| 入力データ | `financials.op_forecast`（`filed_at` 基準） |
| `as_of` 定義 | 「その日の取引開始前に確定していること」を満たす最終営業日 |
| 符号の向き | 大きいほど良い（正の値が上昇要因） |
| 欠損時の扱い | `NULL`（ゼロ埋め禁止） |
| 想定される Rank IC | 0.01 - 0.03 |
| 期待する経済的根拠 | 会社予想の改定は将来のリターンに先行しやすい |

**経済的根拠を書けないファクターは追加しない。** 書けない場合、それは過去データへの当てはめで
あって、将来に効く理由がない。

### 2. `as_of` の定義を確定する（最重要）

ここを間違えるとリークする。判断基準は「その日の朝、注文を出す前に、この値を知り得たか」。

| データ種別 | 使える最新の時点 | 注意 |
| --- | --- | --- |
| 日本株の価格 | 前営業日の終値 | 当日終値は使えない |
| 日本の開示（15時前） | 当日から利用可能 | |
| 日本の開示（15時以降） | 翌営業日から利用可能 | 15時ルール。忘れやすい |
| 米国の開示 | `filed_at` の翌取引日から | 時差の扱いを固定する |
| 財務データ | `filed_at` 基準 | 期末日基準は禁止 |
| マクロ統計 | `vintage_date` 基準 | 改定後の値を過去に遡って使わない |
| 参考現在値（`prices_live`） | **モデルでは使用禁止** | 表示専用 |

実装では `pit_guard` を通す。生のテーブルを直接参照しない。

```python
# 正しい
df = pit_guard(financials, as_of=as_of, timestamp_col="filed_at")

# 誤り（未来の修正再表示を拾う）
df = financials[financials.fiscal_period <= period]
```

### 3. 特徴量を実装

`packages/core/features/` に追加する。

- 入力は `as_of` を必須引数とする。デフォルト値を持たせない。
- 出力は `(ticker, as_of, feature_name, value)` の縦長形式。
- 欠損は `None` を返す。`0`、`-1`、平均値で埋めてはいけない。
- 負の値が意味を持たない指標（PER など）は `None` を返す。
  `earnings_yield`（益回り）のように連続で符号が意味を持つ形に変換して使う。
- 極端値は winsorize（両側1%）してから標準化する。

### 4. セクター中立化と標準化

グループスコアに載せる場合は、セクター内で中央値・MAD による z-score に変換する。平均・標準偏差
ではなく中央値・MAD を使うのは、少数の外れ値でセクター全体の順位が壊れるのを防ぐため。

```python
def sector_neutral_z(values: pd.Series, sectors: pd.Series) -> pd.Series:
    def _z(g: pd.Series) -> pd.Series:
        med = g.median()
        mad = (g - med).abs().median()
        if mad == 0 or pd.isna(mad):
            return pd.Series(np.nan, index=g.index)
        return ((g - med) / (1.4826 * mad)).clip(-3, 3)
    return values.groupby(sectors).transform(_z)
```

セクター内の有効サンプルが5銘柄未満のときは `NaN` を返す。少数セクターで無意味な z-score を
作ってはいけない。

### 5. `feature_version` を上げる

既存ファクターの定義を変更した場合、`feature_version` を上げ、変更日以降のみ新定義を使う。過去の
特徴量を新定義で上書き再計算すると、過去の推奨実績とスコアの対応が壊れ、Evaluator の学習が汚染
される。

```
v3: 2026-06-01 以降。rev_guidance_op_3m を追加
v4: 2026-09-01 以降。mom_12m を直近1ヶ月除外に変更
```

### 6. 相関を確認

既存ファクターとの相関が 0.8 を超える場合、追加する価値はほぼない。LightGBM の重要度が分散し、
解釈も難しくなる。相関行列を確認し、`docs/04-analysis-engine.md` に記録する。

### 7. Purged Walk-Forward で検証

**唯一許可される検証手法**。`KFold`、`ShuffleSplit`、`train_test_split` のランダム分割は禁止。
`T-LEAK-01` が CI で検出する。

```python
cv = PurgedWalkForwardCV(
    n_splits=8,
    train_window_days=252,
    test_window_days=42,
    purge_days=20,        # 予測ホライズンと同じ
    embargo_days=5,
    expanding=True,
)
```

`purge_days` は予測ホライズンと同じにする。H20 の予測で purge が 5日だと、学習期間の末尾の
ラベルが検証期間と重なりリークする。

### 8. 評価と妥当性の判断

| 指標 | 現実的な水準 | 疑うべき水準 |
| --- | --- | --- |
| 単一ファクターの Rank IC | 0.005 - 0.02 | 0.05 超 |
| 合成スコアの Rank IC | 0.02 - 0.04 | 0.10 超 |
| 分位単調性 | Q1 < Q3 < Q5 が概ね成立 | 完全に単調で spread が5%超 |
| 分割間のばらつき | IC標準偏差 0.005 - 0.015 | 全分割で符号が揃い分散が極小 |

**良すぎる結果が出たら、まず [references/leak-checklist.md](references/leak-checklist.md) を
上から順に確認する。** 経験的に、良すぎる結果の原因は9割がリークで、1割が偶然。新しい発見である
可能性はその後に検討する。

### 9. `factors.yaml` とグループ重みを更新

```yaml
groups:
  revision:
    label_ja: 予想改定
    features:
      - id: rev_guidance_op_3m
        weight_within_group: 0.5
        direction: 1
      - id: rev_guidance_sales_3m
        weight_within_group: 0.3
        direction: 1
      - id: rev_analyst_dispersion
        weight_within_group: 0.2
        direction: -1
```

グループ間の重み（`group_weights`）は手で変えず、Evaluator の提案をモデルラボで承認する経路に
乗せる。恣意的な重み調整は多重検定バイアスを増やすだけで、DSR で必ず罰される。

### 10. テストを追加

`T-LEAK`、`T-PIT`、`T-STAT`、`T-DQ` を追加する。詳細は
[references/leak-checklist.md](references/leak-checklist.md) と
[docs/12-testing-validation.md](../../../docs/12-testing-validation.md)。

### 11. UI とドキュメントを更新

- `docs/ui/screens/04-screener.md` のフィルタ項目表
- `docs/ui/components.md` の reason code 一覧（新しい理由コードを作った場合）
- `docs/ui/sample-data.json` の `factors` と `model_health.feature_importance`
- `docs/04-analysis-engine.md` の特徴量定義
- `docs/03-data-model.md` の `features_daily` の説明

## 完了条件

- [ ] 経済的根拠が1文で書ける
- [ ] `as_of` 定義が明文化され、`pit_guard` を通している
- [ ] 欠損が `NULL` で保持され、ゼロ埋めしていない
- [ ] 既存ファクターとの相関が 0.8 未満、または超える理由が記録されている
- [ ] Purged Walk-Forward で検証し、purge が予測ホライズンと一致している
- [ ] Rank IC が現実的な水準にある、または良すぎる理由が検証済み
- [ ] `T-LEAK-04`（合成データ）が引き続きゼロ近傍
- [ ] `feature_version` を上げ、過去を再計算していない
- [ ] `factors.yaml` とドキュメント、UI 仕様が更新されている

## 予測モデルを差し替える場合の追加項目

- ハイパーパラメータ探索の**試行回数を `model_runs.n_trials` に必ず記録する**。DSR の計算に使う。
  記録しないと、そのモデルのバックテストは有意性を判定できず、使えない。
- 分位モデル（0.1 / 0.5 / 0.9）を必ず併せて学習する。点推定だけのモデルは UI に出せない。信頼
  区間なしの予測値表示は仕様違反。
- 信頼区間が異常に狭い（H20 で幅が 2% 未満など）場合はリークを疑う。`T-LEAK-04` を再実行する。
- 旧モデルは `status: archived` として残す。削除しない。過去の推奨がどのモデルから出たかを追跡
  できなくなる。
