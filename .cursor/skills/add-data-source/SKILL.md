---
name: add-data-source
description: 新しいデータソース（株価・財務・開示資料・マクロ指標など）を取り込む Connector を追加する手順。レート制限・生データ保存・スキーマ追加・PIT整合・テスト・ドキュメント更新までを一続きで扱う。新規APIの接続、既存ソースのエンドポイント追加、データソースの差し替え、無料枠から有料プランへの移行を行うときに使う。
---

# データソースの追加

新しいデータソースを追加するときは、必ずこの順序で進める。順序を入れ替えると、後から
「このデータがいつ入手可能だったのか」が分からなくなり、リーク検証ができなくなる。

関連仕様: [02-data-ingestion.md](../../../docs/02-data-ingestion.md)、
[03-data-model.md](../../../docs/03-data-model.md)、
[12-testing-validation.md](../../../docs/12-testing-validation.md)

## 手順

### 1. 事前調査（コードを書く前）

以下を確定させ、`docs/02-data-ingestion.md` に追記できる状態にする。ここが曖昧なまま実装すると
必ず作り直しになる。

- 認証方式（ヘッダ名・キーの取得元・失効の有無）
- レート制限（毎分・毎秒・日次の上限、ドキュメント上の値と実測値）
- 利用規約上の制約（自動取得の可否、頻度、再配布の禁止）
- 提供されるデータの遅延（何営業日・何週間遅れるか）
- 履歴の長さ（いつまで遡れるか）
- レスポンス形式（JSON / CSV / XBRL / PDF）と文字コード
- **各レコードが「いつ公開されたか」を示すフィールドがあるか**（`filed_at` に相当するもの）

最後の項目が最重要。公開日時が取れないソースは、財務・開示系では使ってはいけない。価格系でのみ
許容する。

公式ドキュメントで確認した日付を `sources.yaml` の `last_verified` に必ず記録する。

### 2. 設定を `sources.yaml` に追加

コード中に URL・レート制限・プラン名をハードコードしない。

```yaml
sources:
  new_source:
    base_url: "https://api.example.com/v1"
    auth:
      kind: header          # header | query | none
      header_name: "X-Api-Key"
      env_var: "NEW_SOURCE_API_KEY"
    rate_limit:
      requests: 5
      per_seconds: 60
      burst: 1
    retry:
      max_attempts: 4
      backoff_base_sec: 2.0
      retry_on: [429, 500, 502, 503, 504]
    timeout_sec: 30
    plan: "free"
    delay_note_ja: "無料プランでは12週間遅延"
    last_verified: "2026-08-22"
    enabled: true
```

`enabled: false` で起動できることを必ず確認する。新ソースの障害が全体を止めてはいけない。

### 3. Connector を実装

`packages/core/connectors/` に `Connector` を継承したクラスを追加する。4つのメソッドの責務を
混ぜないこと。

| メソッド | 責務 | やってはいけないこと |
| --- | --- | --- |
| `fetch` | HTTPアクセスと生レスポンスの保存のみ | 正規化、型変換、DB書き込み |
| `normalize` | 生レスポンス → DataFrame への変換のみ | ネットワークアクセス |
| `upsert` | DuckDB / SQLite への冪等な書き込み | 変換ロジック |
| `checkpoint` | 中断位置の保存と復元 | それ以外 |

`fetch` は必ず生レスポンスをそのまま保存する。

```
data/raw/{source}/{endpoint}/dt={YYYY-MM-DD}/{HHmmss}_{seq:04d}.json.gz
```

パス命名は Windows 互換規則に従う。`:` `?` `*` を含めない。詳細は
[references/naming-and-encoding.md](references/naming-and-encoding.md)。

### 4. スキーマを追加

`docs/03-data-model.md` に列名・型・主キー・PIT制約を追記し、DuckDB のマイグレーションSQLを
`packages/core/migrations/duckdb/` に追加する。

- 銘柄コードは**必ず文字列**。`7203` を整数にすると先頭ゼロの銘柄で壊れる。
- 財務・開示系は `filed_at` を主キーに含め、PITビューを用意する。
- 遅延データと現在値データは**別テーブルに分ける**。同じテーブルに混ぜてはいけない。

### 5. テストを追加

最低限、以下を書く。詳細は [references/test-checklist.md](references/test-checklist.md)。

- `T-DQ`: 正常なレスポンスのフィクスチャで `normalize` が期待どおりの DataFrame を返す
- `T-DQ`: 想定外のフィールドが増減した場合に `schema_drift` として記録される
- `T-DQ`: 銘柄コードが文字列型である
- `T-PIT`: `filed_at` より前の日付で参照しても、そのレコードが見えない
- `T-UNIT`: レート制限が守られる（トークンバケットの単体テスト）
- `T-UNIT`: `upsert` が冪等（2回実行して行数が増えない）
- `T-UNIT`: チェックポイントから再開して重複が発生しない
- `T-ENV`: ファイル読み書きに `encoding="utf-8"` が明示されている

### 6. Collector に組み込む

`services/agent/jobs/collector.py` に追加する。このとき:

- 新ソースの失敗が他のフェーズを止めないこと（`prices` 以外はすべて任意）
- 失敗時に `job_runs.metrics` へ記録すること
- フェーズ名を `docs/08-agent-loop.md` のフェーズ一覧に追記すること

### 7. UI への露出

`GET /api/v1/system/freshness` に新ソースが並ぶようにする。`docs/ui/screens/10-settings.md` の
データソース一覧表と `docs/ui/sample-data.json` の `data_freshness` にも追記する。

### 8. ドキュメント更新（必須）

以下を更新していないPRは未完了とみなす。

- `docs/02-data-ingestion.md`: 節を追加（認証・レート制限・エンドポイント・品質チェック・落とし穴）
- `docs/03-data-model.md`: スキーマ
- `docs/11-security-ops.md`: 新しい環境変数を `.env.example` に追記
- `docs/12-testing-validation.md`: 追加したテストID
- `README.md`: データソース一覧

## 完了条件

- [ ] `sources.yaml` に設定があり、`enabled: false` で無効化できる
- [ ] 生レスポンスが `data/raw/` に保存される
- [ ] 初回バックフィルが中断・再開できる
- [ ] レート制限に達しても例外で落ちず、待機してから続行する
- [ ] 認証エラー（401 / 403）は即時中断し、リトライしない
- [ ] `filed_at` を持つデータには PIT ビューがある
- [ ] テストがすべて通り、`T-LEAK-04`（合成データでのリーク検出）が引き続き合格する
- [ ] ドキュメント4点が更新されている

## よくある失敗

| 失敗 | 症状 | 対策 |
| --- | --- | --- |
| 生レスポンスを保存していない | 正規化のバグを後から修正できない、再取得もできない | `fetch` で必ず保存 |
| 正規化後のデータだけを保存 | スキーマ変更に気づけない | 同上 |
| 銘柄コードを整数で保存 | 先頭ゼロの銘柄が消える、US ティッカーが入らない | 文字列で統一 |
| 遅延データを現在値テーブルに混ぜた | バックテストが実運用より良く見える | テーブルを分離し `T-LEAK-02` を追加 |
| `filed_at` ではなく期末日で主キーを構成 | 修正再表示で過去が書き換わり、リークする | `filed_at` を主キーに含める |
| `encoding` を省略した `open()` | 日本語で `UnicodeDecodeError`（cp932） | 常に `encoding="utf-8"` |
| レート制限をスリープで実装 | 並行実行で破綻、再起動で状態が失われる | トークンバケットをSQLiteに永続化 |
