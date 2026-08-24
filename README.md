# AI 株式リサーチ・売買判断支援ツール 仕様書

日米株式（東証・US）を対象とした、個人利用のAIリサーチ・売買判断支援ツールの詳細仕様書一式です。
バックエンド API（`services/api`）とストレージ層は本リポジトリで動かせます。フロントエンドは `apps/web` を参照してください。

## 実装の起動（API）

前提: Python 3.12、[`uv`](https://docs.astral.sh/uv/)、`PYTHONUTF8=1`。データは WSL2 ホーム配下に置く（`/mnt/c` は使わない）。Windows ネイティブで試す場合は `DATA_DIR` を `%USERPROFILE%\ai-stock\data` などにする。

```powershell
$env:PYTHONUTF8 = "1"
Copy-Item .env.example .env   # 値を埋める。EDGAR を叩かない API 起動には空のままでよい
uv sync
uv run python -m packages.core.storage.init_db
uv run python -m services.api.seed
uv run pytest
uv run uvicorn services.api.main:app --host 0.0.0.0 --port 8000
```

WSL では `make sync init-db seed test api` でもよい。systemd unit と `.wslconfig` のサンプルは `infra/`（[docs/15-windows-runtime.md](docs/15-windows-runtime.md)）。

確認:

```powershell
curl.exe http://localhost:8000/health
curl.exe "http://localhost:8000/api/v1/system/health"
curl.exe "http://localhost:8000/api/v1/dashboard?market=JP"
curl.exe "http://localhost:8000/api/v1/recommendations?market=JP"
```

OpenAPI は `http://localhost:8000/api/v1/openapi.json`（`uv run python -m services.api.export_openapi`）。

## このツールが何であって、何でないか

| | |
| --- | --- |
| やること | 公開データと開示資料の収集、統計分析、LLMによる資料読解、スコアリング、推奨カードの生成、決算資料へのワンクリックアクセス、売買日誌と実績分析 |
| やらないこと | **発注（自動売買）**。売買の意思決定と発注は常に人が手で行う |
| 将来拡張 | 自動発注は [docs/14-future-brokerage.md](docs/14-future-brokerage.md) で比較検討のみ。`ExecutionAdapter` インターフェースを先行定義 |

### 設計の前提

この仕様書全体を貫く前提が3つあります。実装時にこれを崩すと、製品としての意味が失われます。

1. **予測は当たらない前提で作る。** すべての予測に信頼区間と的中率（母数付き）を併記します。為替
   予測はランダムウォークをベースラインとし、Diebold-Mariano 検定で優位性を確認できない限り
   「優位性なし」と表示します。株価ランキングは Purged Walk-Forward CV でのみ検証し、バックテスト
   は手数料・スリッページ・回転率上限を必須引数とし、Deflated Sharpe Ratio で多重検定バイアスを
   開示します。
2. **推奨には必ず弱気論拠（bear case）を含める。** 強気論拠と同じ重みで表示し、折りたたみません。
   引用のない主張は Critic が差し戻します。
3. **データの鮮度と出自を常に見せる。** リサーチ用の価格（J-Quants 無料プラン・12週遅延）と参考
   現在値（yfinance・15分遅延）は別テーブルに分離し、後者はモデルの学習・検証に一切使いません。

## 読み進め方

### はじめて読む場合

1. [00-overview.md](docs/00-overview.md) — 目的、スコープ、非機能要件、設計判断の記録、用語集
2. [01-architecture.md](docs/01-architecture.md) — 構成図、データフロー、技術選定の理由
3. [13-roadmap.md](docs/13-roadmap.md) — Phase 0-6 と各Phaseの完了条件

### 実装を始める場合

[13-roadmap.md](docs/13-roadmap.md) の Phase 0 から順に進めます。Phase 2（分析エンジンと検証基盤）
を飛ばして Phase 3（LLM）に進んではいけません。検証されていない分析基盤の上に LLM を載せると、
もっともらしいが根拠のない推奨が出力されます。

### 環境構築から始める場合

[15-windows-runtime.md](docs/15-windows-runtime.md) を先に読み、`.wslconfig`、Hyper-V ファイア
ウォール、`PYTHONUTF8`、データ保存先の位置を先に片付けてください。後から踏むと原因特定に時間を
取られます。

## 文書一覧

### 設計仕様（docs/）

| # | 文書 | 内容 |
| --- | --- | --- |
| 00 | [overview](docs/00-overview.md) | 目的・スコープ・非機能要件・設計判断・用語集 |
| 01 | [architecture](docs/01-architecture.md) | C4風構成図・モノレポ構成・データ層・技術選定理由 |
| 02 | [data-ingestion](docs/02-data-ingestion.md) | データソース別の取得仕様、レート制限、生データ保存、品質チェック |
| 03 | [data-model](docs/03-data-model.md) | DuckDB / SQLite / LanceDB のスキーマ定義、PIT制約、不変条件 |
| 04 | [analysis-engine](docs/04-analysis-engine.md) | 特徴量、GARCH、為替予測、LightGBM、Purged Walk-Forward、DSR |
| 05 | [scoring-screening](docs/05-scoring-screening.md) | セクター中立化z-score、定性オーバーレイ、推奨カードの必須要素 |
| 06 | [filings-access](docs/06-filings-access.md) | EDINET / EDGAR / TDnet のURL生成規則、ローカル配信、要約キャッシュ |
| 07 | [llm-rag](docs/07-llm-rag.md) | 3階層のモデルルーティング、コスト管理、RAG、プロンプト設計、引用検証 |
| 08 | [agent-loop](docs/08-agent-loop.md) | 6ジョブ構成、フィードバックループ、冪等性と再開、ガードレール |
| 09 | [api-spec](docs/09-api-spec.md) | REST API 仕様、部分データの表現、SSE、スキーマ共有 |
| 10 | [mobile-pwa](docs/10-mobile-pwa.md) | PWA、Tailscale 配信、オフライン設計、クラウド移行手順 |
| 11 | [security-ops](docs/11-security-ops.md) | シークレット管理、バックアップと復旧、監視、コスト上限、運用フロー |
| 12 | [testing-validation](docs/12-testing-validation.md) | テスト分類、リーク検出、PIT検証、統計実装の検証、CI構成 |
| 13 | [roadmap](docs/13-roadmap.md) | Phase 0-6、各Phaseの完了条件、やらないことの明示 |
| 14 | [future-brokerage](docs/14-future-brokerage.md) | 自動発注の将来設計（楽天RSS / kabuステーション / Alpaca・IBKR の比較） |
| 15 | [windows-runtime](docs/15-windows-runtime.md) | Windows 11 + WSL2 の落とし穴と対策（原因 + 対策の形式） |

### UI 仕様（docs/ui/） — Figma Make 参照用

構造説明は英語、画面内の実テキストは日本語（`label_en` / `label_ja` の対）で記述しています。
Figma Make には [docs/ui/SKILL.md](docs/ui/SKILL.md) を主指示書として渡します。

| 文書 | 内容 |
| --- | --- |
| [SKILL.md](docs/ui/SKILL.md) | Figma Make へのメイン指示書。譲れない設計原則8項目、言語規則、数値書式、生成禁止項目 |
| [design-system.md](docs/ui/design-system.md) | カラー・タイポ・スペーシング。**日本式（赤=上昇）/ 米国式（緑=上昇）を切替可能なセマンティックトークン** |
| [components.md](docs/ui/components.md) | コンポーネントインベントリ。`RecommendationCard`、`ForecastValue`、`DataFreshnessIndicator` が中核 |
| [states.md](docs/ui/states.md) | loading / empty / not-ready / **partial** / error / stale / offline / degraded |
| [interaction-patterns.md](docs/ui/interaction-patterns.md) | ナビゲーション、レスポンシブ規則、キーボード、避けるべきパターン |
| [sample-data.json](docs/ui/sample-data.json) | 実データ風のモックデータ（7203 トヨタ、6758 ソニー、AAPL、NVDA、USD/JPY 152円台など） |

画面仕様（全10画面、節構成は全ファイル共通）:

| # | 画面 | ルート |
| --- | --- | --- |
| 01 | [dashboard](docs/ui/screens/01-dashboard.md) | `/` |
| 02 | [recommendations](docs/ui/screens/02-recommendations.md) | `/recommendations` |
| 03 | [stock-detail](docs/ui/screens/03-stock-detail.md) | `/stocks/[market]/[ticker]` |
| 04 | [screener](docs/ui/screens/04-screener.md) | `/screener` |
| 05 | [filings-hub](docs/ui/screens/05-filings-hub.md) | `/filings` |
| 06 | [fx-macro](docs/ui/screens/06-fx-macro.md) | `/macro` |
| 07 | [model-lab](docs/ui/screens/07-model-lab.md) | `/model-lab` |
| 08 | [agent-console](docs/ui/screens/08-agent-console.md) | `/agent` |
| 09 | [portfolio-journal](docs/ui/screens/09-portfolio-journal.md) | `/portfolio` |
| 10 | [settings](docs/ui/screens/10-settings.md) | `/settings` |

### SKILLS（.cursor/skills/）

反復する作業手順です。該当する作業に入るときに参照します。

| SKILL | 使うとき |
| --- | --- |
| [add-data-source](.cursor/skills/add-data-source/SKILL.md) | 新規データソースの追加、エンドポイント追加、プラン移行 |
| [add-analysis-factor](.cursor/skills/add-analysis-factor/SKILL.md) | ファクター・モデルの追加。Rank IC が急に改善したときの検証 |
| [run-backtest](.cursor/skills/run-backtest/SKILL.md) | バックテストの実行と DSR による採否判定 |
| [daily-research-report](.cursor/skills/daily-research-report/SKILL.md) | 毎朝の確認、部分失敗時の判断、推奨が0件のときの調査 |
| [implement-screen-from-figma](.cursor/skills/implement-screen-from-figma/SKILL.md) | Figma Make 出力を `apps/web` に落とし込む |
| [agent-eval-loop](.cursor/skills/agent-eval-loop/SKILL.md) | 推奨実績のレビュー、教訓の棚卸し、重み更新の承認 |
| [write-spec-doc](.cursor/skills/write-spec-doc/SKILL.md) | 仕様書の追加・改訂（メタスキル） |
| [verify-windows-runtime](.cursor/skills/verify-windows-runtime/SKILL.md) | 環境が壊れたときの切り分け、月次点検 |

## 技術スタック（予定）

| 領域 | 技術 |
| --- | --- |
| フロントエンド | Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + TanStack Query、PWA |
| API | Python 3.12 + FastAPI（依存管理は `uv`） |
| エージェント | Python worker + APScheduler（cron や Windows タスクスケジューラは使わない） |
| 分析 | pandas, statsmodels, arch (GARCH), scikit-learn, LightGBM |
| 分析用ストレージ | DuckDB + Parquet |
| 状態管理 | SQLite + SQLAlchemy（Phase B で PostgreSQL へ接続文字列の変更のみで移行） |
| ベクトルストア | LanceDB（抽象化層の背後。Phase B は pgvector） |
| LLM | LiteLLM 経由の3階層ルーティング。モデル識別子は `models.yaml` に集約 |
| 実行環境 | Windows 11 + WSL2 (Ubuntu)。Tailscale は Windows ホスト側のみ |

## データソース（すべて無料枠から開始）

| ソース | 用途 | 制約 |
| --- | --- | --- |
| J-Quants API | 日本株の価格・財務 | 無料プランは12週遅延・過去2年・毎分5リクエスト。Light プラン（月1,650円）への移行は設定変更のみ |
| yfinance | 参考現在値（日米）、米国株価格 | 15分遅延。**モデルの学習・検証には使用しない** |
| EDINET API v2 | 日本の開示資料（有報・四半期報告書） | 無料。`Subscription-Key` ヘッダ |
| TDnet | 日本の適時開示 | 公開APIなし。低頻度取得、既定で無効、規約確認のうえ有効化 |
| SEC EDGAR | 米国の開示資料 | 無料。`User-Agent` 必須、約10 req/s |
| FRED API | 為替（DEXJPUS）、金利、CPI | 無料 |

エンドポイントのパス、認証方式、レート制限、プラン内容、LLM の単価は変更されます。実装前に必ず
公式ドキュメントで確認してください。仕様書内の該当箇所にも同じ注記があります。

## 想定コスト

| 項目 | 月額 |
| --- | --- |
| データソース | 0円（すべて無料枠） |
| LLM | $5 - $15 程度（日次バッチ前提。日次上限 $1.50、月次上限 $20 を既定とする） |
| インフラ | 0円（Phase A は自宅PC + Tailscale） |

J-Quants を Light プランに上げる場合は追加で月1,650円。12週遅延が実際に判断を妨げているかを
確認してから決めます。

## 進める前に決めること

実装に入る前に判断が必要な項目です。

1. **J-Quants を無料プランで始めるか、最初から Light にするか。** 無料プランの12週遅延は
   バックテストには支障ありませんが、直近の値動きに基づく判断が参考現在値だけになります。
2. **TDnet を有効にするか。** 公開APIがないため、利用規約を確認してから判断してください。既定は
   無効で、無効でも EDINET の資料で運用できます。
3. **対象ユニバースの広さ。** 全上場 / 時価総額300億円以上 / TOPIX500 / ウォッチリストのみ。
   広げるとデータ収集時間と LLM コストが比例して増えます。
4. **上昇・下落の色（日本式 / 米国式）。** 設定で切り替えられますが、初期値を決めてください。
5. **自動発注に将来着手するか。** 着手条件は
   [13-roadmap.md](docs/13-roadmap.md) と [14-future-brokerage.md](docs/14-future-brokerage.md)
   に記載しています。着手しないという判断も妥当です。

## リポジトリ規約

- 文字コードは UTF-8。`open()` には常に `encoding="utf-8"` を明示し、`PYTHONUTF8=1` を設定する
- 改行コードは LF（`.gitattributes` で `* text=auto eol=lf`）
- パスは `pathlib` を使い、`:` `?` `*` を含む名前を作らない
- リポジトリとデータは WSL2 のホーム配下に置く。`/mnt/c/` 配下は使わない
- 絵文字は使わない
