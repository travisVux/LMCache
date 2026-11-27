# Mode A: build on the machine that has the data (old PC), then put it live on the host. No network calls by default.
#
#   powershell -ExecutionPolicy Bypass -File sync.ps1 -HostReleases \\HOST\ops-releases
#   powershell -ExecutionPolicy Bypass -File sync.ps1 -HostReleases \\HOST\ops-releases -SkipBuild   # dist/ is already fresh
#
# -HostReleases = the host's ops-app\releases folder, shared to this PC (SMB share, write access).
# Steps: build_page -> verify_page (PASS) -> build_today -> export_static (local only: NR_NO_GH=1, TRD_NO_GH=1)
#        -> publish.py on THIS machine with --releases <share>: privacy scan = 0, copy to <share>\.staging-<ts>,
#           rename to <ts>, atomic switch of <share>\CURRENT, keep 5. The host server picks it up on the next request.
# Rollback (from here or on the host):  python -X utf8 publish.py rollback --releases \\HOST\ops-releases
param([Parameter(Mandatory = $true)][string]$HostReleases, [switch]$SkipBuild)
. "$PSScriptRoot\common.ps1"
if (-not (Test-Path (Join-Path $HostReleases 'CURRENT'))) { throw "$HostReleases has no CURRENT: wrong path, or the host has no release yet" }

function Invoke-Py($dir, [string[]]$pyArgs) {
    Push-Location $dir
    try { & $Py @pyArgs; if ($LASTEXITCODE -ne 0) { throw "failed: python $($pyArgs -join ' ')" } }
    finally { Pop-Location }
}

if (-not $SkipBuild) {
    $env:NR_NO_GH = '1'; $env:TRD_NO_GH = '1'
    Invoke-Py $CpuTests @('-I', '-X', 'utf8', 'build_page.py')
    Invoke-Py $CpuTests @('-I', '-X', 'utf8', 'verify_page.py')
    Invoke-Py $CpuTests @('-I', '-X', 'utf8', 'build_today.py')
    Invoke-Py $Backend  @('-X', 'utf8', 'export_static.py')
}
Invoke-Py $Deploy @('-X', 'utf8', 'publish.py', 'publish', '--releases', $HostReleases, '--note', 'sync from build PC (mode A)')
Invoke-Py $Deploy @('-X', 'utf8', 'publish.py', 'list', '--releases', $HostReleases)
