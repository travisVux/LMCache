# Daily backup of ops.db / state.db, then a restore drill into a temp folder (logs/backup-drill.json).
# Used by the scheduled task "ops-app-backup" (user-level, 06:30, before the 07:00 refresh). Off-host copy: OPS_BACKUP_COPY_TO.
. "$PSScriptRoot\common.ps1"
& $Py -X utf8 (Join-Path $PSScriptRoot 'backup.py')
$b = $LASTEXITCODE
& $Py -X utf8 (Join-Path $PSScriptRoot 'backup.py') --drill | Out-Null
if ($b -ne 0) { exit $b } else { exit $LASTEXITCODE }
