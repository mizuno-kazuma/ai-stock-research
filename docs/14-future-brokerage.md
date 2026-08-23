# 14. 将来拡張: 自動発注（設計と3案の比較）

> **本章はスコープ外の将来設計である。** 現バージョンでは自動発注を実装しない。実装するのは `ExecutionAdapter` インターフェースの定義のみであり、これは「後から実装できる形を先に決めておく」ためのものである。着手条件は [13-roadmap.md](13-roadmap.md) §6-7 に記載した通りで、判断支援の精度が実績で確認できるまで着手しない。
>
> **本章の情報（API仕様、料金、レート制限、関数名）は執筆時点の調査結果である。証券会社のAPI仕様は変更されるため、実装時に必ず各社の公式ドキュメントで確認すること。** `[要検証]` を付す。

## 1. なぜ今は実装しないのか

| 理由 | 説明 |
| --- | --- |
| 誤発注のリスク | ソフトウェアのバグが直接金銭損失になる。判断支援ならバグの影響は「変な推奨が出る」で止まる |
| 精度が未検証 | 推奨の的中率が実績で確認できていない段階で自動化すると、精度の低い判断を高速に実行するだけになる |
| 得られる利便性が小さい | 日次バッチで H5 / H20 のホライズンを扱う戦略では、発注は1日に数件である。手動で十分足りる |
| 環境依存が大きい | 後述の通り、日本の証券会社のAPIは Windows デスクトップアプリへの依存が強く、クラウド移行（Phase B）と両立しない |

**発注の自動化が本当に必要になるのは、1日に何十件も発注する高頻度な戦略の場合である。** 本ツールの想定するホライズン（5-20営業日）では、その必要性は低い。

## 2. `ExecutionAdapter` インターフェース（先行定義）

証券会社ごとの差異を吸収する抽象。**この定義だけを先に決めておくことで、実装時に上位のロジックを書き直さずに済む。**

```python
# packages/core/execution/adapter.py
from abc import ABC, abstractmethod
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"

class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"

class TimeInForce(StrEnum):
    DAY = "day"              # 当日限り
    GTC = "gtc"              # 期間指定なし
    OPENING = "opening"      # 寄付
    CLOSING = "closing"      # 引け
    FAK = "fak"              # 一部執行・残数失効
    FOK = "fok"              # 全数執行・不成立時失効

class OrderStatus(StrEnum):
    PENDING = "pending"          # 送信済み・受付待ち
    ACCEPTED = "accepted"        # 取引所受付済み
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    UNKNOWN = "unknown"          # 状態不明。人間の確認が必要

class OrderRequest(BaseModel):
    client_order_id: str          # 冪等キー。ULID。二重発注防止の要
    ticker: str
    market: str                   # 'JP' | 'US'
    side: OrderSide
    quantity: Decimal             # 株数。float を使わない（丸め誤差が金銭に直結）
    order_type: OrderType
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: TimeInForce = TimeInForce.DAY
    account_type: str | None = None    # '特定' | 'NISA' | '一般'
    is_margin: bool = False
    margin_action: Literal["open", "close"] | None = None
    linked_rec_id: str | None = None   # どの推奨に基づくか（追跡用）
    dry_run: bool = True               # 既定は True。実発注は明示的に False を渡す

class OrderResult(BaseModel):
    client_order_id: str
    broker_order_id: str | None
    status: OrderStatus
    filled_quantity: Decimal = Decimal(0)
    avg_fill_price: Decimal | None = None
    submitted_at: datetime
    raw_response: dict            # 監査用に生レスポンスを保持
    error_code: str | None = None
    error_message: str | None = None

class Position(BaseModel):
    ticker: str
    market: str
    quantity: Decimal
    avg_cost: Decimal
    current_price: Decimal | None
    unrealized_pnl: Decimal | None
    account_type: str | None
    is_margin: bool = False
    as_of: datetime

class ExecutionAdapter(ABC):
    """証券会社ごとの発注APIを抽象化する。
    実装は必ず以下を満たすこと。
    - submit は client_order_id により冪等であること（同じIDで2回呼んでも1回しか発注しない）
    - すべての操作を order_audit_log に記録すること
    - dry_run=True のとき、外部に一切のリクエストを送らないこと
    """
    broker_name: str
    supports_markets: list[str]
    supports_margin: bool
    max_orders_per_sec: float

    @abstractmethod
    def submit(self, req: OrderRequest) -> OrderResult: ...

    @abstractmethod
    def cancel(self, broker_order_id: str) -> OrderResult: ...

    @abstractmethod
    def positions(self) -> list[Position]: ...

    @abstractmethod
    def orders(self, *, status: OrderStatus | None = None,
               since: datetime | None = None) -> list[OrderResult]: ...

    @abstractmethod
    def health(self) -> AdapterHealth:
        """発注可能な状態かを返す。
        デスクトップアプリ依存の実装では、アプリが起動しログイン済みかを確認する。"""
```

### 2.1 `Decimal` を使う理由

数量と価格に `float` を使わない。`0.1 + 0.2 != 0.3` の丸め誤差が、株数や金額の計算で実際の損失に繋がる。DB のスキーマも `NUMERIC` 相当の型を使う。

### 2.2 `client_order_id` による冪等性

ネットワークエラーで応答が返らなかった場合、「発注されたのか分からない」状態になる。これが自動発注で最も危険な状況である。

```python
def submit_with_idempotency(adapter: ExecutionAdapter, req: OrderRequest) -> OrderResult:
    """応答が不明な場合、リトライではなく状態照会を行う。
    盲目的なリトライは二重発注のリスクがある。"""
    existing = audit_log.find_by_client_order_id(req.client_order_id)
    if existing and existing.status != OrderStatus.UNKNOWN:
        return existing                          # 既に発注済み
    audit_log.record_attempt(req)
    try:
        result = adapter.submit(req)
    except (TimeoutError, ConnectionError):
        # リトライしない。状態を照会する
        orders = adapter.orders(since=req_submitted_at - timedelta(minutes=5))
        match = find_matching(orders, req)
        if match:
            audit_log.record_result(match)
            return match
        # 本当に不明な場合。人間の確認を要求する
        audit_log.record_unknown(req)
        alerts.create(severity="error", category="execution",
                      title_ja="発注結果が不明です。証券会社の画面で確認してください",
                      body_ja=f"{req.ticker} {req.side} {req.quantity}株")
        return OrderResult(status=OrderStatus.UNKNOWN, ...)
    audit_log.record_result(result)
    return result
```

**タイムアウト時にリトライしないことが重要である。** リトライは二重発注を招く。代わりに状態照会を行い、それでも不明なら人間に確認を求める。

## 3. 案1: 楽天証券 MarketSpeed II RSS

### 3.1 概要

楽天証券は個人向けの REST API を提供していない。`[要検証]` 唯一の公式な発注自動化経路は **MarketSpeed II RSS**（Excel アドイン）である。

| 項目 | 内容 |
| --- | --- |
| 方式 | Excel のワークシート関数として提供されるアドイン |
| 必要環境 | Windows + Microsoft Excel + MarketSpeed II（ログイン状態） |
| 費用 | 無料（一定の条件下。`[要検証]` 楽天証券の口座条件を確認） |
| 対応市場 | 日本株（現物・信用）、先物・オプション |
| REST API | **存在しない** |

### 3.2 発注関数

`[要検証]` 関数名と引数は楽天証券の公式マニュアルで確認する。

| 関数 | 用途 |
| --- | --- |
| `RssStockOrder` | 現物株の新規注文 |
| `RssMarginOpenOrder` | 信用の新規建注文 |
| `RssMarginCloseOrder` | 信用の返済注文 |
| `RssModifyOrder` | 注文の訂正 |
| `RssCancelOrder` | 注文の取消 |

**呼び出し規約（この設計が独特で、実装上の注意点になる）**:

- 第1引数: 注文ID（利用者が採番する任意の識別子）
- 第2引数: トリガー。**この値を `0` から `1` に変化させた瞬間に発注される**
- 以降の引数: 銘柄コード、売買区分、数量、価格、執行条件など

```
=RssStockOrder(A1, B1, "7203", "買い", 100, "指値", 3100, "当日限り")
                ^   ^
             注文ID  トリガー（0→1で発注）
```

トリガー方式である理由は、Excel の再計算が任意のタイミングで走るためである。値の変化を発注の合図にすることで、意図しない再計算による誤発注を防いでいる。

**逆に言えば、トリガーセルの値を誤って書き換えると発注される。** この設計を踏まえ、トリガーセルは専用のセルとして隔離し、他の計算式から参照させない。

### 3.3 Python からの制御（`xlwings`）

```python
# 【将来実装の参考コード。現バージョンでは実装しない】
import xlwings as xw

class RakutenRssAdapter(ExecutionAdapter):
    """MarketSpeed II RSS を xlwings 経由で制御する。
    Windows ネイティブ側で動作する必要がある（WSL2 からは不可）。"""
    broker_name = "rakuten_rss"
    supports_markets = ["JP"]
    supports_margin = True
    max_orders_per_sec = 1.0        # 実測ベースで保守的に設定する

    def __init__(self, workbook_path: Path):
        self.book = xw.Book(workbook_path)
        self.sheet = self.book.sheets["Order"]

    def health(self) -> AdapterHealth:
        """MarketSpeed II が起動しログイン済みかを確認する。
        RSS 関数はアプリ未起動時にエラー値を返すため、
        既知の情報取得関数（RssMarketPrice 等）で疎通を確認する。"""
        self.sheet.range("Z1").formula = '=RssMarketPrice("7203","現在値")'
        self.book.app.calculate()
        val = self.sheet.range("Z1").value
        if val is None or isinstance(val, str):
            return AdapterHealth(ok=False,
                                 reason_ja="MarketSpeed II が起動していないか未ログインです")
        return AdapterHealth(ok=True)

    def submit(self, req: OrderRequest) -> OrderResult:
        if req.dry_run:
            return OrderResult(status=OrderStatus.PENDING, raw_response={"dry_run": True}, ...)
        row = self._next_row()
        self.sheet.range(f"A{row}").value = req.client_order_id
        self.sheet.range(f"B{row}").value = 0                # トリガーを 0 に初期化
        self.sheet.range(f"C{row}").formula = self._build_formula(req, row)
        self.book.app.calculate()
        self.sheet.range(f"B{row}").value = 1                # 0 → 1 で発注
        self.book.app.calculate()
        return self._read_result(row)
```

### 3.4 WSL2 との組み合わせ（ブリッジ構成）

**WSL2 から Excel の COM を触ることはできない。** `xlwings` は Windows の COM インターフェースに依存しており、WSL2 は別のカーネル上で動く Linux 環境であるため、Windows のプロセスに COM 経由でアクセスできない。

したがって以下の二層構成にする。

```
┌─────────────────────────────────────────────────────────┐
│ Windows 11 ホスト                                       │
│                                                         │
│  ┌───────────────────────────────────────────────┐      │
│  │ 発注ブリッジ（Windows ネイティブ Python）      │      │
│  │  FastAPI（127.0.0.1:8765 のみにバインド）      │      │
│  │    POST /orders    → xlwings → Excel → RSS    │      │
│  │    GET  /positions                            │      │
│  │    GET  /health                               │      │
│  └───────────────┬───────────────────────────────┘      │
│                  │ COM                                  │
│  ┌───────────────▼───────────────┐                      │
│  │ Excel + MarketSpeed II RSS     │                     │
│  └───────────────┬───────────────┘                      │
│                  │                                       │
│  ┌───────────────▼───────────────┐                      │
│  │ MarketSpeed II（ログイン状態） │                      │
│  └────────────────────────────────┘                     │
│                                                         │
│  ┌───────────────────────────────────────────────┐      │
│  │ WSL2 (Ubuntu)                                 │      │
│  │  services/agent                               │      │
│  │    RakutenBridgeAdapter                       │      │
│  │      → http://localhost:8765/orders           │      │
│  └───────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────┘
```

**`networkingMode=mirrored` により、WSL2 から Windows ホストの `localhost:8765` に到達できる。** これがこの構成が成立する理由である。従来の NAT モードでは WSL2 から Windows の localhost に直接到達できず、ホストIPを動的に取得する処理が必要だった。

```python
# WSL2 側のアダプタ実装
class RakutenBridgeAdapter(ExecutionAdapter):
    """Windows ホスト側の発注ブリッジを HTTP 経由で呼ぶ。
    mirrored networking のため localhost で到達できる。"""
    broker_name = "rakuten_rss_bridge"

    def __init__(self, base_url: str = "http://localhost:8765"):
        self.client = httpx.Client(base_url=base_url, timeout=30.0)

    def submit(self, req: OrderRequest) -> OrderResult:
        r = self.client.post("/orders", json=req.model_dump(mode="json"))
        r.raise_for_status()
        return OrderResult.model_validate(r.json())
```

**ブリッジのセキュリティ**: `127.0.0.1` のみにバインドし、外部から到達できないようにする。加えて共有シークレット（`.env` の `BRIDGE_TOKEN`）をヘッダで検証する。発注機能を持つエンドポイントを無防備に開けない。

### 3.5 楽天RSS 案の制約と注意点

| 制約 | 詳細 |
| --- | --- |
| Windows + Excel が必須 | Excel のライセンスが必要。クラウド移行（Phase B）と両立しない |
| MarketSpeed II のログインが必須 | セッションが切れると発注できない。`health()` での確認が必須 |
| レイテンシ | **数百ミリ秒から数秒**。Excel の再計算を経由するため。高頻度な用途には不適 |
| Excel のメモリリーク | 長時間稼働でメモリ使用量が増加するとの報告がある `[要検証]`。定期的な Excel の再起動を組み込む（日次でブリッジプロセスと Excel を再起動する設計にする） |
| **他のワークブックを開くと発注不可になる** | MarketSpeed II RSS の安全機構として、対象以外のワークブックを開くと状態が「発注不可」に戻る。**この Excel を他の作業に使ってはならない**（専用の Excel インスタンスを立てる） |
| 状態管理が Excel のセル | プロセスクラッシュ時に注文状態が不明になりやすい。`order_audit_log` への記録を Excel への書き込みより先に行う |
| 訂正・取消の複雑さ | 注文IDの管理を自前で行う必要がある |

**「他のワークブックを開くと発注不可になる」という挙動は、実装後に気付くと原因の特定が難しい。** ブリッジプロセスは専用の Excel インスタンス（`xw.App(visible=False, add_book=False)`）を起動し、そこに専用ワークブックだけを開く。

### 3.6 楽天RSS 案の利点

| 利点 | 詳細 |
| --- | --- |
| 本体と同じPCに同居できる | 既に Windows 11 で運用しているため追加ハードウェアが不要 |
| 楽天証券の口座をそのまま使える | 口座を移す必要がない |
| 情報取得関数も豊富 | 板情報、時価、四本値などを Excel 関数で取得できる（本ツールでは J-Quants / yfinance を使うので不要だが、補助的に使える） |

## 4. 案2: 三菱UFJ eスマート証券 kabuステーションAPI

### 4.1 概要

旧 auカブコム証券。**日本の個人投資家向けで唯一の公式 REST API** である。`[要検証]`

| 項目 | 内容 |
| --- | --- |
| 方式 | REST API（HTTP）+ WebSocket（時価配信） |
| 必要環境 | Windows + kabuステーション（デスクトップアプリ、ログイン状態） |
| 費用 | **Professional プラン以上で無料** `[要検証]`（プランの条件は公式で確認） |
| 対応市場 | 日本株（現物・信用）、先物・オプション |
| レート制限 | **発注系は 10 リクエスト/秒**（2026年7月に引き上げられた `[要検証]`。以前は 5/秒だった） |
| 認証 | APIパスワードでトークンを取得し、`X-API-KEY` ヘッダに付与 `[要検証]` |

### 4.2 なぜこちらの方が素直か

**Excel ブリッジが不要である。** kabuステーションアプリがローカルに HTTP サーバーを立てるため、HTTP クライアントだけで完結する。

```
┌─────────────────────────────────────────────────────┐
│ Windows 11 ホスト                                   │
│                                                     │
│  ┌────────────────────────────────┐                 │
│  │ kabuステーション（ログイン状態） │                │
│  │   ローカル HTTP サーバー         │                │
│  │   localhost:18080（本番）        │                │
│  │   localhost:18081（検証）        │  [要検証]      │
│  └────────────┬───────────────────┘                 │
│               │                                      │
│  ┌────────────▼───────────────────────────┐         │
│  │ WSL2 (Ubuntu)                          │         │
│  │  services/agent                        │         │
│  │    KabuStationAdapter                  │         │
│  │      → http://localhost:18080/kabusapi │         │
│  └────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────┘
```

**mirrored networking により WSL2 から直接 `localhost:18080` に到達できる。** ブリッジプロセスを書く必要がない。これが案1に対する最大の利点である。

### 4.3 主要エンドポイント

`[要検証]` すべて公式の API リファレンスで確認する。

| 用途 | エンドポイント（想定） |
| --- | --- |
| トークン取得 | `POST /kabusapi/token`（body に APIパスワード） |
| 発注（現物・信用） | `POST /kabusapi/sendorder` |
| 注文取消 | `PUT /kabusapi/cancelorder` |
| 注文一覧 | `GET /kabusapi/orders` |
| 残高照会 | `GET /kabusapi/positions` |
| 時価 | `GET /kabusapi/board/{symbol}@{exchange}` |
| 銘柄登録（時価配信用） | `PUT /kabusapi/register` |
| 余力照会 | `GET /kabusapi/wallet/cash` |
| WebSocket（時価配信） | `ws://localhost:18080/kabusapi/websocket` |

```python
# 【将来実装の参考コード。現バージョンでは実装しない】
class KabuStationAdapter(ExecutionAdapter):
    broker_name = "kabu_station"
    supports_markets = ["JP"]
    supports_margin = True
    max_orders_per_sec = 10.0      # [要検証] 2026年7月に 5 → 10 に引き上げ

    def __init__(self, base_url: str, api_password: SecretStr):
        self.client = httpx.Client(base_url=base_url, timeout=15.0)
        self._token: str | None = None
        self._api_password = api_password

    def _ensure_token(self) -> str:
        if self._token is None:
            r = self.client.post("/kabusapi/token",
                                 json={"APIPassword": self._api_password.get_secret_value()})
            r.raise_for_status()
            self._token = r.json()["Token"]
        return self._token

    def health(self) -> AdapterHealth:
        """kabuステーションが起動しログイン済みかを確認する。"""
        try:
            self._ensure_token()
            return AdapterHealth(ok=True)
        except httpx.ConnectError:
            return AdapterHealth(ok=False,
                                 reason_ja="kabuステーションが起動していません")
        except httpx.HTTPStatusError:
            return AdapterHealth(ok=False,
                                 reason_ja="APIパスワードが不正、または未ログインです")

    def submit(self, req: OrderRequest) -> OrderResult:
        if req.dry_run:
            return OrderResult(status=OrderStatus.PENDING, raw_response={"dry_run": True}, ...)
        payload = self._to_kabu_payload(req)     # 各フィールドのコード値への変換
        r = self.client.post("/kabusapi/sendorder", json=payload,
                             headers={"X-API-KEY": self._ensure_token()})
        return self._to_order_result(req, r)
```

### 4.4 kabuステーション案の制約

| 制約 | 詳細 |
| --- | --- |
| kabuステーションの起動が必須 | デスクトップアプリへの依存は案1と同じ。クラウド移行と両立しない |
| Professional プラン以上が条件 | `[要検証]` プランの条件（預かり資産や取引実績）を確認する |
| 口座を移す必要がある | 既に楽天証券を使っている場合、新規口座開設と資金移動が必要 |
| Windows 依存 | kabuステーションは Windows のみ `[要検証]` |
| トークンの有効期限 | セッション切れの再取得処理が必要 |

### 4.5 案1 との比較

| 観点 | 楽天 RSS | kabuステーション API |
| --- | --- | --- |
| 実装の複雑さ | 高（Excel ブリッジが必要） | **低（HTTP のみ）** |
| WSL2 との親和性 | ブリッジ経由 | **直接到達可能** |
| レイテンシ | 数百ms - 数秒 | **数十ms** |
| Excel ライセンス | 必要 | 不要 |
| レート制限 | 実測ベース（保守的に 1/秒） | **10/秒（明示）** |
| 口座 | 既存を使える | 新規開設が必要 |
| デスクトップアプリ依存 | あり | あり |
| ドキュメント | Excel マニュアル | **API リファレンス（Swagger）** |
| 状態管理 | Excel のセル（脆い） | **HTTP レスポンス（明快）** |

**技術的には kabuステーション API が明確に優位である。** 実装時に自動発注を採用する場合、口座開設の手間を許容できるなら kabuステーション API を選ぶ。

## 5. 案3: Alpaca / Interactive Brokers（米国株）

### 5.1 Alpaca

| 項目 | 内容 |
| --- | --- |
| 方式 | REST API + WebSocket。**完全にクラウド対応** |
| 必要環境 | なし（デスクトップアプリ不要） |
| 対応市場 | 米国株、ETF、暗号資産 |
| 費用 | 手数料無料（`[要検証]` 日本居住者の口座開設可否を確認する。これが最大の不確定要素） |
| ペーパートレード | **無料の検証環境がある**。これが大きな利点 |
| 認証 | API Key + Secret |

```python
# 【将来実装の参考コード】
class AlpacaAdapter(ExecutionAdapter):
    broker_name = "alpaca"
    supports_markets = ["US"]
    supports_margin = True
    max_orders_per_sec = 3.0      # [要検証]

    def __init__(self, key: SecretStr, secret: SecretStr, paper: bool = True):
        base = ("https://paper-api.alpaca.markets" if paper
                else "https://api.alpaca.markets")
        self.client = httpx.Client(base_url=base, headers={
            "APCA-API-KEY-ID": key.get_secret_value(),
            "APCA-API-SECRET-KEY": secret.get_secret_value()})

    def submit(self, req: OrderRequest) -> OrderResult:
        if req.dry_run:
            return OrderResult(status=OrderStatus.PENDING, raw_response={"dry_run": True}, ...)
        r = self.client.post("/v2/orders", json={
            "symbol": req.ticker,
            "qty": str(req.quantity),
            "side": req.side.value,
            "type": req.order_type.value,
            "time_in_force": self._map_tif(req.time_in_force),
            "limit_price": str(req.limit_price) if req.limit_price else None,
            "client_order_id": req.client_order_id,    # Alpaca が冪等性を保証する
        })
        return self._to_order_result(req, r)
```

**`client_order_id` を Alpaca 側が受け付け、重複を拒否する。** これにより冪等性がAPI側で保証される。案1・案2では自前で管理する必要がある。

### 5.2 Interactive Brokers (IBKR)

| 項目 | 内容 |
| --- | --- |
| 方式 | TWS API（TCP ソケット）または Client Portal API（REST） |
| 必要環境 | TWS API は **IB Gateway または TWS の起動が必須**（デスクトップアプリ依存）。Client Portal API も認証にゲートウェイが必要 `[要検証]` |
| 対応市場 | 米国株、日本株、その他多数 |
| 費用 | 取引手数料あり |
| 特徴 | 日本株と米国株を1つの口座で扱える |

**IBKR は日本株と米国株を同一口座で扱えるため、アダプタが1つで済む利点がある。** ただし TWS / IB Gateway の起動が必要な点は案1・案2と同じ制約であり、クラウド移行の障害になる。

Client Portal API（REST）を使えばゲートウェイの常駐を減らせるが、認証フローが複雑で、セッション維持のための定期的なリクエストが必要になる `[要検証]`。

### 5.3 米国株案の利点

**Phase B（クラウド移行）後も動く。** これが日本の証券会社との決定的な違いである。Alpaca は完全にクラウド対応であり、デスクトップアプリを必要としない。

したがって、**もし自動発注を実装するなら、米国株から始めるのが技術的に最も素直である**。ペーパートレード環境で検証できることも大きい。

## 6. 3案の総合比較

| 観点 | 楽天 RSS | kabuステーション | Alpaca | IBKR |
| --- | --- | --- | --- | --- |
| 対応市場 | JP | JP | US | JP + US |
| REST API | なし | **あり** | **あり** | あり（制約付き） |
| デスクトップアプリ依存 | Excel + MS2 | kabuステーション | **なし** | TWS / Gateway |
| WSL2 からの到達 | ブリッジ必要 | **直接** | **直接** | 直接（要 Gateway） |
| クラウド移行との両立 | 不可 | 不可 | **可能** | 不可（実質） |
| 検証環境 | なし | 検証環境あり `[要検証]` | **ペーパートレード** | ペーパートレード |
| レイテンシ | 数百ms-数秒 | 数十ms | 数十-数百ms | 数十ms |
| 冪等性の保証 | 自前 | 自前 | **API側** | 自前 |
| 実装難易度 | 高 | 中 | **低** | 高 |
| 口座開設 | 既存 | 必要 | 必要（要確認） | 必要 |

### 6.1 推奨する順序（実装する場合）

1. **Alpaca のペーパートレードで `ExecutionAdapter` の実装と安全機構を検証する**（実弾を使わずに全経路を確認できる）
2. Alpaca の実口座で米国株の自動発注を運用する（クラウド移行後も動く）
3. 日本株が必要になったら kabuステーション API を追加する
4. 楽天 RSS は、口座を移せない事情がある場合の最後の選択肢とする

## 7. 安全機構（どの案でも必須）

自動発注を実装する場合、以下は例外なく必須である。

### 7.1 発注前の二重確認

```python
class TradeConfirmation(BaseModel):
    """発注前に人間が確認する内容。UIに表示し、明示的な承認を得る。"""
    orders: list[OrderRequest]
    total_value: Decimal
    currency: str
    portfolio_impact: dict          # 発注後のポートフォリオ構成比
    linked_recommendations: list[str]
    bear_cases: list[str]           # 各推奨の弱気論拠を再掲する
    risk_checks: list[RiskCheck]
    expires_at: datetime            # 確認の有効期限（5分）
    confirmation_token: str         # ワンタイムトークン
```

**確認画面に bear case を再掲する。** 発注の直前に「この判断が間違っている可能性」を目にする設計にする。これは心理的な安全装置として意味がある。

確認の段階を2つにする。

1. **第1段階**: 発注内容の一覧と影響を表示。「確認する」を押す
2. **第2段階**: 銘柄と数量を再表示し、**数量を手で入力させる**（タイプ・トゥ・コンファーム）。「発注する」を押す

第2段階で数量を手入力させるのは、慣れによる無意識のクリックを防ぐためである。

### 7.2 リスクチェック（発注前に自動実行）

| チェック | 既定値 | 違反時 |
| --- | --- | --- |
| 1銘柄あたりの上限比率 | ポートフォリオの 10% | 発注を拒否 |
| 1回の発注金額の上限 | 50万円 / $5,000 | 発注を拒否 |
| 1日の発注件数の上限 | 5件 | 発注を拒否 |
| 1日の発注金額の合計上限 | 200万円 / $20,000 | 発注を拒否 |
| セクター集中 | 1セクター 30% | 警告（承認で続行可） |
| 現金余力 | 発注後に余力が20%以上残る | 発注を拒否 |
| 指値と現在値の乖離 | 5% 以内 | 発注を拒否（誤入力の検出） |
| 数量の妥当性 | 単元株の整数倍（日本株） | 発注を拒否 |
| 市場の営業時間 | 取引時間内 | 発注を拒否（または予約） |
| 決算発表日 | 当日・前営業日は警告 | 警告 |
| 推奨の鮮度 | 推奨から3営業日以内 | 発注を拒否（古い推奨での発注を防ぐ） |
| Critic の判定 | `approved` のみ | `rejected` の推奨に基づく発注を拒否 |

**「指値と現在値の乖離が5%以内」のチェックは、桁の入力ミス（3,100円を31,000円と入力）を検出する。** これは単純だが効果が大きい。

### 7.3 キルスイッチ

```python
class ExecutionKillSwitch:
    """発注機能を即座に停止する。以下のいずれかで発動する。"""
    def is_active(self) -> bool:
        return any([
            self.settings.get_bool("execution.kill_switch"),      # 手動
            os.environ.get("EXECUTION_KILL_SWITCH") == "1",       # 環境変数
            (KILL_FILE := Path("/tmp/EXECUTION_KILL")).exists(),  # ファイルの存在
            self.daily_order_count >= self.daily_order_cap,        # 件数上限
            self.daily_order_value >= self.daily_value_cap,        # 金額上限
            self.consecutive_errors >= 3,                          # 連続エラー
            self.adapter.health().ok is False,                     # アダプタ不調
        ])
```

**ファイルの存在によるキルスイッチを用意する理由**: UI が壊れていても、SSH やファイルマネージャから `touch /tmp/EXECUTION_KILL` するだけで停止できる。最後の手段として単純な経路を残す。

### 7.4 監査ログ

```sql
CREATE TABLE order_audit_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    client_order_id     TEXT NOT NULL,
    broker              TEXT NOT NULL,
    broker_order_id     TEXT,
    event               TEXT NOT NULL,   -- 'attempt'|'submitted'|'accepted'|'filled'
                                          -- |'canceled'|'rejected'|'unknown'|'blocked'
    ticker              TEXT NOT NULL,
    market              TEXT NOT NULL,
    side                TEXT NOT NULL,
    quantity            TEXT NOT NULL,   -- Decimal を文字列で保存（精度を落とさない）
    price               TEXT,
    order_type          TEXT NOT NULL,
    dry_run             BOOLEAN NOT NULL,
    linked_rec_id       TEXT,
    risk_checks_passed  TEXT,            -- JSON
    confirmation_token  TEXT,
    confirmed_by        TEXT,
    request_payload     TEXT,            -- JSON。送信した内容そのまま
    response_payload    TEXT,            -- JSON。受信した内容そのまま
    error_code          TEXT,
    error_message       TEXT,
    occurred_at         TEXT NOT NULL,
    git_commit          TEXT
);
CREATE INDEX idx_audit_client_order ON order_audit_log(client_order_id, occurred_at);
```

**リクエストとレスポンスを丸ごと保存する。** 発注に関する問題は事後の検証が不可欠であり、「何を送って何が返ったか」が残っていないと原因が特定できない。

### 7.5 段階的な有効化

自動発注を実装したら、以下の順序で段階的に有効化する。各段階で最低1ヶ月運用する。

| 段階 | 内容 |
| --- | --- |
| 1 | `dry_run=True` 固定。ログのみ記録し、実際には発注しない |
| 2 | ペーパートレード環境（Alpaca / kabuステーション検証環境）で実発注 |
| 3 | 実口座、最小単元（1株 / 100株）、1日1件まで |
| 4 | 実口座、通常サイズ、1日1件まで |
| 5 | 実口座、通常サイズ、1日3件まで |
| 6 | 通常運用（1日5件まで） |

**各段階で `order_audit_log` を確認し、想定と一致していることを検証してから次に進む。** 段階1で発見できる問題（数量の単位、価格の丸め、TIFのマッピング）は多い。

## 8. 実装しないという選択

**本章を読んだ上で、自動発注を実装しないという結論も妥当である。**

以下を考えると、実装のコストとリスクに対する見返りは小さい。

- 日次バッチで H5 / H20 のホライズンを扱う戦略では、発注は1日に数件
- 手動発注に要する時間は1件あたり1分程度
- 自動発注の実装と検証には、安全機構を含めると相当な作業量になる
- デスクトップアプリ依存により、常時稼働の要件が厳しくなる（Windows Update での再起動後に kabuステーションが自動ログインしない等）
- 誤発注のリスクは常に残る

**判断支援の精度を上げることに時間を使う方が、期待される効果は大きい。** 本章は「後から実装できる形を先に決めておく」ためのものであり、実装を推奨するものではない。

## 9. 参照

- ロードマップと着手条件: [13-roadmap.md](13-roadmap.md) §6-7
- WSL2 と Windows ホストの通信: [15-windows-runtime.md](15-windows-runtime.md) §2
- 売買記録（手動）: [09-api-spec.md](09-api-spec.md) §2.9
