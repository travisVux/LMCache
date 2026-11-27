# Start Caddy (TLS + basic auth + gzip) in front of server.py, by hand. The scheduled task "ops-app-caddy" runs the same command.
. "$PSScriptRoot\common.ps1"
foreach ($k in 'OPS_DOMAIN', 'OPS_AUTH_USER', 'OPS_AUTH_HASH') {
    if (-not (Get-Item "env:$k" -ErrorAction SilentlyContinue).Value) { throw "$k is empty in $EnvFile" }
}
Push-Location $Deploy
try { & (Get-OpsCaddy) run --config Caddyfile --adapter caddyfile --envfile $EnvFile }
finally { Pop-Location }
exit $LASTEXITCODE
