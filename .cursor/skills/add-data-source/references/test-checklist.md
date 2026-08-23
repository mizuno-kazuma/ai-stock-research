# データソース追加時のテストチェックリスト

テストIDの体系は [docs/12-testing-validation.md](../../../../docs/12-testing-validation.md) に従う。
新規ソースごとに以下をすべて追加する。省略していいものはない。

## T-DQ（データ品質）

| ID例 | 内容 | 失敗したときに何が起きるか |
| --- | --- | --- |
| `T-DQ-{src}-01` | 正常なフィクスチャで `normalize` が期待どおりの列・型・行数を返す | 静かに壊れたデータが下流に流れる |
| `T-DQ-{src}-02` | フィールドが増減したフィクスチャで `schema_drift` が記録される | API仕様変更に気づけない |
| `T-DQ-{src}-03` | 銘柄コードが `str` 型で、先頭ゼロが保持される | `0龍` 系や4桁未満のコードが消える |
| `T-DQ-{src}-04` | 価格の論理検証（`low <= open, close <= high`、`volume >= 0`） | 異常値が特徴量とスコアを汚染する |
| `T-DQ-{src}-05` | 欠損値が `NULL` として保存される（ゼロ埋めされない） | 欠損とゼロの区別が失われ、PERなどで致命的 |
| `T-DQ-{src}-06` | 重複レコードが `upsert` で1行に収束する | 同じ日のデータが二重計上される |
| `T-DQ-{src}-07` | 日付が JST / UTC のどちらで解釈されるか固定されている | 1日ずれた特徴量が生成される |

フィクスチャは実際のレスポンスを匿名化して `tests/fixtures/{source}/` に置く。手書きの理想的な
JSONではなく、**実物のレスポンスを保存する**こと。実物には想定外の空文字列や全角スペースが入る。

## T-PIT（Point-in-Time）

財務・開示・マクロ系のソースでは必須。価格系では該当する場合のみ。

| ID例 | 内容 |
| --- | --- |
| `T-PIT-{src}-01` | `as_of < filed_at` のクエリでそのレコードが返らない |
| `T-PIT-{src}-02` | 修正再表示された同一期間のレコードが、それぞれの `filed_at` で正しく切り替わる |
| `T-PIT-{src}-03` | 日本の開示は当日15時ルールが適用される（15時以降の開示は翌営業日から利用可能） |
| `T-PIT-{src}-04` | マクロ統計は `vintage_date` 基準で、改定後の値が過去に遡って見えない |

`T-PIT-02` の具体例:

```python
def test_restatement_visible_only_after_filing():
    # 2026-05-14 に開示された値 = 1000
    # 2026-08-08 に修正再表示された値 = 1050
    assert financials_pit(as_of="2026-06-01", ticker="7203").operating_income == 1000
    assert financials_pit(as_of="2026-08-09", ticker="7203").operating_income == 1050
```

このテストが通らない構造だと、バックテストで未来の修正後の数値を使ってしまう。

## T-UNIT（単体）

| ID例 | 内容 |
| --- | --- |
| `T-UNIT-{src}-01` | トークンバケットが設定した毎分上限を超えない |
| `T-UNIT-{src}-02` | トークンバケットの状態がプロセス再起動をまたいで保持される |
| `T-UNIT-{src}-03` | 429 応答で指数バックオフして再試行する |
| `T-UNIT-{src}-04` | 401 / 403 応答では**リトライせず即時中断する** |
| `T-UNIT-{src}-05` | 404 応答はスキップとして記録し、ジョブを止めない |
| `T-UNIT-{src}-06` | `upsert` が冪等（同じ入力で2回実行して行数・内容が変わらない） |
| `T-UNIT-{src}-07` | チェックポイントから再開して、重複も欠落も生じない |
| `T-UNIT-{src}-08` | タイムアウト時に部分書き込みが残らない |

`T-UNIT-04` は重要。認証エラーをリトライすると、キーが失効しているときに上限まで無駄に叩き、
場合によってはアカウント側で制限がかかる。

## T-ENV（環境）

| ID例 | 内容 |
| --- | --- |
| `T-ENV-{src}-01` | すべての `open()` に `encoding` が指定されている（Ruff `PLW1514` で担保） |
| `T-ENV-{src}-02` | 生成されるパスに Windows の禁止文字が含まれない |
| `T-ENV-{src}-03` | パス生成が `pathlib` を経由している |

`T-ENV-02` は生成パスに対するプロパティテストとして書くのが確実。

```python
@pytest.mark.parametrize("endpoint", ["bars/daily", "fins:summary", "docs?type=120"])
def test_path_has_no_forbidden_chars(endpoint):
    p = raw_path(Path("/tmp"), "src", endpoint, date(2026, 8, 22),
                 datetime(2026, 8, 22, 6, 4, 12), 1, "json.gz")
    assert not set(str(p.relative_to("/tmp"))) & set('<>:"|?*')
```

## T-LEAK（リーク）— 回帰確認

新規ソースを追加したあと、既存のリーク検出テストが引き続き合格することを確認する。特に:

| ID | 内容 | 追加時に壊れやすい理由 |
| --- | --- | --- |
| `T-LEAK-02` | `prices_live` がモデルから参照されない | 新ソースを現在値テーブルに入れてしまい、特徴量が拾う |
| `T-LEAK-04` | 合成ランダムデータで Rank IC がゼロ近傍 | 新特徴量に未来情報が混入していると数値が跳ねる |

`T-LEAK-04` の Rank IC が急に改善したら、それは成果ではなくリークの兆候として扱う。

## T-SEC（セキュリティ）

| ID例 | 内容 |
| --- | --- |
| `T-SEC-{src}-01` | APIキーがログに出力されない（`SecretStr` とログフィルタ） |
| `T-SEC-{src}-02` | 例外メッセージにキーが含まれない（URLクエリ認証のソースで特に注意） |
| `T-SEC-{src}-03` | SEC EDGAR は `User-Agent` 未設定で起動時に失敗する |

## 実行

```bash
uv run pytest tests/ -k "{src}" -v
uv run pytest tests/ -m "leak" -v      # リーク検出は必ず全件実行
uv run ruff check .
uv run mypy packages/core
```

リーク検出テストが1件でも失敗している状態でマージしてはいけない。スコアと推奨が信用できなくなる。
