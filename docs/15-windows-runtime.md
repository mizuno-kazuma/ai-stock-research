# 15. Windows 11 + WSL2 実行環境のセットアップと固有の落とし穴

## 0. 本章の構成

Windows + WSL2 で本ツールを動かす際に**必ず踏む問題**を、原因と対策のセットで記述する。いずれも後から遭遇すると原因の特定に時間を取られる項目である。

構成の前提:

```
Windows 11（22H2 以降）
 ├─ Tailscale（ホスト側のみ。WSL2 内には入れない）
 ├─ .wslconfig（networkingMode=mirrored, dnsTunneling=true）
 └─ WSL2 (Ubuntu 24.04)
     ├─ systemd
     │   ├─ ai-stock-api.service    (FastAPI :8000)
     │   ├─ ai-stock-agent.service  (APScheduler)
     │   └─ ai-stock-web.service    (Next.js :3000)
     └─ リポジトリとデータ（~/ai-stock 配下。/mnt/c は使わない）
```

## 1. 前提要件

| 項目 | 要件 | 確認方法 |
| --- | --- | --- |
| Windows | **11 22H2 以降** | `winver` |
| WSL | 2.0.0 以降（mirrored networking の要件） | `wsl --version` |
| ディストリビューション | Ubuntu 24.04 LTS 推奨 | `wsl -l -v` |
| ディスク空き容量 | 100GB 以上（データが40GB程度になる） | |
| メモリ | 16GB 以上推奨（LightGBM の学習と DuckDB の集計で使う） | |
| 仮想化 | BIOS で有効 | タスクマネージャ > パフォーマンス > CPU > 仮想化 |

`networkingMode=mirrored` は Windows 11 22H2 以降でのみ利用できる。Windows 10 では使えないため、その場合は §2.5 のフォールバック（`netsh portproxy`）を使う。

## 2. 落とし穴 1: WSL2 のネットワーク到達性

### 2.1 症状

PC のブラウザからは `http://localhost:3000` で見えるのに、**スマートフォンから Tailscale 経由でアクセスすると接続できない。**

### 2.2 原因

WSL2 の既定のネットワークモード（NAT）では、WSL2 は Windows ホストとは別のサブネット上の仮想マシンとして動く。WSL2 内でサービスが `0.0.0.0` にバインドしていても、Windows ホストの外部インターフェース（Tailscale の仮想インターフェースを含む）にはポートが公開されない。

WSL2 には localhost forwarding という機能があり、Windows の `localhost` から WSL2 のポートに繋がる。しかしこれは `127.0.0.1` に対してのみ機能し、Tailscale IP（`100.x.y.z`）や LAN IP からのアクセスは転送されない。これが「PCからは見えるがスマホからは見えない」の直接の原因である。

### 2.3 対策: mirrored networking

`%USERPROFILE%\.wslconfig`（存在しない場合は新規作成）に以下を書く。

```ini
[wsl2]
# WSL2 に Windows ホストのネットワークインターフェースを鏡像化する。
# これにより WSL2 内の 0.0.0.0 バインドが Windows の全インターフェース
# （Tailscale 含む）で到達可能になる。Windows 11 22H2 以降が必要。
networkingMode=mirrored

# DNS 解決を Windows 側にトンネルする。VPN 併用時の名前解決の失敗を防ぐ。
# Tailscale の MagicDNS を使う場合にも効く。
dnsTunneling=true

# ファイアウォールを Hyper-V 側で統合管理する
firewall=true

# 自動プロキシ設定の引き継ぎ（企業ネットワーク等で有効）
autoProxy=true

[experimental]
# メモリを解放する（DuckDB の大きな集計後にホストへ返す）
autoMemoryReclaim=gradual

# ディスクの空き領域を Windows に返す
sparseVhd=true
```

設定後、WSL を完全に停止して再起動する。

```powershell
wsl --shutdown
# 8秒ほど待ってから
wsl
```

**`wsl --shutdown` を実行しないと設定が反映されない。** 単に WSL のターミナルを閉じるだけでは足りない。これに気付かず「設定したのに効かない」と判断するのがよくある誤りである。

確認:

```bash
# WSL2 内で実行。Windows ホストと同じ IP が見えるはず
ip addr show
# mirrored モードでは Windows の Tailscale IP（100.x.y.z）も見える
```

### 2.4 対策の続き: Hyper-V ファイアウォールの受信許可（これを忘れると到達できない）

**mirrored networking を有効にしただけでは、外部からの受信が Hyper-V のファイアウォールでブロックされる。** これが最も見落としやすい設定である。

管理者権限の PowerShell で以下を実行する。

```powershell
# WSL2 の Hyper-V VM に対する既定の受信動作を「許可」にする。
# GUID {40E0AC32-46A5-438A-A0B2-2B479E8F2E90} は WSL 用の固定値。
Set-NetFirewallHyperVVMSetting `
  -Name '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' `
  -DefaultInboundAction Allow
```

確認:

```powershell
Get-NetFirewallHyperVVMSetting -Name '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' |
  Select-Object Name, DefaultInboundAction
# DefaultInboundAction が Allow になっていること
```

**この設定は Windows Update で元に戻ることがある** `[要検証]`。到達できなくなったら最初にこれを確認する。`.cursor/skills/verify-windows-runtime/SKILL.md` の確認項目に含める。

より限定的に、特定ポートのみを許可することもできる。

```powershell
# 全許可ではなく、必要なポートのみを開ける場合
Set-NetFirewallHyperVVMSetting `
  -Name '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' `
  -DefaultInboundAction Block
New-NetFirewallHyperVRule -Name "WSL-AIStock-Web" -DisplayName "AI Stock Web" `
  -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' `
  -Protocol TCP -LocalPorts 3000 -Action Allow
New-NetFirewallHyperVRule -Name "WSL-AIStock-Api" -DisplayName "AI Stock API" `
  -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' `
  -Protocol TCP -LocalPorts 8000 -Action Allow
```

`[要検証]` `New-NetFirewallHyperVRule` のパラメータ名は Windows のバージョンで異なる場合がある。まず `-DefaultInboundAction Allow` で到達性を確認し、動いたら限定的な設定に絞るのが現実的な手順である。

### 2.5 フォールバック: `netsh interface portproxy`

mirrored networking が何らかの理由で使えない場合（Windows 10、または mirrored モードで他のソフトウェアと競合する場合）のフォールバックである。**Windows 11 が確定しているため主経路は mirrored であり、これは補足扱いとする。**

```powershell
# WSL2 の IP アドレスを取得する（NAT モードでは起動ごとに変わる）
$wslIp = (wsl hostname -I).Trim().Split()[0]

# ポートフォワードを設定する
netsh interface portproxy add v4tov4 `
  listenport=3000 listenaddress=0.0.0.0 `
  connectport=3000 connectaddress=$wslIp
netsh interface portproxy add v4tov4 `
  listenport=8000 listenaddress=0.0.0.0 `
  connectport=8000 connectaddress=$wslIp

# Windows ファイアウォールで受信を許可する
New-NetFirewallRule -DisplayName "AI Stock Web" -Direction Inbound `
  -LocalPort 3000 -Protocol TCP -Action Allow
New-NetFirewallRule -DisplayName "AI Stock API" -Direction Inbound `
  -LocalPort 8000 -Protocol TCP -Action Allow

# 確認
netsh interface portproxy show v4tov4
```

**この方式の問題**: NAT モードでは WSL2 の IP が起動ごとに変わるため、**WSL2 を再起動するたびに portproxy を再設定する必要がある**。これを自動化するスクリプトをタスクスケジューラに登録することになり、運用が煩雑になる。mirrored networking を使う理由がここにある。

```powershell
# フォールバックを使う場合の再設定スクリプト（infra/windows/reset-portproxy.ps1）
netsh interface portproxy reset
$wslIp = (wsl hostname -I).Trim().Split()[0]
foreach ($port in @(3000, 8000)) {
  netsh interface portproxy add v4tov4 `
    listenport=$port listenaddress=0.0.0.0 `
    connectport=$port connectaddress=$wslIp
}
```

### 2.6 切り分け手順

到達できない場合、以下の順で確認する。

```bash
# (1) WSL2 内でサービスが listen しているか
ss -tlnp | grep -E ':(3000|8000)'
# → 0.0.0.0:3000 になっていること。127.0.0.1:3000 だと外部から到達できない

# (2) WSL2 内から自分に繋がるか
curl -s -o /dev/null -w '%{http_code}' http://localhost:3000
```

```powershell
# (3) Windows から WSL2 のサービスに繋がるか
curl.exe -s -o NUL -w "%{http_code}" http://localhost:3000

# (4) Windows の Tailscale IP で繋がるか
$tsIp = (tailscale ip -4)
curl.exe -s -o NUL -w "%{http_code}" "http://${tsIp}:3000"

# (5) Hyper-V ファイアウォールの設定
Get-NetFirewallHyperVVMSetting -Name '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}'

# (6) mirrored モードが有効か
Get-Content "$env:USERPROFILE\.wslconfig"
wsl --version
```

(1) で `127.0.0.1:3000` になっている場合は、アプリのバインドアドレスの問題である。Next.js は既定で `0.0.0.0` にバインドするが、`--hostname localhost` が付いていると `127.0.0.1` になる。Uvicorn は `--host 0.0.0.0` を明示する。

(3) が通って (4) が通らない場合は、Hyper-V ファイアウォールの問題である（§2.4）。

## 3. 落とし穴 2: Tailscale を WSL2 内にも入れてしまう

### 3.1 症状

WSL2 内にも Tailscale をインストールすると、通信が不安定になる。小さなリクエストは通るが、**大きなレスポンス（PDF のダウンロード、チャートデータ）が途中で止まる**、あるいは接続が確立しない。

### 3.2 原因

Tailscale は WireGuard による暗号化トンネルであり、パケットにオーバーヘッドを追加する。Windows ホストと WSL2 の両方に Tailscale を入れると、**パケットが二重にカプセル化され、MTU（最大転送単位）が不足する**。

通常の MTU は 1500 バイトである。Tailscale は既定で MTU を 1280 に下げるが、二重になると実効的なペイロードがさらに小さくなり、フラグメンテーションと再送が発生する。小さなパケットは通るが大きなパケットが落ちるという症状になり、「時々繋がらない」という切り分けの難しい状態になる。

**Tailscale の公式ドキュメントもこの構成を非推奨としている** `[要検証]`。

### 3.3 対策

**Tailscale は Windows ホスト側のみにインストールする。**

```powershell
# Windows ホストで実行
winget install tailscale.tailscale
tailscale up
tailscale ip -4       # 100.x.y.z が返る
```

WSL2 内には**インストールしない**。既にインストールしてしまっている場合は削除する。

```bash
# WSL2 内で実行（誤ってインストールしていた場合）
sudo tailscale down
sudo systemctl disable --now tailscaled
sudo apt remove --purge tailscale
```

### 3.4 なぜ WSL2 内に Tailscale が不要なのか

`networkingMode=mirrored` により、WSL2 は Windows ホストのネットワークインターフェースを共有する。**Windows ホストの Tailscale インターフェース（および Tailscale IP）が WSL2 内からもそのまま見える。**

したがって、WSL2 内のサービスが `0.0.0.0:3000` にバインドすれば、Windows ホストの Tailscale IP `100.x.y.z:3000` でアクセスできる。WSL2 内に Tailscale を入れる必要がない。

確認:

```bash
# WSL2 内で実行。Windows の Tailscale IP が見える
ip addr | grep 100\.
```

### 3.5 HTTPS 化（Tailscale Serve）

PWA の Service Worker は HTTPS を要求する（[10-mobile-pwa.md](10-mobile-pwa.md) §2.3）。Tailscale Serve を使う。

```powershell
# Windows ホストで実行
tailscale serve --bg --https=443 http://localhost:3000
tailscale serve status
```

これで `https://<machine-name>.<tailnet-name>.ts.net` でアクセスできる。証明書は Tailscale が自動で発行する。

`[要検証]` `tailscale serve` のコマンド構文はバージョンによって変わる。`tailscale serve --help` で確認する。

**`tailscale funnel`（インターネット公開）は使わない。** tailnet 内に限定することがセキュリティ境界である。

## 4. 落とし穴 3: 文字コード（日本語ロケール Windows で必ず踏む）

### 4.1 症状

EDINET や TDnet から取得した日本語のテキストを読み書きすると、以下のエラーが出る。

```
UnicodeDecodeError: 'cp932' codec can't decode byte 0xe3 in position 12: illegal multibyte sequence
UnicodeEncodeError: 'cp932' codec can't encode character '\u2015' in position 5
```

あるいはエラーにならずに**文字化けしたデータが保存される**（こちらの方が発見が遅れて厄介である）。

### 4.2 原因

Python の `open()` は `encoding` を省略すると `locale.getpreferredencoding()` を使う。**日本語ロケールの Windows ではこれが `cp932`（Shift_JIS 系）になる。** UTF-8 のバイト列を `cp932` として読もうとして失敗する。

WSL2 内であれば通常 `UTF-8` になるが、以下の場合に `cp932` が使われる可能性がある。

- Windows ネイティブ側で Python スクリプトを動かす場合（発注ブリッジなど。[14-future-brokerage.md](14-future-brokerage.md) §3.4）
- 環境変数が Windows から引き継がれた場合
- CI が Windows ランナーで動く場合

さらに、`cp932` には**UTF-8 で表現できるが `cp932` では表現できない文字がある**（全角ダッシュ `―`、丸数字、一部の異体字など）。有価証券報告書のタイトルにこれらが含まれることがあり、書き込み時にエラーになる。

### 4.3 対策 1: `PYTHONUTF8=1` を必須化する

Python の UTF-8 モードを有効にすると、`open()` の既定エンコーディングが UTF-8 になる。

```bash
# WSL2 の ~/.bashrc または ~/.profile
export PYTHONUTF8=1
export LANG=ja_JP.UTF-8
export LC_ALL=ja_JP.UTF-8
```

```ini
# systemd unit（infra/wsl/ai-stock-agent.service）
[Service]
Environment=PYTHONUTF8=1
Environment=LANG=ja_JP.UTF-8
Environment=TZ=Asia/Tokyo
```

```powershell
# Windows 側（発注ブリッジを動かす場合）
[System.Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")
```

### 4.4 対策 2: それでも `encoding="utf-8"` を明示する（規約）

**`PYTHONUTF8=1` だけに頼らない。** 理由は以下。

- 環境変数の設定漏れが起きる（新しい実行経路を追加したとき、CI、他の PC への移行時）
- サブプロセスに環境変数が引き継がれない場合がある
- **Python の UTF-8 モードがデフォルトになるのは Python 3.15 から**である（PEP 686）。それまでは明示が唯一の確実な対策である

したがって以下を規約とする。

```python
# 良い例
path.read_text(encoding="utf-8")
path.write_text(text, encoding="utf-8")
with open(path, "r", encoding="utf-8") as f: ...
with open(path, "w", encoding="utf-8", newline="\n") as f: ...
pd.read_csv(path, encoding="utf-8")
json.loads(path.read_bytes().decode("utf-8"))
logging.FileHandler(log_path, encoding="utf-8")
subprocess.run([...], capture_output=True, text=True, encoding="utf-8")

# 悪い例（encoding 未指定）
path.read_text()
open(path).read()
pd.read_csv(path)
logging.FileHandler(log_path)
```

`newline="\n"` を書き込み時に指定するのは、Windows で `\r\n` に変換されるのを防ぐため（JSONL やログファイルで問題になる）。

### 4.5 対策 3: Ruff で機械的に検出する

規約を人間の注意力に頼らず、CI で検出する。

```toml
# pyproject.toml
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = [
    "E", "F", "W",      # pycodestyle, pyflakes
    "I",                # isort
    "UP",               # pyupgrade
    "B",                # flake8-bugbear
    "PTH",              # flake8-use-pathlib（os.path を禁止し pathlib を強制）
    "PLW1514",          # unspecified-encoding（open() の encoding 未指定を検出）
    "PLW1509",          # subprocess-popen-preexec-fn
    "EXE",              # flake8-executable
    "ASYNC",            # flake8-async
    "RUF",              # Ruff 固有
]
ignore = [
    "E501",             # line-too-long（formatter に任せる）
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["PLW1514"]     # テストでは許容してもよい（ただし推奨しない）
```

**`PLW1514`（unspecified-encoding）が本プロジェクトで最も重要な lint ルールである。** これを有効にすることで、`encoding` を書き忘れたコードがマージされなくなる。

`PYTHONWARNDEFAULTENCODING=1` を開発時に設定すると、実行時に `EncodingWarning` が出る。テスト実行時にこれを有効にし、警告をエラーとして扱う。

```toml
# pyproject.toml
[tool.pytest.ini_options]
filterwarnings = [
    "error::EncodingWarning",     # encoding 未指定を実行時にもエラーにする
]
env = ["PYTHONWARNDEFAULTENCODING=1"]
```

対応するテストは [12-testing-validation.md](12-testing-validation.md) の T-ENV-01（AST を走査して `open()` の `encoding` 指定を検証する）。

### 4.6 対策 4: 標準出力のエンコーディング

Windows のコンソールに日本語を出すと文字化けまたはエラーになることがある。

```python
# services/agent/main.py の冒頭
import sys
if sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
```

構造化ログ（JSON）を使う場合、`ensure_ascii=False` にすると日本語がそのまま出るため読みやすいが、出力先のエンコーディングが UTF-8 であることが前提になる。上記の `reconfigure` とセットで使う。

### 4.7 対策 5: DB とファイルのエンコーディング

| 対象 | 設定 |
| --- | --- |
| SQLite | 既定で UTF-8。追加設定不要 |
| DuckDB | 既定で UTF-8。追加設定不要 |
| Parquet | 既定で UTF-8。追加設定不要 |
| CSV 出力（Excel で開く用） | `encoding="utf-8-sig"`（BOM 付き）。BOM がないと Excel が cp932 と誤認して文字化けする |
| JSON | `ensure_ascii=False` + `encoding="utf-8"` |
| ログファイル | `encoding="utf-8"` |

**Excel で開くための CSV だけは `utf-8-sig` を使う。** これは例外的な扱いであり、他の用途では `utf-8` を使う。

## 5. 落とし穴 4: ファイルパスに使えない文字

### 5.1 症状

Parquet のパーティション名やキャッシュファイル名に `:` を使うと、Windows 側からファイルにアクセスできない。エクスプローラーで見えない、コピーできない、`OSError: [Errno 22] Invalid argument` が出る。

### 5.2 原因

Windows のファイル名には以下の文字が使えない。

```
< > : " / \ | ? *
```

および ASCII 制御文字（0-31）。加えて以下の予約名が使えない（拡張子があっても不可）。

```
CON, PRN, AUX, NUL, COM1-COM9, LPT1-LPT9
```

さらに、末尾のスペースとピリオドが許されない。

WSL2 内（ext4 ファイルシステム）では `:` を含むファイル名を作れるが、**Windows 側から `\\wsl$\Ubuntu\...` 経由でアクセスすると問題になる**。また `/mnt/c` 配下に作ろうとすると失敗する。

日時をファイル名に使う際、ISO 8601 の `2026-08-23T09:30:00` には `:` が含まれるため、これが最も踏みやすいケースである。

### 5.3 対策

```python
# packages/core/storage/paths.py
WINDOWS_FORBIDDEN_CHARS = set('<>:"/\\|?*')
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

def is_valid_path_component(name: str) -> bool:
    """Windows でも使えるパス要素かを判定する。
    WSL2 内でも Windows 互換の命名規則を守る（Windows 側から同じファイルを
    触る可能性があり、後から気付くと修正コストが大きい）。"""
    if not name or name != name.strip(" ."):
        return False
    if set(name) & WINDOWS_FORBIDDEN_CHARS:
        return False
    if name.split(".")[0].upper() in WINDOWS_RESERVED_NAMES:
        return False
    if any(ord(c) < 32 for c in name):
        return False
    return True

def safe_component(name: str) -> str:
    """禁止文字を '_' に置換する。"""
    out = "".join("_" if (c in WINDOWS_FORBIDDEN_CHARS or ord(c) < 32) else c
                  for c in name).strip(" .")
    if out.split(".")[0].upper() in WINDOWS_RESERVED_NAMES:
        out = f"_{out}"
    return out or "_"

def timestamp_component(dt: datetime) -> str:
    """日時をパス要素にする。ISO 8601 の ':' を避ける。"""
    return dt.strftime("%Y%m%dT%H%M%SZ")     # 2026-08-23T09:30:00 → 20260823T093000Z
```

### 5.4 命名規則（本プロジェクトの規約）

| 用途 | 規則 | 例 |
| --- | --- | --- |
| Parquet パーティション | `key=value` 形式。value に禁止文字を含めない | `market=JP/year=2026/month=08` |
| 日付パーティション | `dt=YYYY-MM-DD`（ハイフン区切り） | `dt=2026-08-23` |
| 日時を含むファイル名 | `YYYYMMDDTHHMMSSZ`（コロンなし） | `20260823T093000Z_0001.json.gz` |
| ドキュメント blob | `doc_id` の `:` を `_` に置換 | `edinet_S100XYZW.pdf` |
| バックアップディレクトリ | `YYYYMMDD_HHMMSS` | `20260823_093012` |
| モデルアーティファクト | `{kind}_{market}_{horizon}_{run_id}.txt` | `ranker_JP_H20_01J8XK.txt` |
| ログファイル | `{service}-YYYY-MM-DD.jsonl` | `agent-2026-08-23.jsonl` |

**日本語をファイル名に使わない。** 有価証券報告書のタイトル（「第122期有価証券報告書」）をファイル名にすると、文字コードとパス長の両方の問題を招く。タイトルは DB のカラムに持ち、ファイル名は ID にする。

### 5.5 対策: `pathlib` の徹底

`os.path` の文字列連結は区切り文字の扱いを間違えやすい。`pathlib.Path` を使う。

```python
# 良い例
from pathlib import Path
p = DATA_DIR / "raw" / source / endpoint / f"dt={as_of:%Y-%m-%d}" / filename

# 悪い例
p = os.path.join(DATA_DIR, "raw", source, endpoint, f"dt={as_of}", filename)
p = DATA_DIR + "/raw/" + source + "/" + filename    # 特に悪い
```

Ruff の `PTH` ルール（flake8-use-pathlib）で `os.path` の使用を機械的に検出する（§4.5）。

### 5.6 パス長の制限

Windows の従来の `MAX_PATH` は 260 文字である。Windows 10 以降はレジストリで長いパスを有効にできるが、既定では無効な場合がある。

対策として、パスを短く保つ設計にする。

- `DATA_DIR` を短くする（`/home/user/ai-stock/data`、`/home/user/very/deeply/nested/project/directory/data` にしない）
- パーティションを深くしすぎない（3階層まで）
- ファイル名に日本語や長いタイトルを使わない（§5.4）

## 6. 落とし穴 5: `/mnt/c/` 配下にリポジトリを置く

### 6.1 症状

DuckDB のクエリや Parquet の読み書きが極端に遅い。`uv sync` や `npm install` が異常に時間がかかる。Git の操作が遅い。

### 6.2 原因

`/mnt/c/` は WSL2 が Windows のファイルシステムを 9P プロトコル経由でマウントしたものである。このプロトコル越しの I/O は、WSL2 内の ext4 に比べて**桁違いに遅い**（小さなファイルの大量アクセスで特に顕著）。

本ツールは以下の特性を持つため、この差が致命的になる。

- Parquet ファイルの読み書き（数百MB単位）
- DuckDB のクエリ（大量のランダムアクセス）
- Python パッケージのインストール（数万の小さなファイル）
- `node_modules`（数十万のファイル）
- Git の操作（大量の小さなファイル）

### 6.3 対策

**リポジトリとデータを WSL2 のホームディレクトリ配下に置く。**

```bash
# 良い例
~/ai-stock/                    # = /home/user/ai-stock
~/ai-stock/data/

# 悪い例
/mnt/c/Users/me/ai-stock/
/mnt/c/dev/ai-stock/
```

コードレベルでも強制する（[11-security-ops.md](11-security-ops.md) §1.3）。

```python
@field_validator("data_dir")
@classmethod
def data_dir_not_on_windows_mount(cls, v: Path) -> Path:
    if str(v).startswith("/mnt/"):
        raise ValueError(
            f"DATA_DIR に Windows マウント（{v}）を指定できません。"
            "WSL2 のホーム配下（例: /home/user/ai-stock/data）を使ってください。")
    return v
```

### 6.4 Windows 側からファイルを見る方法

WSL2 のファイルは Windows から `\\wsl$\Ubuntu\home\user\ai-stock` でアクセスできる。エクスプローラーのアドレスバーに入力すれば開ける。

エディタ（VS Code / Cursor）は WSL 拡張機能を使い、**WSL2 内のファイルシステムを直接開く**。Windows 側から `\\wsl$` 経由で開くと 9P プロトコルを経由するため遅い。

```bash
# WSL2 内から起動する（推奨）
cd ~/ai-stock && code .
```

### 6.5 例外: 発注ブリッジ

Windows ネイティブ側で動かすもの（[14-future-brokerage.md](14-future-brokerage.md) §3.4 の発注ブリッジ）は Windows 側に置く。この場合、WSL2 側のリポジトリとは**別のディレクトリ**にし、必要なコードだけをコピーまたは別リポジトリにする。同じディレクトリを両方から触ると、改行コードとパーミッションの問題が起きる。

## 7. 落とし穴 6: 改行コード

### 7.1 症状

シェルスクリプトを実行すると以下のエラーが出る。

```
bash: ./setup.sh: /bin/bash^M: bad interpreter: No such file or directory
```

Git の差分が全行変更として表示される。

### 7.2 原因

Windows のエディタや Git の設定（`core.autocrlf=true`）により、ファイルが CRLF（`\r\n`）で保存される。Linux のシェルは `\r` をコマンド名の一部として解釈するため失敗する。

### 7.3 対策

リポジトリルートに `.gitattributes` を置く。

```gitattributes
# デフォルトは LF に正規化する
* text=auto eol=lf

# 明示的にテキストとして扱うもの
*.py     text eol=lf
*.ts     text eol=lf
*.tsx    text eol=lf
*.js     text eol=lf
*.json   text eol=lf
*.yaml   text eol=lf
*.yml    text eol=lf
*.md     text eol=lf
*.sh     text eol=lf
*.toml   text eol=lf
*.sql    text eol=lf
*.jinja  text eol=lf
*.service text eol=lf

# Windows でのみ使うもの（CRLF を維持する）
*.ps1    text eol=crlf
*.bat    text eol=crlf
*.cmd    text eol=crlf
.wslconfig text eol=crlf

# バイナリ（変換しない）
*.png    binary
*.jpg    binary
*.pdf    binary
*.parquet binary
*.duckdb binary
*.sqlite binary
*.zip    binary
*.gz     binary
*.woff2  binary
```

`.editorconfig` も併せて置く。

```ini
root = true

[*]
end_of_line = lf
insert_final_newline = true
charset = utf-8
trim_trailing_whitespace = true
indent_style = space

[*.{ps1,bat,cmd}]
end_of_line = crlf

[*.{py,pyi}]
indent_size = 4

[*.{ts,tsx,js,jsx,json,yaml,yml}]
indent_size = 2

[*.md]
trim_trailing_whitespace = false
```

既に CRLF が混入している場合の修正:

```bash
# .gitattributes を追加した後
git add --renormalize .
git commit -m "chore: 改行コードを LF に正規化"
```

## 8. 落とし穴 7: PC のスリープと Windows Update による再起動

### 8.1 症状

- 朝になってもダッシュボードが更新されていない
- ジョブが `running` のまま止まっている
- Windows Update の後にサービスが起動していない

### 8.2 原因

| 原因 | 詳細 |
| --- | --- |
| PC のスリープ | 既定では一定時間の無操作でスリープする。スリープ中はスケジュールされたジョブが実行されない |
| Windows Update の自動再起動 | アクティブ時間外に自動で再起動する。実行中のジョブが中断される |
| WSL2 の自動停止 | WSL2 は一定時間アイドルだと停止することがある `[要検証]` |
| systemd が無効 | WSL2 で systemd が有効になっていないとサービスが自動起動しない |

### 8.3 対策 1: 電源設定

```powershell
# 管理者権限の PowerShell で実行

# AC 電源接続時はスリープしない（0 = 無効）
powercfg /change standby-timeout-ac 0
# ディスプレイは切ってよい（15分）
powercfg /change monitor-timeout-ac 15
# ハイバネートを無効化
powercfg /change hibernate-timeout-ac 0
# ディスクをスリープさせない
powercfg /change disk-timeout-ac 0

# 現在の設定を確認
powercfg /query SCHEME_CURRENT SUB_SLEEP
```

**モダンスタンバイ（S0 low power idle）を採用しているノートPCでは、上記の設定でもスリープすることがある** `[要検証]`。この場合は以下も確認する。

```powershell
# スリープの種類を確認
powercfg /a
# ネットワーク接続の維持を許可
powercfg /setacvalueindex SCHEME_CURRENT SUB_NONE CONNECTIVITYINSTANDBY 1
powercfg /setactive SCHEME_CURRENT
```

### 8.4 対策 2: Windows Update のアクティブ時間

Windows Update の自動再起動を完全に止めることは推奨されない（セキュリティ更新が適用されない）。代わりに、再起動されても復旧する設計にする（§8.6）。

アクティブ時間を設定して、再起動のタイミングを制御する。

```
設定 > Windows Update > 詳細オプション > アクティブ時間
  → 「自動的に調整する」をオフにし、6:00 - 23:00 を指定
```

これにより、深夜（バッチが走っていない時間帯）に再起動されるようになる。ただし本ツールのバッチは JST 06:30 と 18:30 に走るため、再起動と重なる可能性は残る。**再起動されても復旧することが本質的な対策である。**

### 8.5 対策 3: WSL2 の systemd と自動起動

まず WSL2 で systemd を有効にする。

```ini
# WSL2 内の /etc/wsl.conf
[boot]
systemd=true

[user]
default=ubuntu

[network]
generateResolvConf=true

[interop]
enabled=true
appendWindowsPath=false      # Windows の PATH を引き継がない（PATH の汚染を防ぐ）
```

設定後、`wsl --shutdown` して再起動する。確認:

```bash
systemctl is-system-running    # running または degraded が返れば systemd が動いている
```

systemd unit を作る。

```ini
# /etc/systemd/system/ai-stock-api.service
[Unit]
Description=AI Stock Research API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/ai-stock
Environment=PYTHONUTF8=1
Environment=LANG=ja_JP.UTF-8
Environment=TZ=Asia/Tokyo
EnvironmentFile=/home/ubuntu/ai-stock/.env
ExecStart=/home/ubuntu/.local/bin/uv run uvicorn services.api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/ai-stock-agent.service
[Unit]
Description=AI Stock Research Agent (APScheduler)
After=network-online.target ai-stock-api.service
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/ai-stock
Environment=PYTHONUTF8=1
Environment=LANG=ja_JP.UTF-8
Environment=TZ=Asia/Tokyo
EnvironmentFile=/home/ubuntu/ai-stock/.env
ExecStart=/home/ubuntu/.local/bin/uv run python -m services.agent.main
Restart=always
RestartSec=30
# 起動時に中断ジョブの再開チェックを行うため、少し待つ
ExecStartPre=/bin/sleep 10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ai-stock-api ai-stock-agent ai-stock-web
systemctl status ai-stock-agent
journalctl -u ai-stock-agent -f
```

### 8.6 対策 4: WSL2 自体を Windows 起動時に立ち上げる

WSL2 は誰かがログインして WSL のコマンドを実行するまで起動しない。Windows の再起動後に自動で WSL2 を起動する必要がある。

タスクスケジューラに登録する。**これは「アプリのジョブスケジューリング」ではなく「WSL2 の起動」だけを担う**点に注意する。ジョブのスケジューリングは APScheduler が行う（[01-architecture.md](01-architecture.md) §5.2 の D-04）。

```powershell
# 管理者権限の PowerShell で実行
$action = New-ScheduledTaskAction -Execute "wsl.exe" -Argument "-d Ubuntu -u root /bin/true"
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
                                        -LogonType S4U -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
                                         -DontStopIfGoingOnBatteries `
                                         -StartWhenAvailable `
                                         -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "Start WSL2 AI Stock" -Action $action `
  -Trigger $trigger -Principal $principal -Settings $settings
```

`-StartWhenAvailable` により、PC がスリープしていて起動時刻を逃した場合でも復帰後に実行される。

`wsl -d Ubuntu -u root /bin/true` は「WSL2 を起動して即座に終了するコマンドを実行する」ことで、WSL2 のインスタンス自体を立ち上げる。systemd が有効なら、これでサービスも起動する。

### 8.7 対策 5: 冪等なジョブとチェックポイントからの再開（最も重要）

**電源設定や再起動の制御は完全ではない。「中断される前提」で設計することが本質的な対策である。**

[08-agent-loop.md](08-agent-loop.md) §9 の通り。要点を再掲する。

| 仕組み | 内容 |
| --- | --- |
| 冪等性 | すべてのジョブは upsert のみ。同じ日で2回実行しても結果が変わらない |
| チェックポイント | 処理単位（営業日、doc_id、ticker）ごとに完了を記録する。**LLM呼び出しは最も細かい粒度で記録する**（再実行がコストに直結するため） |
| 中断の検出 | 15分ごとに `status='running'` かつ2時間以上経過したジョブを検出する。プロセスの生存も確認する |
| 自動再開 | チェックポイントから続きを実行する。完了済みの単位はスキップする |
| APScheduler の `coalesce=True` | スリープで実行時刻を複数回過ぎた場合、まとめて1回だけ実行する |
| APScheduler の `misfire_grace_time=3600` | 予定時刻から1時間以内なら遅れて実行する |
| 再開の上限 | 5回を超えたら諦めて通知する（無限ループの防止） |

```python
# 起動時の処理（services/agent/main.py）
def on_startup() -> None:
    """systemd による再起動後に呼ばれる。中断されたジョブを検出して再開する。"""
    interrupted = repo.find_job_runs(status="running")
    for run in interrupted:
        if is_process_alive(run.pid):
            continue
        logger.warning("interrupted_job_detected", job_run_id=run.id,
                       job_name=run.job_name, started_at=run.started_at)
        repo.update_job_run(run.id, status="interrupted")
        cp = load_checkpoint(run.id)
        if run.resume_chain_length >= 5:
            alerts.create(severity="error", category="runtime",
                          title_ja=f"{run.job_name} の再開が5回を超えました")
            continue
        enqueue_resume(run.job_name, checkpoint=cp, parent_run_id=run.id)
```

**この仕組みがあれば、Windows Update での再起動は「バッチが数分遅れる」程度の影響に収まる。** 電源設定の調整は補助的な対策であり、こちらが主対策である。

### 8.8 スリープ復帰後の時刻ずれ

スリープから復帰した直後、システム時刻の同期が完了する前にジョブが走ることがある。

```python
# 起動時とスリープ復帰時に時刻の妥当性を確認する
def assert_clock_sane() -> None:
    """システム時刻が異常でないことを確認する。
    スリープ復帰直後は NTP 同期が終わっていないことがある。"""
    drift = abs((utcnow() - fetch_ntp_time()).total_seconds())
    if drift > 300:
        raise ClockDriftError(f"システム時刻が {drift:.0f} 秒ずれています")
```

`[要検証]` NTP への問い合わせを毎回行うのは過剰なので、起動時のみに限定する。または `timedatectl status` で同期状態を確認する方法でもよい。

## 9. 落とし穴 8: WSL2 のメモリとディスク

### 9.1 症状

- LightGBM の学習中に WSL2 が OOM で落ちる
- Windows 全体が重くなる
- WSL2 の仮想ディスク（`ext4.vhdx`）が肥大化し、ファイルを削除しても Windows 側の空き容量が増えない

### 9.2 原因

WSL2 は既定でホストメモリの 50%（または 8GB のうち少ない方）を上限とする `[要検証]`。DuckDB の大きな集計や LightGBM の学習でこれを超えることがある。

また、WSL2 の仮想ディスクは自動で縮小しない。ファイルを削除しても `ext4.vhdx` のサイズは減らない。

### 9.3 対策

```ini
# %USERPROFILE%\.wslconfig
[wsl2]
memory=12GB              # ホストが16GBの場合。全部を割り当てない
processors=6
swap=8GB
swapFile=C:\\wsl-swap.vhdx

[experimental]
autoMemoryReclaim=gradual    # 使い終わったメモリをホストに返す
sparseVhd=true               # 仮想ディスクの空き領域をホストに返す
```

`autoMemoryReclaim=gradual` は DuckDB の大きな集計後にメモリをホストへ返すため、Windows 全体の体感が改善する。

DuckDB 側でもメモリ上限を設定する。

```python
con = duckdb.connect(WAREHOUSE, read_only=False)
con.execute("SET memory_limit='6GB'")
con.execute("SET threads=4")
con.execute(f"SET temp_directory='{DATA_DIR / 'duckdb_tmp'}'")   # スピル先
```

**`temp_directory` を明示する**ことが重要である。メモリに収まらない集計はディスクにスピルするが、既定の場所が `/tmp` だと WSL2 の tmpfs（メモリ上）になり、結局 OOM になる。

仮想ディスクの縮小（必要になったとき）:

```powershell
wsl --shutdown
# sparseVhd=true が有効なら自動で縮小されるが、手動で行う場合
diskpart
# DISKPART> select vdisk file="C:\Users\<user>\AppData\Local\Packages\<distro>\LocalState\ext4.vhdx"
# DISKPART> compact vdisk
```

## 10. セットアップ手順（通し）

### 10.1 Windows 側

```powershell
# (1) WSL2 のインストール
wsl --install -d Ubuntu-24.04
wsl --version    # 2.0.0 以降であること

# (2) .wslconfig の作成
@"
[wsl2]
networkingMode=mirrored
dnsTunneling=true
firewall=true
autoProxy=true
memory=12GB
processors=6
swap=8GB

[experimental]
autoMemoryReclaim=gradual
sparseVhd=true
"@ | Out-File -FilePath "$env:USERPROFILE\.wslconfig" -Encoding utf8

# (3) Hyper-V ファイアウォールの受信許可（管理者権限）
Set-NetFirewallHyperVVMSetting `
  -Name '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' `
  -DefaultInboundAction Allow

# (4) Tailscale のインストール（Windows ホストのみ）
winget install tailscale.tailscale
tailscale up
tailscale ip -4

# (5) 電源設定
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change disk-timeout-ac 0
powercfg /change monitor-timeout-ac 15

# (6) WSL2 の自動起動タスク（§8.6 のスクリプト）

# (7) WSL の再起動
wsl --shutdown
```

### 10.2 WSL2 側

```bash
# (1) /etc/wsl.conf の設定
sudo tee /etc/wsl.conf > /dev/null <<'EOF'
[boot]
systemd=true

[user]
default=ubuntu

[interop]
enabled=true
appendWindowsPath=false
EOF

# Windows 側で wsl --shutdown してから再度入る

# (2) ロケールと環境変数
sudo apt update && sudo apt install -y language-pack-ja
sudo locale-gen ja_JP.UTF-8
cat >> ~/.bashrc <<'EOF'
export PYTHONUTF8=1
export LANG=ja_JP.UTF-8
export LC_ALL=ja_JP.UTF-8
export TZ=Asia/Tokyo
EOF
source ~/.bashrc

# (3) タイムゾーン
sudo ln -sf /usr/share/zoneinfo/Asia/Tokyo /etc/localtime
sudo dpkg-reconfigure -f noninteractive tzdata

# (4) 必要なパッケージ
sudo apt install -y build-essential git curl unzip \
    libgomp1 \                # LightGBM の実行に必要
    fonts-noto-cjk            # 日本語フォント（チャート生成で使う場合）

# (5) uv のインストール
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv --version

# (6) Node.js のインストール（fnm または nvm）
curl -fsSL https://fnm.vercel.app/install | bash
source ~/.bashrc
fnm install 22 && fnm default 22

# (7) リポジトリのクローン（ホーム配下。/mnt/c は使わない）
mkdir -p ~/ai-stock && cd ~/ai-stock
git clone <repo-url> .

# (8) 依存のインストール
uv sync
cd apps/web && npm ci && cd ../..

# (9) .env の作成
cp .env.example .env
# エディタで APIキーを設定する

# (10) DB の初期化
uv run alembic upgrade head
uv run python -m packages.core.storage.init_duckdb

# (11) systemd unit の配置（§8.5）
sudo cp infra/wsl/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ai-stock-api ai-stock-agent ai-stock-web

# (12) 動作確認
curl -s http://localhost:8000/api/v1/system/health | jq
systemctl status ai-stock-agent
```

### 10.3 Tailscale Serve（HTTPS 化）

```powershell
# Windows ホストで実行
tailscale serve --bg --https=443 http://localhost:3000
tailscale serve status
# → https://<machine-name>.<tailnet>.ts.net でアクセスできる
```

スマートフォンで Tailscale アプリにログインし、上記 URL を開く。ホーム画面に追加すれば PWA として動作する。

## 11. 検証チェックリスト

環境が壊れたときの切り分けにも使う。詳細な手順は `.cursor/skills/verify-windows-runtime/SKILL.md`。

### 11.1 ネットワーク

- [ ] `wsl --version` が 2.0.0 以降
- [ ] `.wslconfig` に `networkingMode=mirrored` がある
- [ ] `Get-NetFirewallHyperVVMSetting` の `DefaultInboundAction` が `Allow`
- [ ] WSL2 内で `ip addr | grep 100\.` に Tailscale IP が見える
- [ ] WSL2 内で `ss -tlnp | grep 3000` が `0.0.0.0:3000` を示す
- [ ] Windows から `curl http://localhost:3000` が 200 を返す
- [ ] Windows から `curl http://<tailscale-ip>:3000` が 200 を返す
- [ ] スマートフォンから `https://<machine>.<tailnet>.ts.net` が開く
- [ ] **WSL2 内に Tailscale がインストールされていない**（`which tailscale` が空）

### 11.2 文字コード

- [ ] `echo $PYTHONUTF8` が `1`
- [ ] `python -c "import sys; print(sys.getdefaultencoding(), sys.stdout.encoding)"` が UTF-8
- [ ] `locale` が `ja_JP.UTF-8`
- [ ] `ruff check .` で `PLW1514` の違反がない
- [ ] 日本語を含む EDINET のタイトルが DB に正しく保存されている
- [ ] ログファイルの日本語が文字化けしていない

### 11.3 パス・ファイルシステム

- [ ] リポジトリが `/home/` 配下にある（`/mnt/c` ではない）
- [ ] `DATA_DIR` が `/home/` 配下
- [ ] Parquet のパーティション名に `:` `?` `*` がない
- [ ] `.gitattributes` に `* text=auto eol=lf` がある
- [ ] `git status` に改行コードのみの差分が出ていない

### 11.4 常時稼働

- [ ] `systemctl is-system-running` が `running` または `degraded`
- [ ] 3サービスが `enabled` かつ `active`
- [ ] `powercfg /query SCHEME_CURRENT SUB_SLEEP` でスタンバイが無効
- [ ] タスクスケジューラに WSL2 起動タスクが登録されている
- [ ] `wsl --shutdown` の後に WSL2 に入り直すと3サービスが自動起動する
- [ ] `job_runs` に `status='running'` で長時間放置されたレコードがない
- [ ] 意図的に強制終了させた後、チェックポイントから再開される

### 11.5 リソース

- [ ] `free -h` でメモリ上限が `.wslconfig` の設定通り
- [ ] `df -h ~` で空き容量が 20GB 以上
- [ ] DuckDB の `temp_directory` が `/tmp` ではない場所を指している

## 12. 参照

- アーキテクチャ: [01-architecture.md](01-architecture.md) §6
- ジョブの冪等性と再開: [08-agent-loop.md](08-agent-loop.md) §9
- PWA 配信: [10-mobile-pwa.md](10-mobile-pwa.md) §2
- 運用と監視: [11-security-ops.md](11-security-ops.md)
- 環境テスト: [12-testing-validation.md](12-testing-validation.md) §8
- 発注ブリッジ（将来）: [14-future-brokerage.md](14-future-brokerage.md) §3.4
- 検証手順: `.cursor/skills/verify-windows-runtime/SKILL.md`
