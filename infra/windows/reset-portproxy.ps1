# WSL2 NAT モードのフォールバック用。mirrored networking が使えない場合のみ。
# 管理者権限の PowerShell で実行する。
# 詳細: docs/15-windows-runtime.md §2.5
#
# NAT モードでは WSL2 の IP が起動ごとに変わるため、再起動のたびに本スクリプトを走らせる。

netsh interface portproxy reset
$wslIp = (wsl hostname -I).Trim().Split()[0]
if (-not $wslIp) {
    Write-Error "WSL2 の IP を取得できませんでした。"
    exit 1
}
foreach ($port in @(3000, 8000)) {
    netsh interface portproxy add v4tov4 `
        listenport=$port listenaddress=0.0.0.0 `
        connectport=$port connectaddress=$wslIp
}
netsh interface portproxy show v4tov4
