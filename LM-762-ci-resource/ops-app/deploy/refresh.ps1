# Mode C: refresh the Release Desk data on this host and put the new build live — only if every check passes.
# Run by the scheduled task "ops-app-refresh" (or by hand). Collectors call GitHub + Buildkite (read-only).
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File refresh.ps1            # full: collect + build + check + publish
#   powershell -NoProfile -ExecutionPolicy Bypass -File refresh.ps1 -Offline   # no network: rebuild from local files (NR_NO_GH / TRD_NO_GH)
#
# Order: collectors -> ops.db -> build_page -> verify_page (PASS) -> build_today -> export_static -> check_app (all OK)
#        -> publish.py (privacy scan 0, new release folder, atomic CURRENT switch, keep 5).
# Any failed step stops the run; the live release is not touched (the last good build stays live).
# Log: ops-app/logs/refresh-<time>.log (last 30 kept).
# Each step is killed after -StepTimeoutMin minutes (default 40) so a hung collector still ends with a FAILED line.
# Outcome is also written to logs/last-refresh.json (status ok | warn | failed | busy). If OPS_ALERT_URL is set in
# ops-app.env (an ntfy topic or any webhook that accepts a plain-text POST), a failed, busy or GitHub-only run posts one
# short line there (no paths, no tokens).
param([switch]$Offline, [switch]$SkipUiCheck, [int]$StepTimeoutMin = 40)
. "$PSScriptRoot\common.ps1"

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$log = Join-Path $Logs "refresh-$stamp.log"
$lockPath = Join-Path $Logs 'refresh.lock'
function Send-Status($status, $text) {
    $o = [ordered]@{ status = $status; at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'); text = $text; log = (Split-Path $log -Leaf) }
    ($o | ConvertTo-Json -Compress) | Out-File -FilePath (Join-Path $Logs 'last-refresh.json') -Encoding utf8
    if ($env:OPS_ALERT_URL -and $status -ne 'ok') {
        try { Invoke-RestMethod -Method Post -Uri $env:OPS_ALERT_URL -Body "release-desk refresh $($status): $text" -TimeoutSec 20 | Out-Null }
        catch { Add-Content -Path $log -Value "alert post failed: $($_.Exception.GetType().Name)" -Encoding UTF8 }
    } elseif ($status -in @('failed', 'busy')) {
        # no alert channel configured: a local pop-up for the logged-in user (nothing leaves this machine)
        try { & msg.exe $env:USERNAME /TIME:21600 "Release Desk refresh $($status): $text (log: $(Split-Path $log -Leaf))" 2>$null } catch {}
    }
}
try { $lock = [IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'None') }
catch {
    Add-Content -Path $log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') another refresh is running ($(Split-Path $lockPath -Leaf)); this run did nothing" -Encoding UTF8
    Send-Status 'busy' 'another refresh was still running; this run did nothing'
    exit 2
}

function Write-Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $log -Value $line -Encoding UTF8
    Write-Output $line
}

# One step = one python script in its own folder; its stdout+stderr go to the log (cmd redirect: PS 5.1 safe).
function Invoke-Step($name, $dir, $script, [string[]]$scriptArgs = @(), [switch]$Isolated) {
    Write-Log "STEP $name"
    $flags = if ($Isolated) { '-I -X utf8' } else { '-X utf8' }
    $argText = ($scriptArgs | ForEach-Object { '"' + $_ + '"' }) -join ' '
    $cmdLine = "/d /c `"`"$Py`" $flags `"$script`" $argText >> `"$log`" 2>&1`""
    $p = Start-Process -FilePath cmd.exe -ArgumentList $cmdLine -WorkingDirectory $dir -WindowStyle Hidden -PassThru
    if (-not $p.WaitForExit($StepTimeoutMin * 60 * 1000)) {
        & taskkill.exe /T /F /PID $p.Id *> $null
        throw "step '$name' timed out after $StepTimeoutMin min (killed)"
    }
    $code = $p.ExitCode
    if ($code -ne 0) { throw "step '$name' failed (exit $code)" }
}

# Parallel steps (2026-11-27): each writes its own part log, which is appended to the main log when it ends, so the
# log stays readable. Each step still has its own -StepTimeoutMin limit. Wait-Steps waits for ALL given steps (no
# orphan collector keeps writing) and returns the failures; the caller throws, so the live build is still untouched.
function Start-Step($name, $dir, $script, [string[]]$scriptArgs = @(), [switch]$Isolated) {
    $part = Join-Path $Logs "refresh-$stamp-$name.part.log"
    $flags = if ($Isolated) { '-I -X utf8' } else { '-X utf8' }
    $argText = ($scriptArgs | ForEach-Object { '"' + $_ + '"' }) -join ' '
    $cmdLine = "/d /c `"`"$Py`" $flags `"$script`" $argText > `"$part`" 2>&1`""
    $p = Start-Process -FilePath cmd.exe -ArgumentList $cmdLine -WorkingDirectory $dir -WindowStyle Hidden -PassThru
    $null = $p.Handle   # keep the handle so ExitCode is available after the process ends
    $null = Write-Log "START $name (parallel)"   # Write-Log also writes to the pipeline: keep it out of the return value
    return [pscustomobject]@{ Name = $name; P = $p; Part = $part; T0 = Get-Date }
}
function Wait-Steps($steps) {
    $fail = @()
    foreach ($s in $steps) {
        $left = [int][Math]::Max(1000, ($s.T0.AddMinutes($StepTimeoutMin) - (Get-Date)).TotalMilliseconds)
        $why = $null
        if (-not $s.P.WaitForExit($left)) {
            & taskkill.exe /T /F /PID $s.P.Id *> $null
            $why = "step '$($s.Name)' timed out after $StepTimeoutMin min (killed)"
        } else {
            $s.P.WaitForExit()
            if ($s.P.ExitCode -ne 0) { $why = "step '$($s.Name)' failed (exit $($s.P.ExitCode))" }
        }
        # review 3.5: the steps are awaited one after the other, so use the time the process really ended
        $end = try { if ($s.P.HasExited) { $s.P.ExitTime } else { Get-Date } } catch { Get-Date }
        $secs = [int]($end - $s.T0).TotalSeconds
        $null = Write-Log "END $($s.Name) after ${secs}s: $(if ($why) { 'FAILED' } else { 'ok' })"
        if (Test-Path $s.Part) {
            Add-Content -Path $log -Value "----- output of $($s.Name) -----" -Encoding UTF8
            Get-Content -Path $s.Part -Encoding UTF8 | Add-Content -Path $log -Encoding UTF8
            Remove-Item $s.Part -Force -ErrorAction SilentlyContinue
        }
        if ($why) { $fail += $why }
    }
    return $fail   # unrolled: the caller wraps it in @()
}

$ok = $false
$optFail = @()
$runId = $null
try {
    Write-Log "refresh start (offline=$Offline) python=$Py"
    # one sync run = one id shared by the page data (manifest run_id), ops.db (sync_run) and the D1 copy (rd_sync)
    try { $runId = (& $Py -X utf8 (Join-Path $Backend 'sync_run.py') start --note $(if ($Offline) { 'offline' } else { 'scheduled' }) 2>$null | Select-Object -Last 1) }
    catch { $runId = $null }
    if ("$runId" -match '^\d+$') { $env:RD_RUN_ID = "$runId"; Write-Log "sync run $runId" } else { $runId = $null; Write-Log 'sync run id not created (sync_run.py failed)' }
    if ($Offline) {
        $env:NR_NO_GH = '1'; $env:TRD_NO_GH = '1'
    } else {
        if (-not $env:GH_TOKEN) {
            & cmd.exe /d /c "gh auth status >nul 2>&1"
            if ($LASTEXITCODE -ne 0) { throw 'GH_TOKEN is empty and gh is not logged in for this user: no collector was run' }
        }
        # Without a Buildkite token observe_collect / observe_ops_collect still exit 0 but overwrite the snapshots with
        # the Buildkite half empty (seen on this host 2026-11-23). So without the token only the GitHub-only collectors
        # run (tags, publish runs, PyPI, Docker Hub, PR overlap); the Buildkite files keep their last values and the
        # page shows their age (STALE after 48 h).
        $bk = [bool]$env:BUILDKITE_API_TOKEN
        # observe_collect keeps the previous Buildkite half (dated bk_at) when there is no token, so the GitHub half
        # (PR state, head sha, required checks) is fresh every day (expert review round 2, W1).
        # 2026-11-27: the collectors run in PARALLEL (they read different sources and write different files; ops.db
        # writers wait via busy_timeout; Buildkite 429 is retried after RateLimit-Reset). Only dependency kept:
        # overlap_collect reads observe_snapshot.json, so it starts when observe_collect has ended (and after git fetch).
        $obs = Start-Step 'observe_collect' $CpuTests 'observe_collect.py' @('--no-build') -Isolated
        $par = @()
        if ($bk) {
            $par += Start-Step 'observe_ops_collect' $CpuTests 'observe_ops_collect.py' @('--no-build') -Isolated
            $par += Start-Step 'mp_pr_collect'       $CpuTests 'mp_pr_collect.py' -Isolated
            # before / after CI impact of #6730 / #6731 / #6854 (Buildkite + gh, read-only; a network error keeps the last result)
            $par += Start-Step 'collect_ci_impact'   $Backend  'collect_ci_impact.py'
            # the ONE baseline (P1_full) that CI Baseline, Optimal CI and PR Inspector read (cpu_tests/baseline.py):
            # ETL lake update + P1 export + transforms, same start as before, window end = tomorrow (UTC)
            $p1w = Join-Path (Split-Path $CpuTests -Parent) 'P1_full\window.json'
            $p1Since = try { ((Get-Content $p1w -Raw | ConvertFrom-Json).since).Substring(0, 10) } catch { '2026-10-17' }
            $p1Until = (Get-Date).ToUniversalTime().AddDays(1).ToString('yyyy-MM-dd')
            $par += Start-Step 'etl_window' (Split-Path (Split-Path $CpuTests -Parent) -Parent) '..\etl\etl.py' @('window', '--since', $p1Since, '--until', $p1Until, '--out', 'outputs\P1_full')
        } else {
            Write-Log 'BUILDKITE_API_TOKEN is empty: GitHub-only refresh (observe_ops_collect, mp_pr_collect skipped; observe_collect keeps the old Buildkite data)'
        }
        $par += Start-Step 'collect_release' $Backend 'collect_release.py'
        # weekly full build: GitHub Actions runs + their report.json artifacts (gh only, no Buildkite token needed)
        $par += Start-Step 'collect_weekly'  $Backend 'collect_weekly.py'
        # round 2: the rebase / overlap data is only as fresh as origin/dev in the local clone: fetch it (refs only;
        # the checked-out files are not touched). A failed fetch is logged and the run goes on with the old refs.
        $clone = Join-Path (Split-Path (Split-Path $App -Parent) -Parent) 'third_party\LMCache'
        if (Test-Path (Join-Path $clone '.git')) {
            & cmd.exe /d /c "git -C `"$clone`" fetch --quiet --tags --force origin >nul 2>&1"   # cmd redirect: PS 5.1 + Stop would turn git's stderr into an error
            Write-Log "git fetch of the local clone: exit $LASTEXITCODE"
        }
        $fail = @(Wait-Steps @($obs))
        if ($fail.Count -eq 0) {
            $par += Start-Step 'overlap_collect' $CpuTests 'overlap_collect.py' @('--no-build') -Isolated
        } else {
            $null = Write-Log 'overlap_collect not started: observe_collect failed'
        }
        $fail += @(Wait-Steps $par)
        $tc = [int]((Get-Date) - $obs.T0).TotalSeconds
        Write-Log "collectors done in ${tc}s (parallel)"
        # Optional sources (review 3.4): their tabs keep the last good data and say so; a failure here does not block
        # the rest of the page. Every other collector is critical: a failure stops the run (nothing goes live).
        $optional = @('collect_weekly', 'collect_ci_impact', 'etl_window')
        $optFail = @($fail | Where-Object { $f = $_; $optional | Where-Object { $f -like "step '$_'*" } })
        $fail = @($fail | Where-Object { $optFail -notcontains $_ })
        foreach ($f in $optFail) { Write-Log "optional source FAILED, last good data kept: $f" }
        if ($fail.Count) { throw ($fail -join '; ') }
    }
    Invoke-Step 'ingest_files'  $Backend  'ingest_files.py'
    Invoke-Step 'build_page'    $CpuTests 'build_page.py'   -Isolated
    Invoke-Step 'build_today'   $CpuTests 'build_today.py'  -Isolated
    # review 10.5: verify the page after its last builder (Today), so every block it checks is the published one
    Invoke-Step 'verify_page'   $CpuTests 'verify_page.py'  -Isolated
    Invoke-Step 'export_static' $Backend  'export_static.py'
    # every tab on one snapshot (same collector run, same baseline, same entities, no future times): FAIL -> nothing goes live
    Invoke-Step 'check_sync' (Join-Path $App 'tests') 'check_sync.py'
    if (-not $SkipUiCheck) {
        Invoke-Step 'check_app' (Join-Path $App 'tests') 'check_app.py' @('--lang', 'en')
    }
    $note = if ($Offline) { 'refresh (offline rebuild)' } elseif (-not $bk) { 'scheduled refresh (GitHub only)' } else { 'scheduled refresh' }
    Invoke-Step 'publish' $Deploy 'publish.py' @('publish', '--note', $note)
    $ok = $true
    # Database copy on Cloudflare (D1): the live release's ops.db, as one atomic snapshot, then a row-by-row check.
    # Before the Pages upload, so the web page never shows a data build the database does not have yet.
    $d1Err = $null
    if ($env:OPS_D1_DB) {
        try { Invoke-Step 'd1_push' $Deploy 'd1_sync.py' @('push'); Invoke-Step 'd1_verify' $Deploy 'd1_sync.py' @('verify') }
        catch { $d1Err = $_.Exception.Message; Write-Log "D1 sync FAILED: $d1Err (local site is live; the web database keeps its last snapshot)" }
    }
    # daily digest (round 2, W3): local file logs/digest-<day>.md; posted only if OPS_DIGEST_URL is set
    try { Invoke-Step 'digest' $Deploy 'digest.py' } catch { Write-Log "digest failed: $($_.Exception.Message)" }
    # Optional: also upload the new build to Cloudflare Pages (behind Access). Off unless OPS_PAGES_AUTO=1.
    # pages.py refuses to upload when the pages.dev name is not behind Access; a failure here leaves the local site live.
    $pagesErr = $null
    if ($d1Err -and $env:OPS_PAGES_AUTO -eq '1') {
        # review 4.3: keep the web page and the web database on the same snapshot; both stay on the last good one
        $pagesErr = 'skipped: the D1 sync failed, so the web page stays on the build the database has'
        Write-Log "web upload SKIPPED: $pagesErr"
    } elseif ($env:OPS_PAGES_AUTO -eq '1') {
        try { Invoke-Step 'pages_deploy' $Deploy 'pages.py' @('deploy') }
        catch { $pagesErr = $_.Exception.Message; Write-Log "web upload FAILED: $pagesErr (local site is live)" }
    }
    if ($d1Err) {
        Send-Status 'warn' "local build is live, but the Cloudflare database (D1) sync failed: $d1Err"
    } elseif ($pagesErr) {
        Send-Status 'warn' "local build is live, but the Cloudflare Pages upload failed: $pagesErr"
    } elseif ($optFail.Count) {
        Send-Status 'warn' "live, but optional source(s) kept their last data: $($optFail -join '; ')"
    } elseif ($env:OPS_D1_DB -and $env:OPS_PAGES_AUTO -ne '1') {
        # review 3.1 / R4: the database moved on but the web page did not
        Write-Log 'refresh OK with WARNING: D1 has the new snapshot but OPS_PAGES_AUTO is off, so the web page was not uploaded'
        Send-Status 'warn' 'live locally and in the web database, but the web page was not uploaded (OPS_PAGES_AUTO off)'
    } elseif ($Offline) {
        # review 3.3: a rebuild is not a fresh collection; say so (the data age is in /api/sync-status and the page)
        Write-Log 'refresh OK: rebuilt from local data (no source was collected)'
        Send-Status 'ok' 'rebuilt from local data (no new collection)'
    } elseif (-not $Offline -and -not $bk) {
        Write-Log 'refresh OK with WARNING: new build is live, but GitHub only - Buildkite data (CI gates, queue, 24 h CI) was NOT refreshed (BUILDKITE_API_TOKEN empty)'
        Send-Status 'warn' 'live, but Buildkite data not refreshed (no BUILDKITE_API_TOKEN)'
    } else {
        Write-Log 'refresh OK: new build is live'
        Send-Status 'ok' 'new build is live'
    }
} catch {
    Write-Log "refresh FAILED: $($_.Exception.Message). The live build was not changed."
    Send-Status 'failed' "$($_.Exception.Message). The live build was not changed."
} finally {
    if ($runId) {
        $st = if (-not $ok) { 'failed' } elseif ($d1Err -or $pagesErr -or $optFail.Count -or (-not $Offline -and -not $bk)) { 'partial' } else { 'ok' }
        $rel = try { (Get-Content (Join-Path $App 'releases\CURRENT') -ErrorAction Stop).Trim() } catch { '' }
        $fa = @('finish', "$runId", '--status', $st); if ($ok -and $rel) { $fa += @('--release', $rel) }
        # review 3.2: the run row carries the data build it published
        $mf = Join-Path $App "releases\$rel\site\data\manifest.json"
        if ($ok -and $rel -and (Test-Path $mf)) { try { $fa += @('--data-build', (Get-Content $mf -Raw | ConvertFrom-Json).build) } catch {} }
        try { & $Py -X utf8 (Join-Path $Backend 'sync_run.py') @fa 2>$null | Out-Null } catch {}
        Write-Log "sync run $runId finished: $st"
    }
    $lock.Close()
    # review R6: keep 30 days of logs (and never fewer than the last 30 runs)
    Get-ChildItem $Logs -Filter 'refresh-*.log' | Sort-Object Name -Descending | Select-Object -Skip 30 |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force
}
if ($ok) { exit 0 } else { exit 1 }
