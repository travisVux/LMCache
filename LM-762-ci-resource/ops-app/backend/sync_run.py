"""One row per refresh run (sync) in ops.db: the shared identity every tab, API answer and the Cloudflare D1 copy carry.

  python -X utf8 sync_run.py start [--note TEXT]                 # prints the new run id (refresh.ps1 keeps it in RD_RUN_ID)
  python -X utf8 sync_run.py finish <id> --status ok|failed|partial [--release NAME] [--data-build HASH] [--errors JSON]
  python -X utf8 sync_run.py last                                 # last run as JSON

status: running -> ok (every step passed) | partial (published, some source or the D1 push reported errors) | failed.
Python stdlib only.
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

from config import DB_PATH

DDL = """CREATE TABLE IF NOT EXISTS sync_run(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','ok','partial','failed')),
  release TEXT,          -- releases/<name> that went live with this run
  data_build TEXT,       -- data/<build>/ hash of the page data (split_page.py manifest)
  source_ref TEXT,       -- origin/dev sha of the LMCache clone at the start of the run
  partial_errors TEXT,   -- JSON list of {source, error}
  note TEXT)"""


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(db=None):
    import sqlite3
    con = sqlite3.connect(str(db or DB_PATH), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    con.execute(DDL)
    return con


def origin_dev():
    clone = Path(__file__).resolve().parents[3] / "third_party" / "LMCache"
    try:
        p = subprocess.run(["git", "-C", str(clone), "rev-parse", "origin/dev"], capture_output=True, text=True, timeout=30)
        return p.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def start(note=None, db=None):
    con = connect(db)
    with con:
        cur = con.execute("INSERT INTO sync_run(started_at, source_ref, note) VALUES (?,?,?)", (now(), origin_dev(), note))
    return cur.lastrowid


def finish(run_id, status, release=None, data_build=None, errors=None, db=None):
    con = connect(db)
    with con:
        con.execute("UPDATE sync_run SET finished_at=?, status=?, release=COALESCE(?, release), data_build=COALESCE(?, data_build),"
                    " partial_errors=COALESCE(?, partial_errors) WHERE id=?",
                    (now(), status, release, data_build, json.dumps(errors) if errors is not None else None, run_id))


def last(db=None, ok_only=False):
    con = connect(db)
    r = con.execute("SELECT * FROM sync_run " + ("WHERE status IN ('ok','partial') " if ok_only else "") + "ORDER BY id DESC LIMIT 1").fetchone()
    if not r:
        return None
    d = dict(r)
    d["partial_errors"] = json.loads(d["partial_errors"]) if d.get("partial_errors") else []
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["start", "finish", "last"])
    ap.add_argument("id", nargs="?", type=int)
    ap.add_argument("--status", choices=["ok", "partial", "failed"])
    ap.add_argument("--release")
    ap.add_argument("--data-build")
    ap.add_argument("--errors", help="JSON list")
    ap.add_argument("--note")
    a = ap.parse_args()
    if a.cmd == "start":
        print(start(a.note))
    elif a.cmd == "finish":
        if not a.id or not a.status:
            sys.exit("finish needs <id> and --status")
        finish(a.id, a.status, a.release, a.data_build, json.loads(a.errors) if a.errors else None)
    else:
        print(json.dumps(last(), ensure_ascii=False))


if __name__ == "__main__":
    main()
