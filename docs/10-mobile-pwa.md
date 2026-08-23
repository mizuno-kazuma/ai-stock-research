# 10. PWA・モバイル配信・クラウド移行

## 1. 方針

スマートフォンからの利用を、**ネイティブアプリを作らずに PWA で実現する**。理由は以下。

| 理由 | 詳細 |
| --- | --- |
| 単一コードベース | `apps/web` の Next.js アプリがそのままモバイル対応になる |
| Phase B への連続性 | クラウドに移した後も同じアプリが動く。ネイティブアプリならストア配布の問題が発生する |
| ストア審査が不要 | 個人用ツールをストアに出す必要がない |
| 更新が即時 | Service Worker の更新のみ |

トレードオフとして、iOS では Web Push が制約される（ホーム画面追加が必要）ため、**通知を必須機能にしない設計**とする（§5）。

## 2. Phase A: Tailscale 経由の配信

### 2.1 構成

```
[スマートフォン]                    [Windows 11 PC（自宅）]
  Tailscale アプリ                    Tailscale（Windows ホスト側のみ）
       │                                    │
       │  tailnet（WireGuard）              │  networkingMode=mirrored
       └────────────────────────────────────┤
                                            ▼
                                       WSL2 (Ubuntu)
                                         :3000  Next.js
                                         :8000  FastAPI
```

**Tailscale を Windows ホスト側のみに入れる。** WSL2 内にも入れると、Tailscale のパケットが二重にカプセル化されて MTU が不足し通信が壊れる（Tailscale 公式が非推奨としている）。詳細は [15-windows-runtime.md](15-windows-runtime.md) §3。

`networkingMode=mirrored` により、WSL2 内で `0.0.0.0:3000` にバインドしたサービスが Windows ホストの `localhost:3000` および Tailscale IP で到達可能になる。

### 2.2 アクセス URL

| 経路 | URL |
| --- | --- |
| PC のブラウザ（ローカル） | `http://localhost:3000` |
| スマートフォン（Tailscale 経由、MagicDNS） | `http://<machine-name>:3000` |
| スマートフォン（Tailscale IP 直指定） | `http://100.x.y.z:3000` |
| Tailscale Serve 経由（HTTPS） | `https://<machine-name>.<tailnet>.ts.net` |

### 2.3 HTTPS の必要性

**PWA の一部機能（Service Worker、`beforeinstallprompt`、通知）は HTTPS または `localhost` を要求する。** Tailscale IP への HTTP アクセスでは Service Worker が登録できない。

解決策として Tailscale Serve を使う。

```powershell
# Windows ホスト側で実行
tailscale serve --bg --https=443 http://localhost:3000
```

これにより `https://<machine-name>.<tailnet>.ts.net` で有効な TLS 証明書付きのアクセスが可能になる（Tailscale が Let's Encrypt 証明書を自動発行する）。`[要検証]` Tailscale Serve のコマンド構文はバージョンによって変わるため、実装時に `tailscale serve --help` で確認する。

**注意**: `tailscale funnel`（インターネットへの公開）は使わない。tailnet 内のみに限定する。

### 2.4 Tailscale Serve が使えない場合のフォールバック

自己署名証明書 + `mkcert` でローカル CA を作り、スマートフォンに CA 証明書をインストールする方法もあるが、手順が煩雑で iOS では追加設定が必要になる。**まず Tailscale Serve を試し、それで解決するなら他の方法を検討しない。**

HTTP のままでも以下は動く（Service Worker が不要な機能）。

- 通常のページ閲覧
- API 呼び出し
- TanStack Query によるキャッシュ（メモリ内）

動かないのは、オフライン対応、ホーム画面への「アプリとして」の追加、Web Push である。

## 3. PWA の実装

### 3.1 manifest

```json
// apps/web/public/manifest.webmanifest
{
  "name": "AI Stock Research",
  "short_name": "Research",
  "description": "日米株式のAIリサーチ・売買判断支援",
  "start_url": "/?source=pwa",
  "scope": "/",
  "display": "standalone",
  "orientation": "portrait-primary",
  "background_color": "#0B0E14",
  "theme_color": "#0B0E14",
  "lang": "ja",
  "dir": "ltr",
  "icons": [
    {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
    {"src": "/icons/maskable-512.png", "sizes": "512x512", "type": "image/png",
     "purpose": "maskable"}
  ],
  "shortcuts": [
    {"name": "推奨銘柄", "url": "/recommendations", "icons": [{"src": "/icons/rec-96.png", "sizes": "96x96"}]},
    {"name": "決算資料", "url": "/filings", "icons": [{"src": "/icons/filing-96.png", "sizes": "96x96"}]},
    {"name": "ポートフォリオ", "url": "/portfolio", "icons": [{"src": "/icons/pf-96.png", "sizes": "96x96"}]}
  ]
}
```

`background_color` と `theme_color` はダークファーストのため暗色にする（[ui/design-system.md](ui/design-system.md) の `--bg-base`）。

`shortcuts` は Android のロングプレスメニューに出る。iOS では機能しないが害はない。

### 3.2 Service Worker の戦略

Next.js App Router では `next-pwa` の代替として Serwist（`@serwist/next`）を使う `[要検証]`。または手書きの Service Worker を `public/sw.js` に置く。

**キャッシュ戦略を対象別に定義する。**

| 対象 | 戦略 | 理由 |
| --- | --- | --- |
| アプリシェル（HTML/JS/CSS） | Stale-While-Revalidate | 即座に表示し、裏で更新 |
| 静的アセット（アイコン、フォント） | Cache First（最大30日） | 変わらない |
| `/api/v1/dashboard`, `/recommendations` | Network First（フォールバックでキャッシュ） | 最新を優先。オフラインなら前回の内容を出す |
| `/api/v1/documents/{}/file`（PDF） | Cache First（最大100MB、LRU） | 資料は不変。一度読んだものはオフラインで読める |
| `/api/v1/screener`（POST） | キャッシュしない | クエリが多様 |
| `/api/v1/agent/events`（SSE） | キャッシュしない | |
| `/api/v1/trades`（POST/PATCH） | Background Sync キューに入れる | オフラインで入力した売買記録を後で送信 |

```js
// キャッシュした API レスポンスを表示する場合、必ず「オフライン表示」を明示する
// レスポンスヘッダに X-From-Cache を付け、UI がバナーを出す
```

**オフライン時にキャッシュされた古いデータを、それが古いと示さずに表示してはならない。** 株価や推奨は鮮度が本質的に重要であり、「昨日のデータを今日のものとして見る」のは致命的である。UIは以下を表示する。

```
[オフライン]  2026-08-22 09:35 のデータを表示しています
```

### 3.3 Background Sync（売買記録のオフライン入力）

売買記録は移動中に入力したいことが多いため、オフライン対応を優先する。

```js
// 送信失敗時は IndexedDB にキューし、オンライン復帰時に送信
self.addEventListener("sync", (event) => {
  if (event.tag === "sync-trades") {
    event.waitUntil(flushTradeQueue());
  }
});
```

`[要検証]` iOS Safari は Background Sync API を実装していない。iOS では「アプリを次に開いたときに送信する」フォールバックを実装する（`visibilitychange` イベントでキューをフラッシュ）。

## 4. モバイル UI の要件

詳細は [ui/interaction-patterns.md](ui/interaction-patterns.md)。ここでは配信に関わる要件のみ。

| 要件 | 内容 |
| --- | --- |
| ビューポート | `width=device-width, initial-scale=1, viewport-fit=cover` |
| セーフエリア | `env(safe-area-inset-*)` を使い、iPhone のノッチ・ホームバーを避ける |
| ボトムナビゲーション | モバイルでは下部固定の5タブ（ダッシュボード / 推奨 / 検索 / 資料 / ポートフォリオ） |
| タップターゲット | 最小 44x44 px |
| 数値の可読性 | 等幅数字（`font-variant-numeric: tabular-nums`）で桁を揃える |
| チャート | 横スクロールさせない。期間セレクタで表示範囲を切り替える |
| テーブル | モバイルではカードレイアウトに変換する（横スクロールテーブルを避ける） |
| PDF 表示 | `Content-Disposition: inline` でアプリ内表示。ダウンロードさせない |
| プルダウンで更新 | 実装する（モバイルでの期待動作） |
| 通信量 | 初回ロード後は API のみ。1画面あたり 50KB 以下を目標 |

### 4.1 モバイルで優先する画面

すべての画面をモバイル対応させるが、実際にモバイルで使われるのは以下に偏る。

| 優先度 | 画面 | 用途 |
| --- | --- | --- |
| 高 | ダッシュボード | 朝の確認 |
| 高 | 推奨銘柄 | 通勤中の確認 |
| 高 | 決算資料ハブ | 開示のチェックとPDF閲覧 |
| 高 | ポートフォリオ・売買日誌 | 売買記録の入力 |
| 中 | 銘柄詳細 | |
| 中 | 為替・マクロ | |
| 低 | スクリーナー | 条件入力が多いためPC向け |
| 低 | モデルラボ | PC向け |
| 低 | エージェントコンソール | PC向け |
| 低 | 設定 | |

**低優先度の画面はモバイルで「PCでの閲覧を推奨」と表示してもよい。** 全画面を完璧にモバイル対応させるコストを、使われる画面に集中させる。

## 5. 通知

### 5.1 iOS の制約

iOS の Web Push は**ホーム画面に追加した PWA でのみ動作する**（Safari のタブでは動かない）。`[要検証]` iOS のバージョンによって挙動が変わるため、実装時に確認する。

したがって通知を必須機能にしない。以下の3段階で設計する。

| 段階 | 方式 | 実装コスト | 確実性 |
| --- | --- | --- | --- |
| 1（既定） | アプリ内のアラート一覧 + バッジ | 低 | アプリを開かないと気付かない |
| 2 | Web Push（ホーム画面追加が前提） | 中 | iOS では設定が必要 |
| 3 | 外部チャネル（メール / Slack / Discord Webhook / LINE Notify） | 低 | **最も確実** |

**段階3を推奨する。** Webhook で通知を送るのは実装が単純で、OS の制約を受けない。

```python
# packages/core/notify/webhook.py
class WebhookNotifier:
    def send(self, alert: Alert) -> None:
        payload = {"text": f"[{alert.severity}] {alert.title_ja}\n{alert.body_ja}"}
        httpx.post(settings.notify_webhook_url, json=payload, timeout=10)
```

`.env` の `NOTIFY_WEBHOOK_URL` を設定するだけで有効になる（未設定なら段階1のみ）。

### 5.2 通知する事象

| 事象 | 既定 |
| --- | --- |
| 日次バッチの完了（推奨が n 件生成された） | 有効 |
| 日次バッチの失敗 | 有効 |
| 保有銘柄の新規開示（特に業績予想の修正） | 有効 |
| LLM コストキャップの80%到達 | 有効 |
| データソースの3日連続失敗 | 有効 |
| 保有銘柄の `invalidation` 条件の成立 | 有効 |
| モデル劣化の検出 | 有効 |
| 推奨の生成（個別） | 無効（多すぎる） |

通知は**まとめて1日1-2回**にする。個別に飛ぶと通知疲れで無視されるようになる。

## 6. Phase B: クラウド移行

### 6.1 移行の目的

| 動機 | 説明 |
| --- | --- |
| PC の常時稼働から解放される | Windows Update やスリープの影響を受けなくなる |
| 外出先での確実な到達性 | Tailscale の設定不要 |
| 複数デバイスからの利用 | |

移行しない理由（Phase A に留まる選択も妥当）:

| 理由 | 説明 |
| --- | --- |
| コスト | 月 $10-30 程度かかる。データ量が大きいためストレージ費用が主 |
| データ移行の手間 | 40GB のデータをアップロードする必要がある |
| 自宅PCで足りている | 個人用ならこれで十分機能する |

**Phase A で十分機能するなら移行しない。** 移行可能な構成にしておくこと自体に価値があり、実際に移行するかは別問題である。

### 6.2 移行手順

| 順序 | 作業 | 変更内容 |
| --- | --- | --- |
| 1 | Dockerfile の作成 | `services/api`、`services/agent`、`apps/web` の3つ。アプリコードの変更は不要 |
| 2 | PostgreSQL への移行 | Neon / Supabase の無料枠。`DATABASE_URL` を変更し `alembic upgrade head` を実行。SQLite のデータは `pgloader` または自前スクリプトで移行 |
| 3 | オブジェクトストレージへの移行 | Cloudflare R2（エグレス無料が有利）。Parquet と PDF blob を移す。DuckDB は `httpfs` 拡張で `s3://` を直接読める |
| 4 | ベクトルストアの移行 | LanceDB → pgvector。`VectorStore` 実装の差し替え。埋め込みの再生成は不要（ベクトルをそのまま移す） |
| 5 | 認証の追加 | `get_current_user` の実装を差し替える（[09-api-spec.md](09-api-spec.md) §5） |
| 6 | シークレットの移行 | `.env` → Secret Manager。`pydantic-settings` の読み込み元を切り替える |
| 7 | デプロイ | Cloud Run / Fly.io。`apps/web` は Vercel でもよい |
| 8 | スケジューラ | **変更なし**（APScheduler はそのまま動く） |

### 6.3 変更が不要な部分

以下は Phase A / B で共通である。これが「書き換えではなく設定変更で済む」ことの根拠になる。

| 要素 | 理由 |
| --- | --- |
| すべての Connector | 外部APIへのアクセスは環境に依存しない |
| すべての分析ロジック | |
| APScheduler の定義 | アプリ内スケジューラを選んだ理由がここにある |
| LLM ルーティング | LiteLLM 経由なので変わらない |
| API エンドポイント | |
| フロントエンドのコード | API のベースURLのみ環境変数で切り替え |
| SQLAlchemy モデル | Postgres でもそのまま動く（SQLite 固有の型を使っていない前提） |

### 6.4 Phase B での構成案

```
[スマートフォン / PC]
       │ HTTPS + パスキー認証
       ▼
┌──────────────────┐
│ Vercel           │  apps/web (Next.js)
└────────┬─────────┘
         │ HTTPS
         ▼
┌──────────────────────────────────┐
│ Cloud Run / Fly.io               │
│  ├─ api      (FastAPI)           │
│  └─ agent    (APScheduler 常駐)   │
└───┬──────────────┬───────────────┘
    │              │
    ▼              ▼
┌─────────┐  ┌──────────────────┐
│ Neon    │  │ Cloudflare R2    │
│ Postgres│  │ Parquet + PDF    │
│ +pgvector│ │ (DuckDB httpfs)  │
└─────────┘  └──────────────────┘
```

**注意点**: `agent` は常駐プロセスなので、Cloud Run の「リクエストがないときにゼロにスケール」する設定では動かない。最小インスタンス数を1にする（または Fly.io の常時稼働マシンを使う）。これがクラウド移行時のコストの主要因になる。

代替案として、agent を Cloud Run Jobs + Cloud Scheduler で起動する方式もある。ただしこれは APScheduler を捨てることになり、「OS依存のスケジューラを使わない」という設計判断と矛盾する。**Phase B に移行する場合も APScheduler を維持し、常駐インスタンスのコストを受け入れる**方針とする。

### 6.5 コスト見積もり（Phase B）

| サービス | 月額（目安） |
| --- | --- |
| Vercel（Hobby） | $0 |
| Fly.io（shared-cpu-1x, 512MB × 2プロセス、常時稼働） | 約 $5-10 |
| Neon Postgres（無料枠 or Launch） | $0-19 |
| Cloudflare R2（40GB ストレージ + 低頻度アクセス） | 約 $0.6 |
| LLM API | $5-15 |
| Tailscale | $0（Phase B では不要になる） |
| 合計 | **約 $11-45** |

`[要検証]` 各サービスの料金は変動する。実装時に確認する。

## 7. 参照

- Windows/WSL2 のネットワーク設定: [15-windows-runtime.md](15-windows-runtime.md) §2, §3
- API 仕様: [09-api-spec.md](09-api-spec.md)
- レスポンシブとナビゲーション: [ui/interaction-patterns.md](ui/interaction-patterns.md)
- ロードマップ: [13-roadmap.md](13-roadmap.md)
