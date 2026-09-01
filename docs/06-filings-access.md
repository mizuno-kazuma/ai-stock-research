# 06. 決算資料ワンクリックアクセス仕様

## 1. この機能の狙い

株式のリサーチで最も時間を食うのは「資料を探すこと」である。EDINET の検索画面で会社名を入力し、書類種別を選び、日付を絞り、PDFを開く。この一連の操作を**銘柄詳細画面のリンク1つ**に置き換える。

要件:

1. 銘柄詳細画面から、その銘柄の全開示資料を時系列で一覧できる
2. 各資料は**クリック1回で原文（PDF）が開く**。中間ページを経由しない
3. LLM要約が付いており、原文を開く前に内容の見当がつく
4. 同じ資料に対して要約を2回課金しない（キャッシュ）
5. 資料が取得できない場合も、公式サイトの該当ページへのリンクは必ず出す（機能縮退）

## 2. `documents` テーブルの位置付け

すべての開示資料は `documents` テーブル（[03-data-model.md](03-data-model.md) §2.5）に正規化される。ソースごとの差異はここで吸収し、UI・API はソースを意識しない。

```
EDINET ──┐
TDnet  ──┼──► documents（doc_id, ticker, doc_type, title, source_url, pdf_url, filed_at, ...）
EDGAR  ──┘
```

`doc_id` の形式: `{source}:{native_id}`

| source | native_id | 例 |
| --- | --- | --- |
| `edinet` | EDINET の docID | `edinet:S100XXXX` |
| `edgar` | accession number | `edgar:0000320193-26-000012` |
| `tdnet` | 開示日 + 連番 | `tdnet:20260823-0042` |

## 3. EDINET の URL 生成規則

### 3.1 API 経由のダウンロード URL

`[要検証]` 公式仕様書で `type` パラメータの値を確認する。

```python
EDINET_API = "https://api.edinet-fsa.go.jp/api/v2"

def edinet_download_url(doc_id: str, kind: Literal["xbrl", "pdf", "csv"]) -> str:
    """API経由のダウンロードURL。Ocp-Apim-Subscription-Key ヘッダが必要なため、
    ブラウザから直接開くことはできない。サーバ側で取得して保存する。"""
    type_map = {"xbrl": 1, "pdf": 2, "csv": 5}   # [要検証]
    return f"{EDINET_API}/documents/{doc_id}?type={type_map[kind]}"
```

**重要**: このURLは `Ocp-Apim-Subscription-Key` ヘッダが必要なので、UIから直接リンクできない。したがって以下の二段構えにする。

### 3.2 ブラウザで直接開ける URL（人間用）

```python
def edinet_viewer_url(doc_id: str) -> str:
    """EDINET の書類閲覧画面。ヘッダ認証不要でブラウザから開ける。
    [要検証] EDINET のUIリニューアルでパスが変わる可能性がある。"""
    return (
        "https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx"
        f"?S100={doc_id}"          # [要検証] 実際のクエリパラメータ名を確認
    )
```

`[要検証]` EDINET の閲覧画面URLは過去に何度か変わっている。実装時に実際のURLを確認し、この関数1箇所を直せば済むようにしておく。

### 3.3 ローカル配信 URL（推奨経路）

最も確実なのは、**サーバ側でPDFを取得してローカルに保存し、自前のエンドポイントから配信する**方式である。

```
GET /api/v1/documents/{doc_id}/file        → PDFバイナリを返す
GET /api/v1/documents/{doc_id}/file?disposition=inline  → ブラウザ内表示
```

実装:

```python
@router.get("/documents/{doc_id}/file")
async def get_document_file(doc_id: str, disposition: str = "inline"):
    doc = repo.get_document(doc_id)
    if doc.blob_path and (BLOB_ROOT / doc.blob_path).exists():
        return FileResponse(BLOB_ROOT / doc.blob_path, media_type="application/pdf",
                            headers={"Content-Disposition": f"{disposition}; filename=..."})
    # 未取得なら、その場で取得してから返す（初回のみ遅い）
    blob_path = await fetch_and_store(doc)
    if blob_path is None:
        # 取得できない場合は公式サイトへリダイレクト（機能縮退）
        return RedirectResponse(doc.source_url)
    return FileResponse(...)
```

実装は `services/api/document_files.py`。`documents.blob_path` が空でも
`data/raw/{source}/blobs/` の規約パスを探す。ローカルもオンデマンド取得も失敗したら
`source_url`（EDINET 閲覧画面など）へ 302 する。一覧は「原文（別タブ）」がこの
エンドポイントを開き、併せて「提供元サイトで開く」を出す。

**この設計の利点**:

- UI からは常に同じ形式のURLになる（ソースを意識しない）
- 認証ヘッダの問題が起きない
- モバイル（Tailscale経由）からも同じように開ける
- 資料が消えても手元に残る（EDINETは一定期間で古い書類を削除する）

`Content-Disposition: inline` にするのは、iOS Safari で PDF をアプリ内表示させるため。`attachment` にするとダウンロードになり、モバイルでの体験が悪い。

### 3.4 ファイル名の規則（Windows 対応）

```python
def blob_relative_path(doc: Document) -> Path:
    """doc_id ベースのファイル名にする。日本語タイトルをファイル名に使わない。"""
    safe_id = doc.doc_id.replace(":", "_")     # ':' は Windows で使えない
    return Path(doc.source) / doc.filed_at.strftime("%Y") / f"{safe_id}.pdf"
```

- 日本語タイトルをファイル名に使わない（文字コード事故の温床）
- `:` を `_` に置換する（`doc_id` に `:` が含まれるため必須）
- タイトルは `documents.title` カラムに持つ

詳細は [15-windows-runtime.md](15-windows-runtime.md) §5。

## 4. EDGAR の URL 生成規則

### 4.1 CIK のゼロ埋めの違い（実装ミスが多い箇所）

```python
def edgar_urls(cik: str, accession: str, primary_document: str) -> EdgarUrls:
    """CIK のゼロ埋めが URL の種類によって異なることに注意。
    - data.sec.gov/submissions と companyfacts : 10桁ゼロ埋め（'CIK0000320193'）
    - www.sec.gov/Archives のパス            : ゼロ埋めなしの整数（'320193'）
    この違いを取り違えると 404 になる。
    """
    cik_padded = cik.zfill(10)                    # '0000320193'
    cik_int = str(int(cik))                       # '320193'
    accn_nodash = accession.replace("-", "")      # '000032019326000012'
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}"
    return EdgarUrls(
        submissions_json = f"https://data.sec.gov/submissions/CIK{cik_padded}.json",
        companyfacts_json= f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json",
        filing_index     = f"{base}/{accession}-index.htm",
        primary_doc      = f"{base}/{primary_document}",
        filing_summary   = f"{base}/FilingSummary.xml",
        all_files_index  = f"{base}/",
    )
```

### 4.2 primary_document の取得

`submissions.json` のレスポンス構造（配列が並列に並ぶ形式）:

```json
{
  "cik": "320193",
  "filings": {
    "recent": {
      "accessionNumber": ["0000320193-26-000012", "..."],
      "filingDate":      ["2026-05-02", "..."],
      "reportDate":      ["2026-03-31", "..."],
      "form":            ["10-Q", "..."],
      "primaryDocument": ["aapl-20260331.htm", "..."],
      "primaryDocDescription": ["10-Q", "..."],
      "items":           ["", "..."],
      "size":            [4823910, 0]
    },
    "files": [{"name": "CIK0000320193-submissions-001.json", "filingCount": 1000}]
  }
}
```

**注意点**:

- 配列は「列指向」で並んでおり、同じインデックスが同じ提出物に対応する。行として組み立てる処理が必要
- `recent` には直近約1,000件しか入らない。それより古いものは `files[]` の追加JSONを取得する
- `primaryDocument` が空文字列の提出物がある（古い提出物）。その場合は `filing_index` を `source_url` に使う

```python
def parse_submissions(payload: dict) -> list[Filing]:
    recent = payload["filings"]["recent"]
    keys = ["accessionNumber", "filingDate", "reportDate", "form",
            "primaryDocument", "primaryDocDescription", "items"]
    n = len(recent["accessionNumber"])
    return [Filing(**{k: recent[k][i] for k in keys}) for i in range(n)]
```

### 4.3 XBRL Viewer への直リンク

EDGAR には財務諸表をインタラクティブに見られるビューアがある。

```python
def edgar_ixviewer_url(cik: str, accession: str, primary_document: str) -> str:
    """inline XBRL viewer。10-K/10-Q の財務諸表を構造化表示できる。
    [要検証] パスは変更されることがある。"""
    accn_nodash = accession.replace("-", "")
    doc_path = f"/Archives/edgar/data/{int(cik)}/{accn_nodash}/{primary_document}"
    return f"https://www.sec.gov/ix?doc={doc_path}"
```

UI では「原文」「XBRL Viewer」「提出物一覧」の3つのリンクを出す。

## 5. TDnet の URL

TDnet の資料URLは一覧取得時に得られる PDF の直リンクをそのまま使う。ただし TDnet は**一定期間（概ね30日）で公開を終了する**ため、取得時にPDFをローカル保存することが必須である。

```python
def tdnet_source_url(disclosure: dict) -> str:
    # 一覧から得られる PDF URL をそのまま使う
    return disclosure["document_url"]
```

保存後は `documents.blob_path` から配信する。元URLが404になっても手元のコピーで読める。

## 6. 資料一覧の提示方法

### 6.1 銘柄詳細画面での並び

```
2026-05-02  [四半期報告書]  2026年3月期 第1四半期報告書        [要約あり]  [PDF]
2026-04-28  [決算短信]      2026年3月期 第1四半期決算短信      [要約あり]  [PDF]
2026-04-28  [業績予想の修正] 2026年3月期 通期業績予想の修正     [要約あり]  [PDF]
2026-03-31  [有価証券報告書] 第122期 有価証券報告書             [要約あり]  [PDF]
```

- `filed_at` の降順
- `doc_type` でフィルタ可能
- 訂正報告がある場合は元の資料の下にネストして表示（`amends_doc_id`）
- 要約がない資料には「要約する」ボタンを出す（オンデマンドでLLMを呼ぶ）

### 6.2 決算資料ハブ画面

全銘柄横断で新着開示を見る画面（[ui/screens/05-filings-hub.md](ui/screens/05-filings-hub.md)）。

- 当日・直近3日・直近1週間の切替
- 市場・書類種別・保有状況でのフィルタ
- 保有銘柄・ウォッチリスト銘柄の開示を最上部に固定表示
- `guidance_revision` は色を変えて強調（最も情報価値が高い）

## 7. LLM要約のキャッシュ設計

### 7.1 キャッシュキー

```python
def summary_cache_key(doc_id: str, prompt_template: str,
                      doc_content_hash: str) -> tuple[str, str, str]:
    prompt_hash = sha256(prompt_template.encode("utf-8")).hexdigest()[:16]
    return (doc_id, prompt_hash, doc_content_hash[:16])
```

`document_summaries` テーブル（[03-data-model.md](03-data-model.md) §2.6）の `(doc_id, summary_version)` を主キーとし、`prompt_hash` / `input_hash` を保持する。

**キャッシュヒット判定**:

```python
def get_or_create_summary(doc: Document, template: PromptTemplate) -> Summary:
    key = summary_cache_key(doc.doc_id, template.text, doc.content_hash)
    cached = repo.find_summary(doc_id=key[0], prompt_hash=key[1], input_hash=key[2])
    if cached:
        metrics.incr("llm.cache_hit")
        return cached
    # コストキャップの確認
    if cost_guard.would_exceed_cap(estimated_cost(doc)):
        raise CostCapExceeded(...)
    summary = llm.summarize(doc, template)
    repo.save_summary(summary)   # citations が空なら例外
    return summary
```

### 7.2 再要約が必要になる条件

| 条件 | 動作 |
| --- | --- |
| プロンプトテンプレートを改善した | `prompt_hash` が変わるので自動的に再計算される。**過去分の一括再計算は手動トリガのみ**（コストが大きいため） |
| 資料が訂正された | 新しい `doc_id` として別レコードになる。元の要約は残す |
| モデルを変更した | `model_id` が変わる。既存キャッシュは有効なまま使い、新規分から新モデルを使う |
| 利用者が「再要約」を押した | `summary_version` を +1 して再計算 |

**過去分の一括再要約を自動でやらない**ことが重要である。有報1万件を再要約すると数千円単位のコストになる。手動トリガ + 件数上限 + 事前のコスト見積もり表示を必須とする。

### 7.3 コスト見積もりの表示

一括再要約の前に以下を表示する。

```
対象資料: 1,240件
推定入力トークン: 約 62,000,000（PDF平均50,000トークン）
推定出力トークン: 約 620,000
推定コストは実装時の料金表から算出して表示する
（Gemini 3.7 Flash の場合: 入力 $0.75 / 1M、出力 $3.75 / 1M で計算）
→ 概算 $48.8

[キャンセル]  [実行する（コストキャップを一時的に引き上げる）]
```

## 8. 要約の構造

`document_summaries` に格納する要約の形式（LLM に JSON で返させる）。

```json
{
  "summary_ja": "2026年3月期第1四半期は売上高が前年同期比8.2%増の12兆3,450億円、営業利益は同12.4%増の1兆2,340億円。北米での販売台数増加と円安が寄与した。通期の営業利益予想を4兆8,000億円から5兆1,000億円へ上方修正した。",
  "key_points": [
    "売上高 12兆3,450億円（前年同期比 +8.2%）",
    "営業利益 1兆2,340億円（同 +12.4%）",
    "通期営業利益予想を上方修正（4兆8,000億円 → 5兆1,000億円）",
    "北米販売台数が前年同期比 +6.1%",
    "為替前提を 1USD=148円から152円へ変更"
  ],
  "risk_factors": [
    "北米市場での価格競争激化の可能性を新たに言及",
    "半導体供給の制約について前期から継続して記載",
    "為替前提の変更により、円高転換時の下方リスクが拡大"
  ],
  "guidance_tone": "positive",
  "guidance_evidence": "「通期業績予想を上方修正いたします」（p.3）、「北米市場における販売は堅調に推移」（p.5）",
  "qualitative_score": 0.55,
  "citations": [
    {"page": 3, "quote": "通期の連結営業利益予想を5兆1,000億円に修正いたします"},
    {"page": 5, "quote": "北米における販売台数は前年同期比6.1%増となりました"},
    {"page": 12, "quote": "北米市場においては競合他社の価格政策により競争環境が厳しさを増しており"}
  ]
}
```

**`citations` が空の応答は保存しない。** リポジトリ層で検証し、空の場合は1回リトライ（プロンプトに「引用が必須である」を強調して再送）、それでも空なら要約を破棄して `document_summaries` に記録しない（要約なしとして扱う）。

## 9. 資料の取得が失敗した場合（機能縮退）

| 失敗 | 表示 | リンク |
| --- | --- | --- |
| PDF 未取得 | 「原文を取得中」 | 公式サイトへの外部リンクを出す |
| PDF 取得失敗（404） | 「原文の取得に失敗しました」 | 公式サイトへの外部リンク |
| 要約なし | 「要約はまだありません」+ 要約ボタン | PDFリンクは有効 |
| コストキャップ到達 | 「本日のLLM予算に達したため要約を生成できません」 | PDFリンクは有効 |
| ソース自体が停止中 | 「EDINETからの取得が停止しています（最終取得: 3日前）」 | 公式サイトへの外部リンク |

**どのケースでも「公式サイトへのリンク」は必ず出す。** 要約や取得が失敗しても、資料に到達する手段が失われないことが最低保証である。

`GET /api/v1/documents/{doc_id}/file` はローカル PDF が無いとき、EDINET からオンデマンド取得を試み、それでも無ければ `source_url`（閲覧画面）へ 302 する。大量保有報告書などバッチでは PDF を落とさない書類も、一覧の「原文」から公式サイトへ届く。

## 10. 決算発表予定日の管理

「決算前」の警告（[05-scoring-screening.md](05-scoring-screening.md) §7.2）に必要。

| 市場 | 取得方法 |
| --- | --- |
| 日本 | J-Quants の決算発表予定日API `[要検証]`。なければ過去の発表日パターン（前年同期 ± 数日）から推定 |
| 米国 | yfinance の `Ticker.calendar` `[要検証]`。または Finnhub の earnings calendar |

推定値の場合は `earnings_dates.is_estimated = TRUE` を立て、UIに「推定」と表示する。

```sql
CREATE TABLE earnings_dates (
    ticker        VARCHAR NOT NULL,
    market        VARCHAR NOT NULL,
    fiscal_period VARCHAR NOT NULL,
    scheduled_date DATE NOT NULL,
    session       VARCHAR,       -- 'before_open'|'after_close'|'unknown'
    is_estimated  BOOLEAN NOT NULL,
    source        VARCHAR NOT NULL,
    confirmed_at  TIMESTAMP,
    ingested_at   TIMESTAMP NOT NULL,
    PRIMARY KEY (ticker, market, fiscal_period)
);
```

## 11. 参照

- データ取得: [02-data-ingestion.md](02-data-ingestion.md) §5, §6, §7
- スキーマ: [03-data-model.md](03-data-model.md) §2.5, §2.6
- LLM要約のプロンプト: [07-llm-rag.md](07-llm-rag.md) §5
- 画面仕様: [ui/screens/05-filings-hub.md](ui/screens/05-filings-hub.md), [ui/screens/03-stock-detail.md](ui/screens/03-stock-detail.md)
