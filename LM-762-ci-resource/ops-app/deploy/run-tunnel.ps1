# Run the Cloudflare Tunnel for the Release Desk (outbound only: no router port, no firewall rule).
# Reads OPS_TUNNEL_TOKEN from ops-app.env. The public hostname -> http://127.0.0.1:8765 mapping and the
# Cloudflare Access policy live in the Zero Trust dashboard (see CLOUDFLARE.md).
#
#   powershell -ExecutionPolicy Bypass -File run-tunnel.ps1             # run in this window (Ctrl+C stops)
#   powershell -ExecutionPolicy Bypass -File run-tunnel.ps1 -Install    # user-level task "ops-app-tunnel" (at logon, restart)
#   powershell -ExecutionPolicy Bypass -File run-tunnel.ps1 -Uninstall  # remove the task (site goes offline)
param([switch]$Install, [switch]$Uninstall)
. "$PSScriptRoot\common.ps1"
Import-OpsEnv
$name = 'ops-app-tunnel'

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        "removed task $name"
    }
    Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
    exit 0
}

function Get-OpsCloudflared {
    if ($env:OPS_CLOUDFLARED -and (Test-Path $env:OPS_CLOUDFLARED)) { return $env:OPS_CLOUDFLARED }
    $c = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    foreach ($p in "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe", "$env:ProgramFiles\cloudflared\cloudflared.exe") {
        if (Test-Path $p) { return $p }
    }
    $w = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages') -Recurse -Filter cloudflared.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($w) { return $w.FullName }
    throw 'cloudflared.exe not found: winget install --id Cloudflare.cloudflared, or set OPS_CLOUDFLARED in ops-app.env'
}

if (-not $env:OPS_TUNNEL_TOKEN) { throw "OPS_TUNNEL_TOKEN is empty in $EnvFile (see CLOUDFLARE.md step 2)" }
if (-not $env:OPS_TUNNEL_HOSTNAME) { throw "OPS_TUNNEL_HOSTNAME is empty in ${EnvFile}: server.py would answer 421 to the tunnel" }
$cf = Get-OpsCloudflared

if ($Install) {
    $ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $action = New-ScheduledTaskAction -Execute $ps -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $settings = New-ScheduledTaskSettingsSet -RestartCount 9999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
    }
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings `
        -Description 'Release Desk: Cloudflare Tunnel (behind Cloudflare Access)' | Out-Null
    Start-ScheduledTask -TaskName $name
    "installed and started task $name (runs while you are logged on; install-services.ps1 style S4U needs admin)"
    exit 0
}

# The server must already refuse tunnel requests without Access, so check that before going online.
$port = if ($env:OPS_PORT) { $env:OPS_PORT } else { '8765' }
try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/healthz" -Headers @{ 'Cf-Ray' = 'selftest' } -TimeoutSec 10
    throw "server.py on port $port answered $($r.StatusCode) to a tunnel request without Access: restart ops-app-server so it runs the current server.py with OPS_TUNNEL_HOSTNAME set"
} catch [System.Net.WebException] {
    $code = [int]$_.Exception.Response.StatusCode
    if ($code -ne 403) { throw "self-test: expected 403 from server.py for a tunnel request without Access, got $code" }
}

$log = Join-Path $Logs 'tunnel.log'
# the token goes through the environment (TUNNEL_TOKEN), not the command line, so it does not show in process lists
$env:TUNNEL_TOKEN = $env:OPS_TUNNEL_TOKEN
& $cf tunnel --no-autoupdate --logfile $log --loglevel info run
exit $LASTEXITCODE
