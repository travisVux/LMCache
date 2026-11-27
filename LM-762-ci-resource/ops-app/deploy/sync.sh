#!/usr/bin/env sh
# Mode A from a Linux / macOS / Git Bash build machine. Same steps as sync.ps1.
#
#   ./sync.sh /mnt/host-releases            # the host's ops-app/releases, mounted here (SMB/NFS/sshfs) with write access
#   SKIP_BUILD=1 ./sync.sh /mnt/host-releases
#
# Build is local only (NR_NO_GH=1 TRD_NO_GH=1). publish.py does the privacy scan, the copy to .staging-<ts>,
# the rename and the atomic CURRENT switch on the host folder, and keeps the last 5 releases.
set -eu
DEST="${1:?usage: sync.sh <host releases folder>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$(dirname "$HERE")"
CPU="$(dirname "$APP")/plan-2026-11/outputs/cpu_tests"
PY="${OPS_PYTHON:-python3}"
export PYTHONUTF8=1

[ -f "$DEST/CURRENT" ] || { echo "$DEST has no CURRENT: wrong path, or the host has no release yet" >&2; exit 1; }

if [ -z "${SKIP_BUILD:-}" ]; then
  export NR_NO_GH=1 TRD_NO_GH=1
  (cd "$CPU" && "$PY" -I -X utf8 build_page.py)
  (cd "$CPU" && "$PY" -I -X utf8 verify_page.py)
  (cd "$CPU" && "$PY" -I -X utf8 build_today.py)
  (cd "$APP/backend" && "$PY" -X utf8 export_static.py)
fi
(cd "$HERE" && "$PY" -X utf8 publish.py publish --releases "$DEST" --note "sync from build machine (mode A)")
(cd "$HERE" && "$PY" -X utf8 publish.py list --releases "$DEST")
