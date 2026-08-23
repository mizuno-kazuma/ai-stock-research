---
name: implement-screen-from-figma
description: Figma Make が生成した画面を apps/web に実装として落とし込む手順。デザイントークンへの置き換え、方向色の切替対応、API型との接続、状態（loading / empty / error / partial）の実装、必須表示要件（弱気論拠・信頼区間・母数・鮮度）の検証、レスポンシブとアクセシビリティの確認を扱う。Figma出力の取り込み、画面の新規実装、既存画面のデザイン更新反映に使う。
---

# Figma Make 出力の実装への落とし込み

Figma Make の出力はそのままでは使わない。ハードコードされた色と固定値を含んでおり、この
プロダクトで最も重要な「方向色をユーザーが切り替えられる」「部分データを正しく表示する」という
要件を満たさない。以下の順序で変換する。

関連仕様: [docs/ui/](../../../docs/ui/) 一式、
[09-api-spec.md](../../../docs/09-api-spec.md)、
[10-mobile-pwa.md](../../../docs/10-mobile-pwa.md)

## 手順

### 1. 対応する画面仕様を読む

`docs/ui/screens/NN-*.md` を開き、以下を確認する。Figma の出力と仕様が食い違う場合、
**仕様が優先**。Figma は見た目の出発点であって、正しさの基準ではない。

- Component tree（実装するコンポーネントの階層）
- Content spec（`label_ja` をそのまま使う。意訳しない）
- States（4状態すべてを実装する。Figma は通常 loading と error を出力しない）
- Interactions（遷移先とキーボード操作）
- Data source（叩くエンドポイント）

### 2. 色・サイズをトークンに置き換える

Figma 出力の 16進数カラーコードとピクセル値を、`design-system.md` のトークンに機械的に置き換える。

```bash
# 置き換え漏れの検出
rg -n '#[0-9A-Fa-f]{6}' apps/web/app apps/web/components
rg -n 'text-\[|bg-\[|p-\[|gap-\[' apps/web/app apps/web/components
```

置き換え表の主なもの:

| Figma の値 | トークン |
| --- | --- |
| `#0B0E14` | `bg-base` |
| `#131722` | `bg-surface` |
| `#E6E9F0` | `fg-primary` |
| `#9AA4B8` | `fg-secondary` |
| `#F2545B` | 文脈で判断（`dir-up` / `dir-down` / `status-danger`） |
| `#3FBF7F` | 同上（`dir-up` / `status-success`） |
| `#5B8DEF` | `accent` |

**`#F2545B` と `#3FBF7F` は必ず文脈を確認する。** 上昇・下落を表す箇所なら `--dir-up` /
`--dir-down`、状態を表す箇所なら `--status-*`。ここを混同すると、方向色を米国式に切り替えたときに
エラー表示の色まで変わる。

### 3. 方向色を意味づけする

上昇・下落を表示する箇所は、必ず `DirectionValue` コンポーネントを経由する。生の色クラスを
書かない。

```tsx
// 正しい
<DirectionValue value={0.0124} format="percent" showSign />

// 誤り（日本式・米国式の切替に対応できない）
<span className="text-red-500">+1.24%</span>
```

`DirectionValue` の内部で以下を行う。

- `--dir-up` / `--dir-down` / `--dir-flat` を参照（ユーザー設定で値が入れ替わる）
- **符号を常に表示**（`+1.24%`。色だけで方向を伝えない）
- `tabular-nums` を適用
- 0 のときは `--dir-flat` と符号なし

検証:

```bash
rg -n 'text-red|text-green|text-\[#F2545B\]|text-\[#3FBF7F\]' apps/web
```

これらのヒットが0件であること。

### 4. 数値表示をフォーマッタに通す

`docs/ui/SKILL.md` §8 の表に従う。表示ロジックを画面に散らさず、`packages/ui/format.ts` に集約
する。

| 種類 | 関数 | 出力例 |
| --- | --- | --- |
| 円価格 | `formatJpy(3125)` | `3,125円` |
| ドル価格 | `formatUsd(189.42)` | `$189.42` |
| 大きい金額 | `formatJpyLarge(42180000000000)` | `42兆1,800億円` |
| 変化率 | `formatPct(0.0823, {sign: true})` | `+8.23%` |
| スコア | `formatScore(78.4)` | `78.4` |
| z-score | `formatZ(1.42)` | `+1.42` |
| 区間 | `formatInterval(0.024, -0.031, 0.079)` | `+2.4% [-3.1%, +7.9%]` |
| 母数付き比率 | `formatRateWithN(0.58, 34)` | `58% (n=34)` |
| 欠損 | `formatNullable(null)` | `—`（`fg-muted`） |

**`null` を `0` として表示してはいけない。** PER が欠損しているのと PER が 0 なのは意味が違う。
`formatNullable` を経由し、`—` を出す。

```bash
# ゼロ埋めの検出
rg -n '\?\?\s*0|\|\|\s*0\b' apps/web/components apps/web/app
```

### 5. API 型に接続する

型は手書きしない。`packages/schemas` の Pydantic モデルから生成した TypeScript 型を使う。

```bash
uv run python -m packages.schemas.export > openapi.json
npx openapi-typescript openapi.json -o apps/web/lib/api-types.ts
```

CI でこの生成物と実際のファイルが一致することを検証する（`T-API-01`）。型がずれた状態で実装を
進めると、`bear_case_ja` のようなフィールド名の食い違いに実行時まで気づけない。

データ取得は TanStack Query。`docs/ui/interaction-patterns.md` §6.1 の refetch 間隔に従う。

### 6. 4つの状態をすべて実装する

Figma Make は通常、正常時のみを出力する。以下は自分で追加する。`states.md` の該当箇所を参照。

| 状態 | 実装すること |
| --- | --- |
| `loading` | Skeleton を**最終寸法と同じサイズ**で。レイアウトが跳ねないこと |
| `loading-refresh` | 既存コンテンツを表示したまま。空白にしない |
| `empty` | 原因と次の行動を書く。「データがありません」だけは不可 |
| `not-ready` | 指定日のデータ未生成。最新の利用可能日を提示し、そこへ飛べるようにする |
| `partial` | **セクション単位で失敗を表示**。ページ全体をエラーにしない |
| `error` | セクション単位のインライン再試行。入力値は保持する |
| `stale` | 鮮度が期待より古い場合のマーカーとキャプション |
| `offline` | キャッシュ表示 + 取得時刻の明示 |

`partial` が最重要。API は部分データを 200 で返し、`warnings[]` と `meta.data_freshness` を含める。
UI はこれを必ず描画する。

```tsx
{data.warnings?.map((w) => <WarningBanner key={w.code} warning={w} />)}
```

`warnings` を無視した実装は、データが欠けていることをユーザーに伝えないまま推奨を表示することに
なる。

### 7. 必須表示要件を検証する

以下は仕様上の必須要件で、欠けていたら不具合として扱う。実装後に画面ごとに確認する。

| 要件 | 対象 | 確認方法 |
| --- | --- | --- |
| 弱気論拠が常に可視 | 推奨カード | 折りたたみ制御が存在しないこと。`compact` でもプレビュー行があること |
| 予測に区間が併記 | すべての予測値 | `ForecastValue` を経由していること。点推定の単独表示がないこと |
| 比率に母数が併記 | すべての的中率・勝率 | `formatRateWithN` を経由していること |
| 鮮度表示 | すべての画面 | `DataFreshnessIndicator` がヘッダにあること |
| 遅延の明示 | 参考価格を出す箇所 | 「15分遅延」「約定価格には使用できません」のキャプション |
| ベースライン比較 | 為替予測 | `verdict_ja` をそのまま表示していること（加工しない） |
| コスト前提 | バックテスト結果 | 手数料・スリッページ・回転率上限が結果より先に表示されていること |
| 発注UIがない | 全画面 | 「買い」「売り」ボタンが存在しないこと |

機械的な検出:

```bash
# 発注UIの混入
rg -ni 'buy|sell|注文|発注' apps/web/components apps/web/app --glob '!**/*.test.*'
# 弱気論拠の折りたたみ
rg -n 'bearCase' apps/web | rg -n 'Collaps|Accordion|showMore|isOpen'
```

後者がヒットしたら実装を直す。

### 8. レスポンシブを実装する

`interaction-patterns.md` §2 のブレークポイントとレイアウト変換に従う。

| 変換 | 内容 |
| --- | --- |
| テーブル | 768px 未満でカードリストに変換。**横スクロールにしない** |
| サイドバー | 1280px 未満でアイコンレール、768px 未満でボトムナビ |
| チャート | 高さを段階的に縮小。横スクロールにしない |
| ダイアログ | 768px 未満でボトムシート |
| タップ領域 | タッチデバイスで最小 44 x 44px |
| セーフエリア | `env(safe-area-inset-bottom)` をボトムナビに適用 |

### 9. アクセシビリティを確認する

- コントラスト比 4.5:1 以上（本文）、3:1 以上（大きい文字）。両テーマで確認
- 方向を色だけで伝えていない（符号または矢印を併記）
- すべての操作要素がキーボードで到達でき、フォーカスリングが見える
- チャートに同等のデータテーブル表示が用意されている
- ジョブ進捗とアラート件数に `aria-live="polite"`
- `prefers-reduced-motion` でトランジションを無効化
- **数値のカウントアップアニメーションを実装しない**（誤読の原因になる）

### 10. テストを追加する

E2E（Playwright）で `docs/12-testing-validation.md` の確認リストに沿って:

- 推奨カードに弱気論拠が表示されている
- 方向色設定を米国式に切り替えると上昇が緑になる
- 開示PDFが新しいタブで開く
- 部分データ時にセクション単位の警告が出て、他のセクションは表示される
- オフラインでキャッシュ表示と取得時刻が出る
- モバイル幅でテーブルがカードに変換される

## 完了条件

- [ ] 16進数カラーコードとアドホックなピクセル値が0件
- [ ] 方向表示がすべて `DirectionValue` 経由
- [ ] 数値表示がすべてフォーマッタ経由、`null` が `—` で出る
- [ ] API 型が生成物と一致（CI で検証）
- [ ] loading / empty / not-ready / partial / error / offline の6状態が実装済み
- [ ] `warnings[]` を描画している
- [ ] 必須表示要件8項目を満たす
- [ ] 3ブレークポイントで崩れない
- [ ] アクセシビリティ7項目を満たす
- [ ] E2E テストが通る

## よくある失敗

| 失敗 | 症状 | 対策 |
| --- | --- | --- |
| Figma の赤をそのまま使った | 米国式に切り替えても下落が赤にならない | `DirectionValue` を経由 |
| `status-danger` に `dir-down` を使った | 方向色を切り替えるとエラー表示の色が変わる | 文脈でトークンを分ける |
| `partial` を error として扱った | 1つのソースが落ちると画面全体が真っ白 | セクション単位のエラー境界 |
| `warnings` を無視した | データが欠けていることが伝わらない | `WarningBanner` を必ず描画 |
| `null` を `0` で表示 | 赤字企業の PER が 0 倍と表示される | `formatNullable` |
| 弱気論拠を折りたたんだ | 仕様違反 | 折りたたみ制御を削除 |
| モバイルでテーブルを横スクロール | 使えない | カードリストに変換 |
| 数字をアニメーションさせた | 読み取り中に値が変わる | アニメーションを削除 |
