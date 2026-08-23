# 11. セキュリティ・シークレット管理・バックアップ・監視・コスト上限

## 1. シークレット管理

### 1.1 保管場所

| 環境 | 保管方法 |
| --- | --- |
| Phase A（WSL2） | `.env`（gitignore 済み）+ 環境変数 |
| Phase B（クラウド） | Secret Manager / Fly Secrets |
| CI | リポジトリのシークレット（実際の値は使わず、テスト用ダミー） |

**`.env` を絶対に Git に入れない。** `.gitignore` に以下を必ず含める。

```gitignore
.env
.env.*
!.env.example
data/
*.duckdb
*.sqlite
*.sqlite-wal
*.sqlite-shm
__pycache__/
.venv/
node_modules/
.next/
*.parquet
*.lance/
```

`data/` をまとめて除外することで、DBファイル・Parquet・PDF blob の誤コミットを防ぐ。

### 1.2 `.env.example`

実際の値を持たないテンプレートをリポジトリに置く。**全項目を列挙することで、必要なキーの一覧がドキュメントになる。**

```bash
# ===== データソース =====
JQUANTS_API_KEY=
JQUANTS_PLAN=free                    # free | light
EDINET_SUBSCRIPTION_KEY=
FRED_API_KEY=
EDGAR_USER_AGENT=Your Name (your-email@example.com)   # 必須。SECのポリシー
ALPHA_VANTAGE_API_KEY=               # 任意（フォールバック用）
FINNHUB_API_KEY=                     # 任意
TDNET_ENABLED=false                  # 利用規約を確認した上で有効化

# ===== LLM =====
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
OPENAI_API_KEY=                      # 任意（埋め込みのフォールバック）
LITELLM_LOG_LEVEL=WARNING

# ===== ストレージ =====
DATA_DIR=/home/user/ai-stock/data    # WSL2ホーム配下。/mnt/c は禁止
DATABASE_URL=sqlite+aiosqlite:///${DATA_DIR}/state.sqlite
WAREHOUSE_PATH=${DATA_DIR}/warehouse/analytics.duckdb
VECTOR_DIR=${DATA_DIR}/vectors

# ===== アプリ =====
API_HOST=0.0.0.0
API_PORT=8000
WEB_PORT=3000
AUTH_MODE=none                       # none | token | passkey
CORS_ORIGINS=http://localhost:3000
TZ=Asia/Tokyo
PYTHONUTF8=1                         # 必須。文字コード事故の防止

# ===== コスト上限 =====
LLM_DAILY_CAP_USD=1.0
LLM_MONTHLY_CAP_USD=20.0

# ===== 通知 =====
NOTIFY_WEBHOOK_URL=                  # Slack / Discord の Incoming Webhook
NOTIFY_ENABLED=true

# ===== 運用 =====
LOG_LEVEL=INFO
BACKUP_DIR=/home/user/ai-stock/backups
SENTRY_DSN=                          # 任意
```

### 1.3 起動時の検証

```python
# packages/core/config/settings.py
class Settings(BaseSettings):
    jquants_api_key: SecretStr
    edinet_subscription_key: SecretStr
    fred_api_key: SecretStr
    edgar_user_agent: str
    anthropic_api_key: SecretStr
    gemini_api_key: SecretStr
    data_dir: Path
    # ...

    @field_validator("edgar_user_agent")
    @classmethod
    def edgar_ua_must_have_contact(cls, v: str) -> str:
        """SECは実名と連絡先を含むUser-Agentを要求する。
        空や無効な値で叩くとIPブロックされ、復旧に時間がかかる。"""
        if "@" not in v or len(v) < 10:
            raise ValueError(
                "EDGAR_USER_AGENT には実名とメールアドレスを含めてください。"
                "例: 'Taro Yamada (taro@example.com)'")
        return v

    @field_validator("data_dir")
    @classmethod
    def data_dir_not_on_windows_mount(cls, v: Path) -> Path:
        """/mnt/c 配下はI/Oが桁違いに遅く、DuckDB/Parquet処理が実用にならない。"""
        if str(v).startswith("/mnt/"):
            raise ValueError(
                f"DATA_DIR に Windows マウント（{v}）を指定できません。"
                "WSL2 のホーム配下（例: /home/user/ai-stock/data）を使ってください。"
                "詳細: docs/15-windows-runtime.md §6")
        return v
```

**起動時に落とすことが重要である。** 設定ミスを実行時に発見すると、数時間のバックフィルの後で気付くことになる。

### 1.4 ログへの漏洩防止

```python
# SecretStr を使うことで、うっかりログに出しても値が表示されない
>>> settings.jquants_api_key
SecretStr('**********')
>>> str(settings.jquants_api_key)
'**********'
>>> settings.jquants_api_key.get_secret_value()   # 明示的に取り出す
'actual-key-value'
```

加えて、ログフィルタで既知のシークレットパターンをマスクする。

```python
class SecretMaskingFilter(logging.Filter):
    """APIキーがログに出るのを防ぐ最後の砦。
    リクエストURLにキーがクエリパラメータとして含まれる場合（FRED等）に効く。"""
    PATTERNS = [
        (re.compile(r"api_key=[\w-]+"), "api_key=***"),
        (re.compile(r"apikey=[\w-]+"), "apikey=***"),
        (re.compile(r"token=[\w.-]+"), "token=***"),
        (re.compile(r"(sk-|xoxb-)[\w-]{20,}"), r"\1***"),
    ]
```

FRED API はキーをクエリパラメータで渡すため、リクエストURLをそのままログに出すと漏洩する。この項目は具体的なリスクである。

## 2. ネットワークセキュリティ

### 2.1 Phase A

| 項目 | 設定 |
| --- | --- |
| 到達範囲 | Tailscale の tailnet 内のみ |
| インターネットへの公開 | しない（`tailscale funnel` を使わない） |
| バインドアドレス | `0.0.0.0`（WSL2 内。mirrored networking で Windows 側から見える） |
| Windows ファイアウォール | Hyper-V の受信許可が必要（[15-windows-runtime.md](15-windows-runtime.md) §2） |
| 認証 | なし（tailnet 内に限定されるため） |

**tailnet 内に限定することがセキュリティ境界である。** これに依存する以上、Tailscale の ACL 設定を確認しておく。共有デバイスがある tailnet では、ACL でアクセスを制限する。

```jsonc
// Tailscale ACL（tailnet 全体でデバイス共有している場合）
{
  "acls": [
    {"action": "accept", "src": ["autogroup:owner"],
     "dst": ["<windows-host>:3000,8000"]}
  ]
}
```

### 2.2 Phase B

| 項目 | 設定 |
| --- | --- |
| HTTPS | 必須（Vercel / Cloud Run が自動） |
| 認証 | パスキー（WebAuthn）または Bearer トークン |
| レート制限 | 認証エンドポイントに 5 req/min |
| CORS | フロントのオリジンのみ許可 |
| セキュリティヘッダ | `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy` |
| シークレット | Secret Manager |

## 3. LLM に送るデータの制限

[07-llm-rag.md](07-llm-rag.md) §7 の通り。ここでは運用上の確認方法を記す。

| 送らない情報 | 検証方法 |
| --- | --- |
| 保有株数 | `redact` フィルタのユニットテスト |
| 取得単価 | 同上 |
| 評価額・総資産 | 同上 |
| 口座種別 | 同上 |

```python
# packages/core/llm/redact.py
FORBIDDEN_KEYS = {"quantity", "avg_cost", "market_value", "unrealized_pnl",
                  "account_type", "total_assets", "cash_balance", "fee"}

def assert_no_sensitive_data(payload: Any, path: str = "") -> None:
    """プロンプト組み立ての最終段で呼ぶ。禁止キーが含まれていたら例外。"""
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k in FORBIDDEN_KEYS:
                raise SensitiveDataInPromptError(f"{path}.{k} は LLM に送れません")
            assert_no_sensitive_data(v, f"{path}.{k}")
    elif isinstance(payload, list):
        for i, v in enumerate(payload):
            assert_no_sensitive_data(v, f"{path}[{i}]")
```

**この検証を LLM 呼び出しの直前に必ず通す。** プロンプトテンプレートを編集したときに、うっかり保有情報を含めてしまうのを防ぐ。テストは [12-testing-validation.md](12-testing-validation.md) の T-SEC-01。

## 4. バックアップ

### 4.1 対象と優先度

| 対象 | サイズ | 優先度 | 再生成可能か |
| --- | --- | --- | --- |
| `state.sqlite` | 約 50MB | **最高** | **不可**。売買日誌、agent_memory、設定は失うと復元できない |
| `data/raw/` | 約 2GB/年 | 高 | 不可（過去のAPIレスポンスは取り直せない。特に J-Quants 無料プランは2年分しか遡れない） |
| PDF blob | 約 20GB | 中 | 部分的に可能（TDnet は30日で消えるので不可、EDINET/EDGAR は再取得可能） |
| `analytics.duckdb` | 約 1.5GB | 低 | **可能**（Raw層から再構築できる） |
| `data/vectors/` | 約 12GB | 低 | 可能（再埋め込み。ただしコストがかかる） |
| モデルアーティファクト | 約 100MB | 低 | 可能（再学習） |

**`state.sqlite` と `data/raw/` が最優先である。** DuckDB とベクトルストアは再構築できるので、バックアップから外してもよい（容量削減）。

### 4.2 バックアップ方式

```python
# services/agent/jobs/backup.py
# 日次（バッチ完了後）に実行
def daily_backup() -> BackupResult:
    ts = datetime.now(JST).strftime("%Y%m%d_%H%M%S")   # ':' を使わない
    dest = BACKUP_DIR / ts
    dest.mkdir(parents=True)

    # (1) SQLite: オンラインバックアップAPIを使う（コピーではなく）
    #     単純な cp では WAL が中途半端な状態でコピーされ壊れる可能性がある
    with sqlite3.connect(STATE_DB) as src, sqlite3.connect(dest / "state.sqlite") as dst:
        src.backup(dst)

    # (2) DuckDB: EXPORT DATABASE（バイナリコピーはバージョン依存で危険）
    duckdb.connect(WAREHOUSE, read_only=True).execute(
        f"EXPORT DATABASE '{dest / 'warehouse'}' (FORMAT PARQUET)")

    # (3) Raw層: 前日分の差分のみ
    rsync_incremental(RAW_DIR, dest / "raw", since=yesterday())

    # (4) 設定とプロンプト（Gitで管理されているが念のため）
    shutil.copytree(CONFIG_DIR, dest / "config")

    prune_old_backups(keep_daily=7, keep_weekly=4, keep_monthly=6)
    return BackupResult(path=dest, size_bytes=dir_size(dest))
```

**SQLite のバックアップに `cp` を使わない。** WAL モードで動いている DB を単純コピーすると、コミット途中の状態を拾って壊れることがある。`sqlite3` の `backup` API を使う。

**DuckDB のバイナリファイルをコピーしない。** DuckDB のストレージ形式はバージョン間で互換性がないことがある。`EXPORT DATABASE` で Parquet + SQL に出すのが安全である。

### 4.3 保持世代

| 種別 | 保持数 |
| --- | --- |
| 日次 | 7世代 |
| 週次（日曜） | 4世代 |
| 月次（月初） | 6世代 |

### 4.4 オフサイトバックアップ

自宅PCのディスク障害に備え、`state.sqlite` と `raw/` の圧縮アーカイブを週1回クラウドに置く。

| 選択肢 | 特徴 |
| --- | --- |
| Cloudflare R2 | エグレス無料。40GB で月 $0.6 程度 |
| Backblaze B2 | 安価 |
| Google Drive / OneDrive | 既に契約していれば追加費用なし。`rclone` で自動化 |

**最低限 `state.sqlite`（50MB）だけでもオフサイトに置く。** これだけで売買日誌と教訓は守られる。

### 4.5 復旧手順（実際に試しておく）

```
1. 新しい環境に WSL2 をセットアップする（docs/15-windows-runtime.md）
2. リポジトリをクローンする
3. .env を再作成する（APIキーは各サービスから再取得）
4. バックアップから state.sqlite を data/ に配置する
5. バックアップから raw/ を data/raw/ に展開する
6. `uv run python -m services.agent.rebuild --from-raw` を実行する
   → Raw層から DuckDB を再構築する（正規化ロジックを再実行するだけなので API 呼び出しなし）
7. `uv run python -m services.agent.reembed` を実行する（ベクトルストアの再構築、LLMコストが発生）
8. サービスを起動する
```

**手順6が Raw層を保存する意味である。** API を叩き直さずに全データを再構築できる。J-Quants 無料プランでは過去2年しか取得できないため、Raw層がなければ古いデータは永久に失われる。

**復旧手順は年1回、実際に試す。** バックアップが取れていても復元できないケースは頻繁にある。`.cursor/skills/verify-windows-runtime/SKILL.md` にチェック項目として含める。

## 5. 監視

### 5.1 監視対象

| 対象 | 指標 | 異常判定 | 通知 |
| --- | --- | --- | --- |
| 日次バッチ | 完了したか | 予定時刻+2時間で未完了 | Webhook |
| 日次バッチ | 所要時間 | 前週平均の2倍超 | アプリ内 |
| データ鮮度 | ソース別の `latest_as_of` | 期待日付から3営業日以上遅れ | Webhook |
| データソース | 連続失敗回数 | 3日連続 | Webhook |
| データ品質 | 除外行の比率 | 全体の5%超 | アプリ内 |
| スキーマ変更 | `schema_drift_count` | 1件でも | Webhook |
| LLMコスト | 日次・月次の使用額 | キャップの80%到達 | Webhook |
| LLMコスト | キャッシュヒット率 | 50%未満 | アプリ内 |
| モデル | 直近20日の Rank IC | 過去1年の下位10% | アプリ内 |
| モデル | 信頼区間のカバレッジ | 想定から±15ポイント以上乖離 | アプリ内 |
| Critic | 却下率 | 0% または 50%超が3日連続 | アプリ内 |
| ディスク | 空き容量 | 20GB 未満 | Webhook |
| プロセス | api / agent / web の生存 | ダウン | systemd が再起動 + Webhook |
| 中断ジョブ | `status='running'` の滞留 | 2時間超 | 自動再開 + アプリ内 |

### 5.2 ログ

構造化ログ（JSON）を使う。`structlog` を採用する。

```python
logger.info("collector_step_done",
            job_run_id=1284, source="jquants", step="prices",
            rows=4012, api_calls=1, duration_sec=12.4)
```

| 出力先 | 内容 |
| --- | --- |
| 標準出力 | systemd journal 経由で `journalctl -u ai-stock-agent` で参照 |
| ファイル | `data/logs/agent-YYYY-MM-DD.jsonl`（30日保持） |
| DB | 重要なイベントのみ `job_runs` / `alerts` |

**ファイルへの書き込みは必ず `encoding="utf-8"` を明示する**（日本語の銘柄名やタイトルがログに入る。[15-windows-runtime.md](15-windows-runtime.md) §4）。

```python
handler = logging.FileHandler(log_path, encoding="utf-8")   # encoding 必須
```

### 5.3 ヘルスチェック

`GET /api/v1/system/health`（[09-api-spec.md](09-api-spec.md) §2.10）を systemd の watchdog と外部監視の両方から使う。

Phase A では外部監視は不要（自宅PCなので気付く）。Phase B では Uptime Robot 等の無料枠を使う。

### 5.4 エラー追跡

`SENTRY_DSN` が設定されていれば Sentry に送る。個人用ツールでは必須ではないが、**スタックトレースを後から見返せることの価値は大きい**。

送信前に PII とシークレットをスクラブする設定を必ず入れる。

```python
sentry_sdk.init(dsn=..., send_default_pii=False,
                before_send=scrub_sensitive_data)
```

## 6. コスト上限とキルスイッチ

### 6.1 二重の上限

| 上限 | 既定値 | 超過時の動作 | 解除 |
| --- | --- | --- | --- |
| 日次 | $1.00 | LLM 呼び出しを停止。定量スコアのみで続行 | 翌日0時に自動解除 |
| 月次 | $20.00 | 同上 | **手動解除のみ** |

月次を手動解除にするのは、月次を超えている状況は「何かが暴走している」可能性が高く、原因を確認せずに再開すべきでないためである。

### 6.2 事前見積もりによる予防

呼び出し前にトークン数を見積もり、キャップを超えるなら**呼び出さずに拒否する**。

```python
def estimate_cost(tier: str, messages: list[Message],
                  files: list[Path] | None) -> float:
    model = config.resolve(tier)
    input_tokens = count_tokens(messages)
    if files:
        for f in files:
            # PDFのトークン数はページ数から概算する（実測値で係数を調整する）
            input_tokens += estimate_pdf_tokens(f)
    output_tokens = model.max_output_tokens        # 最大値で見積もる（安全側）
    return (input_tokens / 1e6 * model.input_usd_per_mtok
            + output_tokens / 1e6 * model.output_usd_per_mtok)
```

**出力トークンを最大値で見積もる**ことで安全側に倒す。実際の出力が短ければ、記録される実コストは見積もりより小さくなる。

### 6.3 キルスイッチ

| 発動元 | 動作 |
| --- | --- |
| 設定画面のトグル（`llm.kill_switch`） | 即座に全 LLM 呼び出しを停止 |
| 日次キャップ超過 | 自動発動 |
| 月次キャップ超過 | 自動発動（手動解除） |
| 環境変数 `LLM_KILL_SWITCH=1` | 起動時から停止 |

キルスイッチが立っているときの振る舞い（[07-llm-rag.md](07-llm-rag.md) §3）:

- 定量スコアのみで推奨を生成する
- 既存の要約キャッシュは引き続き使う（新規呼び出しのみ停止）
- UI に「定性分析は停止中です」を明示
- `alerts` に記録

### 6.4 コストの可視化

設定画面と エージェントコンソール画面に表示する。

```
【今日】  $0.42 / $1.00     ████████░░░░░░░░░░░░  42%
【今月】  $6.18 / $20.00    ██████░░░░░░░░░░░░░░  31%

用途別（今月）
  開示資料の要約     $3.80  (61%)   324 calls  キャッシュヒット率 78%
  推奨の論拠生成     $1.42  (23%)   142 calls
  Critic レビュー    $0.61  (10%)   142 calls
  Evaluator          $0.21  ( 3%)    20 calls
  埋め込み           $0.14  ( 2%)  3,240 chunks

tier別（今月）
  bulk (Gemini 3.7 Flash)   $3.94
  default (Claude Sonnet 5) $2.24
  deep (Claude Opus 5)      $0.00

[キルスイッチ: OFF ▢]  [日次上限を変更]  [月次上限を変更]
```

### 6.5 データソース費用

無料枠のみで開始するため 0円。有料化を検討する条件を明記しておく。

| 移行先 | 費用 | 検討する条件 |
| --- | --- | --- |
| J-Quants Light | 月1,650円 | 12週遅延が実運用の障害になったとき。または過去5年の履歴が必要になったとき（CV分割数を増やしたい場合） |
| J-Quants Standard 以上 | 要確認 | 財務詳細や信用残など追加データが必要になったとき |
| Alpha Vantage 有料 | - | yfinance が恒久的に壊れたとき |

**J-Quants Light への移行判断基準**: 12週遅延データでバックテストを回し、その戦略を yfinance の現在値で実行する運用が3ヶ月継続できたなら、遅延自体は障害になっていない。障害になるのは「決算直後の反応を捉えたい」ような短期戦略の場合であり、その必要性が確認できてから課金する。

## 7. 運用の日常フロー

| タイミング | 作業 | 所要時間 |
| --- | --- | --- |
| 毎朝 | ダッシュボードを確認（バッチ完了、アラート、新規推奨） | 3分 |
| 毎朝 | 保有銘柄の新規開示を確認 | 2分 |
| 売買時 | 売買日誌に記録（判断理由と感情タグを含める） | 2分 |
| 毎週土曜 | 週次深掘りレビューの結果を確認 | 15分 |
| 毎週土曜 | Critic の却下理由の内訳を確認 | 5分 |
| 毎月初 | モデル再学習の結果と Rank IC を確認 | 15分 |
| 毎月初 | 重み更新の提案を承認 / 却下 | 10分 |
| 毎月初 | LLM コストの内訳を確認 | 5分 |
| 四半期 | agent_memory の棚卸し（有害な教訓の無効化） | 30分 |
| 年1回 | バックアップからの復旧手順を実際に試す | 2時間 |

**「四半期ごとの agent_memory の棚卸し」を運用フローに入れることが重要である。** 自動での無効化（`hit_rate_after < hit_rate_before`）だけでは、単に古くなった教訓が残り続ける。

## 8. インシデント対応

| 事象 | 対応 |
| --- | --- |
| API キーが漏洩した疑い | 各サービスでキーを再発行し `.env` を更新。Git 履歴に混入していないか `git log -p -S "key-prefix"` で確認 |
| EDGAR からブロックされた | User-Agent を確認。レート制限を 5 req/s から 2 req/s に下げる。数日待つ |
| J-Quants がレート制限を返し続ける | `rate_limit_state` を確認。バックフィルジョブが同時実行されていないか確認 |
| LLM コストが想定外に膨らんだ | キルスイッチを ON。`llm_calls` を用途別に集計して原因を特定。キャッシュが効いていない可能性を確認 |
| DuckDB が壊れた | Raw層から再構築（`rebuild --from-raw`） |
| `state.sqlite` が壊れた | バックアップから復元。**Raw層から再生成できないので、これが最も深刻** |
| モデルの成績が急に悪化した | 特徴量ドリフトを確認。データソースの変更（yfinance の仕様変更など）が原因のことが多い |
| 推奨が全く生成されない | ユニバースフィルタが厳しすぎないか。`scores_daily` の行数を確認 |

## 9. 参照

- テストと検証: [12-testing-validation.md](12-testing-validation.md)
- Windows/WSL2 固有の運用: [15-windows-runtime.md](15-windows-runtime.md)
- LLM コスト設計: [07-llm-rag.md](07-llm-rag.md) §2.5, §3
- 環境検証手順: `.cursor/skills/verify-windows-runtime/SKILL.md`
