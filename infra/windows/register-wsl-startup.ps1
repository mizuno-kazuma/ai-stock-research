# Windows 起動時に WSL2 を立ち上げるタスクを登録する。
# 管理者権限の PowerShell で実行する。
# これはアプリのジョブスケジューリングではなく、WSL2 インスタンスの起動だけを担う。
# 詳細: docs/15-windows-runtime.md §8.6

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
