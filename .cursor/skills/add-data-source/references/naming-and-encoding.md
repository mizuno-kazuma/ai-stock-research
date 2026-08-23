# 命名と文字コードの規則（データソース追加時）

Windows 11 + WSL2 で動かす前提のため、WSL2 内であっても Windows 側から同じファイルを触る可能性を
想定して命名規則を守る。詳細な背景は
[docs/15-windows-runtime.md](../../../../docs/15-windows-runtime.md)。

## 1. パス命名

### 生データ

```
data/raw/{source}/{endpoint}/dt={YYYY-MM-DD}/{HHmmss}_{seq:04d}.json.gz
```

例:

```
data/raw/jquants/equities_bars_daily/dt=2026-08-22/060412_0001.json.gz
data/raw/edinet/documents/dt=2026-08-22/150418_0007.pdf
data/raw/sec_edgar/companyfacts/dt=2026-08-21/052210_0003.json.gz
```

### Parquet パーティション

```
data/core/prices_daily/market=JP/dt=2026-08-22/part-0000.parquet
```

### 禁止事項

| 禁止 | 理由 | 代替 |
| --- | --- | --- |
| `:` | Windows のファイル名で使用不可。ISO時刻をそのまま使うと壊れる | `HHmmss` 形式 |
| `?` `*` `<` `>` `|` `"` | Windows のファイル名で使用不可 | `_` に置換 |
| 末尾のドットとスペース | Windows で暗黙に削除される | 除去 |
| `CON` `PRN` `AUX` `NUL` `COM1`-`COM9` `LPT1`-`LPT9` | Windows の予約名 | `_` を付与して回避 |
| ファイル名への日本語タイトル | 文字コード依存の破損、パス長超過 | `doc_id` を使う |
| 260文字を超える絶対パス | Windows の既定の上限 | 階層を浅くする |

### 実装

パス要素の生成は必ず共通関数を通す。文字列連結でパスを組み立てない。

```python
from pathlib import Path

_FORBIDDEN = set('<>:"/\\|?*')
_RESERVED = {"CON", "PRN", "AUX", "NUL",
             *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}


def safe_component(value: str) -> str:
    """パス1要素として安全な文字列に変換する。"""
    cleaned = "".join("_" if ch in _FORBIDDEN or ord(ch) < 32 else ch for ch in value)
    cleaned = cleaned.rstrip(". ")
    if cleaned.upper().split(".")[0] in _RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned or "_"


def timestamp_component(dt) -> str:
    """コロンを含まない時刻要素を返す。"""
    return dt.strftime("%H%M%S")


def raw_path(data_dir: Path, source: str, endpoint: str, dt, ts, seq: int, ext: str) -> Path:
    return (data_dir / "raw" / safe_component(source) / safe_component(endpoint)
            / f"dt={dt:%Y-%m-%d}" / f"{timestamp_component(ts)}_{seq:04d}.{ext}")
```

`os.path.join` と文字列結合ではなく `pathlib.Path` を使う。CI で `os.path.join` の新規使用を
検出する。

## 2. 文字コード

### 原則

日本語ロケールの Windows では Python のデフォルトエンコーディングが `cp932` になる。WSL2 内では
通常 UTF-8 だが、環境変数の引き継ぎや systemd unit の設定次第で変わるため、**環境に依存しない
書き方を規約とする**。UTF-8 モードがデフォルトになるのは Python 3.15 以降なので、それまでは明示が
唯一の確実な対策。

### 規約

```python
# 正しい
with open(path, encoding="utf-8") as f:
    ...
path.read_text(encoding="utf-8")
path.write_text(text, encoding="utf-8")
df.to_csv(path, index=False, encoding="utf-8")

# 誤り（環境によって cp932 になる）
with open(path) as f:
    ...
path.read_text()
```

### 環境変数

`PYTHONUTF8=1` を以下すべてに設定する。1箇所でも漏れると、その経路だけ壊れる。

- `~/.bashrc`（対話実行）
- systemd user unit の `Environment=`（常駐サービス）
- `.env`（アプリ設定）
- CI の環境変数

### CI での機械的検出

Ruff で以下を有効にする。

```toml
[tool.ruff.lint]
extend-select = ["PLW1514", "W605", "UP"]
```

`PLW1514` が `encoding` 未指定の `open()` を検出する。加えて、テスト実行時に
`PYTHONWARNDEFAULTENCODING=1` を設定し、`EncodingWarning` をエラーに昇格させる。

```toml
[tool.pytest.ini_options]
filterwarnings = ["error::EncodingWarning"]
```

### CSV 出力の例外

Excel で開く前提の書き出しのみ `utf-8-sig`（BOM付き）を使う。BOM がないと Excel が cp932 と
誤認して日本語が化ける。

```python
df.to_csv(path, index=False, encoding="utf-8-sig")
```

内部処理・データ層は BOM なしの `utf-8` で統一する。BOM 付きを内部で使うと先頭列名に `\ufeff` が
混入する。

### 標準出力

```python
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
```

ログを Windows 側にリダイレクトする場合に必要。

## 3. 改行コード

`.gitattributes` に以下を設定済みであることを確認する。

```
* text=auto eol=lf
```

既にCRLFで混入している場合は `git add --renormalize .` で正規化する。
