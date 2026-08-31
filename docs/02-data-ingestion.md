# 02. データ収集仕様

> **重要な注意**: 本ドキュメントに記載するエンドポイントパス、認証方式、レート制限、料金は執筆時点の調査結果である。各サービスは仕様変更が頻繁にあるため、**実装着手時に必ず公式ドキュメントで最新の値を検証すること**。特に J-Quants は v1 から v2 への移行で認証方式が変わっており、EDINET も v1 廃止済みである。検証すべき箇所には `[要検証]` を付す。

## 1. 共通設計

### 1.1 Connector 抽象

すべてのデータソースは以下のインターフェースを実装する。`packages/core/connectors/base.py`。

```python
from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Iterator
from pydantic import BaseModel

class FetchWindow(BaseModel):
    start: date
    end: date
    cursor: str | None = None       # ページネーション用の継続トークン

class RawBatch(BaseModel):
    source: str                      # "jquants" | "edinet" | "tdnet" | "yfinance" | "edgar" | "fred"
    endpoint: str                    # 正規化されたエンドポイント識別子
    as_of: date
    fetched_at: str                  # ISO8601 UTC
    request: dict[str, Any]          # 再現用のリクエストパラメータ（キーはマスク済み）
    payload: Any                     # 生レスポンス（無加工）
    next_cursor: str | None = None

class Connector(ABC):
    source: str
    rate_limit_per_min: int
    max_retries: int = 5

    @abstractmethod
    def fetch(self, window: FetchWindow, **kwargs) -> Iterator[RawBatch]:
        """外部APIを叩き、生レスポンスをそのまま yield する。加工は禁止。"""

    @abstractmethod
    def normalize(self, batch: RawBatch) -> "pd.DataFrame":
        """RawBatch を Core 層のスキーマに合わせた DataFrame に変換する。
        ネットワークアクセスをしてはならない（Raw層から再実行可能にするため）。"""

    @abstractmethod
    def upsert(self, df: "pd.DataFrame") -> int:
        """DuckDB の対象テーブルへ upsert する。戻り値は影響行数。"""

    @abstractmethod
    def checkpoint(self) -> "Checkpoint":
        """次回の再開位置を返す。job_runs.checkpoint に保存される。"""
```

**設計上の制約**:

- `fetch` は保存のみを行い、加工しない。`normalize` はネットワークに触らない。この分離により、正規化ロジックのバグ修正時にAPIを再度叩く必要がなくなる（無料枠のレート制限下では決定的に重要）
- `upsert` は必ず冪等。同じ `RawBatch` を2回流しても結果が変わらないこと
- `checkpoint` は「どこまで完了したか」を粒度細かく返す（銘柄コード単位、日付単位）。Windows Update による再起動後にここから再開する

### 1.2 レート制限の実装

`packages/core/connectors/rate_limit.py` にトークンバケットを実装する。

```python
class TokenBucket:
    def __init__(self, rate_per_min: int, burst: int | None = None): ...
    def acquire(self, tokens: int = 1) -> None:
        """トークンが得られるまでブロックする。sleep は time.monotonic ベース。"""
```

- バケット状態は**プロセス内メモリではなく SQLite に永続化する**。再起動直後に制限を超えて叩いてBANされるのを防ぐ（テーブル: `rate_limit_state`）
- 設定は `packages/core/config/sources.yaml` に集約

```yaml
sources:
  jquants:
    rate_limit_per_min: 5          # free plan. light plan は 60  [要検証]
    plan: ${JQUANTS_PLAN}
    delay_weeks: 12                # free plan の遅延。light は 0
    base_url: https://api.jquants.com
  edinet:
    rate_limit_per_min: 60         # 公式に明示なし。安全側に設定  [要検証]
    base_url: https://api.edinet-fsa.go.jp/api/v2
  tdnet:
    rate_limit_per_min: 6          # 礼儀としての自主制限。APIではないため特に保守的に
  edgar:
    rate_limit_per_sec: 10         # SEC の明示上限
    user_agent: ${EDGAR_USER_AGENT}
  yfinance:
    rate_limit_per_min: 60         # 非公式。ブロックされたら下げる
  fred:
    rate_limit_per_min: 120        # [要検証]
  alpha_vantage:
    rate_limit_per_min: 5          # 無料枠。日次上限もある  [要検証]
  finnhub:
    rate_limit_per_min: 60         # 無料枠  [要検証]
```

### 1.3 リトライ方針

| 状況 | 判定 | 動作 |
| --- | --- | --- |
| HTTP 429 | レート制限 | `Retry-After` があれば従う。なければ 4s → 8s → 16s → 32s → 64s |
| HTTP 5xx | 一時障害 | 指数バックオフ（最大5回） |
| HTTP 401 / 403 | 認証失敗 | **即座に中断**しリトライしない。`job_runs` に `auth_error` を記録し通知 |
| HTTP 404 | 対象なし | リトライせずスキップ。`data_gaps` に記録 |
| タイムアウト（接続30s / 読み取り120s） | 一時障害 | 指数バックオフ |
| JSONパース失敗 | 仕様変更の可能性 | リトライせず生レスポンスを Raw層に保存し `schema_drift` として記録・通知 |

`schema_drift` の検出は重要である。無料APIは予告なくレスポンス構造を変えることがあり、静かに壊れるのが最悪のパターンになる。

### 1.4 Raw 層への保存規則

```
data/raw/{source}/{endpoint}/dt={YYYY-MM-DD}/{HHmmss}_{seq:04d}.json.gz
```

- パスに `:` `?` `*` を含めない（Windows側から同じファイルを触る可能性があるため。[15-windows-runtime.md](15-windows-runtime.md) 参照）
- 書き込みは `pathlib.Path` 経由、`encoding="utf-8"` 明示
- 圧縮は gzip。JSON以外（PDF、XBRL ZIP）は `data/raw/{source}/blobs/{doc_id}.{ext}` に格納
- 保持期間: 無期限（サイズ見積もりは [11-security-ops.md](11-security-ops.md)）

## 2. J-Quants API（日本株の価格・財務）

### 2.1 プラン選択

| プラン | 月額 | 履歴 | 遅延 | レート制限 |
| --- | --- | --- | --- | --- |
| Free | 0円 | 約2年 | **12週間** | 5 req/min |
| Light | 1,650円 | 約5年 | なし | 60 req/min |

`[要検証]` 価格・履歴期間・レート制限は公式の料金ページで確認する。

**設計方針**: Free プランで構築し、Light への移行を `.env` の `JQUANTS_PLAN=light` への変更だけで完了させる。コードは以下を `plan` から導出する。

- `delay_weeks`: Free=12, Light=0
- `rate_limit_per_min`: Free=5, Light=60
- `history_years`: Free=2, Light=5
- **yfinance によるギャップ補完の有効/無効**: Free=有効, Light=無効

### 2.2 12週遅延への対処（本ツールで最も事故が起きやすい箇所）

Free プランでは「今日」から12週間前までのデータが存在しない。この穴を埋めないと現在値が表示できない。一方で、遅延データと当日データを同じテーブルに混ぜると、**遅延データを最新値として表示する事故**が起きる。

対策として価格データを2つの経路に完全分離する。

| 経路 | テーブル | ソース | 用途 | UI表示 |
| --- | --- | --- | --- | --- |
| リサーチ経路 | `prices_daily` | J-Quants（権利調整済み・確定値） | バックテスト、モデル学習、ファクター計算 | 「リサーチ基準日: 2026-05-31」と明示 |
| 執行経路 | `prices_live` | yfinance（遅延15-20分程度） | 現在値表示、評価損益、エントリー価格の目安 | 「参考値（遅延あり）」と明示 |

**モデル学習に `prices_live` を使うことをコードレベルで禁止する。** `packages/core/models/` 配下から `prices_live` を参照した場合に失敗するテストを置く（[12-testing-validation.md](12-testing-validation.md)）。

さらに `data_freshness` ビューを用意し、UIヘッダに常時「JP価格: J-Quants 2026-05-31 / yfinance 2026-08-23」を表示する。

### 2.3 認証

v2 は `x-api-key` ヘッダによるAPIキー認証。`[要検証]`

```
x-api-key: {JQUANTS_API_KEY}
```

v1 では「メールアドレス+パスワードで refresh token を取得 → refresh token で id token を取得 → id token を Authorization ヘッダに付与」という2段階の手順が必要だった。v2 でこれが単純化されている。**実装時にどちらの方式が現行かを必ず確認すること。** 万一 v1 方式が必要な場合に備え、`JQuantsAuth` を差し替え可能なクラスとして切り出しておく。

```python
class JQuantsAuth(Protocol):
    def headers(self) -> dict[str, str]: ...

class ApiKeyAuth:      # v2 想定
    def headers(self): return {"x-api-key": self._key}

class RefreshTokenAuth: # v1 互換のフォールバック
    def headers(self): return {"Authorization": f"Bearer {self._id_token()}"}
```

### 2.4 利用エンドポイント

`[要検証]` 以下のパスは調査時点のものである。公式のAPIリファレンスで最新のパスとレスポンス構造を確認する。

| 用途 | エンドポイント（想定） | 取得頻度 | 主なパラメータ |
| --- | --- | --- | --- |
| 銘柄マスタ | `GET /v2/equities/master` | 週1回（月曜） | `date` |
| 日足株価 | `GET /v2/equities/bars/daily` | 日次 | `code` または `date`、`from`、`to` |
| 財務サマリ | `GET /v2/fins/summary` | 日次（新規開示分） | `code` または `date` |

**取得戦略（5 req/min の制約下）**:

- 日足は**銘柄単位ではなく日付単位で取得する**（`date=2026-08-22` で全銘柄の1日分が1リクエストで返る想定）。銘柄単位で回すと4,000銘柄 ÷ 5 req/min = 800分となり成立しない
- 日次バッチは倉庫の最新日 + 5暦日の重なりだけを取り直す。90日分を毎回転送すると無料枠の 5 req/min で2時間を超え、中断判定に引っかかる
- 初回のバックフィルは営業日単位のループ。2年分 ≒ 490営業日 ÷ 5 req/min ≒ 98分。日次バッチとは別の「バックフィルジョブ」として一度だけ実行し、チェックポイントで中断・再開できるようにする
- 銘柄マスタは週1回で十分。上場廃止・新規上場・コード変更を検出したら `securities` テーブルに履歴として残す（`valid_from` / `valid_to`）
- 財務サマリも日付単位で取得し、開示があった銘柄のみが返る想定で処理する

### 2.5 正規化

| J-Quants フィールド（想定） | Core 層カラム | 変換 |
| --- | --- | --- |
| `Code` | `ticker` | 4桁または5桁の文字列として保持。**数値型にしない**（`7203` の先頭ゼロ落ち、`130A` のような英字を含むコードに対応するため） |
| `Date` | `trade_date` | `DATE` |
| `Open` / `High` / `Low` / `Close` | `open` / `high` / `low` / `close` | `DOUBLE`。無調整値 |
| `AdjustmentClose` 等 | `adj_close` 等 | 権利調整済み。**モデル学習にはこちらを使う** |
| `Volume` | `volume` | `BIGINT` |
| `TurnoverValue` | `turnover_value` | `DOUBLE`（売買代金） |

**株式分割の扱い**: 調整済み系列を使うことを原則とするが、調整係数が後から変わる（遡及修正）ことがある。`prices_daily` には `adjustment_factor` と `ingested_at` を保持し、遡及修正が入った場合に検出できるようにする。検出時は該当銘柄の特徴量を再計算する。

## 3. yfinance（米国株の価格、および日本株の直近ギャップ補完）

### 3.1 位置付け

- 米国株の日足の**主ソース**
- 日本株の直近12週の**補完ソース**（`prices_live` テーブル）
- 非公式ライブラリであり、Yahoo Finance の仕様変更で壊れる前提で扱う

### 3.2 呼び出し規則

```python
import yfinance as yf
# 複数銘柄を1回でまとめて取得する（リクエスト数を抑える）
df = yf.download(
    tickers=["AAPL", "NVDA", "7203.T", "6758.T"],
    start="2026-08-01", end="2026-08-24",
    interval="1d", auto_adjust=False, actions=True,
    group_by="ticker", threads=False,   # threads=True は429を誘発しやすい
)
```

- 日本株のティッカーは `{code}.T`（東証）。札証・名証・福証は `.S` / `.N` / `.F` `[要検証]`。マスタから市場コードを引いてサフィックスを決める
- `threads=False` を必須とする。並列化はレート制限に触れやすく、部分的な欠損を静かに生む
- 1バッチ 50銘柄程度に分割し、バッチ間に 1秒の待機を入れる
- `auto_adjust=False` として無調整値と調整値の両方を保持する

### 3.3 品質チェック（yfinance は静かに壊れるため必須）

`normalize` 内で以下を検査し、違反行は `data_quality_flags` テーブルに記録して除外する。

| チェック | 条件 | 対応 |
| --- | --- | --- |
| 値の欠損 | `close` が NaN | 行を除外し `data_gaps` に記録 |
| 論理矛盾 | `high < low` または `close` が `[low, high]` の外 | 行を除外し通知 |
| 異常変動 | 前日比 ±40% 超 かつ 分割・配当イベントなし | フラグを立てるが除外しない（実際に起きうる）。UIで警告表示 |
| ゼロ出来高 | `volume == 0` かつ 価格が動いている | フラグを立てる |
| 日付の重複 | 同一 `(ticker, trade_date)` が複数 | 最後の1件を採用 |
| 通貨の混在 | 日本株なのに価格が3桁小さい等 | `currency` フィールドを検証し不一致なら除外 |

## 4. Alpha Vantage / Finnhub（米国株のフォールバック）

### 4.1 発動条件

yfinance が以下のいずれかに該当した場合のみ呼ぶ。常用しない（無料枠が薄いため）。

- 3回連続でリトライ失敗
- 対象銘柄の直近3営業日分が取得できない
- 品質チェックで50%以上の行が除外された

### 4.2 仕様

| ソース | 用途 | 無料枠の制約 `[要検証]` | エンドポイント |
| --- | --- | --- | --- |
| Alpha Vantage | 日足（`TIME_SERIES_DAILY_ADJUSTED`） | 5 req/min、1日25リクエスト程度 | `https://www.alphavantage.co/query?function=...&apikey=...` |
| Finnhub | 日足・企業プロフィール | 60 req/min | `https://finnhub.io/api/v1/stock/candle?...&token=...` |

無料枠の日次上限が非常に小さいため、フォールバックは**優先度の高い銘柄（保有中 + 推奨候補上位）に限定する**。フォールバックの使用回数は `job_runs.metrics` に記録し、恒常的に発動している場合は主ソースの見直しを促す通知を出す。

## 5. EDINET API v2（日本の開示資料）

### 5.1 認証

Azure API Management のヘッダ `Ocp-Apim-Subscription-Key` に API キーを付与する。
クエリ `Subscription-Key` でも通るが、実装はヘッダに統一する。

```
Ocp-Apim-Subscription-Key: {EDINET_SUBSCRIPTION_KEY}
```

`Subscription-Key` ヘッダは **使わない**。APIM は HTTP 200 のまま本文
`{ "StatusCode": 401, "message": "Access denied due to invalid subscription key." }`
を返し、書類一覧が空に見える。コネクタはこの本文を `AuthError` として中断する。

キーは EDINET のサイトから利用登録して取得する。v1 は廃止済みであり v2 のみを使う。
最終確認: 2026-09-01。

### 5.2 エンドポイント

| 用途 | エンドポイント | パラメータ |
| --- | --- | --- |
| 書類一覧 | `GET /api/v2/documents.json` | `date=YYYY-MM-DD`, `type=1`（メタデータのみ）または `type=2`（提出書類一覧を含む） |
| 書類取得 | `GET /api/v2/documents/{docID}` | `type=1`（XBRL含むZIP）, `type=2`（PDF）, `type=5`（CSV） `[要検証]` |

`[要検証]` `type` パラメータの値と意味は公式仕様書で確認する。

### 5.3 取得戦略

1. 日次バッチで前営業日の `documents.json?date=...&type=2` を1回取得する
2. レスポンスの `results[]` から、対象とする書類種別コード（`docTypeCode`）のみを抽出する

| docTypeCode `[要検証]` | 書類種別 | 取得対象 |
| --- | --- | --- |
| 120 | 有価証券報告書 | あり（PDF + XBRL） |
| 130 | 訂正有価証券報告書 | あり |
| 140 | 四半期報告書 | あり |
| 160 | 半期報告書 | あり |
| 350 | 大量保有報告書 | メタデータのみ |
| その他 | 臨時報告書等 | メタデータのみ |

3. 取得対象の書類は `type=2`（PDF）を優先ダウンロードする。理由は **Gemini 3.7 Flash がPDFをネイティブ入力できる**ため、XBRLパースを経ずに要約できる点にある
4. 数値の厳密な抽出が必要な場合（財務諸表の勘定科目単位）は `type=1` の XBRL も落とし、`arelle` などでパースする。ただし Phase A では PDF + LLM を主経路とし、XBRLパースは Phase C 以降の任意項目とする
5. ダウンロード済みかは `documents.blob_path` の有無で判定し、同じ書類を再ダウンロードしない

### 5.4 文字コード（Windows環境で必ず踏む落とし穴）

EDINET のレスポンスとファイル名には日本語が含まれる。日本語ロケールの Windows で Python のデフォルトエンコーディングは `cp932` であり、UTF-8のバイト列を読むと `UnicodeDecodeError` になる。

- `PYTHONUTF8=1` を必須とする
- それでも `open()` には `encoding="utf-8"` を明示する
- 書類名（`docDescription`）をファイル名に使わない。`docID` をファイル名にし、日本語タイトルはDBのカラムに持つ

詳細は [15-windows-runtime.md](15-windows-runtime.md)。

## 6. TDnet（日本の適時開示）

### 6.1 前提と姿勢

TDnet は**公開APIではない**。東証が提供する閲覧サービスであり、機械的なアクセスは利用規約上グレーである。したがって以下を厳守する。

- **低頻度アクセス**: 日次バッチで1回のみ。ポーリング間隔を短くしない（設定上の下限を10分とし、既定は1日1回）
- **同時接続1**: 並列取得しない
- **User-Agent の明示**: 個人利用であることと連絡先を含める
- **`robots.txt` の尊重**
- **失敗時は機能縮退**: TDnet が取得できなくても、EDINET と価格データがあれば推奨は生成できる。TDnet を必須依存にしない
- **本ツールが取得したTDnetの内容を再配布しない**

`TDNET_ENABLED=false` を既定値とし、利用者が規約を確認した上で明示的に有効化する設計とする。設定画面にも規約への注意文を表示する。

### 6.2 取得内容

適時開示の一覧（開示日時、会社コード、会社名、表題、PDF URL）を取得し、`documents` テーブルに `source='tdnet'` として保存する。決算短信・業績修正・自己株買い・株式分割の検出が主目的である。

表題からの分類ルール（正規表現）:

| パターン | `doc_type` |
| --- | --- |
| `決算短信` | `earnings_flash` |
| `業績予想の修正` / `業績予想の下方修正` / `上方修正` | `guidance_revision` |
| `配当予想の修正` | `dividend_revision` |
| `自己株式の取得` | `buyback` |
| `株式分割` | `stock_split` |
| `代表者の異動` / `役員の異動` | `management_change` |
| 上記以外 | `other_disclosure` |

`guidance_revision` は定性スコアへの寄与が大きいため、検出したら当該銘柄をその日のLLM分析対象に必ず含める（[08-agent-loop.md](08-agent-loop.md)）。

### 6.3 代替案

TDnet の取得が困難または規約上避けたい場合、以下で代替できる。

- 決算短信の主要数値は J-Quants の `/v2/fins/summary` で取得できる（開示から反映までのラグは要確認）
- 業績修正の検出は、財務サマリの会社予想値の変化を日次で差分検出することで代替可能（`guidance_revision_detected` フラグ）

この代替経路を実装しておくことで、TDnet を無効化しても主要機能が失われない構成にする。

## 7. SEC EDGAR（米国の開示資料）

### 7.1 必須ルール

SEC は明確なアクセスポリシーを公開している。違反するとIPブロックされる。

- **`User-Agent` ヘッダに実名と連絡先メールアドレスを含めることが必須**

```
User-Agent: AI Stock Research Personal Tool (contact@example.com)
Accept-Encoding: gzip, deflate
```

- **10 リクエスト/秒を超えない**（本ツールでは安全側に 5 req/s とする）
- `Accept-Encoding: gzip` を付ける（帯域への配慮）

`EDGAR_USER_AGENT` は `.env` の必須項目とし、未設定なら起動時にエラーで落とす。空の User-Agent で叩くとブロックされ、復旧に時間がかかる。

### 7.2 エンドポイント

| 用途 | エンドポイント | 備考 |
| --- | --- | --- |
| 提出物一覧 | `https://data.sec.gov/submissions/CIK{cik:010d}.json` | CIKは10桁ゼロ埋め。直近1,000件が含まれ、それ以前は `files[]` の追加JSONに分割される |
| 財務ファクト（全社） | `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json` | US-GAAP タクソノミの全期間の数値。**PIT情報として `end` / `filed` / `frame` を持つ点が重要** |
| 個別コンセプト | `https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{tag}.json` | 特定勘定のみ取得したい場合 |
| 全社横断フレーム | `https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/USD/CY2026Q1I.json` | クロスセクショナル比較に便利 |
| 全文検索 | `https://efts.sec.gov/LATEST/search-index?q=...` `[要検証]` | 公式UIの裏側API。仕様変更に注意。使用は補助的に留める |
| ティッカー→CIK対応 | `https://www.sec.gov/files/company_tickers.json` | 週1回取得して `securities` テーブルを更新 |

### 7.3 companyfacts の PIT 処理（リーク防止の要）

`companyfacts` の各データポイントは以下を持つ。

```json
{"start": "2026-01-01", "end": "2026-03-31", "val": 123456000,
 "accn": "0000320193-26-000012", "fy": 2026, "fp": "Q1",
 "form": "10-Q", "filed": "2026-05-02", "frame": "CY2026Q1"}
```

**`end`（会計期間の末日）ではなく `filed`（提出日）を PIT の基準にする。** `end=2026-03-31` の数値は `filed=2026-05-02` にならないと市場は知り得ない。`end` を基準に特徴量を作ると1ヶ月分の未来情報が漏れる。

`financials` テーブルには `period_end` と `filed_at` の両方を持ち、特徴量計算では必ず `filed_at <= as_of` で絞り込む。この制約は SQL のビュー（`financials_pit`）として定義し、特徴量計算からは生テーブルを直接参照させない。

### 7.4 取得対象書類

| form | 内容 | 扱い |
| --- | --- | --- |
| 10-K | 年次報告書 | 全文をLLM分析対象にする |
| 10-Q | 四半期報告書 | 全文をLLM分析対象にする |
| 8-K | 臨時報告 | Item 2.02（業績発表）と Item 5.02（役員異動）のみ抽出 |
| DEF 14A | 委任状 | メタデータのみ |
| SC 13D/G | 大量保有 | メタデータのみ |
| 4 | 内部者取引 | 集計値のみ（インサイダー売買の方向性を特徴量にする） |

### 7.5 filing URL の生成規則

accession number（例: `0000320193-26-000012`）から資料URLを生成する。

```
accn_nodash = accn.replace("-", "")            # 000032019326000012
base = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}"
index_url    = f"{base}/{accn}-index.htm"      # 提出物インデックス
primary_url  = f"{base}/{primary_document}"    # submissions.json の primaryDocument
```

`cik_int` はゼロ埋めしない整数であることに注意（`submissions` のパスは10桁ゼロ埋め、Archives のパスは整数）。この差異はよくある実装ミスの原因になる。詳細は [06-filings-access.md](06-filings-access.md)。

## 8. FRED API（為替・マクロ）

### 8.1 認証とエンドポイント

```
GET https://api.stlouisfed.org/fred/series/observations
  ?series_id=DEXJPUS&api_key={FRED_API_KEY}&file_type=json
  &observation_start=2016-01-01&observation_end=2026-08-23
```

無料。APIキーはFREDのサイトで即時発行される。

### 8.2 取得系列

| series_id | 内容 | 頻度 | 用途 |
| --- | --- | --- | --- |
| `DEXJPUS` | USD/JPY 為替レート | 日次（営業日） | 為替予測の目的変数 |
| `DFF` | 米国 実効FFレート | 日次 | 金利差の米側 |
| `DGS2` | 米国2年国債利回り | 日次 | 金利差（短期） |
| `DGS10` | 米国10年国債利回り | 日次 | 金利差（長期） |
| `IRLTLT01JPM156N` | 日本 長期金利 | 月次 `[要検証]` | 金利差の日本側 |
| `CPIAUCSL` | 米国CPI（総合） | 月次 | インフレ |
| `CPALTT01JPM659N` | 日本CPI `[要検証]` | 月次 | インフレ差 |
| `UNRATE` | 米国失業率 | 月次 | 景況 |
| `T10Y2Y` | 米10年-2年スプレッド | 日次 | イールドカーブ |
| `VIXCLS` | VIX | 日次 | リスクセンチメント |
| `NIKKEI225` | 日経225 | 日次 | 市場ベンチマーク |
| `SP500` | S&P500 | 日次 | 市場ベンチマーク |

`[要検証]` 日本側の金利・CPIの series_id は FRED 上の名称が変わることがある。実装時に FRED の検索で確認する。日本の統計は日銀・総務省が一次ソースであり、FRED経由では公表が遅れる場合がある点に留意する。

### 8.3 改訂（revision）の扱い

マクロ統計は後から改訂される。FRED は `realtime_start` / `realtime_end` パラメータで「ある時点で公表されていた値」を取得できる（ALFRED機能）。

```
&realtime_start=2026-05-01&realtime_end=2026-05-01
```

**バックテストではこれを使い、改訂後の値でモデルを学習しないようにする。** 実装上は `macro_series` テーブルに `vintage_date`（その値が公表された日）を持たせ、`vintage_date <= as_of` で絞る。

日次の為替や金利は改訂されないため、`vintage_date = observation_date` として扱ってよい。改訂対象は CPI、失業率、GDPなどの月次・四半期統計に限られる。

## 9. データソース優先順位と競合解決

同じ事実が複数ソースから得られる場合の優先順位を定義する。`packages/core/config/sources.yaml` の `precedence` セクション。

| データ | 第1優先 | 第2優先 | 第3優先 |
| --- | --- | --- | --- |
| 日本株 日足（リサーチ用） | J-Quants | （なし。欠損は欠損として扱う） | - |
| 日本株 日足（現在値） | yfinance | J-Quants（12週前まで） | - |
| 米国株 日足 | yfinance | Finnhub | Alpha Vantage |
| 日本株 財務 | J-Quants fins | EDINET XBRL | - |
| 米国株 財務 | EDGAR companyfacts | Finnhub | - |
| USD/JPY | FRED (DEXJPUS) | yfinance (`JPY=X`) | - |
| 日本の開示 | EDINET | TDnet | - |

競合が発生した場合は第1優先を採用するが、`data_conflicts` テーブルに差分を記録する。乖離が閾値（価格なら 1%）を超えた場合は通知する。ソース間の乖離は、どちらかのソースが壊れている強いシグナルである。

## 10. 初回バックフィル手順

日次バッチとは別のワンショットジョブとして実装する（`services/agent/jobs/backfill.py`）。

| 順序 | 対象 | 所要時間見積もり | チェックポイント粒度 |
| --- | --- | --- | --- |
| 1 | 銘柄マスタ（JP: J-Quants、US: company_tickers.json） | 5分 | なし（1リクエスト） |
| 2 | FRED 全系列 10年分 | 5分 | series_id 単位 |
| 3 | J-Quants 日足 2年分（営業日ループ） | 約100分（5 req/min） | 営業日単位 |
| 4 | yfinance 米国株 5年分（50銘柄ずつ） | 約20分 | バッチ単位 |
| 5 | yfinance 日本株 直近12週（`prices_live`） | 約10分 | バッチ単位 |
| 6 | EDGAR companyfacts（対象1,000銘柄） | 約10分（5 req/s） | CIK単位 |
| 7 | EDINET 書類一覧 過去1年分（日次ループ） | 約10分 | 日付単位 |
| 8 | 特徴量の一括計算 | 約15分 | 日付単位 |

合計約3時間。**中断・再開が可能であることが必須要件**である（PCのスリープやWindows Updateで中断される前提）。`backfill_progress` テーブルに各ステップの完了位置を持つ。

## 11. 監視すべき指標

`job_runs.metrics`（JSON）に以下を記録し、エージェントコンソール画面に表示する。

| 指標 | 意味 | 異常判定 |
| --- | --- | --- |
| `rows_fetched` | 取得行数 | 前日比で50%以上減少したら異常 |
| `rows_rejected` | 品質チェックで除外した行数 | 全体の5%超で警告 |
| `api_calls` | ソース別のAPI呼び出し回数 | レート制限の80%超で警告 |
| `retry_count` | リトライ回数 | 増加傾向は主ソースの不調 |
| `fallback_used` | フォールバック発動回数 | 0でないことが続けば主ソース見直し |
| `latest_as_of` | ソース別の最新データ日付 | 期待日付とのズレ |
| `schema_drift_count` | 想定外のレスポンス構造 | 1件でも即通知 |

## 12. 参照

- スキーマ定義: [03-data-model.md](03-data-model.md)
- 決算資料へのアクセス: [06-filings-access.md](06-filings-access.md)
- 文字コード・パス規則: [15-windows-runtime.md](15-windows-runtime.md)
- 新規データソース追加手順: `.cursor/skills/add-data-source/SKILL.md`
