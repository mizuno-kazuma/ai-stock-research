# Hyper-V ファイアウォールで WSL2 への受信を許可する。
# 管理者権限の PowerShell で実行する。
# 詳細: docs/15-windows-runtime.md §2.4
#
# mirrored networking を有効にしただけでは、外部からの受信が
# Hyper-V ファイアウォールでブロックされる。

$wslVm = '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}'

Set-NetFirewallHyperVVMSetting -Name $wslVm -DefaultInboundAction Allow

Get-NetFirewallHyperVVMSetting -Name $wslVm |
    Select-Object Name, DefaultInboundAction
