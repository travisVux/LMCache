# Shared settings for the deploy scripts. Dot-source it:  . "$PSScriptRoot\common.ps1"
$ErrorActionPreference = 'Stop'

$Deploy    = $PSScriptRoot
$App       = Split-Path $Deploy -Parent                       # ops-app/
$Backend   = Join-Path $App 'backend'
$CpuTests  = Join-Path (Split-Path $App -Parent) 'plan-2026-11\outputs\cpu_tests'
$Releases  = Join-Path $App 'releases'
$Logs      = Join-Path $App 'logs'
$EnvFile   = Join-Path $Deploy 'ops-app.env'
New-Item -ItemType Directory -Force $Logs | Out-Null

# Python 3.11+ (3.13 on this host). Override with OPS_PYTHON in ops-app.env.
function Get-OpsPython {
    if ($env:OPS_PYTHON -and (Test-Path $env:OPS_PYTHON)) { return $env:OPS_PYTHON }
    $p = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
    if (Test-Path $p) { return $p }
    $c = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($c -and $c.Source -notlike '*WindowsApps*') { return $c.Source }
    throw 'Python 3.11+ not found: install it or set OPS_PYTHON in ops-app.env'
}

function Get-OpsCaddy {
    if ($env:OPS_CADDY -and (Test-Path $env:OPS_CADDY)) { return $env:OPS_CADDY }
    $c = Get-Command caddy.exe -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $w = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages') -Recurse -Filter caddy.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($w) { return $w.FullName }
    throw 'caddy.exe not found: winget install CaddyServer.Caddy, or set OPS_CADDY in ops-app.env'
}

# KEY=VALUE lines (# comments). Values go to this process only; nothing is printed.
function Import-OpsEnv {
    if (-not (Test-Path $EnvFile)) { return }
    foreach ($line in Get-Content $EnvFile -Encoding UTF8) {
        $t = $line.Trim()
        if (-not $t -or $t.StartsWith('#') -or -not $t.Contains('=')) { continue }
        $k, $v = $t.Split('=', 2)
        Set-Item -Path "env:$($k.Trim())" -Value $v.Trim().Trim('"')
    }
}

$env:PYTHONUTF8 = '1'
Import-OpsEnv
$Py = Get-OpsPython
