# Start the Release Desk web server in production mode (serves releases/<CURRENT>, 127.0.0.1 only).
# Used by the scheduled task "ops-app-server"; you can also run it by hand.
. "$PSScriptRoot\common.ps1"
$port = if ($env:OPS_PORT) { $env:OPS_PORT } else { '8765' }
if (-not (Test-Path (Join-Path $Releases 'CURRENT'))) { throw "no live release yet: run deploy\publish.py publish first" }
& $Py -X utf8 (Join-Path $Backend 'server.py') --host 127.0.0.1 --port $port --root $Releases --log (Join-Path $Logs 'access.log')
exit $LASTEXITCODE
