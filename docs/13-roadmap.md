# 13. ロードマップ（Phase 0-6）

## 0. 進め方の原則

**期間ではなく、完了条件（Definition of Done）で区切る。** 個人プロジェクトでは使える時間が不定であり、日数の見積もりは意味を持たない。各 Phase は「何が動いていれば次に進めるか」で定義する。

各 Phase の完了条件は検証可能な形で書く。「実装した」ではなく「テストが通り、画面で確認できる」ことを条件にする。

原則として **1つ前の Phase の完了条件を満たすまで次に進まない**。特に Phase 2（分析）を飛ばして Phase 3（LLM）に進むと、根拠のないLLM出力を見て満足する状態になりやすい。

## Phase 0: 基盤とデータ取得の1本

**狙い**: 最小の縦断（外部API → 保存 → API → 画面）を1本通す。ここでモノレポの配線とWSL2環境の問題を全部潰す。

### 実装項目

| # | 項目 | 参照 |
| --- | --- | --- |
| 0-1 | WSL2 環境のセットアップ（`.wslconfig`、Hyper-V ファイアウォール、Tailscale） | [15](15-windows-runtime.md) §2, §3 |
| 0-2 | モノレポの骨格（`apps/web`, `services/api`, `services/agent`, `packages/core`, `packages/schemas`） | [01](01-architecture.md) §3 |
| 0-3 | `uv` ワークスペースの設定、`pyproject.toml` の分割 | [01](01-architecture.md) §5.2 |
| 0-4 | `.gitattributes`（`* text=auto eol=lf`）、`.gitignore`、`.env.example` | [11](11-security-ops.md) §1 |
| 0-5 | Ruff / mypy / Prettier / ESLint の設定（`PLW1514`, `PTH` を有効化） | [12](12-testing-validation.md) §8 |
| 0-6 | `Settings`（pydantic-settings）と起動時検証（EDGAR UA、DATA_DIR） | [11](11-security-ops.md) §1.3 |
| 0-7 | `Connector` 抽象と `TokenBucket`（SQLite永続化） | [02](02-data-ingestion.md) §1 |
| 0-8 | FRED コネクタ（最も単純なので最初に作る） | [02](02-data-ingestion.md) §8 |
| 0-9 | DuckDB / SQLite の初期スキーマと Alembic マイグレーション | [03](03-data-model.md) §5 |
| 0-10 | FastAPI の骨格、`Envelope` レスポンス、`/system/health` | [09](09-api-spec.md) §1, §3 |
| 0-11 | Next.js の骨格、Tailwind + shadcn/ui、design-system のトークン適用 | [ui/design-system.md](ui/design-system.md) |
| 0-12 | 為替チャート1枚を表示する画面 | [ui/screens/06-fx-macro.md](ui/screens/06-fx-macro.md) |
| 0-13 | APScheduler の骨格と `job_runs` への記録 | [08](08-agent-loop.md) §2 |
| 0-14 | systemd unit（api / agent / web） | [15](15-windows-runtime.md) §7 |
| 0-15 | OpenAPI → TS 型生成のパイプライン | [09](09-api-spec.md) §3 |

### 完了条件

- [ ] スマートフォンから Tailscale 経由で `https://<machine>.<tailnet>.ts.net` にアクセスし、USD/JPY のチャートが表示される
- [ ] `ruff check` / `mypy` / `tsc --noEmit` が全て通る
- [ ] T-ENV-01（`open()` の encoding 明示）、T-ENV-02（パス文字制限）、T-ENV-04（DATA_DIR 検証）が通る
- [ ] `journalctl -u ai-stock-agent` でスケジューラのログが見える
- [ ] WSL2 を再起動しても3サービスが自動起動する
- [ ] `GET /api/v1/system/health` が全コンポーネント `ok` を返す
- [ ] `npm run gen:api` で TS 型が生成され、差分がない

### この Phase で潰しておくべき落とし穴

WSL2 の環境問題（ネットワーク到達性、文字コード、パス、systemd 自動起動）を**ここで全部確認する**。後の Phase で機能を作り込んだ後に環境問題が出ると、原因の切り分けが難しくなる。`.cursor/skills/verify-windows-runtime/SKILL.md` を一度通す。

## Phase 1: データ収集の完成

**狙い**: 全データソースを繋ぎ、初回バックフィルを完了させる。ここが終われば分析に必要なデータが揃う。

### 実装項目

| # | 項目 | 参照 |
| --- | --- | --- |
| 1-1 | J-Quants コネクタ（銘柄マスタ、日足、財務サマリ）。`JQuantsAuth` を差し替え可能に | [02](02-data-ingestion.md) §2 |
| 1-2 | `JQUANTS_PLAN` による free / light の切替（遅延・レート制限・履歴期間を導出） | [02](02-data-ingestion.md) §2.1 |
| 1-3 | yfinance コネクタ（米国主ソース + 日本のギャップ補完） | [02](02-data-ingestion.md) §3 |
| 1-4 | `prices_daily` と `prices_live` の二経路分離 | [02](02-data-ingestion.md) §2.2 |
| 1-5 | 価格データの品質チェック（論理矛盾、異常変動、重複） | [02](02-data-ingestion.md) §3.3 |
| 1-6 | EDGAR コネクタ（submissions、companyfacts、company_tickers） | [02](02-data-ingestion.md) §7 |
| 1-7 | `financials` の PIT 処理（`filed_at` 基準）と `financials_pit` ビュー | [03](03-data-model.md) §2.4 |
| 1-8 | EDINET コネクタ（書類一覧、PDF取得） | [02](02-data-ingestion.md) §5 |
| 1-9 | Alpha Vantage / Finnhub フォールバック | [02](02-data-ingestion.md) §4 |
| 1-10 | Raw層の保存（`data/raw/{source}/{endpoint}/dt=.../`） | [02](02-data-ingestion.md) §1.4 |
| 1-11 | `data_gaps` / `data_conflicts` / `data_quality_flags` の記録 | [03](03-data-model.md) §2.15 |
| 1-12 | Collector ジョブとチェックポイント（営業日単位、doc_id単位） | [08](08-agent-loop.md) §3, §9 |
| 1-13 | バックフィルジョブ（中断・再開可能） | [02](02-data-ingestion.md) §10 |
| 1-14 | `data_freshness` ビューと UI ヘッダへの表示 | [03](03-data-model.md) §2.15 |
| 1-15 | 決算資料ハブ画面（一覧、フィルタ、PDF配信） | [ui/screens/05-filings-hub.md](ui/screens/05-filings-hub.md) |
| 1-16 | `documents/{doc_id}/file` エンドポイント（ローカル配信） | [06](06-filings-access.md) §3.3 |
| 1-17 | バックアップジョブ（SQLite backup API、EXPORT DATABASE） | [11](11-security-ops.md) §4 |

### 完了条件

- [ ] 初回バックフィルが完走する（日本株2年 + 米国株5年 + マクロ10年）。中断して再開しても重複や欠損が出ない
- [ ] `prices_daily` に日本株4,000銘柄 × 約490営業日のデータがある
- [ ] `data_freshness` が UI ヘッダに表示され、J-Quants の12週遅延が明示されている
- [ ] 決算資料ハブから有報のPDFがワンクリックで開く（PCとスマートフォンの両方）
- [ ] T-DQ-01〜05、T-PIT-01〜03 が通る
- [ ] `TDNET_ENABLED=false` の状態で全機能が動く（TDnet が必須依存になっていない）
- [ ] バックアップが日次で作られ、`state.sqlite` の復元が実際に成功する

### TDnet の扱い

TDnet はこの Phase では**実装するが既定で無効**にする。代替経路（`financials.forecast_op_income` の差分検出による業績修正の検出）を先に実装し、TDnet がなくても業績修正が検出できる状態にする（[02](02-data-ingestion.md) §6.3）。

## Phase 2: 分析エンジンと検証基盤

**狙い**: 統計的に妥当な分析基盤を作る。**ここを飛ばして LLM に進んではならない。**

### 実装項目

| # | 項目 | 参照 |
| --- | --- | --- |
| 2-1 | `pit_guard`（`assert_pit_safe`、`effective_date`） | [04](04-analysis-engine.md) §1.1 |
| 2-2 | 特徴量の実装（リターン、モメンタム、ボラ、テクニカル、流動性） | [04](04-analysis-engine.md) §1.2-1.5 |
| 2-3 | 特徴量の実装（バリュエーション、クオリティ、成長、改定、為替感応度） | [04](04-analysis-engine.md) §1.6-1.9 |
| 2-4 | 欠損値の扱い（ゼロ埋め禁止、負のPERの NULL 化） | [04](04-analysis-engine.md) §1.10 |
| 2-5 | GARCH(1,1)（収束・定常性チェックとフォールバック） | [04](04-analysis-engine.md) §1.3.1 |
| 2-6 | **`PurgedWalkForwardCV` の実装** | [04](04-analysis-engine.md) §3.3 |
| 2-7 | **T-LEAK-01〜06 の実装（特に T-LEAK-04 の合成データテスト）** | [12](12-testing-validation.md) §2 |
| 2-8 | LightGBM ランカー（回帰 + 分位点回帰の3モデル） | [04](04-analysis-engine.md) §3.4, §3.5 |
| 2-9 | Rank IC の計算と `model_runs` への記録（`n_trials` 含む） | [04](04-analysis-engine.md) §3.6 |
| 2-10 | ランダムウォークのベースラインと ARIMAX | [04](04-analysis-engine.md) §2.2, §2.3 |
| 2-11 | **Diebold-Mariano 検定（HAC分散付き）** | [04](04-analysis-engine.md) §2.5 |
| 2-12 | VECM（共和分検定で判定してから使う） | [04](04-analysis-engine.md) §2.4 |
| 2-13 | バックテストエンジン（コスト必須引数、サイズ依存スリッページ） | [04](04-analysis-engine.md) §4.1, §4.2 |
| 2-14 | **Deflated Sharpe Ratio** | [04](04-analysis-engine.md) §4.4 |
| 2-15 | セクター中立化 z-score（MADベース） | [05](05-scoring-screening.md) §2.2 |
| 2-16 | ファクターグループ集約と `quant_score` | [05](05-scoring-screening.md) §3, §4 |
| 2-17 | レジーム検出（ボラ、相関、モデル劣化、特徴量ドリフト） | [04](04-analysis-engine.md) §5 |
| 2-18 | Analyst ジョブ | [08](08-agent-loop.md) §4 |
| 2-19 | スクリーナー画面と API | [ui/screens/04-screener.md](ui/screens/04-screener.md) |
| 2-20 | 銘柄詳細画面（チャート、財務、特徴量、資料一覧） | [ui/screens/03-stock-detail.md](ui/screens/03-stock-detail.md) |
| 2-21 | 為替・マクロ画面（ファンチャート、DM検定結果、金利差） | [ui/screens/06-fx-macro.md](ui/screens/06-fx-macro.md) |
| 2-22 | モデルラボ画面（Rank IC、特徴量重要度、バックテスト結果） | [ui/screens/07-model-lab.md](ui/screens/07-model-lab.md) |

### 完了条件

- [ ] **T-LEAK-04（合成ノイズデータで Rank IC の t統計量が 2.5 未満）が通る**
- [ ] T-LEAK-01〜06、T-PIT-01〜05、T-STAT-01〜05 が全て通る
- [ ] 実データでの Rank IC が測定されている（値の大小は問わない。**0.10 を超える場合はリークを疑って再検証する**）
- [ ] バックテストが実行でき、Deflated Sharpe Ratio が出力される
- [ ] 為替画面に「ランダムウォークに対する優位性は確認できていません」が表示される（DM検定で有意でない場合）
- [ ] スクリーナーで条件を指定して500件以内の結果が3秒以内に返る
- [ ] 特徴量計算が全銘柄で10分以内に完了する

### この Phase での判断ポイント

Rank IC が 0.02 を下回る場合、モデルに実用的な予測力がない。その場合の選択肢:

1. 特徴量を追加する（`.cursor/skills/add-analysis-factor/SKILL.md`）
2. ホライズンを変える（H5 が効かず H20 が効くことはよくある）
3. ユニバースを絞る（流動性の高い銘柄に限定すると IC が上がることがある）
4. **予測モデルを諦め、`quant_score` によるルールベースのスクリーニングに留める**

選択肢4は失敗ではない。**予測力がないのに予測を表示するより、スクリーニングツールとして正直に使う方が実用的である。** この判断を Phase 2 の完了時点で明示的に行う。

## Phase 3: LLM と決算資料の読解

**狙い**: 定性分析を加える。Phase 2 の定量基盤があるため、LLM の出力を定量データと突き合わせて検証できる状態で始める。

### 実装項目

| # | 項目 | 参照 |
| --- | --- | --- |
| 3-1 | `models.yaml` と `LLMRouter`（tier ベースの呼び出し） | [07](07-llm-rag.md) §2 |
| 3-2 | `CostGuard`（日次・月次キャップ、キルスイッチ） | [07](07-llm-rag.md) §3 |
| 3-3 | `llm_calls` / `cost_budget` への記録 | [03](03-data-model.md) §3.4 |
| 3-4 | `redact` フィルタと `assert_no_sensitive_data` | [11](11-security-ops.md) §3 |
| 3-5 | 開示資料の要約（`doc_summary.jinja`、PDFネイティブ入力） | [07](07-llm-rag.md) §5.2 |
| 3-6 | `document_summaries` のキャッシュ（`prompt_hash` + `input_hash`） | [06](06-filings-access.md) §7 |
| 3-7 | チャンク分割とセクション識別 | [07](07-llm-rag.md) §4.2 |
| 3-8 | 埋め込み生成と LanceDB への格納（`VectorStore` 抽象経由） | [03](03-data-model.md) §4 |
| 3-9 | ハイブリッド検索（ベクトル + BM25、RRF） | [07](07-llm-rag.md) §4.3, §4.4 |
| 3-10 | 引用検証（`verify_citation`、`normalize_ja`） | [07](07-llm-rag.md) §4.5 |
| 3-11 | `qual_score` の集約（鮮度減衰、確信度の独立計算） | [08](08-agent-loop.md) §5.2 |
| 3-12 | `total_score`（±12点の調整上限） | [05](05-scoring-screening.md) §6.3 |
| 3-13 | Researcher ジョブ（対象絞り込み、コストキャップ時のフォールバック） | [08](08-agent-loop.md) §5 |
| 3-14 | オンデマンド要約 API（`POST /documents/{doc_id}/summary`） | [09](09-api-spec.md) §2.5 |
| 3-15 | 銘柄詳細への要約表示、決算資料ハブへの要約表示 | [ui/screens/03-stock-detail.md](ui/screens/03-stock-detail.md) |
| 3-16 | コスト可視化（設定画面） | [11](11-security-ops.md) §6.4 |

### 完了条件

- [ ] 有報PDF（100ページ超）が1回のLLM呼び出しで要約される
- [ ] 同じ資料に2回課金されない（キャッシュヒット率が2日目以降 70% 超）
- [ ] **T-LLM-03（コストキャップ到達時に定量スコアのみで推奨が生成される）が通る**
- [ ] T-LLM-01, 02, 07, 08、T-SEC-01, 02 が通る
- [ ] 引用検証が捏造された引用を検出する（実データで確認）
- [ ] 日次コストが $1.0 のキャップ内に収まる（1週間の実運用で確認）
- [ ] 保有株数・取得単価がプロンプトに含まれないことをログで確認

## Phase 4: エージェントループと推奨生成

**狙い**: 推奨カードを生成し、Critic で検証し、Evaluator で自己評価する完全なループを回す。

### 実装項目

| # | 項目 | 参照 |
| --- | --- | --- |
| 4-1 | ユニバースフィルタとリスク制約 | [05](05-scoring-screening.md) §7.1, §7.2 |
| 4-2 | reason codes の付与 | [05](05-scoring-screening.md) §7.4 |
| 4-3 | `hit_rate_prior` の算出（母数併記、n<20 で conviction=low 強制） | [05](05-scoring-screening.md) §7.7 |
| 4-4 | Strategist ジョブと `thesis.jinja`（bear case の敵対的指示） | [08](08-agent-loop.md) §6 |
| 4-5 | `recommendations` の不変条件検証（リポジトリ層） | [03](03-data-model.md) §2.9 |
| 4-6 | Critic の機械的検証（引用、鮮度、PIT、定型文、確信度、信頼区間） | [08](08-agent-loop.md) §7.2 |
| 4-7 | Critic の LLM 検証（`critic.jinja`） | [07](07-llm-rag.md) §5.4 |
| 4-8 | 却下率の監視 | [08](08-agent-loop.md) §7.5 |
| 4-9 | Evaluator の実績計算（翌営業日始値エントリー、MFE/MAE） | [08](08-agent-loop.md) §8.2 |
| 4-10 | 集計指標（conviction別的中率の単調性、信頼区間カバレッジ） | [08](08-agent-loop.md) §8.3 |
| 4-11 | `agent_memory` の更新（追加、置換、無効化） | [08](08-agent-loop.md) §8.4 |
| 4-12 | 教訓の有効性評価（`memory_ids_used` を用いた比較） | [08](08-agent-loop.md) §8.5 |
| 4-13 | `factor_weights` の再フィット提案（承認制） | [05](05-scoring-screening.md) §8 |
| 4-14 | 中断ジョブの検出と再開（`resume_interrupted_jobs`） | [08](08-agent-loop.md) §9.3 |
| 4-15 | 推奨銘柄画面（カード、bear case、引用、実績履歴） | [ui/screens/02-recommendations.md](ui/screens/02-recommendations.md) |
| 4-16 | ダッシュボード画面 | [ui/screens/01-dashboard.md](ui/screens/01-dashboard.md) |
| 4-17 | エージェントコンソール画面 | [ui/screens/08-agent-console.md](ui/screens/08-agent-console.md) |
| 4-18 | SSE によるジョブ進捗配信 | [09](09-api-spec.md) §2.8 |
| 4-19 | Webhook 通知 | [10](10-mobile-pwa.md) §5 |

### 完了条件

- [ ] 日次バッチが平日に自動実行され、60分以内に完了する
- [ ] 推奨カードが生成され、**すべてに bear case（20文字以上、定型文でない）と引用がある**
- [ ] T-LLM-04, 05, 06、T-INT-01〜04 が通る
- [ ] Critic の却下率が 10-30% の範囲にある（0% でも 50%超 でもない）
- [ ] 60営業日の運用後、`recommendation_outcomes` に実績が蓄積され、conviction別の的中率が表示される
- [ ] `agent_memory` に教訓が生成され、次回のプロンプトに注入されていることがログで確認できる
- [ ] WSL2 を強制再起動しても、中断されたジョブがチェックポイントから再開される
- [ ] Webhook 通知が届く

### この Phase での重要な観察点

運用開始から60営業日は `conviction` が `low` に固定される（実績がないため）。**この期間に「確信度が上がらない」ことを不具合と誤認しないこと。** これは意図した振る舞いである。

60営業日後に conviction 別の的中率が単調（high > medium > low）でない場合、確信度の付け方が機能していない。これは重要な発見であり、`agent_memory` に caveat として記録される。

## Phase 5: ポートフォリオ・売買日誌・PWA の仕上げ

**狙い**: 実際の売買と結びつけ、「推奨の質」と「実行の質」を分離して測れるようにする。

### 実装項目

| # | 項目 | 参照 |
| --- | --- | --- |
| 5-1 | `trades` / `positions` の CRUD | [03](03-data-model.md) §3.5 |
| 5-2 | CSV インポート（証券会社の取引履歴形式） | [09](09-api-spec.md) §2.9 |
| 5-3 | 評価損益の計算（`prices_live` ベース、遅延を明示） | [09](09-api-spec.md) §2.9 |
| 5-4 | `linked_rec_id` による推奨との紐付け | [03](03-data-model.md) §3.5 |
| 5-5 | `emotion_tag` の記録と分析 | [09](09-api-spec.md) §2.9 |
| 5-6 | `trades/analysis`（推奨の質 vs 実行の質の分離） | [09](09-api-spec.md) §2.9 |
| 5-7 | ポートフォリオ・売買日誌画面 | [ui/screens/09-portfolio-journal.md](ui/screens/09-portfolio-journal.md) |
| 5-8 | 設定画面（色設定、コスト上限、キルスイッチ、プラン切替） | [ui/screens/10-settings.md](ui/screens/10-settings.md) |
| 5-9 | 上昇下落カラーの切替（日本式 / 米国式） | [ui/design-system.md](ui/design-system.md) |
| 5-10 | PWA（manifest、Service Worker、キャッシュ戦略） | [10](10-mobile-pwa.md) §3 |
| 5-11 | オフライン表示バナー | [10](10-mobile-pwa.md) §3.2 |
| 5-12 | Background Sync（売買記録のオフライン入力） | [10](10-mobile-pwa.md) §3.3 |
| 5-13 | ボトムナビゲーション（モバイル） | [ui/interaction-patterns.md](ui/interaction-patterns.md) |
| 5-14 | Tailscale Serve による HTTPS 化 | [10](10-mobile-pwa.md) §2.3 |
| 5-15 | E2E テスト（T-E2E-01〜10） | [12](12-testing-validation.md) §11 |
| 5-16 | 週次深掘りレビュー（`deep` 層） | [07](07-llm-rag.md) §2.4 |

### 完了条件

- [ ] スマートフォンのホーム画面にアプリとして追加でき、スタンドアロン表示になる
- [ ] オフラインでも直近のダッシュボードが見え、「オフライン表示」が明示される
- [ ] オフラインで入力した売買記録がオンライン復帰後に送信される
- [ ] 上昇下落の色設定を切り替えると全画面で反映される
- [ ] `trades/analysis` で `emotion_tag` 別の的中率が表示される
- [ ] T-E2E-01〜10 が通る
- [ ] 週次深掘りレビューが土曜に自動実行される

## Phase 6: 改善とチューニング（継続的）

**狙い**: 完成ではなく、継続的な改善のサイクルを回す。

### 継続的な作業

| 頻度 | 作業 | SKILL |
| --- | --- | --- |
| 随時 | 新規データソースの追加 | `.cursor/skills/add-data-source/` |
| 随時 | 新規ファクターの追加と検証 | `.cursor/skills/add-analysis-factor/` |
| 随時 | バックテストによる戦略の検証 | `.cursor/skills/run-backtest/` |
| 随時 | 仕様書の追加・改訂 | `.cursor/skills/write-spec-doc/` |
| 月次 | モデルの再学習と Rank IC の確認 | |
| 月次 | 重み更新の承認判断 | `.cursor/skills/agent-eval-loop/` |
| 月次 | LLM コストの内訳確認とプロンプト最適化 | |
| 四半期 | `agent_memory` の棚卸し | `.cursor/skills/agent-eval-loop/` |
| 四半期 | プロンプトの改善（A/B比較） | [07](07-llm-rag.md) §5.6 |
| 年次 | バックアップからの復旧手順の実施 | `.cursor/skills/verify-windows-runtime/` |
| 環境不調時 | WSL2 / Tailscale / 文字コードの切り分け | `.cursor/skills/verify-windows-runtime/` |

### 検討する拡張（優先度順）

| # | 拡張 | 前提条件 | 参照 |
| --- | --- | --- | --- |
| 6-1 | J-Quants Light への移行 | 12週遅延が実運用の障害になったと確認できたとき | [11](11-security-ops.md) §6.5 |
| 6-2 | XBRL の直接パース（`arelle`） | LLMによる数値抽出の精度が不足したとき | [02](02-data-ingestion.md) §5.3 |
| 6-3 | セクター・テーマ単位の分析 | 個別銘柄の分析が安定したとき | |
| 6-4 | イベントドリブン分析（決算サプライズの反応） | 決算発表日データが揃ったとき | [06](06-filings-access.md) §10 |
| 6-5 | ポートフォリオ最適化（リスクパリティ等） | 保有銘柄が10以上になったとき | |
| 6-6 | クラウド移行（Phase B） | 自宅PCの常時稼働が負担になったとき | [10](10-mobile-pwa.md) §6 |
| 6-7 | **自動発注（`ExecutionAdapter` の実装）** | **判断支援の精度が実績で確認できたとき。それ以前には着手しない** | [14](14-future-brokerage.md) |

### 6-7 に着手する条件（明示）

自動発注は最後である。着手条件を明示しておく。

- [ ] 推奨の的中率が 6ヶ月以上安定して 55% を超えている
- [ ] conviction 別の的中率が単調である（確信度の付け方が妥当）
- [ ] バックテストの Deflated Sharpe Ratio が有意である
- [ ] 手動売買での実行の質（`trades/analysis`）が把握できている
- [ ] 上記を踏まえて「自動化する価値がある」と判断できる

**これらが満たされないまま自動発注を実装すると、精度の低い判断を高速に実行するだけになる。** 判断支援の精度が上がっていないなら、自動化しても損失が加速するだけである。

## 実装の依存関係

```
Phase 0（基盤）
   │
   ▼
Phase 1（データ）
   │
   ▼
Phase 2（分析・検証）  ←── ここを飛ばさない
   │
   ├──────────────┐
   ▼              ▼
Phase 3（LLM）   （Phase 2 単独でもスクリーニングツールとして使える）
   │
   ▼
Phase 4（エージェント）
   │
   ▼
Phase 5（PWA・売買日誌）
   │
   ▼
Phase 6（継続改善）
   │
   ▼（条件を満たした場合のみ）
自動発注（docs/14）
```

**Phase 2 が完了した時点で、既に実用的なツールになっている**（スクリーナー + 決算資料ワンクリック + 為替の統計分析）。Phase 3 以降は付加価値であり、途中で止めても損失にならない構成にしている。

## 各 Phase での「やらないこと」

途中で手を広げないための明示。

| Phase | やらないこと |
| --- | --- |
| 0 | 認証、Docker、CI/CD の作り込み |
| 1 | 分析、LLM、推奨 |
| 2 | LLM、推奨カード、エージェント |
| 3 | 推奨生成、Critic、Evaluator |
| 4 | ポートフォリオ、PWA の作り込み |
| 5 | クラウド移行、自動発注 |
| 全体 | 自動発注、証券口座連携、マルチユーザー、SaaS化 |

## 参照

- 各仕様書: [README.md](../README.md) のインデックス
- 自動発注の将来設計: [14-future-brokerage.md](14-future-brokerage.md)
- 環境構築: [15-windows-runtime.md](15-windows-runtime.md)
