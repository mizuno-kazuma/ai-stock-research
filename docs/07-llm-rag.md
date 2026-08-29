# 07. LLM ルーティング・RAG・プロンプト設計

> **前提の明示**: 本章に記載するモデル名・価格・コンテキスト長は執筆時点の情報である。**LLMの価格とモデル識別子は変動が非常に速い。** そのため本ツールでは、モデル識別子をアプリケーションコードに一切書かず、`packages/core/config/models.yaml` の1ファイルに集約する。実装時には必ず各プロバイダの公式価格ページで最新の値を確認し、この設定ファイルのみを更新する。

## 1. LiteLLM を使う理由

LiteLLM を薄いプロキシとして挟む。

| 得られるもの | 説明 |
| --- | --- |
| モデル識別子の一元管理 | アプリコードは `tier="bulk"` のような論理名で呼び、実モデル名は設定ファイルにのみ存在する |
| プロバイダ横断の統一インターフェース | Anthropic / Google / OpenAI を同じ呼び出し形式で扱える |
| フォールバック | 主モデルが失敗したら代替モデルへ自動切替 |
| コスト計測 | トークン数と料金を呼び出しごとに取得できる（`llm_calls` テーブルへの記録に使う） |
| リトライ・タイムアウト | 標準機能として付いてくる |
| キャッシュ | プロンプトキャッシュの制御 |

**使わない場合の問題**: モデルが世代交代するたびに、コード中の `"claude-sonnet-4-5-20250929"` のような文字列を探して置換する作業が発生する。これはコード全体に散らばりやすく、テストコードやプロンプトのメタデータにも残る。1年で数回起きる作業を毎回手作業にしないための投資である。

## 2. 3階層のモデルルーティング

### 2.1 階層の定義

| tier | 用途 | モデル（執筆時点） | 価格（入力/出力、1Mトークンあたり） | コンテキスト |
| --- | --- | --- | --- | --- |
| `bulk` | 大量処理。開示資料の要約、PDF読解、チャンク抽出 | Gemini 3.7 Flash | $0.75 / $3.75 | 1M |
| `default` | 既定の推論。推奨の論拠生成、エージェント統括、Critic | Claude Sonnet 5 | $3 / $15（導入価格 $2 / $10、2026-08-31まで） | 1M |
| `deep` | 週次の深掘り。ポートフォリオ全体レビュー、戦略の再考 | Claude Opus 5 | $5 / $25（1Mウィンドウ全域でフラット） | 1M |

`[要検証]` すべての価格・モデル名・コンテキスト長。特に以下の点。

- Gemini 3.7 Flash の $0.75 / $3.75 は**導入価格であり、2026-12-31 まで**。2027-01-01 から $1.50 / $7.50 へ倍額になる。この前提でコスト見積もりを立てる
- Claude Sonnet 5 の $2 / $10 も導入価格で 2026-08-31 まで。以降は $3 / $15
- Claude Opus 5 は長コンテキスト時の追加料金がない（1Mウィンドウ全域でフラット）。これは長い有報全文を扱う際に有利

### 2.2 `models.yaml`

```yaml
# packages/core/config/models.yaml
# ここがモデル識別子の唯一の定義場所。アプリコードにモデル名を書かない。
version: 3
last_verified: "2026-08-23"     # 公式価格ページで確認した日付

tiers:
  bulk:
    primary: gemini-3.7-flash
    fallbacks: [claude-sonnet-5]
    max_output_tokens: 4096
    temperature: 0.2
  default:
    primary: claude-sonnet-5
    fallbacks: [gemini-3.7-flash]
    max_output_tokens: 8192
    temperature: 0.3
  deep:
    primary: claude-opus-5
    fallbacks: [claude-sonnet-5]
    max_output_tokens: 16384
    temperature: 0.4

models:
  gemini-3.7-flash:
    litellm_model: "gemini/gemini-3.7-flash"     # [要検証] 実際の識別子
    provider: google
    input_usd_per_mtok: 0.75                     # 導入価格（2026-12-31まで）
    output_usd_per_mtok: 3.75
    input_usd_per_mtok_after_2027: 1.50
    output_usd_per_mtok_after_2027: 7.50
    context_window: 1000000
    supports_pdf_input: true                     # これが bulk 層に選ぶ決定的な理由
    supports_json_mode: true
    supports_prompt_cache: true
  claude-sonnet-5:
    litellm_model: "anthropic/claude-sonnet-5"   # [要検証]
    provider: anthropic
    input_usd_per_mtok: 3.00
    output_usd_per_mtok: 15.00
    intro_input_usd_per_mtok: 2.00               # 2026-08-31 まで
    intro_output_usd_per_mtok: 10.00
    intro_until: "2026-08-31"
    context_window: 1000000
    supports_pdf_input: true
    supports_json_mode: true
    supports_prompt_cache: true
  claude-opus-5:
    litellm_model: "anthropic/claude-opus-5"     # [要検証]
    provider: anthropic
    input_usd_per_mtok: 5.00
    output_usd_per_mtok: 25.00
    context_window: 1000000
    long_context_surcharge: false                # 1M全域でフラット
    supports_pdf_input: true
    supports_json_mode: true

embeddings:
  primary: gemini-embedding
  models:
    gemini-embedding:
      litellm_model: "gemini/gemini-embedding-001"  # [要検証]
      dimensions: 3072
      usd_per_mtok: 0.15                             # [要検証]
    text-embedding-3-small:
      litellm_model: "openai/text-embedding-3-small"
      dimensions: 1536
      usd_per_mtok: 0.02
```

`last_verified` フィールドを持つことで、「この価格情報はいつ確認したものか」が明示される。90日以上前の場合、起動時に警告を出す。

### 2.3 ルーティングの実装

```python
# packages/core/llm/router.py
class LLMRouter:
    def __init__(self, config: ModelsConfig, cost_guard: CostGuard,
                 call_log: LLMCallLog):
        ...

    def complete(
        self, *, tier: Literal["bulk", "default", "deep"],
        purpose: str,                  # 'doc_summary'|'thesis'|'critic'|'evaluator'|...
        messages: list[Message],
        files: list[Path] | None = None,     # PDF 等
        response_schema: type[BaseModel] | None = None,
        entity: str | None = None,           # ticker や doc_id（ログ用）
        job_run_id: int | None = None,
    ) -> LLMResponse:
        """tier から実モデルを解決して呼ぶ。呼び出し側はモデル名を知らない。"""
        if self.cost_guard.is_killed():
            raise KillSwitchActive()
        estimated = self.estimate_cost(tier, messages, files)
        if self.cost_guard.would_exceed_cap(estimated):
            raise CostCapExceeded(estimated=estimated, remaining=...)
        ...
```

**呼び出し側にモデル名を渡させない**（`tier` のみ）。これにより、モデルを変えたいときに触るのは `models.yaml` だけになる。

### 2.4 tier の選択基準

| 処理 | tier | 理由 |
| --- | --- | --- |
| 有報PDFの要約（100ページ超） | `bulk` | 入力トークンが大きい。PDFネイティブ入力が使える |
| 決算短信の要約 | `bulk` | 同上 |
| 開示文書のチャンク抽出・分類 | `bulk` | 単純作業で件数が多い |
| リスク要因の前期比較 | `bulk` | 入力が大きい |
| 推奨の論拠生成（thesis + bear case） | `default` | 推論の質が結果を左右する。件数は日次10件程度 |
| Critic の敵対的レビュー | `default` | 論理の検証が主。手を抜くと機能しない |
| Evaluator の教訓抽出 | `default` | 日次1回 |
| 週次ポートフォリオレビュー | `deep` | 週1回。`weekly_review` ジョブが土曜 09:00 に起動し、直近の推奨と実績を1回のコンテキストに入れる。API キーが無ければ `partial` で集計だけ残す |
| 戦略・重み設計の再考 | `deep` | 月1回程度 |
| 埋め込み生成 | （embedding） | |

### 2.5 コスト見積もり

日次の想定呼び出し量（JP + US 両市場）:

| 処理 | 件数/日 | 入力トークン/件 | 出力トークン/件 | tier | 日次コスト概算 |
| --- | --- | --- | --- | --- | --- |
| 開示資料の要約 | 20（キャッシュミス分） | 40,000 | 1,200 | bulk | 800K in + 24K out → 約 $0.69 |
| リスク要因の比較 | 5 | 30,000 | 800 | bulk | 150K in + 4K out → 約 $0.13 |
| 推奨の論拠生成 | 10 | 15,000 | 1,500 | default | 150K in + 15K out → 約 $0.68 |
| Critic レビュー | 10 | 12,000 | 800 | default | 120K in + 8K out → 約 $0.48 |
| Evaluator | 1 | 25,000 | 2,000 | default | 25K in + 2K out → 約 $0.11 |
| 埋め込み | 300チャンク | 1,000 | - | embedding | 300K → 約 $0.05 |
| **日次合計** | | | | | **約 $2.1** |

これを平日20営業日で $42/月となり、目標の $5-15 を超える。したがって以下の削減策を適用する。

| 削減策 | 効果 |
| --- | --- |
| 開示資料の要約対象を絞る（保有 + ウォッチリスト + 上位20件のみ） | 20件 → 8件、約 $0.41 削減 |
| プロンプトキャッシュを使う（システムプロンプト + agent_memory を固定部分にする） | 入力コストの約30%削減 |
| Critic を `bulk` 層でのスクリーニング + `default` 層での詳細検証の2段にする | 約 $0.25 削減 |
| 推奨件数を1日5件に絞る（設定既定は10件） | 約 $0.58 削減 |
| 週次深掘りは週1回のみ（`deep` 層を日次で使わない） | - |

削減後の日次コストは約 $0.8、月約 $16。さらに実際にはキャッシュヒットが効くため、**月 $5-15 が現実的な範囲**となる。ただし 2027-01-01 の Gemini 価格倍増でおおよそ倍になる点を織り込んでおく。

**日次コストキャップの既定値を $1.0 とする**（`settings` の `llm.daily_cap_usd`）。これは上記見積もりに対して余裕を持たせた値であり、暴走時のブレーキとして機能する。

## 3. コストガードとキルスイッチ

```python
# packages/core/llm/cost_guard.py
class CostGuard:
    def would_exceed_cap(self, estimated_usd: float) -> bool:
        daily = self.spent_today() + estimated_usd
        monthly = self.spent_this_month() + estimated_usd
        return daily > self.daily_cap or monthly > self.monthly_cap

    def is_killed(self) -> bool:
        """settings.llm.kill_switch または キャップ超過による自動停止"""
        return (self.settings.get_bool("llm.kill_switch")
                or self.budget.kill_switch_on)

    def record(self, call: LLMCall) -> None:
        """呼び出し後に実コストを記録し、キャップ到達時は自動でキルスイッチを立てる。"""
        self.log.insert(call)
        self.budget.add(call.cost_usd)
        if self.budget.spent_usd > self.daily_cap:
            self.budget.kill_switch_on = True
            self.alerts.create(severity="warning", category="cost",
                               title_ja="LLMの日次予算に達しました",
                               body_ja=f"本日の使用額 ${...}。定性分析を停止しました。")
```

**キルスイッチが立ったときの振る舞い**:

- 以降のLLM呼び出しは `KillSwitchActive` 例外で即座に失敗する
- 呼び出し側（Researcher / Strategist）は例外を捕捉し、**定量スコアのみで処理を続行する**
- 推奨カードは生成される（`qual_score = NULL`）が、UIに「本日は定性分析が停止しています」を表示する
- 日付が変わると `daily` のキルスイッチは自動解除される。`monthly` の場合は手動解除が必要

**このフォールバックが機能することがテストで担保されていること**が重要である（[12-testing-validation.md](12-testing-validation.md) の T-LLM-03）。コストキャップに達したときにシステム全体が止まるなら、キャップの意味がない。

### 3.1 コスト管理のUI

設定画面に以下を表示する。

```
今日の使用額     $0.42 / $1.00  ████████░░░░░░░░░░░░
今月の使用額     $6.18 / $20.00 ██████░░░░░░░░░░░░░░
キャッシュヒット率  73%
最も高い用途     開示資料の要約（$3.80、月間の61%）

[キルスイッチ: OFF]  [日次上限を変更]  [月次上限を変更]
```

## 4. RAG 設計

### 4.1 いつ RAG を使い、いつ使わないか

| 状況 | 方式 | 理由 |
| --- | --- | --- |
| 単一の資料を要約する | **RAG を使わない。全文をコンテキストに入れる** | 1Mコンテキストがあるので有報全文（約20万トークン）が入る。チャンク分割による文脈の断絶を避けられる |
| 複数資料を横断して質問する | RAG | 全部入れるとコストが大きい |
| 銘柄について自由質問する | RAG | どの資料が関係するか事前に分からない |
| リスク要因を前期と比較する | 両方の資料の該当セクションを直接抽出（RAGではなくセクション指定） | 比較には該当箇所の全文が必要 |
| 推奨の bear case を作る | RAG（ネガティブ寄りのクエリで検索） | 反論材料を探す用途に適する |

**単一資料の要約に RAG を使わない判断は重要である。** 1Mコンテキストのモデルを使う最大の利点は「分割せずに全部読ませられる」ことにある。チャンク分割すると「第2四半期の売上は前四半期比で減少したが、これは季節要因である」という文脈が切れる可能性がある。

### 4.2 チャンク分割規則

RAG 用のチャンクは以下の規則で作る。

| 項目 | 値 | 理由 |
| --- | --- | --- |
| 分割単位 | 見出し優先 → 段落 → 文 | セクション境界を跨がない |
| チャンクサイズ | 800-1,200 トークン | 埋め込みモデルの適正範囲であり、引用として提示するのに適した長さ |
| オーバーラップ | 150 トークン | 境界で情報が切れるのを緩和 |
| メタデータ | `doc_id`, `ticker`, `doc_type`, `filed_at`, `section`, `page_from`, `page_to` | **`filed_at` は鮮度フィルタに必須** |
| 日本語の境界 | 句点（。）で切る | 文の途中で切らない |
| 表の扱い | 表全体を1チャンクにする（分割しない） | 表を分割すると数値と項目名が離れる |

**重要セクションの識別**: 以下のセクションは特別扱いし、`section` フィールドに正規化名を入れる。

| 日本（有報・短信） | 米国（10-K/10-Q） | 正規化名 |
| --- | --- | --- |
| 事業等のリスク | Item 1A. Risk Factors | `risk_factors` |
| 経営者による財政状態、経営成績及びキャッシュ・フローの状況の分析 | Item 7. MD&A | `mdna` |
| 業績等の概要 / 経営成績 | Results of Operations | `results` |
| 今後の見通し / 次期の業績予想 | Outlook / Guidance | `outlook` |
| 財務諸表 | Financial Statements | `financials` |
| 重要な会計上の見積り | Critical Accounting Estimates | `accounting_estimates` |

セクション識別は正規表現ベースの見出しマッチで行い、失敗した場合は `section = 'other'` とする。

### 4.3 検索

```python
def retrieve(
    query: str, *, ticker: str, market: str,
    k: int = 8,
    filed_after: date | None = None,       # 鮮度フィルタ
    doc_types: list[str] | None = None,
    sections: list[str] | None = None,
    as_of: date | None = None,             # PIT 制約。これより後の資料を除外
) -> list[SearchHit]:
    """ハイブリッド検索: ベクトル検索 + キーワード検索（BM25）の結果を統合する。"""
    q_vec = embed(query)
    vec_hits = vector_store.search(q_vec, k=k*3, filters={
        "ticker": ticker, "market": market,
        "filed_at": {"$lte": as_of} if as_of else None,
        "doc_type": {"$in": doc_types} if doc_types else None,
    })
    kw_hits = duckdb_fts_search(query, ticker=ticker, k=k*3, as_of=as_of)
    return reciprocal_rank_fusion(vec_hits, kw_hits)[:k]
```

**ハイブリッド検索にする理由**: 日本語の財務文書では固有名詞や勘定科目名（「のれん減損」「持分法投資損益」）での完全一致が効く。ベクトル検索だけでは、意味が近い別の語に流れることがある。DuckDB の FTS 拡張でキーワード検索を担う。

**PIT 制約 (`as_of`) を検索にも適用する**ことが重要である。バックテストや過去の推奨を再現するとき、当時知り得なかった資料を検索してはいけない。

### 4.4 Reciprocal Rank Fusion

```python
def reciprocal_rank_fusion(*rankings: list[SearchHit], k: int = 60) -> list[SearchHit]:
    """複数の順位リストを統合する。スコアのスケールが違っても混ぜられる。"""
    scores = defaultdict(float)
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            scores[hit.chunk_id] += 1.0 / (k + rank)
    return sorted(..., key=lambda h: -scores[h.chunk_id])
```

### 4.5 引用の生成と検証

すべてのLLM出力に引用を必須とする。引用は以下の形式。

```python
class Citation(BaseModel):
    doc_id: str
    page: int | None
    quote: str          # 原文からの直接引用（改変禁止）
    chunk_id: str | None = None
```

**Critic による引用検証**（[08-agent-loop.md](08-agent-loop.md) §6）:

```python
def verify_citation(c: Citation) -> CitationVerdict:
    doc = repo.get_document(c.doc_id)
    if doc is None:
        return CitationVerdict.DOC_NOT_FOUND        # 存在しない資料の捏造
    text = get_document_text(c.doc_id, page=c.page)
    if text is None:
        return CitationVerdict.PAGE_NOT_FOUND
    # 完全一致ではなく正規化後の部分一致で判定する
    # （LLMは全角半角やスペースを変えることがある）
    if normalize_ja(c.quote) in normalize_ja(text):
        return CitationVerdict.VERIFIED
    # 類似度でも判定（軽微な改変を許容するが、大きく違えば却下）
    if similarity(normalize_ja(c.quote), normalize_ja(text)) >= 0.9:
        return CitationVerdict.VERIFIED_FUZZY
    return CitationVerdict.QUOTE_NOT_FOUND          # 原文にない内容の捏造
```

`normalize_ja` は全角英数の半角化、空白除去、記号の正規化（NFKC）を行う。

**`DOC_NOT_FOUND` または `QUOTE_NOT_FOUND` が1つでもある推奨は、Critic が `rejected` にする。** これが「LLMの出力を鵜呑みにしない」ことの実装上の担保である。

## 5. プロンプト設計

プロンプトは `packages/core/llm/prompts/*.jinja` にテンプレートとして置く。ハッシュがキャッシュキーになるため、些細な変更でも再計算が走る点に注意する。

### 5.1 共通のシステムプロンプト

```
あなたは日本と米国の株式を分析するリサーチアシスタントです。
以下の原則を厳守してください。

1. 提供された資料に書かれていることのみを述べる。推測を事実として述べない
2. すべての主張に、資料からの直接引用（ページ番号付き）を添える
3. 引用は原文をそのまま写す。要約や言い換えを引用として提示しない
4. 資料に情報がない場合は「資料に記載なし」と明記する。埋めない
5. 数値は資料の値をそのまま使う。単位（百万円/十億円/千ドル）を必ず確認する
6. 投資判断の推奨（買え・売れ）を述べない。判断材料の提示に留める
7. 出力は指定されたJSONスキーマに厳密に従う

出力言語: 日本語（引用部分は原文の言語のまま）
```

**プロンプトキャッシュの活用**: このシステムプロンプトと `agent_memory` の注入部分は毎回同一なので、プロンプトキャッシュの対象にする。LiteLLM の `cache_control` を使う。入力コストの削減効果が大きい。

### 5.2 開示資料の要約（`doc_summary.jinja`）

```jinja
{# tier: bulk / PDFをネイティブ入力する #}
以下は {{ company_name }}（{{ ticker }}）が {{ filed_at }} に提出した
{{ doc_type_ja }}です。

## タスク

1. 3-5文で要約する（summary_ja）
2. 重要な数値を5点まで箇条書きにする（key_points）。必ず数値と前年同期比を含める
3. リスク要因を抽出する（risk_factors）。前期資料と比較できる場合は、
   新規追加されたリスクを明示する
4. 経営陣の見通しのトーンを判定する（guidance_tone）
   - positive: 上方修正、あるいは明確に前向きな表現がある
   - neutral: 予想据え置き、定型的な表現のみ
   - cautious: 不確実性への言及が増えている、条件付きの表現が多い
   - negative: 下方修正、あるいは明確に慎重な表現がある
   判定根拠となる原文を guidance_evidence に引用すること
5. 定性スコアを -1.0 から +1.0 で付ける（qualitative_score）
   根拠のない加点をしない。判断できない場合は 0.0 とする
6. 引用を3件以上挙げる（citations）。上記1-5の根拠となった箇所を選ぶ

{% if prev_doc_available %}
## 前期資料との比較

前期（{{ prev_period }}）の資料も添付しています。以下の変化に注目してください。
- リスク要因の追加・削除
- 会社予想の変更
- 説明のトーンの変化
{% endif %}

## 出力スキーマ

{{ schema_json }}

## 制約

- citations が空の出力は無効です。必ず1件以上含めてください
- 資料に記載のない数値を出力してはいけません
```

### 5.3 推奨の論拠生成（`thesis.jinja`）

```jinja
{# tier: default #}
## 対象銘柄

{{ ticker }} {{ company_name }}（{{ market }}、{{ sector_name }}）

## 定量データ

| 項目 | 値 | セクター内順位 |
|---|---|---|
| 定量スコア | {{ quant_score }} | {{ sector_rank }}/{{ sector_count }} |
| バリュー z | {{ value_z }} | |
| モメンタム z | {{ momentum_z }} | |
| クオリティ z | {{ quality_z }} | |
| 成長 z | {{ growth_z }} | |
| 低ボラ z | {{ lowvol_z }} | |
| 改定 z | {{ revision_z }} | |
| ML予測（{{ horizon }}） | {{ ml_pred }} [{{ ml_pred_lo }}, {{ ml_pred_hi }}] | |
| PER / PBR | {{ per }} / {{ pbr }} | |
| ROIC | {{ roic }} | |
| 実現ボラ(60日) | {{ realized_vol }} | |

## 検出された reason codes

{{ reason_codes | join(", ") }}

## 関連する開示資料の抜粋

{% for hit in retrieved_chunks %}
### [{{ hit.doc_id }}] {{ hit.title }}（{{ hit.filed_at }}、p.{{ hit.page_from }}、{{ hit.section }}）
{{ hit.text }}
{% endfor %}

## 過去の類似ケースの実績

同様の reason code の組み合わせでの過去の的中率: {{ hit_rate_prior }}（n={{ n_prior_samples }}）
平均超過リターン: {{ avg_excess_return }}

## 蓄積された教訓

{% for m in agent_memory %}
- [{{ m.category }}] {{ m.lesson_ja }}（根拠: {{ m.evidence_ja }}、n={{ m.n_observations }}）
{% endfor %}

## タスク

1. **thesis_ja**: この銘柄に注目すべき論拠を2-4行で書く。
   定量データの数値と、資料からの引用の両方を根拠にする。

2. **bear_case_ja**: **この推奨を却下すべき理由を3つ挙げる。**
   以下を必ず検討すること。
   - 定量スコアの構成要素で最も低いグループは何か。それは何を意味するか
   - 割安と判断した場合、それがバリュートラップである可能性
   - 開示資料に記載されたリスク要因のうち、この論拠を崩すもの
   - 過去の類似ケースで失敗した事例があるか
   一般論ではなく、この銘柄のデータと資料に基づいて具体的に書く。

3. **invalidation_ja**: この見立てを捨てるべき具体的な条件を書く。
   「株価が下がったら」ではなく、「次期の会社予想が下方修正されたら」
   「営業利益率が X% を下回ったら」のように検証可能な条件にする。

4. **conviction**: low / medium / high。以下を考慮する。
   - 過去の類似ケースの母数（n < 20 なら low 以外にしない）
   - ML予測の信頼区間の幅
   - データの鮮度
   - 開示資料の量と鮮度

5. **citations**: 上記の根拠となった引用を3件以上。

## 制約

- bear_case_ja を「特にありません」「リスクは限定的」のような内容にしてはならない。
  却下すべき理由を具体的に3つ挙げられない場合、この銘柄は推奨に適さない。
  その場合は conviction を low とし、bear_case_ja に「明確な弱気論拠を
  特定できなかったため、分析が不十分である可能性がある」と書くこと。
- 「買い」「売り」という語を使わない。
- 目標株価を提示しない（統計的根拠のない数字になるため）。
```

**`bear_case_ja` の指示の書き方が本ツールの核心である。** 「リスクを書け」と指示すると「市場環境の悪化」のような無内容な定型文が返る。「**却下すべき理由を3つ挙げよ**」と敵対的に指示することで、具体的な内容が出る。

### 5.4 Critic の敵対的レビュー（`critic.jinja`）

```jinja
{# tier: default #}
あなたは投資判断のレビュー担当です。以下の推奨を批判的に検証してください。
あなたの役割は、この推奨の弱点を見つけることです。承認することではありません。

## 検証対象の推奨

{{ recommendation_json }}

## 元データ

- データ鮮度: {% for f in data_freshness %}{{ f.source }}={{ f.latest_as_of }} {% endfor %}
- 使用した特徴量バージョン: {{ feature_version }}
- 引用された資料: {% for d in source_docs %}{{ d.doc_id }}（{{ d.filed_at }}）{% endfor %}

## 引用の検証結果（システムによる機械的検証）

{% for c in citation_verdicts %}
- {{ c.doc_id }} p.{{ c.page }}: {{ c.verdict }}
{% endfor %}

## 検証項目

以下を順に確認し、問題があれば指摘してください。

1. **データ鮮度**: 使用データが古すぎないか。
   J-Quants無料プランの12週遅延を考慮しているか。
   現在値として遅延データを使っていないか。

2. **リーク**: 論拠に、その時点で知り得なかった情報が含まれていないか。
   決算発表日の当日終値で決算内容を織り込んでいないか。

3. **引用の実在性**: 上記の機械的検証で NOT_FOUND があれば、
   それに依存する主張は無効です。

4. **論理の飛躍**: 定量データと論拠の間に飛躍がないか。
   「ROICが高い」から「株価が上がる」への論理は成立していないため、
   そのような主張は指摘すること。

5. **bear case の実質性**: bear_case_ja が定型文になっていないか。
   具体的な数値や資料の記述に基づいているか。

6. **確信度の妥当性**: conviction が過去実績の母数に対して高すぎないか。
   n < 20 で medium 以上になっていないか。

7. **信頼区間の提示**: 期待リターンに信頼区間が付いているか。
   区間が極端に広い（予測に意味がない）のに高い確信度になっていないか。

## 出力

- verdict: approved / revised / rejected
- issues: 検出した問題のリスト（severity: critical / major / minor）
- revised_fields: revised の場合、修正すべきフィールドと修正案
- notes_ja: 総括

## 判定基準

- critical が1つでもあれば rejected
- major が2つ以上あれば rejected
- major が1つなら revised
- minor のみなら approved（ただし notes_ja に記載する）

critical に該当するもの:
- 引用が実在しない
- リークがある
- 現在値として遅延データを使っている
- bear_case_ja が実質的に空
```

### 5.5 Evaluator の教訓抽出（`evaluator.jinja`）

```jinja
{# tier: default #}
## 評価対象

過去 {{ horizon }} の実績が確定した推奨 {{ n }} 件の一覧です。

{% for r in outcomes %}
### {{ r.ticker }}（{{ r.as_of }}、{{ r.action }}、conviction={{ r.conviction }}）
- 論拠: {{ r.thesis_ja }}
- 弱気論拠: {{ r.bear_case_ja }}
- reason codes: {{ r.reason_codes | join(", ") }}
- 予測: {{ r.expected_ret }} [{{ r.expected_ret_lo }}, {{ r.expected_ret_hi }}]
- 実績: 超過リターン {{ r.excess_return }}（的中: {{ r.is_hit }}）
- 期間中の最大不利変動: {{ r.max_adverse_excursion }}
{% endfor %}

## 集計

- 全体の的中率: {{ hit_rate }}（n={{ n }}）
- conviction 別の的中率: {{ hit_rate_by_conviction }}
- reason code 別の的中率: {{ hit_rate_by_reason_code }}
- 予測が信頼区間内に収まった比率: {{ coverage_rate }}

## タスク

1. **繰り返し現れるパターン**を特定する。
   偶然と区別できる程度の頻度があるものだけを挙げる（最低 n=10）。

2. 各パターンについて、以下を出力する。
   - scope: global / market / sector / ticker のいずれか
   - category: lesson（教訓）/ bias（体系的な偏り）/ pattern（規則性）/ caveat（注意点）
   - lesson_ja: 以降の分析で参照すべき短い文（150文字以内）
   - evidence_ja: なぜそう言えるかの根拠（該当する rec_id と数値）
   - n_observations: 根拠となった観測数
   - confidence: 0.0-1.0

3. **信頼区間のキャリブレーション**を評価する。
   coverage_rate が 60%（q20-q80の想定）から大きく乖離している場合、
   モデルが過信または過度に慎重であることを指摘する。

4. 既存の教訓（下記）のうち、実績と矛盾するものを特定する。

{% for m in existing_memory %}
- [{{ m.memory_id }}] {{ m.lesson_ja }}（適用前的中率 {{ m.hit_rate_before }} →
  適用後 {{ m.hit_rate_after }}、n={{ m.n_observations }}）
{% endfor %}

## 制約

- n < 10 のパターンを教訓として出力してはいけません。
- 「モメンタムが有効だった」のような一般論ではなく、
  「JP市場のH5で REV_UP_GUIDANCE と MOM_STRONG_12M が同時に立つケースの
  的中率は 68%（n=31）だが、REV_UP_GUIDANCE 単独では 51%（n=88）である」
  のように、条件と数値を伴う具体的な内容にしてください。
- 結果の良し悪しではなく、再現しそうな規則性のみを教訓にしてください。
```

### 5.6 週次深掘り（`weekly_review.jinja`）

`deep` 層。土曜 09:00 の `weekly_review` ジョブが使う。API キーが無ければジョブは LLM を呼ばず、件数と的中率だけ `job_runs.metrics` に残して `partial`。

```jinja
{# version: 1 #}
{# tier: deep #}
## 週次深掘りレビュー

対象日: {{ as_of }}
推奨件数（直近）: {{ n_recs }}
確定した実績: {{ n_outcomes }}
的中率: {{ hit_rate }}
確信度別的中率: {{ hit_rate_by_conviction }}
重み提案の有無: {{ weight_proposal }}

## タスク

1. **summary_ja**: 今週の推奨と実績を3-8行で要約する。数字を入れる。
2. **lessons**: 週次で残すべき教訓。n_observations >= 10 のものだけ。
   日次 Evaluator と重複する一般論は出さない。
3. **action_items_ja**: 来週の運用で確認すべき具体的な項目を最大5件。

「必ず」「確実に」は使わない。サンプルが足りなければその旨を summary_ja に書く。
```

出力スキーマは `WeeklyReviewOutput`（`summary_ja` / `lessons` / `action_items_ja`）。保有株数・評価額は渡さない（§7）。

### 5.7 プロンプトのバージョン管理

| 項目 | 規則 |
| --- | --- |
| ファイル配置 | `packages/core/llm/prompts/{name}.jinja` |
| バージョン | ファイル冒頭に `{# version: 3 #}` を書き、`document_summaries.summary_version` に反映 |
| 変更時の影響 | `prompt_hash` が変わるため、以降の呼び出しはキャッシュミスになる。**過去分の一括再計算は自動で行わない** |
| A/B比較 | 新旧プロンプトで同じ資料を処理し、出力を並べて比較する開発用スクリプトを用意する（`scripts/compare_prompts.py`） |
| レビュー | プロンプト変更は必ず 5件以上の実データで出力を確認してからコミットする |

## 6. 構造化出力

すべてのLLM呼び出しは Pydantic モデルでスキーマを指定し、JSON で受け取る。

```python
class DocSummaryOutput(BaseModel):
    summary_ja: str = Field(min_length=50, max_length=600)
    key_points: list[str] = Field(min_length=1, max_length=8)
    risk_factors: list[str] = Field(max_length=10)
    guidance_tone: Literal["positive", "neutral", "cautious", "negative"]
    guidance_evidence: str = Field(min_length=10)
    qualitative_score: float = Field(ge=-1.0, le=1.0)
    citations: list[Citation] = Field(min_length=1)   # 1件以上を型で強制

    @field_validator("citations")
    @classmethod
    def quotes_not_empty(cls, v):
        for c in v:
            if len(c.quote.strip()) < 10:
                raise ValueError("引用が短すぎます")
        return v
```

**Pydantic の制約で「引用1件以上」を強制する。** LLMがスキーマを守らなかった場合はバリデーションエラーになり、1回リトライする（プロンプトに違反内容を追記して再送）。2回目も失敗したらその処理をスキップし、`llm_calls` に `status='schema_error'` を記録する。

## 7. LLM に渡さない情報（プライバシー）

以下はプロンプトに含めない。`packages/core/llm/redact.py` でフィルタする。

| 情報 | 理由 |
| --- | --- |
| 保有株数・取得単価・評価額 | 資産情報を外部に送らない |
| 口座種別（NISA/特定） | 同上 |
| 総資産額・現金残高 | 同上 |
| 個人を識別する情報 | 同上 |

保有していることの「事実」は渡してよい（`is_held: true`）。数量と金額を渡さない。ポートフォリオレビュー（`deep` 層）では**比率のみ**を渡す（「A社が20%、B社が15%」）。

```python
def redact_portfolio(positions: list[Position]) -> list[dict]:
    total = sum(p.market_value for p in positions)
    return [{"ticker": p.ticker, "weight_pct": round(p.market_value / total * 100, 1),
             "unrealized_pnl_pct": round(p.unrealized_pnl_pct, 1)}
            for p in positions]
```

## 8. 参照

- 決算資料の取得と要約キャッシュ: [06-filings-access.md](06-filings-access.md)
- エージェントの各ジョブ: [08-agent-loop.md](08-agent-loop.md)
- コスト管理と監視: [11-security-ops.md](11-security-ops.md)
- LLM出力のテスト: [12-testing-validation.md](12-testing-validation.md) §6
