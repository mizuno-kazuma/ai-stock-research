# リーク検証チェックリスト

Rank IC やバックテスト成績が想定より良いとき、**上から順に**確認する。経験的に上にあるものほど
頻度が高い。1件見つかったらそこで止めず、最後まで確認する。リークは重複して存在することが多い。

## レベル1: 定番のリーク（最も頻度が高い）

### 1.1 交差検証の分割方法

```bash
rg -n "KFold|ShuffleSplit|train_test_split|StratifiedKFold|cross_val_score" packages/ services/
```

時系列データでランダム分割すると、未来のサンプルで学習して過去を予測することになる。`T-LEAK-01`
で CI 検出しているが、新規コードで持ち込まれることがある。許可されるのは
`PurgedWalkForwardCV` のみ。

### 1.2 purge / embargo の不足

```python
# 確認: purge_days は予測ホライズンと一致しているか
assert cv.purge_days >= horizon_days
```

H20（20営業日先を予測）のラベルは、起点から20営業日後まで確定しない。学習期間の末尾20営業日分の
ラベルは検証期間と重なる。purge がこれより短いと必ずリークする。

embargo は自己相関の残りを切るために追加で5営業日。

### 1.3 参考現在値（`prices_live`）の混入

```bash
rg -n "prices_live" packages/core/features/ packages/core/models/ services/agent/
```

`prices_live` は 15分遅延の表示専用データで、リサーチ用の `prices_daily` とは系列が異なる。
特徴量・モデル・バックテストのどこからも参照してはいけない。`T-LEAK-02` が検出する。

### 1.4 財務データを期末日基準で参照

```bash
rg -n "fiscal_period\s*<=|period_end\s*<=" packages/
```

期末日基準で参照すると、修正再表示された後の数値を過去の日付で使ってしまう。`financials_pit`
ビューまたは `pit_guard` を経由すること。

### 1.5 15時ルールの適用漏れ

日本の開示は15時以降に出るものが多い。当日15:04 に出た開示を当日の特徴量に入れると、当日の
引け前に知り得なかった情報でその日のリターンを予測することになる。

```python
def available_from(filed_at: datetime) -> date:
    """開示が特徴量に使えるようになる営業日を返す。"""
    jst = filed_at.astimezone(JST)
    if jst.time() >= time(15, 0):
        return next_business_day(jst.date())
    return jst.date()
```

## レベル2: 集計と正規化に潜むリーク

### 2.1 全期間の統計量で標準化

```python
# 誤り: 全期間の平均・標準偏差を使うと未来の情報が入る
df["z"] = (df.value - df.value.mean()) / df.value.std()

# 正しい: 各日のクロスセクション内で標準化する
df["z"] = df.groupby("as_of").value.transform(sector_neutral_z)
```

これは最も見つけにくいリークの一つ。数値上は「わずかに良くなる」程度なので、リークと気づかずに
放置されやすい。

### 2.2 欠損値を全期間の平均で補完

同じ理由でリークする。欠損は `NULL` のまま LightGBM に渡す。LightGBM は欠損を扱える。

### 2.3 winsorize の閾値を全期間から算出

各日のクロスセクション内で分位点を取る。全期間の分位点を使うと未来が入る。

### 2.4 ユニバース選択のリーク（サバイバルバイアス）

現在上場している銘柄だけで過去を検証すると、上場廃止・経営破綻した銘柄が除外され、成績が
実際より良く出る。`securities` テーブルの `valid_from` / `valid_to` を使い、各時点で実在した
銘柄のみを対象にする。

```python
universe = securities[(securities.valid_from <= as_of) &
                      ((securities.valid_to.isna()) | (securities.valid_to > as_of))]
```

### 2.5 セクター分類の変更

セクターコードは変わる。現在のセクター分類で過去を中立化すると、後から分かったセクター変更を
使っていることになる。履歴付きのセクター分類を参照する。

## レベル3: バックテスト固有のリーク

### 3.1 エントリータイミング

シグナル発生日の終値で約定させると、その日の終値を知った上でその日に入れることになる。
**翌営業日の始値**でエントリーする。`T-LEAK-05` が検出する。

```python
# 正しい
entry_price = prices.loc[next_business_day(signal_date), "open"]
```

### 3.2 コストの省略

`fee_bps` / `slippage_bps` / `max_turnover_pct` は必須引数で、デフォルト値を持たせない。
`T-LEAK-06` がデフォルト値の存在を検出する。コスト前の成績は必ず良く見えるので、コスト前後の
両方を出力し、UI にはコスト後を主として出す。

### 3.3 出来高を超える約定

流動性の低い銘柄で、当日出来高の数割を約定させると現実には成立しない。1日の約定量を出来高の
5%以内などに制限する。制限しない場合、小型株で非現実的な成績が出る。

### 3.4 リバランス日の未来情報

月次リバランスで「月末時点のスコア」を使う場合、月末のスコアはその日の終値に依存する。翌営業日の
始値で入るなら整合するが、月末の終値で入るなら不整合。

### 3.5 生存する戦略だけを報告

パラメータを変えて何度も試し、良かったものだけを報告するのが最も多い実質的なリーク。
**試行回数を記録し DSR で罰する**ことで構造的に防ぐ。`model_runs.n_trials` と
`backtest_runs.n_trials` を必ず埋める。

## レベル4: 決定的な検証

### 4.1 合成ランダムデータでのゼロ確認（`T-LEAK-04`）

最も強力な検証。完全にランダムな価格系列と特徴量を生成し、パイプライン全体を通す。予測力が
存在しえないので、Rank IC はゼロ近傍（|IC| < 0.01 程度）でなければならない。

```python
def test_synthetic_random_data_has_no_predictive_power():
    prices = generate_random_walk(n_tickers=500, n_days=750, seed=42)
    features = compute_features(prices)          # 実装済みの本物のパイプライン
    labels = compute_forward_excess_returns(prices, horizon=20)
    ic = run_purged_walk_forward(features, labels).mean_rank_ic
    assert abs(ic) < 0.01, f"合成データで IC={ic:.4f}。リークの可能性が高い"
```

このテストが落ちたら、実データでの成績はすべて無効として扱う。新しいファクターを追加したら必ず
再実行する。

### 4.2 ラベルシャッフル検証

ラベルをランダムにシャッフルして学習する。IC がゼロ近傍にならなければ、特徴量側に未来情報が
入っている。

### 4.3 時間反転検証

時系列を反転させて学習・検証する。妙に良い成績が出る場合、時点整合が壊れている。

### 4.4 単一時点の再現

ある日の特徴量を、その日の夜のバッチで計算した値と、3ヶ月後に再計算した値で比較する。一致しなけ
ればどこかで未来の情報を使っている。修正再表示が絡む財務系で頻出する。

```python
def test_feature_is_reproducible_at_later_date():
    v1 = compute_features(as_of=date(2026, 5, 1), snapshot_at=date(2026, 5, 1))
    v2 = compute_features(as_of=date(2026, 5, 1), snapshot_at=date(2026, 8, 1))
    pd.testing.assert_frame_equal(v1, v2)
```

## 良すぎる結果を見たときの判断フロー

```
Rank IC が 0.10 を超えた
  ↓
T-LEAK-04（合成データ）を実行
  ↓ IC がゼロ近傍でない
  → パイプライン全体にリークがある。レベル1から順に確認
  ↓ IC がゼロ近傍
  ↓
ラベルシャッフル検証を実行
  ↓ IC がゼロ近傍でない
  → 特徴量側に未来情報。レベル2を確認
  ↓ IC がゼロ近傍
  ↓
単一時点の再現テストを実行
  ↓ 一致しない
  → PIT の扱いが壊れている。レベル1.4 / 1.5 を確認
  ↓ 一致する
  ↓
バックテストのエントリータイミングとコストを確認（レベル3）
  ↓ 問題なし
  ↓
検証期間が短すぎないか、特定の局面に偏っていないかを確認
n_trials を DSR に反映させて有意性を再判定
  ↓ DSR でも有意
  → ここまで来たら記録して残す。ただし本番の重み変更は
    別の期間・別の市場での再現を確認してから
```

最後まで来ても、実運用で同じ成績が出る保証はない。Rank IC 0.03 前後で「予測はほぼ当たらない」
前提を維持したまま、スクリーニングと開示読解の価値で勝負する方が現実的。
