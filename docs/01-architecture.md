# 01. アーキテクチャ

## 1. システムコンテキスト（C4 Level 1）

```
                     ┌──────────────────────────────────────┐
                     │            利用者（1名）             │
                     │  PC ブラウザ / スマートフォン(PWA)   │
                     └───────────────┬──────────────────────┘
                                     │ HTTPS over Tailscale
                                     ▼
        ┌────────────────────────────────────────────────────────┐
        │   AI Stock Research System（Windows 11 + WSL2 上）      │
        │                                                        │
        │   apps/web (Next.js)  ──►  services/api (FastAPI)      │
        │                                   │                    │
        │                            services/agent (worker)     │
        │                                   │                    │
        │              DuckDB + Parquet / SQLite / LanceDB       │
        └───────┬───────────────┬───────────────┬────────────────┘
                │               │               │
                ▼               ▼               ▼
      ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
      │ 市場データ    │  │ 開示情報      │  │ LLM / 埋込み  │
      │ J-Quants      │  │ EDINET v2     │  │ LiteLLM 経由  │
      │ yfinance      │  │ TDnet         │  │ Gemini/Claude │
      │ Alpha Vantage │  │ SEC EDGAR     │  │ 埋め込みAPI    │
      │ Finnhub       │  │               │  │               │
      │ FRED          │  │               │  │               │
      └──────────────┘  └──────────────┘  └──────────────┘
```

外部システムはすべて読み取り専用（LLMは書き込みを伴わない推論のみ）。証券会社への接続は本バージョンでは存在しない。

## 2. コンテナ構成（C4 Level 2）

| コンテナ | 技術 | 責務 | 通信 |
| --- | --- | --- | --- |
| `apps/web` | Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui + TanStack Query | UI。PWA として manifest / Service Worker を持つ | `services/api` へ REST |
| `services/api` | Python 3.12 + FastAPI + Uvicorn | 読み取りAPI、書き込みAPI（売買日誌・設定）、SSE によるジョブ進捗配信 | DuckDB / SQLite / LanceDB を直接参照 |
| `services/agent` | Python 3.12 worker + APScheduler | データ収集・分析・LLM呼び出し・推奨生成・自己評価 | 外部API、DB。`services/api` とはDB共有 |
| `packages/schemas` | Pydantic v2 + TypeScript 型生成 | API契約の単一情報源。OpenAPIから TS 型を自動生成 | ビルド時のみ |
| `packages/core` | Python ライブラリ | Connector 抽象、ファクター計算、モデル、バックテスト、LLMクライアント | `services/*` から import |

`services/api` と `services/agent` を分離する理由は、エージェントの長時間ジョブがAPIの応答性を損なわないようにするため。ただしPhase Aでは同一ホスト上の別プロセスとして動かし、プロセス間通信はDBを介した非同期のみとする（メッセージブローカーは導入しない）。

## 3. リポジトリ構成（モノレポ）

```
.
├── README.md
├── .gitattributes                  # * text=auto eol=lf
├── .env.example
├── docs/                           # 本仕様書群
├── .cursor/skills/                 # 反復タスク用SKILLS
├── apps/
│   └── web/
│       ├── app/                    # App Router
│       │   ├── (dashboard)/page.tsx
│       │   ├── recommendations/page.tsx
│       │   ├── stocks/[ticker]/page.tsx
│       │   ├── screener/page.tsx
│       │   ├── filings/page.tsx
│       │   ├── macro/page.tsx
│       │   ├── model-lab/page.tsx
│       │   ├── agent/page.tsx
│       │   ├── portfolio/page.tsx
│       │   └── settings/page.tsx
│       ├── components/ui/          # shadcn/ui
│       ├── components/domain/      # ドメイン固有（RecommendationCard 等）
│       ├── lib/api-client.ts       # 生成された型を用いたfetchラッパ
│       ├── public/manifest.webmanifest
│       └── next.config.ts
├── services/
│   ├── api/
│   │   ├── main.py
│   │   ├── routers/
│   │   ├── deps.py
│   │   └── pyproject.toml
│   └── agent/
│       ├── main.py                 # APScheduler 起動点
│       ├── jobs/
│       │   ├── collector.py
│       │   ├── analyst.py
│       │   ├── researcher.py
│       │   ├── strategist.py
│       │   ├── critic.py
│       │   └── evaluator.py
│       └── pyproject.toml
├── packages/
│   ├── core/
│   │   ├── connectors/             # jquants.py, edinet.py, tdnet.py, yfinance.py, edgar.py, fred.py
│   │   ├── storage/               # duckdb_repo.py, sqlite_repo.py, parquet_lake.py, vector_store.py
│   │   ├── factors/
│   │   ├── models/                # garch.py, arimax.py, ranker.py
│   │   ├── backtest/
│   │   ├── llm/                   # router.py, prompts/, cache.py
│   │   └── config/
│   │       ├── settings.py         # pydantic-settings
│   │       └── models.yaml         # LLMモデル識別子はここだけ
│   └── schemas/
├── data/                           # gitignore。WSL2ホーム配下必須
│   ├── raw/                        # 生レスポンス（Parquet/JSON.gz）
│   ├── warehouse/                  # DuckDB ファイルと派生Parquet
│   ├── state.sqlite
│   └── vectors/                    # LanceDB
└── infra/
    ├── wsl/                        # systemd unit, セットアップスクリプト
    └── windows/                    # .wslconfig サンプル, PowerShell スクリプト
```

## 4. データフロー

### 4.1 日次バッチ（平日 JST 06:30 / 18:30 の2回）

```
[06:30 JST]  US市場クローズ後のフロー
  Collector(US)  → yfinance で米国日足・EDGARで新規提出物を取得
                 → FRED で為替・マクロ更新
  Analyst        → 特徴量再計算（US + FX）
  Researcher     → 新規開示のLLM要約（未要約のものだけ）
  Strategist     → 推奨候補生成（US）
  Critic         → 引用検証・鮮度検証
  Evaluator      → T+5 / T+20 到達した過去推奨の実績評価

[18:30 JST]  JP市場クローズ後のフロー
  Collector(JP)  → J-Quants 日足（無料プランは12週前まで）
                 → yfinance で直近ギャップ補完
                 → EDINET 書類一覧、TDnet 適時開示
  Analyst → Researcher → Strategist → Critic → Evaluator  （JP版）
```

各ジョブは前段の完了を待つが、**前段が部分失敗した場合も利用可能なデータだけで実行する**（機能縮退）。ジョブ間の依存は `job_runs` テーブルの状態で判定する。

### 4.2 データの層構造（Medallion 風）

| 層 | 場所 | 内容 | 更新方式 |
| --- | --- | --- | --- |
| Raw | `data/raw/{source}/{endpoint}/dt={YYYY-MM-DD}/*.json.gz` | APIの生レスポンスを無加工で保存 | 追記のみ（不変） |
| Staging | `data/warehouse/staging/*.parquet` | 型変換・カラム名正規化のみ済み | 日次で再生成可能 |
| Core | DuckDB のテーブル（`prices_daily`, `financials`, `documents` など） | 正規化済みの事実テーブル | upsert |
| Feature | DuckDB `features_daily` | 分析用の特徴量。PIT を厳守 | 日次 append |
| Serving | DuckDB `recommendations`, `scores_daily`、および事前集計ビュー | UIが直接読む | 日次 append |
| State | SQLite `state.sqlite` | ジョブ実行履歴、設定、売買日誌、agent_memory、LLMコストログ | 随時更新 |
| Vector | LanceDB `data/vectors/` | 開示資料チャンクの埋め込み | 追記 |

**Raw層を必ず残すことが再現性の根拠**である。J-Quants無料プランは 5 req/min であり、正規化ロジックのバグ修正のために全銘柄を再取得すると数時間かかる。Raw層があればその再取得が不要になる。

## 5. 技術選定の理由

### 5.1 フロントエンド

| 技術 | 選定理由 | 代替案と却下理由 |
| --- | --- | --- |
| Next.js (App Router) | Server Components でチャート用データの初期表示を高速化できる。PWA化の実績が豊富。Phase B で Vercel / Cloud Run にそのまま載る | Vite + React SPA: 初期表示が遅く、SEOは不要だがLCP要件に不利 |
| TypeScript | OpenAPI から型生成し、API契約の破壊をビルド時に検出する | JavaScript: 型のない状態でスキーマ変更を追うのは非現実的 |
| Tailwind CSS | design-system.md のトークンをそのまま `theme` に落とせる。Figma Make の出力もTailwind前提が多い | CSS Modules: トークン運用が煩雑 |
| shadcn/ui | コードがリポジトリ内に入るので改変が容易。ダークファーストのテーマ切替が素直 | MUI: バンドルが重く、デザイントークンの上書きが面倒 |
| TanStack Query | 部分失敗（partial-data 状態）をクエリ単位で表現できる。ポーリングとキャッシュ制御が宣言的 | SWR: 十分だがミューテーション・再試行制御はTanStack Queryが強い |
| Recharts | 依存が軽く、日足数百本のラインチャート・バーチャートに十分 | TradingView Lightweight Charts: ローソク足は綺麗だが、スコア分布などの汎用チャートに弱い。Phase Bで併用検討 |

### 5.2 バックエンド

| 技術 | 選定理由 | 代替案と却下理由 |
| --- | --- | --- |
| Python 3.12 | 分析ライブラリ（statsmodels / arch / LightGBM）が事実上Python専用。3.12を選ぶのは3.13以降の一部ライブラリ対応が未成熟な場合を避けるため（実装時に3.13の対応状況を確認する） | 3.11: 型構文と性能で3.12が有利 |
| FastAPI | Pydantic v2 と OpenAPI 生成が標準装備。TS型生成のパイプラインが単純になる | Flask: OpenAPI生成が手作業寄り |
| uv | 依存解決が高速で、モノレポの複数 `pyproject.toml` をワークスペースとして扱える。WSL2上のインストール時間が体感で大きく変わる | Poetry: 遅い。pip + requirements: ロックの再現性が弱い |
| APScheduler | **アプリ内スケジューラであることが選定理由そのもの**。cron / Windows タスクスケジューラはOS依存で、Phase Bのクラウド移行時に作り直しになる。WSL2は起動タイミングが不定でcronの起動保証が弱い | cron: OS依存、WSL2で起動しないことがある。Celery beat: ブローカー（Redis）が増える |
| Pydantic Settings | `.env` と環境変数から型付き設定を読む。設定キーの一覧がコードで自明になる | 素のos.environ: 型と必須チェックがない |

### 5.3 ストレージ

| 技術 | 用途 | 選定理由 |
| --- | --- | --- |
| DuckDB + Parquet | 分析クエリ（時系列スキャン、ウィンドウ関数、クロスセクショナル集計） | 列指向で数百万行の日足を秒で走査できる。Parquetを外部テーブルとして直接読める。単一ファイルで運用が軽い |
| SQLite (via SQLAlchemy) | 状態管理（ジョブ履歴、設定、売買日誌、agent_memory、コストログ） | 行単位の更新が多い。**SQLAlchemy を通すことで Phase B の PostgreSQL 移行が接続文字列の変更だけで済む** |
| LanceDB | 開示資料チャンクの埋め込み | 埋め込みファイルベースでサーバー不要。`VectorStore` 抽象の背後に置き、Phase B では pgvector に差し替える |

**DuckDBとSQLiteを併用する理由**: 分析は「大量行の読み取り・集計」、状態管理は「少量行の頻繁な更新」であり、要求が正反対である。DuckDBは書き込みの同時実行が弱く（単一ライタ）、状態管理には不向き。SQLiteは列指向の集計が遅い。両方を1つに寄せると必ずどちらかで詰まる。

### 5.4 分析ライブラリ

| ライブラリ | 用途 |
| --- | --- |
| pandas | 特徴量計算の主要インターフェース。DuckDBとの相互変換が容易 |
| statsmodels | ARIMAX、VECM、Diebold-Mariano検定、単位根検定 |
| arch | GARCH(1,1) / EGARCH によるボラティリティ推定 |
| scikit-learn | 前処理、交差検証の基盤（Purged Walk-Forward は自作の `BaseCrossValidator` として実装） |
| LightGBM | クロスセクショナル・ランキング（`lambdarank` または回帰） |
| numpy / scipy | 数値計算、統計検定 |

### 5.5 LLM

| 技術 | 選定理由 |
| --- | --- |
| LiteLLM | **モデル識別子と価格が1ファイル（`packages/core/config/models.yaml`）に集約される**ことが最大の理由。モデル世代交代のたびにアプリコードを触る必要がなくなる。フォールバック・リトライ・コスト計測が標準機能として付いてくる |
| Gemini 3.7 Flash | 大量処理層。**PDFをネイティブ入力できる**ため、有価証券報告書のPDFを前処理なしで投入できる。1Mコンテキスト |
| Claude Sonnet 5 | 既定の推論・エージェント統括層。1Mコンテキスト |
| Claude Opus 5 | 週次の深掘り層。1Mウィンドウ全域でフラット価格 |

詳細な価格とルーティング条件は [07-llm-rag.md](07-llm-rag.md)。**価格・モデル名は変動が速いため、本ドキュメントの値は実装時に必ず公式の価格ページで検証すること。**

## 6. プロセス構成と起動シーケンス（Phase A）

```
WSL2 (Ubuntu) 起動
  └─ systemd
      ├─ ai-stock-api.service     : uvicorn services.api.main:app --host 0.0.0.0 --port 8000
      ├─ ai-stock-agent.service   : python -m services.agent.main   （APScheduler 常駐）
      └─ ai-stock-web.service     : node apps/web/.next/standalone/server.js --port 3000

Windows ホスト
  └─ Tailscale （ホスト側のみ。WSL2内には入れない）
       └─ tailnet 内の他デバイスから http://<windows-host>:3000 で到達
```

`networkingMode=mirrored` により、WSL2内で `0.0.0.0:3000` にバインドしたサービスは Windows ホストの `localhost:3000` および Tailscale IP で到達可能になる。Hyper-V ファイアウォールの受信許可設定が別途必要（[15-windows-runtime.md](15-windows-runtime.md) 参照）。

## 7. 環境変数と設定の境界

| 種別 | 保存先 | 例 |
| --- | --- | --- |
| シークレット | `.env`（gitignore） / 環境変数 | `JQUANTS_API_KEY`, `EDINET_SUBSCRIPTION_KEY`, `FRED_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` |
| 構成（コード管理） | `packages/core/config/*.yaml` | LLMモデル識別子、ファクター定義、ルーティング閾値 |
| 実行時設定（ユーザー変更可） | SQLite `settings` テーブル | 上昇下落カラー、表示通貨、通知の有無、リスク許容度 |
| プラン依存の切替 | `.env` | `JQUANTS_PLAN=free|light`（free の場合のみ yfinance ギャップ補完を有効化） |

`JQUANTS_PLAN` を設定値として持つことで、Light プランへの移行がコード変更なしで完了する（D-02 の実装上の担保）。

## 8. Phase A / Phase B の差分一覧

| 要素 | Phase A（自宅PC） | Phase B（クラウド） | 移行に必要な作業 |
| --- | --- | --- | --- |
| 実行環境 | WSL2 上の systemd | Cloud Run / Fly.io のコンテナ | Dockerfile 追加のみ（アプリコード変更なし） |
| 状態DB | SQLite | PostgreSQL (Neon / Supabase) | `DATABASE_URL` の変更 + alembic migration 実行 |
| 分析DB | ローカル DuckDB ファイル | オブジェクトストレージ上の Parquet + DuckDB | `WAREHOUSE_URI` の変更（`s3://` 対応） |
| ベクトルDB | LanceDB | pgvector | `VectorStore` 実装の差し替え（抽象は同じ） |
| スケジューラ | APScheduler（プロセス常駐） | APScheduler（同じ） | 変更なし |
| 到達性 | Tailscale | HTTPS + 認証 | 認証ミドルウェア追加 |
| 秘密情報 | `.env` | Secret Manager | 読み込み元の切替のみ |

## 9. 主要な非同期・障害時の振る舞い

| 事象 | 振る舞い |
| --- | --- |
| J-Quants がレート制限を返す | 指数バックオフで待機。当日中に完了しなければ `job_runs` に `partial` を記録し、翌日に差分を取得 |
| yfinance が空を返す | 該当銘柄をスキップし `data_gaps` テーブルに記録。UIは「価格データ欠損」を表示 |
| LLM がコストキャップに達した | 以降のLLM呼び出しを停止し、定量スコアのみで推奨を生成。UIに「定性分析は本日停止中」を表示 |
| Windows Update による再起動 | systemd がサービスを再起動。各ジョブは `job_runs.checkpoint` から再開 |
| DuckDB ファイルのロック競合 | API側は読み取り専用接続を使う。書き込みは agent プロセスのみに限定 |

## 10. 参照

- データソースの詳細: [02-data-ingestion.md](02-data-ingestion.md)
- スキーマ定義: [03-data-model.md](03-data-model.md)
- API仕様: [09-api-spec.md](09-api-spec.md)
- Windows/WSL2 固有事項: [15-windows-runtime.md](15-windows-runtime.md)
