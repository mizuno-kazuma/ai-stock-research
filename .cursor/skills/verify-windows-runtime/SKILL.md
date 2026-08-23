---
name: verify-windows-runtime
description: Windows 11 + WSL2 実行環境の検証と切り分け手順。mirrored networking、Hyper-V ファイアウォール、Tailscale 経由のスマホからの到達性、PYTHONUTF8 と文字コード、データ保存先の位置、スリープと Windows Update 後の自動再開を順に確認する。スマホからアクセスできない、日本語が文字化けする、再起動後にジョブが動いていない、動作が異常に遅いといった症状の切り分けに使う。
---

# Windows/WSL2 実行環境の検証

症状から入る場合は「症状別の切り分け」から読む。定期点検の場合は上から順に実行する。

関連仕様: [15-windows-runtime.md](../../../docs/15-windows-runtime.md)、
[10-mobile-pwa.md](../../../docs/10-mobile-pwa.md)

## 症状別の切り分け

| 症状 | 最初に見る節 |
| --- | --- |
| スマホからアクセスできない | §2 ネットワーク |
| PC のブラウザでは開けるがスマホでは開けない | §2.3 Hyper-V ファイアウォール |
| 日本語が文字化けする、`UnicodeDecodeError` | §3 文字コード |
| ファイル名やパスでエラー | §4 パス |
| 朝ジョブが動いていない | §5 常時稼働 |
| 再起動後にデータが欠けている | §5.4 チェックポイント再開 |
| DuckDB / Parquet の読み書きが異常に遅い | §4.2 データ保存先 |
| WSL2 がメモリを食い潰す | §6 リソース |
| Tailscale 経由で接続が不安定、大きなレスポンスで切れる | §2.4 Tailscale の二重導入 |

## 1. 一括診断

アプリが起動していれば、まずこれを実行する。

```bash
curl -s -X POST localhost:8000/api/v1/system/diagnostics | jq -r \
  '.data.checks[] | "\(.status)\t\(.category)\t\(.name)\t\(.detail_ja // "")"'
```

または `/settings#system` の「診断を実行」。失敗した項目に対応する節へ進む。

アプリが起動しない場合は §2.1 から手動で確認する。

## 2. ネットワーク

### 2.1 WSL2 内でサービスが上がっているか

```bash
# WSL2 内で実行
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/api/v1/system/health
curl -s -o /dev/null -w '%{http_code}\n' localhost:3000
ss -tlnp | grep -E ':(3000|8000)'
```

`0.0.0.0` または `*` で待ち受けていること。`127.0.0.1` のみだと mirrored でも外から届かない。

Next.js: `next dev -H 0.0.0.0`
FastAPI: `uvicorn --host 0.0.0.0 --port 8000`

### 2.2 mirrored networking が有効か

```bash
# WSL2 内
cat /proc/sys/kernel/osrelease            # WSL2 であること
ip addr show | grep -E 'inet .*(eth0|lo)' # mirrored ならホストと同じIPが見える
```

```powershell
# Windows 側（PowerShell）
Get-Content $env:USERPROFILE\.wslconfig
```

期待する内容:

```ini
[wsl2]
networkingMode=mirrored
dnsTunneling=true
autoProxy=true
firewall=true
```

変更した場合は必ず反映させる。**設定を書いただけでは効かない。**

```powershell
wsl --shutdown
# 数秒待ってから WSL2 を起動
```

`networkingMode=mirrored` は Windows 11 22H2 以降が必要。Windows 10 では使えないため、その場合は
§2.5 のフォールバックへ。

### 2.3 Hyper-V ファイアウォールの受信許可

mirrored モードで最も多い原因。PC のブラウザからは開けるがスマホからは開けない場合はこれ。

```powershell
# 現在の設定を確認
Get-NetFirewallHyperVVMSetting -Name '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}'
```

`DefaultInboundAction` が `Allow` でなければ許可する（管理者権限の PowerShell）。

```powershell
Set-NetFirewallHyperVVMSetting -Name '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -DefaultInboundAction Allow
```

**Windows Update でこの設定が戻ることがある。** 突然スマホから繋がらなくなったら、まずここを
再確認する。定期点検の項目に入れておく。

より絞った許可にしたい場合は、既定を Block のままポート単位で許可する。

```powershell
New-NetFirewallHyperVRule -Name "ai-stock-web" -DisplayName "AI Stock Web" `
  -Direction Inbound -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' `
  -Protocol TCP -LocalPorts 3000 -Action Allow
```

### 2.4 Tailscale の場所を確認

**Tailscale は Windows ホスト側にのみインストールする。WSL2 内には入れない。**

```bash
# WSL2 内で実行。何も出ないのが正しい
which tailscale tailscaled
systemctl status tailscaled 2>/dev/null
```

WSL2 内に入っていた場合はアンインストールする。WSL2 内と Windows ホストの両方に入れると、
Tailscale のパケットが二重にカプセル化されて MTU が不足し、小さなリクエストは通るのに大きな
レスポンスだけ落ちるという切り分けにくい症状になる。Tailscale 公式もこの構成を推奨していない。

```powershell
# Windows 側で状態を確認
tailscale status
tailscale ip -4
```

mirrored モードでは、WSL2 のサービスが Windows の Tailscale IP でそのまま見える。

### 2.5 スマホからの到達性

```bash
# Windows 側の Tailscale IP を確認したうえで、スマホのブラウザで開く
# http://100.x.y.z:3000
```

繋がらない場合の確認順序:

1. スマホが同じ tailnet に参加しているか（Tailscale アプリで確認）
2. Windows 側で `tailscale status` にスマホが出ているか
3. Windows 側から `curl http://localhost:3000` が通るか
4. §2.3 のファイアウォール設定
5. Windows Defender ファイアウォールで node/python が許可されているか

### 2.6 HTTPS（PWA 機能に必要）

Service Worker、通知、インストールは HTTPS でないと動かない。Tailscale Serve を使う。

```powershell
tailscale serve --bg --https 443 http://localhost:3000
tailscale serve status
```

`https://<machine>.<tailnet>.ts.net` でアクセスできること。HTTP のままだとオフライン表示や
ホーム画面追加が機能しない。

### 2.7 フォールバック: portproxy

mirrored が使えない環境のみ。WSL2 の IP は起動ごとに変わるため、恒久策にはならない。

```powershell
# WSL2 の IP を取得して転送設定
$ip = (wsl hostname -I).Trim().Split()[0]
netsh interface portproxy add v4tov4 listenport=3000 listenaddress=0.0.0.0 connectport=3000 connectaddress=$ip
netsh interface portproxy show all
```

WSL2 を再起動したら設定し直す必要がある。

## 3. 文字コード

### 3.1 環境変数

```bash
echo "PYTHONUTF8=$PYTHONUTF8"
python3 -c "import sys, locale; print(sys.flags.utf8_mode, sys.getdefaultencoding(), locale.getpreferredencoding())"
```

期待値: `PYTHONUTF8=1`、`1 utf-8 UTF-8`。

`sys.flags.utf8_mode` が 0 なら設定が効いていない。以下すべてを確認する。1箇所でも漏れると
その経路だけ壊れる。

- `~/.bashrc` に `export PYTHONUTF8=1`
- systemd user unit に `Environment=PYTHONUTF8=1`
- `.env` に `PYTHONUTF8=1`
- CI の環境変数

```bash
systemctl --user show ai-stock-agent -p Environment
```

### 3.2 実際に日本語を読む

```bash
python3 - <<'PY'
from pathlib import Path
p = Path("/tmp/enc_test.txt")
p.write_text("有価証券報告書 業績予想の修正 ソニーグループ", encoding="utf-8")
print(p.read_text(encoding="utf-8"))
print(p.read_text())          # encoding 省略。UTF-8モードなら通る
PY
```

2行目で例外が出るなら UTF-8 モードが効いていない。

### 3.3 コード側の規約

```bash
uv run ruff check --select PLW1514 .
```

違反があれば `encoding="utf-8"` を追加する。テスト実行時は `EncodingWarning` をエラーにする。

```bash
PYTHONWARNDEFAULTENCODING=1 uv run pytest tests/ -W error::EncodingWarning
```

### 3.4 CSV の書き出し

Excel で開く前提のファイルのみ `utf-8-sig`。内部処理は `utf-8`。BOM を内部で使うと列名の先頭に
`\ufeff` が混入する。

## 4. パスとファイルシステム

### 4.1 パスに使えない文字

```bash
# 生成済みのパスに Windows の禁止文字が含まれていないか
find "$DATA_DIR" -name '*[:?*<>|"]*' -print | head -20
```

1件でもヒットしたら命名規則の違反。`data/raw/` と Parquet のパーティション名を確認する。

```bash
uv run pytest tests/ -k "path or naming" -v
```

### 4.2 データ保存先の位置（性能に直結）

```bash
echo "$DATA_DIR"
df -h "$DATA_DIR" | tail -1
```

`/mnt/c/`、`/mnt/d/` 配下だと 9P プロトコル経由になり、I/O が桁違いに遅い。DuckDB と Parquet の
読み書きで顕著に影響する。**WSL2 のホームディレクトリ配下（`/home/<user>/ai-stock/data`）に置く。**

実測して確認する。

```bash
# WSL2 ネイティブ
dd if=/dev/zero of=/home/$USER/iotest bs=1M count=512 oflag=direct 2>&1 | tail -1
# Windows マウント（比較用）
dd if=/dev/zero of=/mnt/c/Temp/iotest bs=1M count=512 2>&1 | tail -1
rm -f /home/$USER/iotest /mnt/c/Temp/iotest
```

10倍以上の差が出るのが正常。差がほとんどないなら、逆に WSL2 側のディスクに問題がある。

起動時バリデーションで `/mnt/` 配下を拒否していることも確認する。

```bash
DATA_DIR=/mnt/c/data uv run python -m services.api.main
# 起動時エラーになるのが正しい
```

なお、**バックアップ先は `/mnt/d/` などの Windows ドライブでよい**。書き込み頻度が低く、WSL2 の
仮想ディスクとは別の物理ディスクに置ける利点が上回る。

### 4.3 改行コード

```bash
cat .gitattributes                 # * text=auto eol=lf があること
git ls-files --eol | grep -v 'i/lf' | head -20
```

CRLF が混入していたら正規化する。

```bash
git add --renormalize .
git status
```

## 5. 常時稼働

### 5.1 電源設定

```powershell
powercfg /query SCHEME_CURRENT SUB_SLEEP
# スリープと休止状態が無効（0）になっていること
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change monitor-timeout-ac 10
```

モニタのオフは問題ない。スリープするとジョブが止まる。

### 5.2 Windows Update の再起動

```powershell
Get-WindowsUpdateLog   # 直近の更新履歴
# アクティブ時間を設定（設定アプリ > Windows Update > 詳細オプション）
```

再起動は完全には避けられない。避けるのではなく、再起動されても復帰する設計に頼る（§5.4）。

### 5.3 WSL2 と systemd の自動起動

```bash
# systemd が有効か
cat /etc/wsl.conf              # [boot] systemd=true
systemctl --user is-enabled ai-stock-agent
systemctl --user status ai-stock-agent
loginctl show-user "$USER" | grep Linger    # Linger=yes であること
```

`Linger=no` だとログアウト時にサービスが止まる。

```bash
sudo loginctl enable-linger "$USER"
```

Windows 起動時に WSL2 自体を立ち上げる設定（タスクスケジューラ）も確認する。

```powershell
Get-ScheduledTask -TaskName "*wsl*" | Select TaskName, State
```

### 5.4 チェックポイントからの自動再開（最重要）

再起動対策の本体はここ。設定ではなく設計で守る。

```bash
# 中断状態のジョブが残っていないか
curl -s 'localhost:8000/api/v1/agent/jobs?limit=20' | jq -r \
  '.data[] | select(.status=="interrupted") | "\(.job_run_id)\t\(.job_name)\t\(.started_at)"'
```

中断ジョブがあれば、自動再開されているかを確認する。`trigger` が `auto_resume` の実行が後続して
いれば正常。

```bash
curl -s 'localhost:8000/api/v1/agent/jobs?limit=20' | jq -r \
  '.data[] | select(.trigger=="auto_resume") | "\(.job_run_id)\t\(.job_name)\t\(.status)"'
```

再開されていない場合は手動で実行する。冪等なので同じ日付で再実行して問題ない。

```bash
uv run python -m services.agent.run collector_jp --date 2026-08-22
```

意図的に検証する場合:

```bash
# ジョブ実行中に強制終了し、再起動後に再開されるか確認
systemctl --user restart ai-stock-agent
# checkpoint から続いているか、job_runs.checkpoint を確認
```

### 5.5 スリープ復帰後の時刻ずれ

APScheduler の設定を確認する。

```python
# coalesce=True         復帰後に溜まった実行を1回にまとめる
# max_instances=1       多重起動を防ぐ
# misfire_grace_time=3600  1時間以内の遅れは実行する
```

`coalesce=False` だと、8時間スリープした後に8回分のジョブが一斉に走り、レート制限とLLMコストを
使い切る。

## 6. リソース

```bash
free -h
nproc
cat /proc/meminfo | grep -i swap
df -h /
```

```powershell
Get-Content $env:USERPROFILE\.wslconfig
```

推奨設定（物理16GBの場合）:

```ini
[wsl2]
memory=10GB
processors=6
swap=4GB
autoMemoryReclaim=gradual
sparseVhd=true
```

`autoMemoryReclaim=gradual` がないと、WSL2 が確保したメモリを Windows 側に返さない。
`sparseVhd=true` がないと仮想ディスクが縮小せず、削除しても空き容量が戻らない。

DuckDB 側でも上限を設定する。

```sql
SET memory_limit='6GB';
SET temp_directory='/home/user/ai-stock/data/tmp';
```

`temp_directory` を指定しないと、大きなクエリで一時ファイルが予期しない場所に作られる。

仮想ディスクの縮小（WSL2 停止中に Windows 側で実行）:

```powershell
wsl --shutdown
wsl --manage Ubuntu --set-sparse true
```

## 定期点検チェックリスト（月1回）

- [ ] `.wslconfig` の内容が意図どおり（Windows Update で戻っていないか）
- [ ] Hyper-V ファイアウォールの受信許可が `Allow`（**最も戻りやすい**）
- [ ] スマホから Tailscale 経由で HTTPS でアクセスできる
- [ ] WSL2 内に Tailscale が入っていない
- [ ] `PYTHONUTF8=1` が対話・systemd・`.env` すべてで有効
- [ ] `DATA_DIR` が `/mnt/` 配下でない
- [ ] `data/` に禁止文字を含むパスがない
- [ ] 電源設定でスリープが無効
- [ ] `systemctl --user is-enabled` が enabled、`Linger=yes`
- [ ] 中断ジョブが残っていない、または再開されている
- [ ] ディスク空き容量が `data/` の想定成長（月2-3GB）に対して十分
- [ ] バックアップが直近で成功している
