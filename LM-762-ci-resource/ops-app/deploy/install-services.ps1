# Install the Release Desk as Windows scheduled tasks (Windows equivalent of a systemd unit). Run ONCE in an
# elevated PowerShell (Run as administrator). The tasks run as the normal user given by -User (not as SYSTEM / admin),
# start at boot without anyone logged on (S4U), and restart on failure.
#
#   powershell -ExecutionPolicy Bypass -File install-services.ps1                    # install / update, then start
#   powershell -ExecutionPolicy Bypass -File install-services.ps1 -RefreshAt 07:00,19:00
#   powershell -ExecutionPolicy Bypass -File install-services.ps1 -NoRefresh         # mode A/B: no scheduled refresh
#   powershell -ExecutionPolicy Bypass -File install-services.ps1 -Uninstall
#
# Tasks:
#   ops-app-server   python server.py --root releases (127.0.0.1:8765)  at startup, restart every 1 min on failure
#   ops-app-caddy    caddy run (80/443, TLS, basic auth, gzip)           at startup, restart every 1 min on failure
#   ops-app-refresh  refresh.ps1 (mode C: collect, build, check, publish) daily at -RefreshAt
#   ops-app-backup   backup.py (ops.db + state.db, keep 14)              daily 03:00
param(
    [string]$User = "$env:USERDOMAIN\$env:USERNAME",
    [string[]]$RefreshAt = @('07:00'),   # host clock; this host is UTC+7 (SE Asia Standard Time) = 07:00 Viet Nam time
    [int]$RefreshEveryMin = 0,           # >0: again every N minutes all day (default once a day); a run takes ~15 min
    [switch]$NoRefresh,
    [switch]$Uninstall
)
. "$PSScriptRoot\common.ps1"

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw 'Run this in an elevated PowerShell (Run as administrator).' }
$names = 'ops-app-server', 'ops-app-caddy', 'ops-app-refresh', 'ops-app-backup'

if ($Uninstall) {
    foreach ($n in $names) {
        if (Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue) {
            Stop-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $n -Confirm:$false
            "removed task $n"
        }
    }
    Get-NetFirewallRule -DisplayName 'ops-app Caddy (HTTP/HTTPS)' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    exit 0
}

if (-not (Test-Path $EnvFile)) { throw "Create $EnvFile from ops-app.env.example first." }
foreach ($k in 'OPS_DOMAIN', 'OPS_AUTH_USER', 'OPS_AUTH_HASH') {
    if (-not (Get-Item "env:$k" -ErrorAction SilentlyContinue).Value) { throw "$k is empty in $EnvFile" }
}
if (-not (Test-Path (Join-Path $Releases 'CURRENT'))) { throw 'No live release yet: run  python -X utf8 publish.py publish  first.' }

# Secrets file: only the service user, Administrators and SYSTEM can read it.
& icacls.exe $EnvFile /inheritance:r /grant:r "${User}:(R,W)" 'Administrators:(F)' 'SYSTEM:(F)' | Out-Null

$caddy = Get-OpsCaddy
$port = if ($env:OPS_PORT) { $env:OPS_PORT } else { '8765' }
$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType S4U -RunLevel Limited
$always = New-ScheduledTaskSettingsSet -RestartCount 9999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$batch = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew `
    -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

function Set-OpsTask($name, $action, $trigger, $settings, $desc) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
    }
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description $desc | Out-Null
    "installed task $name"
}

Set-OpsTask 'ops-app-server' `
    (New-ScheduledTaskAction -Execute $Py -WorkingDirectory $Backend `
        -Argument "-X utf8 `"$Backend\server.py`" --host 127.0.0.1 --port $port --root `"$Releases`" --log `"$Logs\access.log`"") `
    (New-ScheduledTaskTrigger -AtStartup) $always 'Release Desk web server (read-only), behind Caddy'

Set-OpsTask 'ops-app-caddy' `
    (New-ScheduledTaskAction -Execute $caddy -WorkingDirectory $Deploy `
        -Argument "run --config Caddyfile --adapter caddyfile --envfile `"$EnvFile`"") `
    (New-ScheduledTaskTrigger -AtStartup) $always 'Release Desk reverse proxy: TLS, basic auth, gzip'

if (-not $NoRefresh) {
    $trig = @($RefreshAt | ForEach-Object {
        $t = New-ScheduledTaskTrigger -Daily -At $_
        if ($RefreshEveryMin -gt 0) {   # data stays fresh through the day; IgnoreNew + refresh.ps1's busy check stop overlaps
            $t.Repetition = (New-ScheduledTaskTrigger -Once -At $_ -RepetitionInterval (New-TimeSpan -Minutes $RefreshEveryMin) `
                -RepetitionDuration (New-TimeSpan -Days 1)).Repetition
        }
        $t })
    Set-OpsTask 'ops-app-refresh' `
        (New-ScheduledTaskAction -Execute $ps -WorkingDirectory $Deploy `
            -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Deploy\refresh.ps1`"") `
        $trig $batch 'Release Desk data refresh (mode C): collect, build, check, publish; last good build stays live on failure'
} elseif (Get-ScheduledTask -TaskName 'ops-app-refresh' -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName 'ops-app-refresh' -Confirm:$false
    'removed task ops-app-refresh (-NoRefresh)'
}

Set-OpsTask 'ops-app-backup' `
    (New-ScheduledTaskAction -Execute $Py -WorkingDirectory $Deploy -Argument "-X utf8 `"$Deploy\backup.py`"") `
    (New-ScheduledTaskTrigger -Daily -At '03:00') $batch 'Release Desk SQLite backup (keep 14)'

if (-not (Get-NetFirewallRule -DisplayName 'ops-app Caddy (HTTP/HTTPS)' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName 'ops-app Caddy (HTTP/HTTPS)' -Direction Inbound -Action Allow -Protocol TCP `
        -LocalPort 80, 443 -Program $caddy | Out-Null
    'firewall: inbound TCP 80, 443 allowed for caddy.exe'
}

Start-ScheduledTask -TaskName 'ops-app-server'
Start-ScheduledTask -TaskName 'ops-app-caddy'
'started ops-app-server and ops-app-caddy'
"check:  curl.exe -s https://$env:OPS_DOMAIN/healthz"
